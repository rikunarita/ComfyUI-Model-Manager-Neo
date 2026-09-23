//! huff0 encoder — a step-for-step port of `HUF_compress` /
//! `HUF_compress_internal` / `HUF_compress4X_usingCTable_internal` /
//! `HUF_compress1X_usingCTable_internal_body` (vendored `huf_compress.c`).
//!
//! Output is BYTE-IDENTICAL to the C encoder for the same input (same
//! histogram decisions, same incompressible/RLE heuristics, same tableLog,
//! same tree, same weight-header choice, same reverse-order bit packing and
//! flush points), which turns the L2 golden diff into an exact byte compare.
//!
//! `zipnn_core.c` only ever calls `HUF_compress(dst, origChunkSize, src,
//! srcSize)` = `HUF_compress2(dst, cap, src, len, 255, HUF_TABLELOG_DEFAULT
//! = 11)` = the 4-stream variant without table repeat — that is the only
//! path ported (Plan §4.5-5).

use super::tree::{HuffCTable, build_c_table};
use super::weights;
use crate::{CodecError, CodecResult, HUF_BLOCKSIZE_MAX};

/// `HUF_compress(dst, maxDstSize, src, srcSize)`.
///
/// `Ok(None)` mirrors the C's return-0 ("incompressible — store the chunk
/// raw"), including the error paths `zipnn_core.c` treats as incompressible
/// (an `HUF_isError` result also lands in the raw branch because the huge
/// error code fails the `compSize < uncomp * 0.95` test).
///
/// # Errors
/// Only `src.len() > HUF_BLOCKSIZE_MAX` (the C's srcSize_wrong — zipnn
/// never sends bigger planes because the Python layer clamps the chunk).
pub fn huf_compress(src: &[u8], dst_capacity: usize) -> CodecResult<Option<Vec<u8>>> {
    let mut scratch = Vec::new();
    let mut out = Vec::new();
    match huf_compress_scratch(src, dst_capacity, &mut scratch, &mut out)? {
        Some(()) => Ok(Some(out)),
        None => Ok(None),
    }
}

/// Scratch-recycling variant used by the chunk-parallel codec layer: the
/// bit-writer buffer (`writer_scratch`) and the output block (`out`) are
/// caller-owned and reused across blocks — eliminating the per-plane-chunk
/// alloc+memset of the writer buffer (the C mallocs a fresh buffer per
/// chunk; this is a strict, output-neutral improvement).
///
/// Returns `Ok(Some(()))` when `out` holds the block, `Ok(None)` where the C
/// returns 0 (incompressible).
pub fn huf_compress_scratch(
    src: &[u8],
    dst_capacity: usize,
    writer_scratch: &mut Vec<u8>,
    out: &mut Vec<u8>,
) -> CodecResult<Option<()>> {
    if src.len() > HUF_BLOCKSIZE_MAX {
        return Err(CodecError::Size(format!(
            "huff0 block {} > HUF_BLOCKSIZE_MAX {HUF_BLOCKSIZE_MAX}",
            src.len()
        )));
    }
    huf_compress_internal(src, dst_capacity, writer_scratch, out)
}

fn huf_compress_internal(
    src: &[u8],
    dst_capacity: usize,
    writer_scratch: &mut Vec<u8>,
    out: &mut Vec<u8>,
) -> CodecResult<Option<()>> {
    let src_size = src.len();
    // C: if (!srcSize) return 0; if (!dstSize) return 0;
    if src_size == 0 || dst_capacity == 0 {
        return Ok(None);
    }
    if dst_capacity <= 8 {
        return Ok(None); // BIT_initCStream would fail → C returns 0 via the writers
    }

    // --- histogram (HIST_count_wksp with maxSV=255 → HIST_countFast:
    // <1500 bytes = simple loop, otherwise the 4-way parallel-counter
    // stripe loop from hist.c — four counter tables kill the store-
    // forwarding stalls a single RMW counter hits on skewed alphabets) ---
    let mut count = [0u32; 256];
    if src_size < 1500 {
        for &b in src {
            count[b as usize] += 1;
        }
    } else {
        let mut c1 = [0u32; 256];
        let mut c2 = [0u32; 256];
        let mut c3 = [0u32; 256];
        let mut c4 = [0u32; 256];
        let mut ip = 4usize;
        let mut cached = u32::from_le_bytes(src[0..4].try_into().expect("4 bytes"));
        while ip + 16 <= src_size {
            for _ in 0..4 {
                let c = cached;
                cached = u32::from_le_bytes(src[ip..ip + 4].try_into().expect("4 bytes"));
                ip += 4;
                c1[(c & 0xFF) as usize] += 1;
                c2[((c >> 8) & 0xFF) as usize] += 1;
                c3[((c >> 16) & 0xFF) as usize] += 1;
                c4[(c >> 24) as usize] += 1;
            }
        }
        ip -= 4; // the last cached word was read but not processed
        while ip < src_size {
            c1[src[ip] as usize] += 1;
            ip += 1;
        }
        for s in 0..256 {
            count[s] = c1[s] + c2[s] + c3[s] + c4[s];
        }
    }
    let mut max_sv: usize = 0;
    let mut largest: usize = 0;
    for (s, &c) in count.iter().enumerate() {
        if c > 0 {
            max_sv = s;
        }
        if c as usize > largest {
            largest = c as usize;
        }
    }
    // C: single symbol → 1-byte RLE block
    if largest == src_size {
        if dst_capacity < 1 {
            return Ok(None);
        }
        out.clear();
        out.push(src[0]);
        return Ok(Some(()));
    }
    // C heuristic: largest <= (srcSize >> 7) + 4 → "probably not compressible"
    if largest <= (src_size >> 7) + 4 {
        return Ok(None);
    }

    // --- tree ---
    let huff_log = weights::optimal_table_log(src_size, max_sv as u32);
    let (tree, max_bits) = match build_c_table(&count, max_sv, huff_log) {
        Ok(v) => v,
        Err(_) => return Ok(None), // C CHECK_F would abort the call → zipnn stores raw
    };
    let huff_log = max_bits;

    // --- weight header (FSE attempt, else direct nibbles) ---
    out.clear();
    out.reserve(dst_capacity.min(src_size + 512));
    let h_size = match weights::write_c_table(out, &tree.nb_bits, max_sv, huff_log) {
        Ok(v) => v,
        // C: writeCTable errors (e.g. maxSV > 128 on the direct path) →
        // CHECK_V_F propagates → zipnn_core stores the chunk raw.
        Err(_) => return Ok(None),
    };
    // C: if (hSize + 12 >= srcSize) return 0
    if h_size + 12 >= src_size {
        return Ok(None);
    }

    // --- 4-stream bitstream ---
    match compress_4x_using_ctable(out, dst_capacity, src, &tree, writer_scratch) {
        Some(()) => {}
        None => return Ok(None), // any writer failure → C returns 0 → raw
    }
    // C compressCTable_internal: if (total >= srcSize - 1) return 0
    if out.len() >= src_size.saturating_sub(1) {
        return Ok(None);
    }
    Ok(Some(()))
}

/// `HUF_compress4X_usingCTable_internal`: jump table (3×LE16 sizes of the
/// first three streams) + four independently encoded segments, each via
/// `HUF_compress1X_usingCTable_internal`. Appends to `out` (which already
/// holds the weight header). Returns None where the C returns 0.
fn compress_4x_using_ctable(
    out: &mut Vec<u8>,
    dst_capacity: usize,
    src: &[u8],
    tree: &HuffCTable,
    writer_scratch: &mut Vec<u8>,
) -> Option<()> {
    let src_size = src.len();
    let header_len = out.len();
    // C: minimum space check `dstSize < 6 + 1 + 1 + 1 + 8` (dstSize = the
    // remaining capacity after the header) and `srcSize < 12`
    if dst_capacity.saturating_sub(header_len) < 6 + 1 + 1 + 1 + 8 {
        return None;
    }
    if src_size < 12 {
        return None;
    }
    let segment_size = src_size.div_ceil(4);

    // Grow the writer backing buffer ONCE for the whole block (the previous
    // per-stream resize shrank it each time and re-zeroed on the next
    // block's first stream — a hidden ~70-100 KiB memset per block). Each
    // stream still gets its own `end` from the remaining capacity, exactly
    // like the C's `oend - op` per call.
    writer_scratch.resize(dst_capacity + 8, 0);
    out.extend_from_slice(&[0u8; 6]); // jump table placeholder
    let mut ip = 0usize;
    for k in 0..3 {
        let seg = &src[ip..ip + segment_size];
        let before = out.len();
        compress_1x(seg, dst_capacity - before, tree, writer_scratch, out)?;
        let stream_len = out.len() - before;
        if stream_len > u16::MAX as usize {
            return None; // C asserts cSize <= 65535 (LE16 jump entries)
        }
        let at = header_len + 2 * k;
        out[at..at + 2].copy_from_slice(&(stream_len as u16).to_le_bytes());
        ip += segment_size;
    }
    // fourth stream: the remainder (no jump entry — length is implied)
    let seg = &src[ip..];
    let before = out.len();
    compress_1x(seg, dst_capacity - before, tree, writer_scratch, out)?;
    Some(())
}

/// `HUF_compress1X_usingCTable_internal_body`: encode one segment in
/// REVERSE symbol order (LIFO bitstream), with the exact flush pattern of
/// the 64-bit C build (FLUSHBITS_1/2 compile to no-ops; the unconditional
/// flush runs after every 4 symbols and after the 1–3 symbol tail).
fn compress_1x(
    src: &[u8],
    dst_size: usize,
    tree: &HuffCTable,
    buf: &mut [u8],
    out: &mut Vec<u8>,
) -> Option<()> {
    if dst_size < 8 {
        return None;
    }
    // Register-local rewrite of BIT_CStream + HUF_compress1X: container,
    // bit position and cursor live in locals (LLVM keeps them in
    // registers); flushes use the C's clamping semantics (BIT_flushBits:
    // overflow pins the cursor to `end` and is reported at close); the
    // symbol walk is bounds-check-free via chunks_exact().rev(). OUTPUT IS
    // BYTE-IDENTICAL to the C writer (same reverse symbol order, same
    // flush cadence — cadence-invariant byte stream, see below — same
    // sentinel); the L2 golden diff enforces it on every case.
    // `buf` is the caller-owned scratch, already sized ≥ dst_size + 8.
    debug_assert!(buf.len() >= dst_size + 8);
    let end = dst_size - 8; // C: endPtr = start + dstCapacity - 8
    let packed = &tree.packed;
    let mut container: u64 = 0;
    let mut bit_pos: u32 = 0;
    let mut pos: usize = 0;
    let mut overflowed = false;

    macro_rules! flush {
        () => {
            let nb = (bit_pos >> 3) as usize;
            // single range-checked 8-byte array store (no memcpy call, no
            // length assert — the window is a [u8; 8] after try_into)
            let w: &mut [u8; 8] = (&mut buf[pos..pos + 8])
                .try_into()
                .expect("writer headroom");
            *w = container.to_le_bytes();
            pos += nb;
            if pos > end {
                pos = end;
                overflowed = true;
            }
            bit_pos &= 7;
            container >>= nb * 8;
        };
    }
    macro_rules! encode {
        ($sym:expr) => {{
            let e = packed[$sym as usize];
            // huffLog ≤ HUF_TABLELOG_DEFAULT(11) on every encode path
            // (optimal_table_log caps at the passed max), so 5 pending
            // symbols + 7 leftover bits ≤ 62 < 64 below.
            debug_assert!(e >> 16 >= 1 && e >> 16 <= 11);
            container |= u64::from(e as u16) << bit_pos; // movzx, no mask uop
            bit_pos += e >> 16;
        }};
    }

    // FLUSH-CADENCE INVARIANCE: the serialized byte stream depends only on
    // the serial bit order, not on how often the container is spilled —
    // BIT_flushBits writes the low floor(bitPos/8) bytes each time, so any
    // cadence ≤ 64-bit capacity yields identical bytes (the C's own
    // flushBitsFast/flushBits split relies on this). The C flushes every 4
    // symbols (4×12+7 = 55 bits); with this encoder's hard 11-bit cap we
    // flush every 5 (5×11+7 = 62 < 64) — 20% fewer flushes, byte-identical
    // output (the L2 golden diff asserts exactly that on every case).
    let n5 = src.len() / 5;
    // tail 0-4 symbols (encoded first = read last), then flush (the C also
    // flushes unconditionally after its 1-3 symbol tail switch)
    for idx in (n5 * 5..src.len()).rev() {
        encode!(src[idx]);
    }
    flush!();
    // main loop: 5 symbols + flush per iteration; the group converts to
    // [u8; 5] once so the symbol fetches are static array reads.
    for g in src[..n5 * 5].chunks_exact(5).rev() {
        let g: &[u8; 5] = g.try_into().expect("group of 5");
        encode!(g[4]);
        encode!(g[3]);
        encode!(g[2]);
        encode!(g[1]);
        encode!(g[0]);
        flush!();
    }
    // BIT_closeCStream: sentinel + final flush + overflow verdict
    container |= 1u64 << bit_pos;
    bit_pos += 1;
    flush!();
    let _ = container; // the final flush's container shift is intentionally dead
    if overflowed || pos >= end {
        return None;
    }
    let size = pos + usize::from(bit_pos > 0);
    out.extend_from_slice(&buf[..size]);
    Some(())
}
