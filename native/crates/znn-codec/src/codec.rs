//! The `zipnn_core` equivalent layer — chunked, plane-parallel compression
//! and decompression with the exact payload layout of the vendored C core
//! (Plan §4.5, Appendix B.2), so that existing `.znn` files and C-produced
//! goldens are byte-compatible in both directions.
//!
//! Payload layout (after the caller-supplied header):
//! ```text
//! [chunkTypes : numBuf × numChunks × u8]       plane-major
//! [cumSizes   : numBuf × numChunks × u64 LE]   inclusive cumulative per plane
//! [data       : plane0 chunks | plane1 chunks | …]
//! ```
//! Chunk i of plane b = `data[planeBase_b + cum[b][i-1] .. planeBase_b +
//! cum[b][i]]` (`cum[b][-1] = 0`); type 0 = raw plane bytes, type 1 = one
//! huff0 block (RFC 8878 §4.2.1).
//!
//! Compression decisions mirror `compression_worker` exactly: per plane
//! chunk, `huf_compress(plane, …)`; the block is kept when
//! `size != 0 && (size as f64) < (planeLen as f64) * threshold` (C compares
//! in double — same IEEE arithmetic here), otherwise the raw plane is
//! stored. The C header quirk is reproduced too: `py_zipnn_core` overwrites
//! header bytes [24:32] with the total result size (`resBufSize`).
//!
//! Decompression mirrors `py_combine_dtype` (uniform `chunk/numBuf` plane
//! lengths for non-final chunks; the final chunk splits `lastTotal` with the
//! first `lastTotal % numBuf` planes getting +1) and ADDS the validation
//! the C omits (Plan §4.4.2): chunkType ∈ {0,1}, cumSizes monotonic and
//! exactly spanning the payload, raw slice lengths matching the expected
//! plane lengths, and an output-size cap so hostile headers cannot bomb the
//! allocator.
//!
//! Parallelism: a DEDICATED rayon pool (never the global pool — Plan §4.2.1),
//! default `min(available_parallelism, 16)` threads like the Python layer's
//! `threads=min(cpu_count(), 16)`. Output is deterministic regardless of
//! thread count (the assembly pass is sequential).

use std::sync::OnceLock;

use rayon::prelude::*;

use crate::dtype::validate_mode;
use crate::header::ZnHeader;
use crate::planes::{join, plane_sizes, split};
use crate::reorder::{ReorderKind, kind_for};
use crate::{CodecError, CodecResult, HUF_BLOCKSIZE_MAX, huf};

/// Parameters mirroring the C ABI (`zipnn_core(header, data, num_buf,
/// bit_reorder, byte_reorder, is_review, chunk, threshold, check_th,
/// threads)`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CoreParams {
    /// Number of byte planes: 1 (fp8), 2 (f16/bf16) or 4 (f32).
    pub num_buf: usize,
    /// `bits_mode`: 1 = sign/exponent reorder active (ignored for 1 plane).
    pub bit_reorder: u8,
    /// `bytes_mode`: 220 (4-plane), 10 (2-plane / 1-plane).
    pub byte_reorder: u8,
    /// Original chunk size in bytes (production: 256 KiB; fp8: ≤ 128 KiB).
    pub chunk: usize,
    /// Compression threshold (production 0.95).
    pub threshold: f64,
    /// Worker threads; 0 = pool default (`min(parallelism, 16)`).
    pub threads: usize,
}

impl Default for CoreParams {
    fn default() -> Self {
        Self {
            num_buf: 4,
            bit_reorder: 1,
            byte_reorder: 220,
            chunk: crate::DEFAULT_CHUNK,
            threshold: crate::DEFAULT_THRESHOLD,
            threads: 0,
        }
    }
}

/// One chunk's per-plane results: (chunkType, bytes).
type ChunkPlanes = Vec<(u8, Vec<u8>)>;
/// Per-chunk compression outcome.
type ChunkResult = CodecResult<ChunkPlanes>;
/// Per-worker decompression scratch: plane decode buffers + the X2 table.
type DecScratch = (Vec<Vec<u8>>, Option<Box<huf::decode::DTableEntries>>);

// `is_review` and `check_th_after_percent` are accepted-and-ignored: the C
// `is_review` path only counts zero bytes into dead locals, and the
// threshold re-check is commented out upstream (`zipnn_core.c` L594-596) —
// neither affects output bytes (verified by reading the C, 2026-09-23).

// ---------------------------------------------------------------------------
// Dedicated rayon pool (Plan §4.2.1: never the global pool)
// ---------------------------------------------------------------------------

static POOL: OnceLock<rayon::ThreadPool> = OnceLock::new();

fn default_threads() -> usize {
    std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(1)
        .min(16)
}

fn global_pool() -> &'static rayon::ThreadPool {
    POOL.get_or_init(|| {
        rayon::ThreadPoolBuilder::new()
            .num_threads(default_threads())
            .thread_name(|i| format!("znn-codec-{i}"))
            .build()
            .expect("znn-codec dedicated rayon pool")
    })
}

/// Run `f` on a pool with the requested thread count: the shared dedicated
/// pool for the default (or 0 = default), a one-off local pool otherwise
/// (the C ABI takes `threads` per call; building a scratch pool keeps the
/// contract without resizing the shared one).
fn with_threads<F, T>(threads: usize, f: F) -> T
where
    F: FnOnce() -> T + Send,
    T: Send,
{
    let want = if threads == 0 {
        default_threads()
    } else {
        threads
    };
    if want == default_threads() || want == 0 {
        global_pool().install(f)
    } else {
        match rayon::ThreadPoolBuilder::new()
            .num_threads(want)
            .thread_name(move |i| format!("znn-codec-t{want}-{i}"))
            .build()
        {
            Ok(pool) => pool.install(f),
            Err(_) => global_pool().install(f), // fall back rather than fail
        }
    }
}

// ---------------------------------------------------------------------------
// Compression (py_zipnn_core equivalent)
// ---------------------------------------------------------------------------

/// Compress `data` into the C-core payload format, prefixed by `header`.
///
/// `header` is copied verbatim EXCEPT bytes [24:32], which the C overwrites
/// with the total result size — mirrored here. The header must be ≥ 32
/// bytes (32 + packed shape for TORCH/NUMPY).
///
/// # Errors
/// Invalid parameters (plane count, byte_reorder mode, chunk 0), or a
/// single chunk plane larger than `HUF_BLOCKSIZE_MAX` with a chunk size
/// that cannot be clamped (the Python layer clamps fp8 chunks upstream).
pub fn zipnn_core(header: &[u8], data: &[u8], params: &CoreParams) -> CodecResult<Vec<u8>> {
    let n = params.num_buf;
    if !matches!(n, 1 | 2 | 4) {
        return Err(CodecError::Unsupported(format!(
            "num_buf {n} outside {{1,2,4}} (8-plane f64 is Phase 4)"
        )));
    }
    validate_mode(params.byte_reorder, n)?;
    if params.chunk == 0 {
        return Err(CodecError::Unsupported("chunk size 0".to_owned()));
    }
    if header.len() < crate::HEADER_LEN {
        return Err(CodecError::Header(
            "header shorter than 32 bytes".to_owned(),
        ));
    }
    // threshold <= 0 is legal (C then never picks huff0 — the L2 harness
    // uses 0 to dump raw plane layouts); NaN would poison comparisons.
    if params.threshold.is_nan() {
        return Err(CodecError::Unsupported("NaN threshold".to_owned()));
    }
    let kind = kind_for(params.bit_reorder, n, false);

    let num_chunks = data.len().div_ceil(params.chunk); // C formula (0 for empty)
    let types_len = n * num_chunks;
    let cums_len = types_len * 8;
    let header_len = header.len();

    // Compress chunks in parallel (deterministic assembly below).
    let chunk_results: Vec<ChunkResult> = with_threads(params.threads, || {
        (0..num_chunks)
            .into_par_iter()
            .map(|c| {
                let start = c * params.chunk;
                let end = (start + params.chunk).min(data.len());
                compress_chunk(&data[start..end], n, kind, params.threshold)
            })
            .collect()
    });
    let mut plane_totals = vec![0usize; n];
    let chunk_results = {
        let mut out = Vec::with_capacity(num_chunks);
        for r in chunk_results {
            let planes = r?;
            for (b, (_, bytes)) in planes.iter().enumerate() {
                plane_totals[b] += bytes.len();
            }
            out.push(planes);
        }
        out
    };

    let res_buf_size = header_len + types_len + cums_len + plane_totals.iter().sum::<usize>();
    // Single allocation for the whole result (the vec![] fill is fully
    // overwritten below — the safe-Rust price for the parallel assembly,
    // which nets out far ahead of the sequential extend it replaced:
    // ~28% of compress e2e was single-threaded cross-core copying).
    let mut out = vec![0u8; res_buf_size];
    // header, with [24:32] = resBufSize (C `py_zipnn_core` memcpy)
    out[..header_len].copy_from_slice(header);
    let patched = (res_buf_size as u64).to_le_bytes();
    out[24..32].copy_from_slice(&patched);
    // plane-major view of the chunk results (layout is plane-major, the
    // results are chunk-major)
    let by_plane: Vec<Vec<&(u8, Vec<u8>)>> = (0..n)
        .map(|b| (0..num_chunks).map(|c| &chunk_results[c][b]).collect())
        .collect();
    // chunkTypes (plane-major)
    for (b, row) in by_plane.iter().enumerate() {
        for (c, (t, _)) in row.iter().enumerate() {
            out[header_len + b * num_chunks + c] = *t;
        }
    }
    // cumSizes (plane-major, inclusive)
    let cums_at = header_len + types_len;
    for (b, row) in by_plane.iter().enumerate() {
        let mut cum = 0u64;
        for (c, (_, bytes)) in row.iter().enumerate() {
            cum += bytes.len() as u64;
            let at = cums_at + (b * num_chunks + c) * 8;
            out[at..at + 8].copy_from_slice(&cum.to_le_bytes());
        }
    }
    // data: plane-major, chunks in order — copied in PARALLEL into disjoint
    // slices (the sequential assembly showed up as ~28% of compress e2e:
    // cross-core cache transfers at ~1.5 GB/s). Output bytes are identical
    // (fixed layout); only the copy work moves to the pool.
    {
        let data_start = header_len + types_len + cums_len;
        let mut sizes = Vec::with_capacity(types_len);
        for row in &by_plane {
            for (_, bytes) in row {
                sizes.push(bytes.len());
            }
        }
        let mut region = &mut out[data_start..];
        let mut slices: Vec<&mut [u8]> = Vec::with_capacity(sizes.len());
        for &sz in &sizes {
            let (head, rest) = region.split_at_mut(sz);
            slices.push(head);
            region = rest;
        }
        debug_assert!(region.is_empty());
        let results_ref = &chunk_results;
        let nch = num_chunks.max(1);
        with_threads(params.threads, || {
            slices.into_par_iter().enumerate().for_each(|(idx, dst)| {
                let b = idx / nch;
                let c = idx % nch;
                dst.copy_from_slice(&results_ref[c][b].1);
            });
        });
    }
    debug_assert_eq!(out.len(), res_buf_size);
    Ok(out)
}

thread_local! {
    /// Per-worker plane scratch: grow-only buffers reused across chunks —
    /// `Vec::resize` zero-fills only when growing, so a steady chunk size
    /// pays the memset exactly once per worker thread instead of per chunk.
    /// Raw (type-0) planes STEAL their scratch buffer (zero-copy) and the
    /// next chunk replenishes it — compressible streams never pay that,
    /// all-raw streams pay alloc+fill exactly like the C core does.
    static PLANE_SCRATCH: std::cell::RefCell<Vec<Vec<u8>>> =
        const { std::cell::RefCell::new(Vec::new()) };
    /// (bit-writer backing buffer, huff0 block out-buffer) — recycled per
    /// worker; kills the per-plane-chunk writer alloc+memset.
    static HUF_SCRATCH: std::cell::RefCell<(Vec<u8>, Vec<u8>)> =
        const { std::cell::RefCell::new((Vec::new(), Vec::new())) };
    /// Decompression scratch: per-plane decode buffers + the reusable 4096-
    /// entry X2 table (16 KiB) — one set per worker thread.
    static DEC_SCRATCH: std::cell::RefCell<DecScratch> = const { std::cell::RefCell::new((Vec::new(), None)) };
}

/// Compress one chunk: split into planes (fused reorder) then huff0-or-raw
/// per plane. Returns per-plane (chunkType, bytes).
fn compress_chunk(
    src: &[u8],
    n: usize,
    kind: ReorderKind,
    threshold: f64,
) -> CodecResult<ChunkPlanes> {
    // Single-plane fast path (fp8): the C's split_bytearray_dtype8 is a pure
    // byte copy — we feed `src` to huff0 directly (output-identical, one
    // full-size copy and its memory traffic saved). The raw fallback still
    // materialises an owned Vec (ownership, same as stealing a scratch).
    if n == 1 && kind == ReorderKind::None {
        let plane_len = src.len();
        if plane_len == 0 {
            return Ok(vec![(0u8, Vec::new())]);
        }
        let block: Option<Vec<u8>> = if plane_len > HUF_BLOCKSIZE_MAX {
            None
        } else {
            HUF_SCRATCH.with(|cell| {
                let (wbuf, bout) = &mut *cell.borrow_mut();
                match huf::compress_block_scratch(src, plane_len + 32, wbuf, bout)? {
                    // take(): the finished block IS the result (no copy);
                    // the next call re-reserves into the empty Vec.
                    Some(()) => Ok(Some(std::mem::take(bout))),
                    None => Ok(None),
                }
            })?
        };
        let keep = match &block {
            Some(bytes) => {
                !bytes.is_empty() && (bytes.len() as f64) < (plane_len as f64) * threshold
            }
            None => false,
        };
        return Ok(vec![if keep {
            (1u8, block.expect("keep implies Some"))
        } else {
            (0u8, src.to_vec())
        }]);
    }

    let sizes = plane_sizes(src.len(), n);
    PLANE_SCRATCH.with(|cell| {
        let mut scratch = cell.borrow_mut();
        if scratch.len() < n {
            scratch.resize_with(n, Vec::new);
        }
        for (b, buf) in scratch.iter_mut().enumerate().take(n) {
            buf.resize(sizes[b], 0);
        }
        {
            let mut planes: Vec<&mut [u8]> = scratch
                .iter_mut()
                .take(n)
                .map(|v| v.as_mut_slice())
                .collect();
            split(src, &mut planes, kind)?;
        }
        let mut out = Vec::with_capacity(n);
        for b in 0..n {
            let plane_len = sizes[b];
            if plane_len == 0 {
                // C: NULL plane buffer → skipped entirely; calloc'd type 0 / size 0
                out.push((0u8, Vec::new()));
                continue;
            }
            // C: HUF_compress(dst, origChunkSize /* cap */, plane, planeLen).
            // Blocks that survive C's internal guards are always < planeLen-1,
            // so a cap of planeLen + 32 is decision-identical. An oversized
            // plane (> HUF_BLOCKSIZE_MAX — only reachable with non-standard
            // chunk params) makes the C return ERROR(srcSize_wrong), whose
            // huge value fails the threshold test → raw; mirror that.
            let block: Option<Vec<u8>> = if plane_len > HUF_BLOCKSIZE_MAX {
                None
            } else {
                HUF_SCRATCH.with(|cell| {
                    let (wbuf, bout) = &mut *cell.borrow_mut();
                    match huf::compress_block_scratch(&scratch[b], plane_len + 32, wbuf, bout)? {
                        Some(()) => Ok(Some(std::mem::take(bout))),
                        None => Ok(None),
                    }
                })?
            };
            let keep = match &block {
                Some(bytes) => {
                    !bytes.is_empty() && (bytes.len() as f64) < (plane_len as f64) * threshold
                }
                None => false,
            };
            if keep {
                out.push((1u8, block.expect("keep implies Some")));
            } else {
                // CLONE (not steal): the scratch buffer stays allocated and
                // sized, so the next chunk's `resize` is a no-op — stealing
                // would force an alloc + full zero-fill refill per chunk
                // (the split below overwrites every byte anyway; the C pays
                // malloc-per-chunk here, we pay one hot memcpy instead).
                out.push((0u8, scratch[b].clone()));
            }
        }
        Ok(out)
    })
}

// ---------------------------------------------------------------------------
// Decompression (py_combine_dtype equivalent)
// ---------------------------------------------------------------------------

/// Decompress a C-core payload (the bytes AFTER the 32-byte header + shape;
/// i.e. what `zipnn.py` passes to `combine_dtype`).
///
/// `max_output` caps the output allocation (hostile-header guard, Plan
/// §4.4.2); `None` uses a built-in sanity bound derived from the payload.
///
/// # Errors
/// Any structural violation: short payload, chunkType ∉ {0,1}, non-monotonic
/// or over-reaching cumSizes, raw slice length ≠ expected plane length,
/// huff0 corruption, or `orig_len` above the cap.
pub fn combine_dtype(
    payload: &[u8],
    orig_len: usize,
    params: &CoreParams,
    max_output: Option<usize>,
) -> CodecResult<Vec<u8>> {
    let n = params.num_buf;
    if !matches!(n, 1 | 2 | 4) {
        return Err(CodecError::Unsupported(format!(
            "num_buf {n} outside {{1,2,4}}"
        )));
    }
    // The C ratio gates: dtype32 → only 220; dtype16 → 10/8/1 (8/1 are the
    // uint16 truncation modes, Phase 4); numBuf==1 → no gate (combine is a
    // memcpy there — mirror that tolerance for compatibility).
    if n != 1 {
        validate_mode(params.byte_reorder, n)?;
    }
    if params.chunk == 0 {
        return Err(CodecError::Unsupported("chunk size 0".to_owned()));
    }
    let kind = kind_for(params.bit_reorder, n, false);

    // Output-size cap FIRST (before any orig_len-derived arithmetic — the
    // L3 fuzzer found that `orig_len + chunk - 1` overflows on hostile
    // u64::MAX-scale header values). Callers SHOULD pass the declared
    // tensor size; the fallback bound keeps hostile inputs from bombing
    // the allocator with multi-GB zero fills.
    let cap = max_output.unwrap_or(usize::max(
        payload.len().saturating_mul(64),
        16 * 1024 * 1024,
    ));
    if orig_len > cap {
        return Err(CodecError::Corrupt(format!(
            "orig_len {orig_len} exceeds the output cap {cap} (hostile or truncated header?)"
        )));
    }
    let num_chunks = orig_len.div_ceil(params.chunk); // cap-checked above
    if num_chunks == 0 {
        return Ok(Vec::new()); // orig_len == 0 (chunk ≥ 1)
    }
    let types_len = n * num_chunks;
    let cums_len = types_len * 8;
    if payload.len() < types_len + cums_len {
        return Err(CodecError::Corrupt(format!(
            "payload {} bytes < metadata {} bytes ({} chunks × {n} planes)",
            payload.len(),
            types_len + cums_len,
            num_chunks
        )));
    }

    let types = &payload[..types_len];
    let cums_raw = &payload[types_len..types_len + cums_len];
    let data = &payload[types_len + cums_len..];

    // parse cumSizes (u64 LE, plane-major) with monotonic + range validation.
    // Plane offsets accumulate in CHECKED u64 (the L3 fuzzer found the naive
    // usize accumulation overflowing on hostile u64::MAX cumulative values —
    // in release the wrap could even slip past the span check below).
    let mut cums = vec![0u64; types_len];
    for (i, slot) in cums.iter_mut().enumerate() {
        *slot = u64::from_le_bytes(cums_raw[i * 8..i * 8 + 8].try_into().expect("8 bytes"));
    }
    let mut plane_base = vec![0u64; n + 1];
    for b in 0..n {
        let mut prev = 0u64;
        for c in 0..num_chunks {
            let v = cums[b * num_chunks + c];
            if v < prev {
                return Err(CodecError::Corrupt(format!(
                    "cumSizes not monotonic (plane {b}, chunk {c}: {v} < {prev})"
                )));
            }
            prev = v;
        }
        plane_base[b + 1] = plane_base[b]
            .checked_add(prev)
            .ok_or_else(|| CodecError::Corrupt(format!("cumSizes overflow at plane {b}")))?;
    }
    if plane_base[n] > data.len() as u64 {
        return Err(CodecError::Corrupt(format!(
            "cumSizes span {} bytes but the payload data region is {}",
            plane_base[n],
            data.len()
        )));
    }
    // valid files span the data region EXACTLY (resBufSize assembly)
    if plane_base[n] != data.len() as u64 {
        return Err(CodecError::Corrupt(format!(
            "payload has {} trailing bytes after the plane data (cumSizes span {})",
            data.len() - plane_base[n] as usize,
            plane_base[n]
        )));
    }
    // plane_base[n] ≤ data.len() ≤ isize::MAX ⇒ every offset below fits usize
    let plane_base: Vec<usize> = plane_base.iter().map(|&v| v as usize).collect();

    // expected per-chunk plane lengths (C `decompLen` formulas)
    let uniform = params.chunk / n; // non-final chunks (C: origChunkSize/numBuf)
    let last_total = orig_len - uniform_total(params.chunk, n, num_chunks - 1);
    // C: lastDecompLen = lastTotal/numBuf; first (lastTotal%numBuf) planes +1
    let last_base = last_total / n;
    let last_rem = last_total % n;

    let mut dst = vec![0u8; orig_len];
    let results: Vec<CodecResult<()>> = with_threads(params.threads, || {
        dst.par_chunks_mut(params.chunk)
            .enumerate()
            .map(|(c, dst_slice)| {
                let cur_len = dst_slice.len();
                let exp: Vec<usize> = if c + 1 == num_chunks {
                    (0..n).map(|b| last_base + usize::from(b < last_rem)).collect()
                } else {
                    vec![uniform; n]
                };
                if exp.iter().sum::<usize>() != cur_len && num_chunks > 0 {
                    // only possible with chunk sizes that do not divide
                    // evenly (C is self-inconsistent there — see module
                    // docs); reject instead of mis-decoding.
                    return Err(CodecError::Corrupt(format!(
                        "chunk {c}: plane lengths {exp:?} do not sum to {cur_len} (chunk size must be a multiple of num_buf for non-final chunks)"
                    )));
                }
                // Gather planes with the per-worker scratch: raw (type-0)
                // planes borrow the payload directly (zero-copy), huff0
                // planes decode into recycled buffers (no per-chunk alloc).
                DEC_SCRATCH.with(|cell| {
                    let mut s = cell.borrow_mut();
                    let (planes_scratch, entries_slot) = &mut *s;
                    let entries = entries_slot.get_or_insert_with(huf::decode::new_dtable_scratch);
                    // single-plane fast path: decode/copy straight into the
                    // output slice (no plane-scratch round trip)
                    if n == 1 {
                        let t = types[c];
                        let prev_cum = if c == 0 { 0 } else { cums[c - 1] };
                        let cum = cums[c];
                        let start = plane_base[0] + prev_cum as usize;
                        let end = plane_base[0] + cum as usize;
                        if end > data.len() || start > end {
                            return Err(CodecError::Corrupt(format!(
                                "chunk slice out of bounds (chunk {c})"
                            )));
                        }
                        let slice = &data[start..end];
                        match t {
                            0 => {
                                if slice.len() != dst_slice.len() {
                                    return Err(CodecError::Corrupt(format!(
                                        "raw plane chunk {c} is {} bytes, expected {}",
                                        slice.len(),
                                        dst_slice.len()
                                    )));
                                }
                                dst_slice.copy_from_slice(slice);
                            }
                            1 => huf::decompress_block_direct(slice, dst_slice, entries)?,
                            other => {
                                return Err(CodecError::Corrupt(format!(
                                    "unknown chunkType {other} (only 0=raw, 1=huff0)"
                                )))
                            }
                        }
                        return Ok(());
                    }
                    if planes_scratch.len() < n {
                        planes_scratch.resize_with(n, Vec::new);
                    }
                    let mut raw_slices: Vec<Option<&[u8]>> = vec![None; n];
                    for b in 0..n {
                        let t = types[b * num_chunks + c];
                        let prev_cum = if c == 0 { 0 } else { cums[b * num_chunks + c - 1] };
                        let cum = cums[b * num_chunks + c];
                        let start = plane_base[b] + prev_cum as usize;
                        let end = plane_base[b] + cum as usize;
                        if end > data.len() || start > end {
                            return Err(CodecError::Corrupt(format!(
                                "chunk slice out of bounds (plane {b}, chunk {c})"
                            )));
                        }
                        let slice = &data[start..end];
                        match t {
                            0 => {
                                if slice.len() != exp[b] {
                                    return Err(CodecError::Corrupt(format!(
                                        "raw plane {b} chunk {c} is {} bytes, expected {}",
                                        slice.len(),
                                        exp[b]
                                    )));
                                }
                                raw_slices[b] = Some(slice);
                            }
                            1 => {
                                huf::decompress_block_into(slice, exp[b], &mut planes_scratch[b], entries)?;
                            }
                            other => {
                                return Err(CodecError::Corrupt(format!(
                                    "unknown chunkType {other} (only 0=raw, 1=huff0)"
                                )))
                            }
                        }
                    }
                    let slots: Vec<&[u8]> =
                        planes_scratch.iter().take(n).map(|v| v.as_slice()).collect();
                    let planes: Vec<&[u8]> =
                        (0..n).map(|b| raw_slices[b].unwrap_or(slots[b])).collect();
                    join(&planes, dst_slice, kind)?;
                    Ok(())
                })
            })
            .collect()
    });
    for r in results {
        r?;
    }
    Ok(dst)
}

/// Σ of the C's uniform non-final chunk plane sizes: `(numChunks-1) *
/// numBuf * (chunk/numBuf)` — computed the way `py_combine_dtype` derives
/// `oneChunkSize` (sum of per-plane `origChunkSize/numBuf`).
fn uniform_total(chunk: usize, n: usize, full_chunks: usize) -> usize {
    full_chunks * n * (chunk / n)
}

/// High-level helper: decompress a FULL container (header + payload) —
/// validates the header, derives the plane scheme from the dtype code and
/// header fields exactly like `zipnn.py decompress()`.
///
/// # Errors
/// Header/shape/payload problems (propagated), unsupported dtypes (Phase 4
/// codes), delta/streaming containers (Phase 3).
pub fn decompress_container(blob: &[u8], max_output: Option<usize>) -> CodecResult<Vec<u8>> {
    let (header, _shape, used) = ZnHeader::parse(blob)?;
    let chunk_hint = header.validate_for_decode()?;
    let scheme = crate::dtype::scheme_for_dtype(header.dtype_code)?;
    // zipnn.py decompress: byte_reorder/bit_reorder straight from the
    // header; the plane count from the dtype code (4 default, 2 for
    // f16/bf16, 1 for fp8). For numBuf==1 the C ignores byte_reorder
    // entirely (combine = memcpy) — mirrored by the n==1 gate skip below.
    let params = CoreParams {
        num_buf: scheme.num_planes,
        bit_reorder: header.bit_reorder,
        byte_reorder: header.byte_reorder,
        chunk: chunk_hint,
        threshold: crate::DEFAULT_THRESHOLD,
        threads: 0,
    };
    combine_dtype(
        &blob[used..],
        header.original_len as usize,
        &params,
        max_output,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hdr32() -> Vec<u8> {
        let h = ZnHeader {
            version: [0, 5, 4],
            byte_reorder: 220,
            bit_reorder: 1,
            method: 1,
            input_format: crate::header::InputFormat::Byte,
            delta_compressed_type: 0,
            lossy: [0, 0, 0],
            streaming: false,
            streaming_chunk_log2: 0,
            compression_chunk_log2: 18,
            dtype_code: 1,
            original_len: 0,
            comp_len_field: 0,
        };
        h.encode().to_vec()
    }

    fn roundtrip(data: &[u8], params: &CoreParams) {
        let mut header = hdr32();
        header.resize(32, 0);
        let comp = zipnn_core(&header, data, params).expect("compress");
        assert_eq!(
            &comp[..32 - 8],
            &header[..32 - 8],
            "header preserved (except comp_len field)"
        );
        let out = combine_dtype(&comp[32..], data.len(), params, None).expect("decompress");
        assert_eq!(&out, data, "roundtrip len {}", data.len());
    }

    #[test]
    fn roundtrip_f32_pattern() {
        // realistic-ish f32 planes: gaussian bf16-style byte patterns
        let mut data = Vec::with_capacity(700_000);
        let mut x = 12345u32;
        for i in 0..175_000 {
            x = x.wrapping_mul(1664525).wrapping_add(1013904223);
            // sign+exponent concentrated, mantissa noisy → compressible planes
            let f = ((x >> 8) as f32 / 8_388_608.0 - 1.0) * 0.001;
            data.extend_from_slice(&f.to_le_bytes());
            if i % 997 == 0 {
                data.extend_from_slice(&0.0f32.to_le_bytes());
            }
        }
        roundtrip(&data, &CoreParams::default());
    }

    #[test]
    fn roundtrip_all_plane_configs() {
        let data: Vec<u8> = (0..300_000usize)
            .map(|i| ((i.wrapping_mul(7919)) % 251) as u8)
            .collect();
        for params in [
            CoreParams {
                num_buf: 4,
                bit_reorder: 1,
                byte_reorder: 220,
                ..CoreParams::default()
            },
            CoreParams {
                num_buf: 2,
                bit_reorder: 1,
                byte_reorder: 10,
                ..CoreParams::default()
            },
            CoreParams {
                num_buf: 2,
                bit_reorder: 0,
                byte_reorder: 10,
                ..CoreParams::default()
            },
            CoreParams {
                num_buf: 1,
                bit_reorder: 1,
                byte_reorder: 10,
                chunk: HUF_BLOCKSIZE_MAX,
                ..CoreParams::default()
            },
            CoreParams {
                num_buf: 1,
                bit_reorder: 0,
                byte_reorder: 10,
                chunk: HUF_BLOCKSIZE_MAX,
                ..CoreParams::default()
            },
        ] {
            roundtrip(&data, &params);
            // odd length (final-chunk remainders 1..3 → the Appendix-C class)
            for cut in [1usize, 2, 3, 4, 5] {
                roundtrip(&data[..data.len() - cut], &params);
            }
        }
    }

    #[test]
    fn roundtrip_appendix_c_lengths_end_to_end() {
        // the exact lengths that SEGFAULT the C core (total % 262144 ∈ 1..3)
        let data: Vec<u8> = (0..524_296).map(|i| (i % 253) as u8).collect();
        for total in [
            262_145usize,
            262_146,
            262_147,
            524_289,
            524_290,
            524_291,
            262_209, // +65 (65 % 4 = 1)
            262_208, // +64
        ] {
            roundtrip(&data[..total], &CoreParams::default());
        }
    }

    #[test]
    fn empty_and_tiny_inputs() {
        let params = CoreParams::default();
        roundtrip(&[], &params);
        roundtrip(&[1], &params);
        roundtrip(&[1, 2], &params);
        roundtrip(&[1, 2, 3], &params); // planes {1,0,0,0} — C would SEGV
        roundtrip(&[1, 2, 3, 4], &params);
        roundtrip(&[9; 262_144], &params); // RLE everywhere
    }

    #[test]
    fn payload_layout_matches_c_structure() {
        // deterministic check of the byte structure (sizes/offsets), the
        // byte-exact content equality is the L2 golden suite's job
        let data = vec![7u8; 300_000]; // 2 chunks (262144 + 37856)
        let params = CoreParams::default();
        let header = hdr32();
        let comp = zipnn_core(&header, &data, &params).expect("compress");
        let num_chunks = 2;
        let types_len = 4 * num_chunks;
        let cums_len = types_len * 8;
        assert_eq!(&comp[..24], &hdr32()[..24]);
        // [24:32] = resBufSize
        let res = u64::from_le_bytes(comp[24..32].try_into().unwrap()) as usize;
        assert_eq!(res, comp.len());
        let types = &comp[32..32 + types_len];
        assert!(types.iter().all(|&t| t <= 1));
        let mut cums = Vec::new();
        for i in 0..types_len {
            cums.push(u64::from_le_bytes(
                comp[32 + types_len + i * 8..32 + types_len + i * 8 + 8]
                    .try_into()
                    .unwrap(),
            ));
        }
        // per plane monotonic
        for b in 0..4 {
            let p = &cums[b * num_chunks..(b + 1) * num_chunks];
            assert!(p.windows(2).all(|w| w[1] >= w[0]));
        }
        // data region size == last cum of each plane summed
        let data_len: u64 = (0..4).map(|b| cums[(b + 1) * num_chunks - 1]).sum();
        assert_eq!(comp.len(), 32 + types_len + cums_len + data_len as usize);
    }

    #[test]
    fn hostile_payloads_error_not_panic() {
        let params = CoreParams::default();
        let hostile: Vec<Vec<u8>> = vec![
            vec![],
            vec![0u8; 10],
            vec![2u8; 100],                 // bad chunkTypes
            vec![0u8; 36 + 8 * 4 * 2 + 10], // monotonic-violating cums below
        ];
        for mut h in hostile {
            for orig in [0usize, 1, 100, 300_000] {
                // corrupt cumSizes when long enough
                if h.len() > 44 {
                    h[40] = 0xFF;
                    h[48] = 0x00;
                    h[49] = 0xFF;
                }
                let _ = combine_dtype(&h, orig, &params, Some(1 << 20));
            }
        }
        // cumSizes overshooting the payload
        let mut p = vec![0u8; 36 + 8 * 8];
        p[36..44].copy_from_slice(&u64::MAX.to_le_bytes()); // plane0 chunk0 cum = MAX
        let _ = combine_dtype(&p, 300_000, &params, Some(1 << 20));
        // orig_len bomb must hit the cap
        let ok = zipnn_core(&hdr32(), &[1u8; 1000], &params).unwrap();
        assert!(combine_dtype(&ok[32..], usize::MAX / 2, &params, Some(1 << 20)).is_err());
    }

    #[test]
    fn threads_param_does_not_change_output() {
        let data: Vec<u8> = (0..600_000).map(|i| ((i * 31) % 256) as u8).collect();
        let base = CoreParams::default();
        let c0 = zipnn_core(&hdr32(), &data, &base).expect("c");
        for threads in [1usize, 2, 3] {
            let p = CoreParams { threads, ..base };
            let c = zipnn_core(&hdr32(), &data, &p).expect("c");
            assert_eq!(c, c0, "threads={threads} must not change bytes");
            let out = combine_dtype(&c[32..], data.len(), &p, None).expect("d");
            assert_eq!(out, data);
        }
    }

    #[test]
    fn unsupported_modes_are_explicit_errors() {
        let data = [0u8; 1024];
        assert!(
            zipnn_core(
                &hdr32(),
                &data,
                &CoreParams {
                    num_buf: 8,
                    ..CoreParams::default()
                }
            )
            .is_err()
        );
        assert!(
            zipnn_core(
                &hdr32(),
                &data,
                &CoreParams {
                    num_buf: 4,
                    byte_reorder: 41,
                    ..CoreParams::default()
                }
            )
            .is_err()
        );
        assert!(
            zipnn_core(
                &hdr32(),
                &data,
                &CoreParams {
                    num_buf: 2,
                    byte_reorder: 8,
                    ..CoreParams::default()
                }
            )
            .is_err()
        );
        assert!(
            zipnn_core(
                &hdr32(),
                &data,
                &CoreParams {
                    chunk: 0,
                    ..CoreParams::default()
                }
            )
            .is_err()
        );
        // oversized chunk is ACCEPTED (planes > 128 KiB just store raw —
        // mirroring the C's error→raw fallback) and must round-trip
        let big_data: Vec<u8> = (0..1_048_576usize)
            .map(|i| ((i / 3000) % 17) as u8)
            .collect();
        let big = CoreParams {
            chunk: 1 << 21,
            ..CoreParams::default()
        };
        let comp = zipnn_core(&hdr32(), &big_data, &big).expect("compress");
        let types = &comp[32..32 + 4];
        assert!(types.iter().all(|&t| t == 0), "oversized planes store raw");
        let out = combine_dtype(&comp[32..], big_data.len(), &big, None).expect("decompress");
        assert_eq!(out, big_data);
    }

    #[test]
    fn threshold_zero_stores_everything_raw() {
        // L2 golden-generator mode: threshold 0 → C never keeps huff0 blocks
        let data: Vec<u8> = (0..300_000).map(|i| ((i / 97) % 13) as u8).collect();
        let params = CoreParams {
            threshold: 0.0,
            ..CoreParams::default()
        };
        let comp = zipnn_core(&hdr32(), &data, &params).expect("compress");
        let types = &comp[32..32 + 4 * 2];
        assert!(types.iter().all(|&t| t == 0), "all raw");
        // data region = pure plane bytes → the golden layout for L2
        let out = combine_dtype(&comp[32..], data.len(), &params, None).expect("decompress");
        assert_eq!(out, data);
    }
}
