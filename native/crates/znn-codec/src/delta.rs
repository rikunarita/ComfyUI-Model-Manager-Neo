//! File-level delta (de)compression — Phase 3 (Plan §4.5-6, §6.2).
//!
//! The native replacement of `py/compress.py`'s `delta_compress_files` /
//! `delta_decompress_file`, which wrap the official ZipNN delta API
//! (`ZipNN(bytearray_dtype="float32", delta_compressed_type="byte")`).
//! A fine-tune shares most bytes with its base; the delta file stores the
//! XOR difference, plane-split + huff0-coded as a FLOAT32 byte container
//! (4 planes, bit_reorder=1, byte_reorder=220, dtype code 1, header byte 9
//! = 1) — exactly the container the vendored `zipnn.py` writes, so Neo and
//! official ZipNN delta files stay interchangeable (Plan §7 R12).
//!
//! # Wire format
//!
//! * **Header-length alignment** (legacy `_delta_aligned_bytes`): ZipNN's
//!   byte delta XORs raw bytes, so both sides must have the SAME length.
//!   Fine-tunes of one architecture always have an identical data section,
//!   but their JSON headers routinely differ — the shorter header is
//!   space-padded (trailing spaces are valid JSON whitespace) and its 8-byte
//!   length prefix adjusted, giving both files the "padded rendering"
//!   `[u64 hlen+pad][header][spaces×pad][data]`. The pads travel in the
//!   sidecar `<delta>.neo-delta.json` (`basePad`/`ftPad`) so decompression
//!   restores the fine-tune BYTE-EXACTLY. Neo adds a third sidecar key,
//!   `ftSha256` — the SHA-256 of the original fine-tune file (Plan §4.4.3:
//!   restore-time verification; sidecars are Neo-private, so this is
//!   compatibility-neutral).
//! * **Compression output is the official STREAMING form** (Plan §4.5-6):
//!   the padded renderings are XORed in 1 MiB streaming chunks and each
//!   chunk is emitted as one complete ZN container (`header[13] = 128+20`,
//!   `[24:32]` = container size — the layout `zipnn.py`'s streaming
//!   decompress walks). Peak RAM is O(streaming chunk) instead of the
//!   legacy O(4–5 × file) of whole-file `f.read()` + numpy XOR copies
//!   (KPI K4).
//! * **Decompression accepts BOTH forms**: the streaming chain Neo writes
//!   AND the single-container files the legacy Python path (and the
//!   official non-streaming byte API) produced — `header[13] == 0`.
//!
//! # Compatibility contract (error wording reaches the UI verbatim)
//!
//! The legacy messages are contract (Plan §4.5-6: the UI displays them
//! as-is): the data-size mismatch RuntimeError of `_delta_aligned_bytes`,
//! and `zipnn.py`'s "Length of delta file has to match the length of the
//! decompressed file." / "The data wasn't compressed using delta
//! compression …" ValueErrors — carried by [`StError::Message`] (displayed
//! without a prefix).
//!
//! # Integrity (Plan §4.4.3)
//!
//! Compress records `ftSha256` (the ORIGINAL fine-tune file digest, hashed
//! on a worker thread over the same mmap pages the XOR loop reads);
//! decompress verifies the restored bytes against it INLINE (the
//! AtomicWriter hasher — zero extra I/O). A mismatch KEEPS the delta file
//! and retreats the restore to `<dst>.corrupt`; sidecars without the key
//! (legacy files) skip verification with a logged note. `paranoid` mode
//! re-decodes the finished artifact against the base and compares BEFORE
//! the rename.
//!
//! Hostile inputs are errors, never panics or allocation bombs: container
//! chains are bounds-walked, every declared `original_len` is checked
//! against the remaining expected length BEFORE it is allocated (the
//! expected total is exactly known from the base rendering), and the C
//! core's Appendix-C SEGFAULT class (`total % 256 KiB ∈ {1,2,3}` — reachable
//! through delta padding with real files, proven in Phase 0 BENCH §4.3)
//! decodes through the bounds-checked Rust codec (pinned by the end-to-end
//! regression tests below, Plan §6.2 Phase 3).

use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;

use sha2::{Digest, Sha256};

use crate::codec::{self, CoreParams};
use crate::header::{InputFormat, METHOD_HUFFMAN, ZnHeader};
use crate::pipeline::{Hooks, JobOpts, Phase, Verified, corrupt_path, io_ctx};
use crate::safetensors_io::{AtomicWriter, PREFIX_LEN, StError, StResult, hex, sha256_chunks};
use crate::znn_tensor::ZNN_VERSION;
use crate::{
    DEFAULT_CHUNK, DEFAULT_CHUNK_LOG2, DEFAULT_THRESHOLD, HEADER_LEN, HUF_BLOCKSIZE_MAX, dtype,
};

/// Streaming chunk of the delta output (Plan §4.5-6: 1 MiB — `zipnn.py`
/// `streaming_chunk=1024*1024`).
pub const STREAMING_CHUNK: usize = 1024 * 1024;

/// Header byte 13 of the streaming delta containers: the streaming flag
/// (MSB) + `log2(STREAMING_CHUNK)` — `zipnn.py` writes
/// `128 + int(math.log(streaming_chunk, 2))`.
pub const DELTA_CHUNK_LOG2: u8 = 20;

/// Header byte 9 value of a byte-level delta (`zipnn.py`:
/// `delta_compressed_type == "byte"` → 1; "file" → 2 — both mean "the
/// payload is an XOR delta", and `zipnn.py decompress` accepts any non-zero
/// value, mirrored below).
const DELTA_TYPE_BYTE: u8 = 1;

/// The delta sidecar suffix (`py/compress.py _delta_meta_path`).
pub const SIDECAR_SUFFIX: &str = ".neo-delta.json";

// Legacy error wording (verbatim UI contract — see the module docs).
const MSG_LEN_MISMATCH: &str =
    "Length of delta file has to match the length of the decompressed file.";
const MSG_NOT_DELTA: &str =
    "The data wasn't compressed using delta compression and you're trying to delta-decompress it.";

/// `_delta_aligned_bytes`'s architecture-mismatch RuntimeError (wording is
/// UI contract).
fn msg_data_sizes(base_data: u64, ft_data: u64) -> String {
    format!(
        "the two models have different tensor data sizes \
         ({base_data} vs {ft_data} bytes): delta compression \
         only works between a base and a fine-tune with the exact same \
         architecture and tensor layout"
    )
}

/// The sidecar path of a delta file (`<delta>.neo-delta.json`).
#[must_use]
pub fn sidecar_path(delta: &Path) -> PathBuf {
    let mut s = delta.as_os_str().to_os_string();
    s.push(SIDECAR_SUFFIX);
    PathBuf::from(s)
}

/// The `.neo-delta.json` record (Plan Appendix B.3: `basePad`/`ftPad` are
/// the legacy keys; `ftSha256` is the Neo Phase-3 integrity addition).
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct DeltaMeta {
    /// Spaces appended to the BASE header rendering.
    pub base_pad: u64,
    /// Spaces appended to the FINE-TUNE header rendering.
    pub ft_pad: u64,
    /// SHA-256 of the original fine-tune file (None = legacy sidecar →
    /// restore-time verification is skipped with a note).
    pub ft_sha256: Option<String>,
}

impl DeltaMeta {
    /// The sidecar JSON body. Key names and order match the legacy
    /// `json.dump({"basePad":…, "ftPad":…})` (readers are key-based, but
    /// keeping the historical order makes regenerated sidecars stable);
    /// `ftSha256` is appended last.
    #[must_use]
    pub fn sidecar_json(&self) -> String {
        match &self.ft_sha256 {
            Some(sha) => format!(
                "{{\"basePad\":{},\"ftPad\":{},\"ftSha256\":\"{}\"}}",
                self.base_pad, self.ft_pad, sha
            ),
            None => format!(
                "{{\"basePad\":{},\"ftPad\":{}}}",
                self.base_pad, self.ft_pad
            ),
        }
    }
}

/// `zipnn_complete` stats of a delta run (legacy key set — delta payloads
/// carry `originalBytes`/`compressedBytes` only, no tensor counts).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DeltaStats {
    /// Compress: the PADDED rendering length (legacy `len(ft_bytes)`).
    /// Decompress: the restored fine-tune file size (legacy `len(restored)`).
    pub original_bytes: u64,
    /// The delta file size, both directions.
    pub compressed_bytes: u64,
}

/// Result of a delta compression (the job-result payload).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeltaCompressOutcome {
    /// The ws-contract stats.
    pub stats: DeltaStats,
    /// The sidecar record written next to the delta file.
    pub meta: DeltaMeta,
    /// Non-fatal notes (dir-fsync warnings …).
    pub warnings: Vec<String>,
}

/// Result of a delta decompression.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeltaDecompressOutcome {
    /// The ws-contract stats.
    pub stats: DeltaStats,
    /// How the restore was verified.
    pub verified: Verified,
    /// Non-fatal notes.
    pub warnings: Vec<String>,
}

// ---------------------------------------------------------------------------
// Raw safetensors access + the padded "rendering" (virtual, zero-copy)
// ---------------------------------------------------------------------------

/// Map a file read-only — the crate's single reviewed `unsafe` boundary
/// (see `safetensors_io::StContainer::open` for the full rationale; delta
/// reads base/fine-tune/delta files exactly the same way).
// SAFETY: same reviewed pattern as StContainer::open — a read-only shared
// mapping of files Neo never mutates while mapped; every consumed byte is
// bounds- and structure-validated, so a foreign writer racing the map
// degrades to a verification error, not UB in Neo's own logic.
#[allow(unsafe_code)]
fn map_file(path: &Path) -> StResult<memmap2::Mmap> {
    let file = std::fs::File::open(path)?;
    let len = file.metadata()?.len();
    if len == 0 {
        // mmap of an empty file fails with EINVAL on Linux — reject first.
        return Err(StError::Format(format!(
            "file is empty: {}",
            path.display()
        )));
    }
    Ok(unsafe { memmap2::Mmap::map(&file) }?)
}

/// Split a raw `.safetensors` image: the declared header length plus the
/// header/data slices (legacy `_safetensors_split`, validated — a prefix
/// reaching past the file is a corrupt-input ERROR, never a mis-slice).
fn split_raw(file: &[u8]) -> StResult<(u64, &[u8], &[u8])> {
    if file.len() < PREFIX_LEN {
        return Err(StError::Format(format!(
            "not a safetensors file: {} bytes (need at least {PREFIX_LEN} for the header prefix)",
            file.len()
        )));
    }
    let header_len = u64::from_le_bytes(file[..PREFIX_LEN].try_into().expect("8 bytes"));
    let hl = usize::try_from(header_len).map_err(|_| {
        StError::Format("safetensors header length exceeds the address space".to_owned())
    })?;
    let avail = file.len() - PREFIX_LEN;
    if hl > avail {
        return Err(StError::Format(format!(
            "truncated safetensors: the header prefix declares {header_len} bytes but only {avail} follow"
        )));
    }
    Ok((
        header_len,
        &file[PREFIX_LEN..PREFIX_LEN + hl],
        &file[PREFIX_LEN + hl..],
    ))
}

/// The padded rendering of one safetensors file — the byte-equal-length
/// view both sides of the delta XOR (legacy `_delta_aligned_bytes`),
/// materialised lazily region by region (NEVER as a whole-file copy — the
/// K4 memory guarantee):
///
/// ```text
/// [u64 LE hlen+pad][header JSON][spaces × pad][data section]
/// ```
struct Rendering<'a> {
    prefix: [u8; PREFIX_LEN],
    header: &'a [u8],
    pad: usize,
    data: &'a [u8],
    total: usize,
}

impl<'a> Rendering<'a> {
    fn new(file: &'a [u8], pad: u64) -> StResult<Self> {
        let (header_len, header, data) = split_raw(file)?;
        let pad_sz = usize::try_from(pad).map_err(|_| StError::Format(msg_pad_absurd(pad)))?;
        let hl = usize::try_from(header_len)
            .map_err(|_| StError::Format("header length overflow".to_owned()))?;
        let total = PREFIX_LEN
            .checked_add(hl)
            .and_then(|v| v.checked_add(pad_sz))
            .and_then(|v| v.checked_add(data.len()))
            .ok_or_else(|| StError::Format(msg_pad_absurd(pad)))?;
        let prefixed = header_len
            .checked_add(pad)
            .ok_or_else(|| StError::Format(msg_pad_absurd(pad)))?;
        Ok(Self {
            prefix: prefixed.to_le_bytes(),
            header,
            pad: pad_sz,
            data,
            total,
        })
    }

    fn len(&self) -> usize {
        self.total
    }

    /// Fill `dst` with `dst.len()` rendering bytes starting at `off`
    /// (callers guarantee `off + dst.len() <= len()`; the chunk loops only
    /// ever ask for in-bounds ranges).
    fn copy_range(&self, off: usize, dst: &mut [u8]) {
        if dst.is_empty() {
            return;
        }
        let e0 = PREFIX_LEN;
        let e1 = e0 + self.header.len();
        let e2 = e1 + self.pad;
        let e3 = self.total;
        let want_end = off + dst.len();
        debug_assert!(off <= e3 && want_end <= e3);
        // prefix region [0, e0)
        if off < e0 {
            let e = e0.min(want_end);
            dst[..e - off].copy_from_slice(&self.prefix[off..e]);
        }
        // header region [e0, e1)
        if want_end > e0 && off < e1 {
            let s = off.max(e0);
            let e = e1.min(want_end);
            dst[s - off..e - off].copy_from_slice(&self.header[s - e0..e - e0]);
        }
        // pad region [e1, e2) — spaces
        if want_end > e1 && off < e2 {
            let s = off.max(e1);
            let e = e2.min(want_end);
            dst[s - off..e - off].fill(b' ');
        }
        // data region [e2, e3)
        if want_end > e2 {
            let s = off.max(e2);
            let e = e3.min(want_end);
            if e > s {
                dst[s - off..e - off].copy_from_slice(&self.data[s - e2..e - e2]);
            }
        }
    }
}

fn msg_pad_absurd(pad: u64) -> String {
    format!(
        "delta sidecar padding {pad} is absurdly large — the sidecar does not belong to this delta/base pair"
    )
}

/// Prefix a non-I/O parse error with which side of the pair failed.
fn annotate(e: StError, what: &str, path: &Path) -> StError {
    match e {
        StError::Io(io) => io_ctx(io, "reading", path),
        StError::Format(msg) => StError::Format(format!("{what}: {msg}")),
        other => other,
    }
}

// ---------------------------------------------------------------------------
// Compression
// ---------------------------------------------------------------------------

/// Delta-compress `ft` against `base` into `dst` + its sidecar (the native
/// path of the legacy `delta_compress_files`; the output is the official
/// streaming container chain — see the module docs).
///
/// Ordering / crash guarantees mirror Phase 2 (Plan §4.4.4): `dst` appears
/// only through the AtomicWriter rename AFTER the artifact is complete and
/// fsynced (and, in paranoid mode, fully re-decoded and sha-verified); the
/// sidecar is committed after the delta file. Removing the now-redundant
/// fine-tune stays the Python layer's job (after this returns Ok),
/// preserving the legacy ordering guarantee.
///
/// # Errors
/// Length-mismatched data sections (legacy wording), parse/I-O failures,
/// cancellation, and paranoid-verification failures. Any error leaves NO
/// partial output behind and BOTH models untouched.
pub fn delta_compress(
    base: &Path,
    ft: &Path,
    dst: &Path,
    opts: &JobOpts,
    hooks: &Hooks,
) -> StResult<DeltaCompressOutcome> {
    if dst.exists() {
        return Err(StError::Format(format!(
            "target already exists: {}",
            dst.display()
        )));
    }
    // the delta file lands in a NEW `<base>_DeltaZNN` folder — the legacy
    // engine created it here (`os.makedirs(dirname(out), exist_ok=True)`)
    // (no let-chains: the MSRV floor is 1.85)
    if let Some(parent) = dst.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent).map_err(|e| io_ctx(e, "creating", parent))?;
        }
    }
    hooks.phase(Phase::Prepare);
    let base_map = map_file(base).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "reading", base),
        other => other,
    })?;
    let ft_map = map_file(ft).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "reading", ft),
        other => other,
    })?;
    let base_file: &[u8] = &base_map;
    let ft_file: &[u8] = &ft_map;
    let (base_hlen, _, base_data) =
        split_raw(base_file).map_err(|e| annotate(e, "base model", base))?;
    let (ft_hlen, _, ft_data) = split_raw(ft_file).map_err(|e| annotate(e, "fine-tune", ft))?;
    if base_data.len() != ft_data.len() {
        // legacy wording (UI contract)
        return Err(StError::Message(msg_data_sizes(
            base_data.len() as u64,
            ft_data.len() as u64,
        )));
    }
    // header-length equalisation (legacy `_delta_aligned_bytes`): the
    // shorter header is space-padded up to the longer one.
    let base_pad = ft_hlen.saturating_sub(base_hlen);
    let ft_pad = base_hlen.saturating_sub(ft_hlen);
    let base_r = Rendering::new(base_file, base_pad)?;
    let ft_r = Rendering::new(ft_file, ft_pad)?;
    debug_assert_eq!(base_r.len(), ft_r.len());
    let total = base_r.len();
    let num_chunks = total.div_ceil(STREAMING_CHUNK).max(1);
    if let Some(p) = hooks.progress {
        p.set_total(num_chunks as u64);
    }

    let params = CoreParams {
        num_buf: 4,
        bit_reorder: 1,
        byte_reorder: 220,
        chunk: DEFAULT_CHUNK,
        threshold: DEFAULT_THRESHOLD,
        threads: opts.threads,
    };
    let mut writer = AtomicWriter::new(dst, false).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "writing", dst),
        other => other,
    })?;

    // The chunk loop and the fine-tune SHA-256 run concurrently (Plan
    // §4.4.3-1: the hash rides the same mmap pages the XOR loop reads — a
    // scoped thread needs no lifetime gymnastics).
    let loop_outcome: StResult<(String, u64)> = std::thread::scope(|s| {
        let sha_handle = s.spawn(|| sha256_chunks(ft_file, hooks.cancel));
        let result: StResult<()> = (|| {
            hooks.phase(Phase::Delta);
            let cap = STREAMING_CHUNK.min(total).max(1);
            let mut base_scratch: Vec<u8> = Vec::with_capacity(cap);
            let mut xor_scratch: Vec<u8> = Vec::with_capacity(cap);
            let mut container: Vec<u8> = Vec::new();
            for off in (0..total).step_by(STREAMING_CHUNK) {
                hooks.check_cancel()?;
                let len = (total - off).min(STREAMING_CHUNK);
                base_scratch.resize(len, 0);
                xor_scratch.resize(len, 0);
                base_r.copy_range(off, &mut base_scratch);
                ft_r.copy_range(off, &mut xor_scratch);
                for (x, b) in xor_scratch.iter_mut().zip(base_scratch.iter()) {
                    *x ^= *b;
                }
                container.clear();
                let header = ZnHeader {
                    version: ZNN_VERSION,
                    byte_reorder: 220,
                    bit_reorder: 1,
                    method: METHOD_HUFFMAN,
                    input_format: InputFormat::Byte,
                    delta_compressed_type: DELTA_TYPE_BYTE,
                    lossy: [0, 0, 0],
                    streaming: true,
                    streaming_chunk_log2: DELTA_CHUNK_LOG2,
                    compression_chunk_log2: DEFAULT_CHUNK_LOG2,
                    dtype_code: dtype::FLOAT32,
                    original_len: len as u64,
                    comp_len_field: 0, // zipnn_core_into writes the container size
                };
                codec::zipnn_core_into(
                    &mut container,
                    &header.encode(),
                    &xor_scratch[..len],
                    &params,
                    hooks.cancel,
                )?;
                writer.write_all(&container)?;
                hooks.bump();
            }
            Ok(())
        })();
        let sha = match sha_handle.join() {
            Ok(r) => r,
            Err(_) => Err(StError::Format(
                "the sha256 worker panicked (this is a bug — please report)".to_owned(),
            )),
        };
        match (result, sha) {
            (Ok(()), Ok(digest)) => Ok((digest, writer.written())),
            (Err(e), _) => Err(e),
            (Ok(_), Err(e)) => Err(e),
        }
    });
    let (ft_sha, compressed_bytes) = match loop_outcome {
        Ok(v) => v,
        Err(e) => {
            writer.abort();
            return Err(e);
        }
    };

    hooks.phase(Phase::Write);
    if let Err(e) = writer.finish() {
        writer.abort();
        return Err(match e {
            StError::Io(io) => io_ctx(io, "writing", dst),
            other => other,
        });
    }

    let mut warnings: Vec<String> = Vec::new();
    let meta = DeltaMeta {
        base_pad,
        ft_pad,
        ft_sha256: Some(ft_sha.clone()),
    };

    // Paranoid mode (Plan §4.4.3-4, same semantics as the tensor pipeline):
    // fully re-decode the finished artifact against the base and compare
    // with the fine-tune digest BEFORE the rename — a failed paranoid run
    // removes the artifact and leaves BOTH models untouched. The internal
    // decode does not drive the job progress (BENCH §7.3-7).
    if opts.paranoid {
        hooks.phase(Phase::Verify);
        let tmp = writer.tmp_path().to_path_buf();
        let verify = (|| -> StResult<()> {
            let delta_map = map_file(&tmp).map_err(|e| match e {
                StError::Io(io) => io_ctx(io, "reading", &tmp),
                other => other,
            })?;
            let mut hasher = Sha256::new();
            let mut emitted = 0u64;
            let inner = Hooks {
                progress: None,
                cancel: hooks.cancel,
            };
            let meta_nosha = DeltaMeta {
                base_pad,
                ft_pad,
                ft_sha256: None,
            };
            delta_restore(
                &delta_map,
                &base_r,
                &meta_nosha,
                &inner,
                opts.threads,
                &mut |b: &[u8]| {
                    hasher.update(b);
                    emitted += b.len() as u64;
                    Ok(())
                },
            )?;
            let got = hex(&hasher.finalize());
            if got != ft_sha || emitted != ft_file.len() as u64 {
                return Err(StError::Verification(format!(
                    "paranoid delta re-decode did not reproduce the fine-tune \
                     (sha {got} vs recorded {ft_sha}, {emitted} of {} bytes) — \
                     the delta artifact was removed; both models are untouched",
                    ft_file.len()
                )));
            }
            Ok(())
        })();
        if let Err(e) = verify {
            writer.abort();
            return Err(e);
        }
    }

    writer.commit()?;
    if let Some(w) = writer.take_dir_sync_warning() {
        warnings.push(w);
    }

    // The sidecar is part of the artifact (without it a padded delta is
    // unrestorable): commit it atomically right after the delta file, and
    // FAIL the job when it cannot be written — Python removes the redundant
    // fine-tune only after the whole job succeeded, so a sidecar failure
    // never loses data (retrying then reports "target already exists" with
    // both models still intact).
    let sidecar = sidecar_path(dst);
    let mut sc = AtomicWriter::new(&sidecar, false).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "writing", &sidecar),
        other => other,
    })?;
    let sc_result = (|| -> StResult<()> {
        sc.write_all(meta.sidecar_json().as_bytes())?;
        sc.finish()?;
        sc.commit()
    })();
    if let Err(e) = sc_result {
        sc.abort();
        return Err(e);
    }
    if let Some(w) = sc.take_dir_sync_warning() {
        warnings.push(w);
    }

    hooks.phase(Phase::Done);
    Ok(DeltaCompressOutcome {
        stats: DeltaStats {
            // legacy contract: the PADDED rendering length (len(ft_bytes))
            original_bytes: total as u64,
            compressed_bytes,
        },
        meta,
        warnings,
    })
}

// ---------------------------------------------------------------------------
// Decompression
// ---------------------------------------------------------------------------

/// Decode ONE ZN container of a delta chain into `scratch` (grow-only) and
/// return its decoded length. `remaining_expected` is the allocation cap:
/// a container declaring more bytes than the base rendering still expects
/// is the legacy length mismatch — refused BEFORE the resize (Plan §4.4.2:
/// hostile headers must never bomb the allocator).
fn decode_delta_container(
    container: &[u8],
    scratch: &mut Vec<u8>,
    remaining_expected: usize,
    threads: usize,
    cancel: Option<&AtomicBool>,
) -> StResult<usize> {
    let (hdr, _shape, used) = ZnHeader::parse_delta(container)?;
    if hdr.compression_chunk_log2 == 0 || u32::from(hdr.compression_chunk_log2) >= usize::BITS {
        return Err(header_err(&format!(
            "compression_chunk log2 {} outside 1..={}",
            hdr.compression_chunk_log2,
            usize::BITS - 1
        )));
    }
    let scheme = dtype::scheme_for_dtype(hdr.dtype_code)?;
    // zipnn.py decompress_bin: the plane count comes from the dtype code,
    // the reorder modes from the header; FP8 clamps the chunk to 128 KiB
    // (the Phase-2 `fp8_container_chunk_clamp` finding applies here too).
    let mut chunk = 1usize << hdr.compression_chunk_log2;
    if scheme.num_planes == 1 {
        chunk = chunk.min(HUF_BLOCKSIZE_MAX);
    }
    let orig_len = usize::try_from(hdr.original_len)
        .map_err(|_| StError::Message(MSG_LEN_MISMATCH.to_owned()))?;
    if orig_len > remaining_expected {
        // legacy per-chunk check (wording is UI contract)
        return Err(StError::Message(MSG_LEN_MISMATCH.to_owned()));
    }
    scratch.clear();
    scratch.resize(orig_len, 0);
    let params = CoreParams {
        num_buf: scheme.num_planes,
        bit_reorder: hdr.bit_reorder,
        byte_reorder: hdr.byte_reorder,
        chunk,
        threshold: DEFAULT_THRESHOLD,
        threads,
    };
    codec::combine_dtype_into(scratch, &container[used..], &params, cancel)?;
    Ok(orig_len)
}

/// A header-level codec error as an [`StError`].
fn header_err(msg: &str) -> StError {
    StError::Codec(crate::CodecError::Header(msg.to_owned()))
}

/// Streaming un-padding state machine: turns padded-rendering bytes into
/// the ORIGINAL fine-tune file bytes (the inverse of `_delta_aligned_bytes`
/// + `_delta_unpad`):
///
/// ```text
/// rendering:  [u64 hlen+ftPad][header][spaces × ftPad][data]
/// output:     [u64 hlen     ][header][               ][data]
/// ```
struct Unpadder {
    ft_pad: u64,
    state: UnpadState,
    prefix_buf: [u8; PREFIX_LEN],
    prefix_got: usize,
    header_remaining: u64,
    pad_remaining: u64,
    emitted: u64,
}

#[derive(PartialEq, Eq)]
enum UnpadState {
    Prefix,
    Header,
    Pad,
    Data,
}

impl Unpadder {
    fn new(ft_pad: u64) -> Self {
        Self {
            ft_pad,
            state: UnpadState::Prefix,
            prefix_buf: [0u8; PREFIX_LEN],
            prefix_got: 0,
            header_remaining: 0,
            pad_remaining: 0,
            emitted: 0,
        }
    }

    fn feed<F>(&mut self, mut chunk: &[u8], sink: &mut F) -> StResult<()>
    where
        F: FnMut(&[u8]) -> StResult<()>,
    {
        loop {
            match self.state {
                UnpadState::Prefix => {
                    if chunk.is_empty() {
                        return Ok(());
                    }
                    let want = PREFIX_LEN - self.prefix_got;
                    let n = want.min(chunk.len());
                    self.prefix_buf[self.prefix_got..self.prefix_got + n]
                        .copy_from_slice(&chunk[..n]);
                    self.prefix_got += n;
                    chunk = &chunk[n..];
                    if self.prefix_got == PREFIX_LEN {
                        let padded_hlen = u64::from_le_bytes(self.prefix_buf);
                        let orig_hlen = padded_hlen.checked_sub(self.ft_pad).ok_or_else(|| {
                            StError::Format(format!(
                                "delta sidecar ftPad {} exceeds the restored header length \
                                 {padded_hlen} — the sidecar does not belong to this delta file",
                                self.ft_pad
                            ))
                        })?;
                        sink(&orig_hlen.to_le_bytes())?;
                        self.emitted += PREFIX_LEN as u64;
                        self.header_remaining = orig_hlen;
                        self.pad_remaining = self.ft_pad;
                        self.state = UnpadState::Header;
                    }
                }
                UnpadState::Header => {
                    if self.header_remaining == 0 {
                        self.state = if self.pad_remaining > 0 {
                            UnpadState::Pad
                        } else {
                            UnpadState::Data
                        };
                        continue;
                    }
                    if chunk.is_empty() {
                        return Ok(());
                    }
                    let n = (self.header_remaining as usize).min(chunk.len());
                    sink(&chunk[..n])?;
                    self.emitted += n as u64;
                    self.header_remaining -= n as u64;
                    chunk = &chunk[n..];
                }
                UnpadState::Pad => {
                    if self.pad_remaining == 0 {
                        self.state = UnpadState::Data;
                        continue;
                    }
                    if chunk.is_empty() {
                        return Ok(());
                    }
                    let n = (self.pad_remaining as usize).min(chunk.len());
                    // The pad region is spaces by construction; anything
                    // else means the sidecar pads do not belong to this
                    // delta — the ftSha256 verification catches that with
                    // the authoritative message, so no per-byte check here.
                    self.pad_remaining -= n as u64;
                    chunk = &chunk[n..];
                }
                UnpadState::Data => {
                    if chunk.is_empty() {
                        return Ok(());
                    }
                    let n = chunk.len();
                    sink(chunk)?;
                    self.emitted += n as u64;
                    chunk = &chunk[n..];
                }
            }
        }
    }

    /// All rendering bytes consumed: zero-length trailing zones normalise
    /// to `Data`, and the prefix must have been seen (the rendered-total
    /// check ran before this).
    fn finish(self) -> StResult<u64> {
        let drained = self.state == UnpadState::Data
            || (self.state == UnpadState::Header && self.header_remaining == 0)
            || (self.state == UnpadState::Pad && self.pad_remaining == 0);
        if !drained || self.prefix_got != PREFIX_LEN {
            return Err(StError::Message(MSG_LEN_MISMATCH.to_owned()));
        }
        Ok(self.emitted)
    }
}

/// The delta restore core shared by [`delta_decompress`] and the paranoid
/// re-decode: walk the container chain of `delta`, XOR each decoded chunk
/// against the base rendering, un-pad, and feed the original fine-tune
/// bytes to `sink`. Returns the number of bytes fed.
///
/// Accepts both the streaming chain (Neo/official `is_streaming` output)
/// and the single-container legacy form. Every length disagreement answers
/// with the legacy `zipnn.py` message (UI contract).
fn delta_restore<F>(
    delta: &[u8],
    base: &Rendering,
    meta: &DeltaMeta,
    hooks: &Hooks,
    threads: usize,
    sink: &mut F,
) -> StResult<u64>
where
    F: FnMut(&[u8]) -> StResult<()>,
{
    if delta.len() < HEADER_LEN {
        return Err(header_err(&format!(
            "delta file is {} bytes — shorter than a ZN header",
            delta.len()
        )));
    }
    let first = ZnHeader::decode_delta(delta)?;
    if first.delta_compressed_type == 0 {
        // legacy zipnn.py decompress() guard (wording is UI contract)
        return Err(StError::Message(MSG_NOT_DELTA.to_owned()));
    }
    let expected_total = base.len();
    let mut unpadder = Unpadder::new(meta.ft_pad);
    let mut scratch: Vec<u8> = Vec::new();
    let mut base_scratch: Vec<u8> = Vec::new();
    let mut rendered = 0usize;

    if first.streaming {
        let mut off = 0usize;
        while off < delta.len() {
            hooks.check_cancel()?;
            let hdr = ZnHeader::decode_delta(&delta[off..])?;
            let Some(clen) = usize::try_from(hdr.comp_len_field)
                .ok()
                .filter(|&c| c >= HEADER_LEN)
            else {
                return Err(StError::Codec(crate::CodecError::Corrupt(format!(
                    "delta container at offset {off} declares an invalid size {} (chain corruption)",
                    hdr.comp_len_field
                ))));
            };
            let Some(end) = off.checked_add(clen) else {
                return Err(StError::Codec(crate::CodecError::Corrupt(
                    "delta container chain size overflows".to_owned(),
                )));
            };
            if end > delta.len() {
                return Err(StError::Codec(crate::CodecError::Corrupt(format!(
                    "delta container at offset {off} declares {clen} bytes but only {} remain (truncated file)",
                    delta.len() - off
                ))));
            }
            let n = decode_xored(
                &delta[off..end],
                base,
                rendered,
                expected_total,
                threads,
                hooks.cancel,
                &mut scratch,
                &mut base_scratch,
            )?;
            unpadder.feed(&scratch[..n], sink)?;
            rendered += n;
            off = end;
            hooks.bump();
        }
    } else {
        hooks.check_cancel()?;
        let n = decode_xored(
            delta,
            base,
            rendered,
            expected_total,
            threads,
            hooks.cancel,
            &mut scratch,
            &mut base_scratch,
        )?;
        unpadder.feed(&scratch[..n], sink)?;
        rendered = n;
        hooks.bump();
    }

    // legacy final check: the decoded total must EQUAL the base rendering
    // length (wording is UI contract)
    if rendered != expected_total {
        return Err(StError::Message(MSG_LEN_MISMATCH.to_owned()));
    }
    unpadder.finish()
}

/// Decode one container and XOR it against the base rendering at `rendered`
/// (the decoded rendering chunk lands in `scratch`).
#[allow(clippy::too_many_arguments)]
fn decode_xored(
    container: &[u8],
    base: &Rendering,
    rendered: usize,
    expected_total: usize,
    threads: usize,
    cancel: Option<&AtomicBool>,
    scratch: &mut Vec<u8>,
    base_scratch: &mut Vec<u8>,
) -> StResult<usize> {
    let remaining = expected_total.saturating_sub(rendered);
    let n = decode_delta_container(container, scratch, remaining, threads, cancel)?;
    if n > 0 {
        base_scratch.resize(n, 0);
        base.copy_range(rendered, base_scratch);
        for (x, b) in scratch[..n].iter_mut().zip(base_scratch.iter()) {
            *x ^= *b;
        }
    }
    Ok(n)
}

/// Restore the exact fine-tuned file from `delta` + its `base` model into
/// `dst` (the native path of the legacy `delta_decompress_file`).
///
/// `meta` is the parsed `.neo-delta.json` sidecar (`basePad`/`ftPad`/
/// `ftSha256`); a missing sidecar degrades exactly like the legacy path
/// (pads 0, no verification) — the length checks then fail with the legacy
/// wording unless the pads genuinely were zero.
///
/// Verification (Plan §4.4.3): with `ftSha256` present and `opts.verify`
/// (default ON) the restore is hashed inline; a mismatch KEEPS the delta
/// file and retreats the restore to `<dst>.corrupt`.
///
/// # Errors
/// Structure/hostile-input errors, the legacy length-mismatch messages,
/// I/O failures, cancellation, and verification failures. Errors leave the
/// base and delta files untouched and no partial output behind.
pub fn delta_decompress(
    base: &Path,
    delta: &Path,
    dst: &Path,
    meta: &DeltaMeta,
    opts: &JobOpts,
    hooks: &Hooks,
) -> StResult<DeltaDecompressOutcome> {
    if dst.exists() {
        return Err(StError::Format(format!(
            "target already exists: {}",
            dst.display()
        )));
    }
    hooks.phase(Phase::Prepare);
    let base_map = map_file(base).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "reading", base),
        other => other,
    })?;
    let delta_map = map_file(delta).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "reading", delta),
        other => other,
    })?;
    let base_file: &[u8] = &base_map;
    let base_r =
        Rendering::new(base_file, meta.base_pad).map_err(|e| annotate(e, "base model", base))?;

    // Progress total: the streaming chunk the file declares when it is a
    // chain (sanity-bounded: a hostile log2 must not explode the total),
    // 1 for the single-container legacy form.
    let total = match ZnHeader::decode_delta(&delta_map) {
        Ok(h) if h.streaming && (1..=40).contains(&h.streaming_chunk_log2) => {
            let chunk = 1usize << h.streaming_chunk_log2;
            base_r.len().div_ceil(chunk).max(1) as u64
        }
        _ => 1,
    };
    if let Some(p) = hooks.progress {
        p.set_total(total);
    }

    let want_sha = opts.verify && meta.ft_sha256.is_some();
    let mut writer = AtomicWriter::new(dst, want_sha).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "writing", dst),
        other => other,
    })?;
    hooks.phase(Phase::Delta);
    let step = delta_restore(
        &delta_map,
        &base_r,
        meta,
        hooks,
        opts.threads,
        &mut |b: &[u8]| writer.write_all(b),
    );
    let emitted = match step {
        Ok(v) => v,
        Err(e) => {
            writer.abort();
            return Err(e);
        }
    };
    hooks.phase(Phase::Write);
    let digest = match writer.finish() {
        Ok(d) => d,
        Err(e) => {
            writer.abort();
            return Err(match e {
                StError::Io(io) => io_ctx(io, "writing", dst),
                other => other,
            });
        }
    };

    hooks.phase(Phase::Verify);
    let mut warnings: Vec<String> = Vec::new();
    let verified = match (meta.ft_sha256.as_deref(), digest) {
        (Some(expected), Some(actual)) if expected.eq_ignore_ascii_case(&actual) => {
            Verified::Sha256
        }
        (Some(expected), Some(actual)) => {
            let corrupt = corrupt_path(dst);
            writer.reject_to(&corrupt)?;
            return Err(StError::Verification(format!(
                "the restored fine-tune does not match ftSha256 (recorded {expected}, computed {actual}) — \
                 the delta file was KEPT and the failed restore was moved to {} for diagnosis; \
                 the base model may have changed since the delta was made",
                corrupt.display()
            )));
        }
        (Some(_), None) => {
            // unreachable: the hasher is enabled whenever a sha is recorded
            writer.abort();
            return Err(StError::Format(
                "internal: hasher produced no digest despite a recorded ftSha256".to_owned(),
            ));
        }
        (None, _) => {
            if opts.verify {
                warnings.push(
                    "no ftSha256 in the delta sidecar (created before Neo Phase 3, or by the official tooling): \
                     byte-exact verification skipped (Plan §4.4.3-4)"
                        .to_owned(),
                );
            } else {
                warnings.push(
                    "ftSha256 is recorded but verification was disabled via opts — the restore was NOT checked"
                        .to_owned(),
                );
            }
            Verified::Skipped
        }
    };
    writer.commit()?;
    if let Some(w) = writer.take_dir_sync_warning() {
        warnings.push(w);
    }
    hooks.phase(Phase::Done);
    Ok(DeltaDecompressOutcome {
        stats: DeltaStats {
            original_bytes: emitted,
            compressed_bytes: delta_map.len() as u64,
        },
        verified,
        warnings,
    })
}

/// Fuzz-only entry point (the L3 `delta_decompress` target): runs the whole
/// restore core on arbitrary bytes — a hostile delta chain, hostile sidecar
/// pads and a hostile base image — with a bounded counting sink. Must never
/// panic and never allocate beyond the base-rendering bound (`delta_restore`
/// caps every container against the remaining expected length) or
/// `max_output`.
///
/// # Errors
/// Every invalid input, as a display string (the harness only needs the
/// Ok/Err split; the string keeps failures debuggable).
#[doc(hidden)]
pub fn delta_restore_fuzz(
    delta: &[u8],
    base_file: &[u8],
    base_pad: u64,
    ft_pad: u64,
    max_output: usize,
) -> Result<u64, String> {
    let base = Rendering::new(base_file, base_pad).map_err(|e| e.to_string())?;
    let meta = DeltaMeta {
        base_pad,
        ft_pad,
        ft_sha256: None,
    };
    let hooks = Hooks::default();
    let mut emitted = 0usize;
    delta_restore(delta, &base, &meta, &hooks, 1, &mut |b: &[u8]| {
        emitted += b.len();
        if emitted > max_output {
            return Err(StError::Format("fuzz output cap exceeded".to_owned()));
        }
        Ok(())
    })
    .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests;
