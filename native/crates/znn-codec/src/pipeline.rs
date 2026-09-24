//! The safetensors compression / decompression pipelines (Plan §4.3, §4.4.3,
//! Phase 2) — the Rust replacement of `py/compress.py`'s
//! `compress_safetensors` / `decompress_safetensors`, with the semantics of
//! the official `zipnn_compress_safetensors.py` scripts preserved exactly
//! (per-tensor ZN blobs, `znn_compressed_vectors` infos, the "not worth it"
//! pass-through rule) and the Neo integrity pipeline added:
//!
//! * **compress** streams: mmap source → per tensor compress → append the
//!   piece straight into `<dst>.tmp` at a pre-computed worst-case header
//!   offset → seek-back header patch → fsync → (paranoid: decompress-verify
//!   the artifact) → rename. Peak RAM is O(one tensor) — no RAM dict of the
//!   whole model, no `tensor.clone()`, no spill copy (KPI K1). The source
//!   SHA-256 runs on a worker thread over the same mmap pages (Plan §4.4.3
//!   step 1) and is recorded as `znn_neo_src_sha256`.
//! * **decompress** writes the canonical restored header FIRST (every
//!   restored size is known from the blob headers before any payload is
//!   decoded), then streams tensor-by-tensor with an INLINE SHA-256 — the
//!   end-to-end verification costs zero extra I/O (Plan §4.4.3: default ON).
//!   Mismatch on a byte-exact-capable file → the compressed source is KEPT
//!   and the restore is retreated to `<dst>.corrupt`; sources whose header
//!   was not canonical (`znn_neo_exact="0"`) fall back to the structural
//!   guarantee of Plan §4.7.4 (tensor data + metadata equal) instead of
//!   failing on formatting.
//!
//! The worst-case-header single-pass design is a documented refinement of
//! Plan §4.3's "RAM/spoil" sketch: trailing spaces inside the declared
//! header region are valid JSON whitespace (the same trick the legacy delta
//! padding uses), so the payload can stream at a fixed offset and the exact
//! header is patched in afterwards — one write pass instead of three. The
//! bound is tight (per-entry maxima computed from the source header, never a
//! fixed slack) and a defensive rewrite fallback exists should it ever be
//! exceeded (`hmax_slack < 0` exercises it in tests).
//!
//! All container writes go through [`AtomicWriter`] (sibling `.tmp` → fsync
//! → verify → rename → dir fsync); cancellation is cooperative at tensor and
//! codec-chunk granularity (Plan §4.2.2 invariant 4).

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU8, AtomicU64, Ordering};

use jiter::Jiter;

use crate::safetensors_io::{
    AtomicWriter, OutEntry, PREFIX_LEN, StContainer, StError, StResult, TensorEntry,
    build_header_region, fsync_dir, is_enospc, py_dumps_compressed_vectors, sha256_chunks,
    trim_json_tail,
};
use crate::znn_tensor::{
    TensorScheme, compress_tensor_into, decompress_tensor_into, inspect_tensor,
    scheme_for_st_dtype, shape_string,
};

// ---------------------------------------------------------------------------
// Metadata keys (shared with py/compress.py — the wire contract)
// ---------------------------------------------------------------------------

/// Official ZipNN infos key (`zipnn.util_safetensors.METADATA_KEY`).
pub const METADATA_KEY: &str = "znn_compressed_vectors";
/// Neo: pre-compression on-disk size of the source file (legacy-compatible).
pub const ORIGINAL_SIZE_KEY: &str = "znn_neo_original_bytes";
/// Neo: SHA-256 of the whole source file (Plan §4.4.3, new in Phase 2).
pub const SRC_SHA_KEY: &str = "znn_neo_src_sha256";
/// Neo: "1" when the source header is canonical — decompression can then
/// restore byte-exactly and ENFORCES the sha; "0" downgrades to the
/// structural guarantee (Plan §4.7.4).
pub const EXACT_KEY: &str = "znn_neo_exact";
/// Neo: Phase-4 marker (Neo-extension dtypes present). Phase 2 never writes
/// it, but restore strips it so future files round-trip cleanly.
pub const EXTENDED_KEY: &str = "znn_neo_extended";
/// Neo: `"1"` when the SOURCE file had no `__metadata__` key at all — the
/// compressed file must carry one (the infos live there), and without this
/// record the restore could not tell "no metadata" from "empty metadata"
/// (the reference writer omits `__metadata__` for None but writes `{}` for
/// an empty map — the distinction is bytes).
pub const SRC_META_ABSENT_KEY: &str = "znn_neo_src_meta_absent";

/// Every Neo/ZipNN bookkeeping key — stripped from source metadata before
/// compressing (stale records must never leak into the new file) and from
/// the restored metadata on decompression (legacy parity: the restored file
/// carries exactly the metadata the original had).
pub const BOOKKEEPING_KEYS: [&str; 6] = [
    METADATA_KEY,
    ORIGINAL_SIZE_KEY,
    SRC_SHA_KEY,
    EXACT_KEY,
    EXTENDED_KEY,
    SRC_META_ABSENT_KEY,
];

/// Diagnostic suffix of a failed-verification restore (Plan §4.4.3).
pub const CORRUPT_SUFFIX: &str = ".corrupt";

// ---------------------------------------------------------------------------
// Progress / cancellation hooks
// ---------------------------------------------------------------------------

/// Job phase (wire values match the legacy ws `phase` strings; the Python
/// layer maps the extra ones onto them so the UI contract is unchanged).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum Phase {
    /// Parsing / planning.
    Prepare = 0,
    /// The per-tensor loop (compress+write / decode+write).
    Tensors = 1,
    /// Container assembly (header patch, fsync).
    Write = 2,
    /// Integrity verification (paranoid re-decode / sha compare).
    Verify = 3,
    /// Terminal: succeeded.
    Done = 4,
    /// Terminal: failed (see the job's error).
    Failed = 5,
}

impl Phase {
    /// The wire string of a phase (`"prepare"` … `"failed"`).
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Prepare => "prepare",
            Self::Tensors => "tensors",
            Self::Write => "write",
            Self::Verify => "verify",
            Self::Done => "done",
            Self::Failed => "failed",
        }
    }

    /// Inverse of [`as_str`]; unknown values map to [`Phase::Prepare`].
    #[must_use]
    pub fn from_u8(v: u8) -> Self {
        match v {
            1 => Self::Tensors,
            2 => Self::Write,
            3 => Self::Verify,
            4 => Self::Done,
            5 => Self::Failed,
            _ => Self::Prepare,
        }
    }
}

/// Atomic job progress (Plan §4.3: the Python side polls at 10 Hz instead
/// of the legacy GIL-reacquiring `run_coroutine_threadsafe` callbacks).
#[derive(Debug)]
pub struct Progress {
    done: AtomicU64,
    total: AtomicU64,
    phase: AtomicU8,
}

impl Progress {
    /// A fresh progress counter (phase `Prepare`, `total` items).
    #[must_use]
    pub fn new(total: u64) -> Self {
        Self {
            done: AtomicU64::new(0),
            total: AtomicU64::new(total),
            phase: AtomicU8::new(Phase::Prepare as u8),
        }
    }

    /// Replace the item total (known only after parsing).
    pub fn set_total(&self, total: u64) {
        self.total.store(total, Ordering::Relaxed);
    }

    /// One item finished.
    pub fn bump(&self) {
        self.done.fetch_add(1, Ordering::Relaxed);
    }

    /// Set the phase.
    pub fn set_phase(&self, phase: Phase) {
        self.phase.store(phase as u8, Ordering::Relaxed);
    }

    /// (done, total, phase) snapshot for the polling API.
    #[must_use]
    pub fn snapshot(&self) -> (u64, u64, Phase) {
        (
            self.done.load(Ordering::Relaxed),
            self.total.load(Ordering::Relaxed),
            Phase::from_u8(self.phase.load(Ordering::Relaxed)),
        )
    }
}

/// Optional progress sink + cancellation flag threaded through a job.
#[derive(Debug, Default)]
pub struct Hooks<'a> {
    /// Progress counter (the mm-core job registry owns one per job).
    pub progress: Option<&'a Progress>,
    /// Cooperative cancellation (checked at tensor + codec-chunk bounds).
    pub cancel: Option<&'a AtomicBool>,
}

impl Hooks<'_> {
    fn cancelled(&self) -> bool {
        self.cancel.is_some_and(|c| c.load(Ordering::Relaxed))
    }
    fn check_cancel(&self) -> StResult<()> {
        if self.cancelled() {
            Err(StError::Cancelled)
        } else {
            Ok(())
        }
    }
    fn phase(&self, p: Phase) {
        if let Some(pr) = self.progress {
            pr.set_phase(p);
        }
    }
    fn bump(&self) {
        if let Some(pr) = self.progress {
            pr.bump();
        }
    }
}

/// Job-level options (the `opts` dict of the Python API, Plan §4.2.2).
#[derive(Debug, Clone)]
pub struct JobOpts {
    /// Codec worker threads (0 = pool default `min(parallelism, 16)`).
    pub threads: usize,
    /// Compress only: re-decode the finished artifact and verify it against
    /// the source sha BEFORE it is renamed into place (Plan §4.4.3-4,
    /// default off).
    pub paranoid: bool,
    /// Decompress only: compare the restore against `znn_neo_src_sha256`
    /// (Plan §4.4.3-2 — 既定 ON; the switch exists for the symmetry the plan
    /// implies, e.g. bulk migrations that re-verify out of band).
    pub verify: bool,
    /// Decompress only: per-tensor allocation cap — hostile `.znn` files
    /// may declare arbitrary `original_len` values and must ERROR, never
    /// OOM-kill the host (Plan §4.4.2). Default 64 GiB: far above any real
    /// single tensor, far below a u64 bomb.
    pub max_restore_bytes: usize,
    /// Test hook (hidden): shift the worst-case header bound by this many
    /// bytes — a negative value forces the defensive rewrite fallback.
    #[doc(hidden)]
    pub hmax_slack: i64,
}

impl Default for JobOpts {
    fn default() -> Self {
        Self {
            threads: 0,
            paranoid: false,
            verify: true,
            max_restore_bytes: 64 * 1024 * 1024 * 1024,
            hmax_slack: 0,
        }
    }
}

// ---------------------------------------------------------------------------
// Outcomes (the JSON the Python layer forwards; stats keys are the legacy
// ws contract — byte-identical shapes, golden-tested in tests/)
// ---------------------------------------------------------------------------

/// `zipnn_complete` stats of a compress run (legacy key set).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompressStats {
    /// Sum of the tensor payload bytes of the source (= its data region).
    pub original_bytes: u64,
    /// Sum of the bytes stored per tensor (blob or pass-through).
    pub compressed_bytes: u64,
    /// Tensor count.
    pub tensors: usize,
    /// Tensors actually stored compressed (infos count).
    pub compressed_tensors: usize,
}

/// Full compress result (stats + the integrity record).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompressOutcome {
    /// The ws-contract stats.
    pub stats: CompressStats,
    /// SHA-256 of the source file (recorded in the output metadata).
    pub src_sha256: String,
    /// Whether a Neo decompression of this file restores byte-exactly
    /// (source header was canonical) — the `znn_neo_exact` value.
    pub exact: bool,
    /// Non-fatal notes (e.g. pass-through of out-of-band float tensors).
    pub warnings: Vec<String>,
}

/// How a decompression was verified.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verified {
    /// Restored bytes SHA-256 == `znn_neo_src_sha256` (byte-exact).
    Sha256,
    /// Source was non-canonical (`znn_neo_exact="0"`): sha differs by
    /// formatting; the structural guarantee (Plan §4.7.4) was checked
    /// instead — tensor data + metadata equal, container valid.
    Structural,
    /// No `znn_neo_src_sha256` (official-CLI / legacy files): verification
    /// skipped and logged (Plan §4.4.3-4).
    Skipped,
}

impl Verified {
    /// Wire value recorded in the job result JSON.
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Sha256 => "sha256",
            Self::Structural => "structural",
            Self::Skipped => "skipped",
        }
    }
}

/// `zipnn_complete` stats of a decompress run (legacy key set).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecompressStats {
    /// Tensor count of the compressed file.
    pub tensors: usize,
    /// Tensors decoded from ZN blobs.
    pub decompressed_tensors: usize,
}

/// Full decompress result.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecompressOutcome {
    /// The ws-contract stats.
    pub stats: DecompressStats,
    /// How (or whether) the restore was verified.
    pub verified: Verified,
    /// Non-fatal notes (skipped verification, structural fallback, …).
    pub warnings: Vec<String>,
}

fn io_ctx(e: std::io::Error, what: &str, path: &Path) -> StError {
    if is_enospc(&e) {
        StError::Io(std::io::Error::new(
            e.kind(),
            format!(
                "disk full (ENOSPC) while {what} {} — the partial output was removed, existing files are untouched; free space and retry",
                path.display()
            ),
        ))
    } else {
        StError::Io(e)
    }
}

// ---------------------------------------------------------------------------
// Compress
// ---------------------------------------------------------------------------

/// What ended up stored for one tensor (the header is built after the loop).
#[derive(Debug, Clone, Copy)]
enum Piece {
    /// Stored compressed: a U8 vector of `len` bytes (the ZN blob).
    Blob { len: u64 },
    /// Stored verbatim (pass-through): original dtype/shape/bytes.
    Pass,
}

/// Whether a tensor's dtype is in the Phase-2 compression band.
enum Band {
    /// Compressible now (f32/f16/bf16/fp8×2 — `znn_tensor`'s band table).
    In(TensorScheme),
    /// A float dtype the band does not cover yet (F64/C64/MX/FNUZ/…) — the
    /// legacy path RAISES on these (`ValueError: Support only torch.dtype
    /// float32/bfloat16/float16`); Neo passes them through (strictly more
    /// capable, same format; Phase 4 compresses them).
    OutOfBandFloat,
    /// Non-float (integers/BOOL) — pass-through, like the legacy path.
    NotFloat,
}

/// Float-family dtypes outside the Phase-2 compression band (warning fuel).
const OUT_OF_BAND_FLOATS: [&str; 8] = [
    "F64",
    "C64",
    "F8_E8M0",
    "F8_E4M3FNUZ",
    "F8_E5M2FNUZ",
    "F4",
    "F6_E2M3",
    "F6_E3M2",
];

fn compressible_scheme(t: &TensorEntry) -> Band {
    if let Some(scheme) = scheme_for_st_dtype(&t.dtype) {
        return Band::In(scheme);
    }
    if OUT_OF_BAND_FLOATS.contains(&t.dtype.as_str()) {
        return Band::OutOfBandFloat;
    }
    Band::NotFloat
}

/// The metadata map of a compressed file: surviving source entries (original
/// order) + the Neo records (`znn_neo_*` then the infos key — the legacy
/// pipeline's insertion order).
fn build_compress_meta(
    kept: &[(String, String)],
    file_len: u64,
    sha: &str,
    exact: bool,
    meta_absent: bool,
    infos_json: &str,
) -> Vec<(String, String)> {
    let mut meta = kept.to_vec();
    meta.push((ORIGINAL_SIZE_KEY.to_owned(), file_len.to_string()));
    meta.push((SRC_SHA_KEY.to_owned(), sha.to_owned()));
    meta.push((
        EXACT_KEY.to_owned(),
        if exact { "1" } else { "0" }.to_owned(),
    ));
    if meta_absent {
        meta.push((SRC_META_ABSENT_KEY.to_owned(), "1".to_owned()));
    }
    meta.push((METADATA_KEY.to_owned(), infos_json.to_owned()));
    meta
}

/// Compress `src` (.safetensors) into `dst` (.znn.safetensors) — the native
/// path of the legacy `compress_safetensors` (same format, same metadata
/// contract, plus `znn_neo_src_sha256` / `znn_neo_exact`).
///
/// The source is NEVER modified; `dst` appears atomically (rename) only
/// after the artifact is complete and fsynced — and, in paranoid mode,
/// fully re-decoded and sha-verified. The original-file removal stays the
/// Python layer's job (after this returns Ok), preserving the legacy
/// ordering guarantee (Plan §4.4.3-5).
///
/// # Errors
/// Parse/codec/I-O failures, cancellation, and verification failures in
/// paranoid mode. Any error leaves NO partial output behind.
pub fn compress_file(
    src: &Path,
    dst: &Path,
    opts: &JobOpts,
    hooks: &Hooks,
) -> StResult<CompressOutcome> {
    if dst.exists() {
        return Err(StError::Format(format!(
            "target already exists: {}",
            dst.display()
        )));
    }
    hooks.phase(Phase::Prepare);
    let (st, mmap) = StContainer::open(src).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "reading", src),
        other => other,
    })?;
    let file_len = mmap.len() as u64;
    let total = u64::try_from(st.tensors.len()).unwrap_or(u64::MAX);
    if let Some(p) = hooks.progress {
        p.set_total(total.max(1));
    }

    // Surviving source metadata (original order, stale ZipNN/Neo records
    // stripped so re-compressing a restored file never doubles them up).
    let kept_meta: Vec<(String, String)> = st
        .metadata
        .iter()
        .flatten()
        .filter(|(k, _)| !BOOKKEEPING_KEYS.contains(&k.as_str()))
        .cloned()
        .collect();
    let exact = st.canonical;
    let meta_absent = st.metadata.is_none();

    // Worst-case infos (every compressible tensor lands in the map; the
    // actual infos are a subset → the real JSON is never longer). Sorted by
    // name: the legacy path iterates `safe_open(...).keys()`, which the
    // safetensors binding sorts, and Neo reproduces that byte-for-byte.
    let mut worst_infos: Vec<(String, String, String)> = Vec::new();
    let mut passthrough_floats: Vec<String> = Vec::new();
    for t in &st.tensors {
        match compressible_scheme(t) {
            Band::In(scheme) => worst_infos.push((
                t.name.clone(),
                scheme.torch_name.to_owned(),
                shape_string(&t.shape),
            )),
            Band::OutOfBandFloat => passthrough_floats.push(t.name.clone()),
            Band::NotFloat => {}
        }
    }
    worst_infos.sort_by(|a, b| a.0.cmp(&b.0));
    let worst_meta = build_compress_meta(
        &kept_meta,
        file_len,
        &"0".repeat(64),
        exact,
        meta_absent,
        &py_dumps_compressed_vectors(&worst_infos),
    );

    // Worst-case header bound (see the module docs): per entry the LONGER of
    // (pass-through form, compressed form) with the SOURCE offsets — the
    // compressed cumulative sums only ever shrink, and decimal digit counts
    // are monotone, so the real header JSON never exceeds this.
    let h_max = {
        let worst_shapes: Vec<Vec<u64>> = st
            .tensors
            .iter()
            .map(|t| {
                let alt = format!("[{}]", t.len());
                if alt.len() > shape_string(&t.shape).len() {
                    vec![t.len()]
                } else {
                    t.shape.clone()
                }
            })
            .collect();
        let entries: Vec<OutEntry> = st
            .tensors
            .iter()
            .zip(&worst_shapes)
            .map(|(t, sh)| OutEntry {
                name: &t.name,
                dtype: if "U8".len() > t.dtype.len() {
                    "U8"
                } else {
                    &t.dtype
                },
                shape: sh,
                start: t.start,
                end: t.end,
            })
            .collect();
        let bound = i64::try_from(build_header_region(Some(&worst_meta), &entries).len())
            .unwrap_or(i64::MAX);
        usize::try_from((bound + opts.hmax_slack).max(PREFIX_LEN as i64))
            .expect("header bound stays positive")
    };

    // Stream: prefix + the H_max placeholder region, then the pieces.
    let mut writer = AtomicWriter::new(dst, false).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "creating the output for", dst),
        other => other,
    })?;
    writer.write_all(&(h_max as u64).to_le_bytes())?;
    for _ in 0..h_max / 65536 {
        writer.write_all(&[b' '; 65536])?;
    }
    writer.write_all(&vec![b' '; h_max % 65536])?;

    hooks.phase(Phase::Tensors);
    let mut infos: Vec<(String, String, String)> = Vec::new();
    let mut pieces: Vec<Piece> = Vec::with_capacity(st.tensors.len());
    let mut original_bytes = 0u64;
    let mut compressed_bytes = 0u64;
    // ONE grow-only blob buffer for the whole file (no per-tensor alloc):
    // peak RAM stays O(largest tensor) — the K1 budget.
    let mut blob_buf: Vec<u8> = Vec::new();

    // The source SHA-256 streams over the SAME mmap pages on a worker thread
    // while the tensor loop runs (Plan §4.4.3-1: near-zero added cost — the
    // pages are already hot; scoped thread = no lifetime gymnastics).
    let loop_outcome: StResult<String> = std::thread::scope(|s| {
        let sha_handle = s.spawn(|| sha256_chunks(&mmap, hooks.cancel));
        let mut result: StResult<()> = Ok(());
        for t in &st.tensors {
            let step = (|| -> StResult<()> {
                hooks.check_cancel()?;
                let data = st.data(&mmap, t)?;
                match compressible_scheme(t) {
                    Band::In(scheme) => {
                        compress_tensor_into(
                            &mut blob_buf,
                            &scheme,
                            data,
                            &t.shape,
                            opts.threads,
                            hooks.cancel,
                        )?;
                        if (blob_buf.len() as u64) < t.len() {
                            // worth it — store the blob as a U8 vector and
                            // record it in infos (legacy rule: a blob that is
                            // `>= uncompressed_size` keeps the original AND
                            // stays out of the infos map)
                            writer.write_all(&blob_buf)?;
                            infos.push((
                                t.name.clone(),
                                scheme.torch_name.to_owned(),
                                shape_string(&t.shape),
                            ));
                            pieces.push(Piece::Blob {
                                len: blob_buf.len() as u64,
                            });
                            compressed_bytes += blob_buf.len() as u64;
                        } else {
                            writer.write_all(data)?;
                            pieces.push(Piece::Pass);
                            compressed_bytes += t.len();
                        }
                    }
                    _ => {
                        writer.write_all(data)?;
                        pieces.push(Piece::Pass);
                        compressed_bytes += t.len();
                    }
                }
                original_bytes += t.len();
                hooks.bump();
                Ok(())
            })();
            if let Err(e) = step {
                result = Err(e);
                break;
            }
        }
        let src_sha = match sha_handle.join() {
            Ok(r) => r,
            Err(_) => Err(StError::Format("sha256 worker panicked".to_owned())),
        }?;
        result?;
        Ok(src_sha)
    });
    let src_sha = match loop_outcome {
        Ok(sha) => sha,
        Err(e) => {
            writer.abort();
            return Err(e);
        }
    };

    // Exact header: every stored length is known → real offsets → real JSON.
    hooks.phase(Phase::Write);
    infos.sort_by(|a, b| a.0.cmp(&b.0));
    let infos_json = py_dumps_compressed_vectors(&infos);
    let meta = build_compress_meta(
        &kept_meta,
        file_len,
        &src_sha,
        exact,
        meta_absent,
        &infos_json,
    );
    let owned: Vec<(String, String, Vec<u64>, u64, u64)> = {
        let mut v = Vec::with_capacity(st.tensors.len());
        let mut offset = 0u64;
        debug_assert_eq!(pieces.len(), st.tensors.len());
        for (t, piece) in st.tensors.iter().zip(&pieces) {
            let (dtype, shape, len) = match piece {
                Piece::Blob { len } => ("U8".to_owned(), vec![*len], *len),
                Piece::Pass => (t.dtype.clone(), t.shape.clone(), t.len()),
            };
            // checked cumulative offsets: a hostile file declaring many
            // capped-but-large tensors must ERROR on overflow, never wrap
            let end = offset.checked_add(len).ok_or_else(|| {
                StError::Format(
                    "restored file size overflows u64 (hostile blob headers?)".to_owned(),
                )
            })?;
            v.push((t.name.clone(), dtype, shape, offset, end));
            offset = end;
        }
        v
    };
    let entries: Vec<OutEntry> = owned
        .iter()
        .map(|(n, d, s, a, b)| OutEntry {
            name: n,
            dtype: d,
            shape: s,
            start: *a,
            end: *b,
        })
        .collect();
    let region = build_header_region(Some(&meta), &entries);
    let json = trim_json_tail(&region);
    if json.len() > h_max {
        // Defensive fallback — the bound construction above makes this
        // unreachable; a negative `hmax_slack` exercises it in tests. The
        // payload is already durable in the tmp: flush (finish), then
        // rewrite the container with the exact header. The second finish()
        // below is a no-op afterwards (the inner writer is consumed).
        writer.finish()?;
        let tmp = writer.tmp_path().to_path_buf();
        rewrite_with_header(&tmp, h_max, &region)?;
    } else {
        // Patch the JSON over the placeholder; the remaining reserved bytes
        // are already spaces (valid JSON whitespace up to the declared
        // region length H_max).
        writer.patch(u64::try_from(PREFIX_LEN).expect("8"), json)?;
    }
    writer.finish()?;

    // Paranoid mode (Plan §4.4.3-4): fully re-decode the artifact and verify
    // it against the source sha BEFORE the rename — a failed paranoid run
    // leaves dst non-existent and the tmp removed.
    let mut warnings: Vec<String> = Vec::new();
    if opts.paranoid {
        hooks.phase(Phase::Verify);
        let verify_dst = PathBuf::from(format!("{}.verify.tmp", dst.display()));
        let corrupt_of_verify = PathBuf::from(format!("{}{CORRUPT_SUFFIX}", verify_dst.display()));
        let _ = std::fs::remove_file(&verify_dst);
        let _ = std::fs::remove_file(&corrupt_of_verify);
        let tmp_src = writer.tmp_path().to_path_buf();
        // The verification decode is an INTERNAL step: it must not drive the
        // job's progress counter (done would exceed total — the UI computes
        // done/total) — only the cancellation flag is shared.
        let inner_hooks = Hooks {
            progress: None,
            cancel: hooks.cancel,
        };
        let decoded = decompress_file(&tmp_src, &verify_dst, opts, &inner_hooks);
        let passed = match &decoded {
            Ok(out) => {
                warnings.extend(out.warnings.iter().map(|w| format!("paranoid: {w}")));
                !matches!(out.verified, Verified::Skipped)
            }
            Err(_) => false,
        };
        let _ = std::fs::remove_file(&verify_dst);
        let _ = std::fs::remove_file(&corrupt_of_verify);
        if !passed {
            let err = decoded.err().unwrap_or_else(|| {
                StError::Verification(
                    "paranoid re-decode did not verify the artifact (no sha recorded?)".to_owned(),
                )
            });
            writer.abort();
            return Err(err);
        }
    }
    if !exact {
        warnings.push(
            "the source header is not in canonical safetensors form (hand-edited or exotic writer): \
             decompression will restore tensor data + metadata identically but not byte-for-byte, \
             and verification downgrades to the structural check (Plan §4.7.4)"
                .to_owned(),
        );
    }
    if !passthrough_floats.is_empty() {
        let shown: Vec<&str> = passthrough_floats
            .iter()
            .take(3)
            .map(String::as_str)
            .collect();
        warnings.push(format!(
            "{} floating-point tensor(s) outside the compression band stored as-is (Phase 4 adds them): {}{}",
            passthrough_floats.len(),
            shown.join(", "),
            if passthrough_floats.len() > 3 { ", …" } else { "" }
        ));
    }

    writer.commit()?;
    hooks.phase(Phase::Done);
    Ok(CompressOutcome {
        stats: CompressStats {
            original_bytes,
            compressed_bytes,
            tensors: st.tensors.len(),
            compressed_tensors: infos.len(),
        },
        src_sha256: src_sha,
        exact,
        warnings,
    })
}

/// Rewrite a streamed tmp (payload at `PREFIX_LEN + old_hmax`) with the
/// exact header region — the defensive fallback of the bound proof.
fn rewrite_with_header(tmp: &Path, old_hmax: usize, region: &[u8]) -> StResult<()> {
    use std::fs::{File, OpenOptions};
    use std::io::{BufWriter, Seek, SeekFrom, Write};
    let fix = PathBuf::from(format!("{}.fix", tmp.display()));
    {
        let mut src_f = File::open(tmp)?;
        let dst_f = OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(&fix)?;
        let mut bw = BufWriter::with_capacity(1024 * 1024, &dst_f);
        bw.write_all(&(region.len() as u64).to_le_bytes())?;
        bw.write_all(region)?;
        src_f.seek(SeekFrom::Start((PREFIX_LEN + old_hmax) as u64))?;
        std::io::copy(&mut src_f, &mut bw)?;
        bw.flush()?;
        dst_f.sync_all()?;
    }
    std::fs::remove_file(tmp)?;
    std::fs::rename(&fix, tmp)?;
    fsync_dir(tmp.parent().unwrap_or_else(|| Path::new(".")))?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Decompress
// ---------------------------------------------------------------------------

/// What the restore writes for one tensor.
#[derive(Debug, Clone, PartialEq, Eq)]
enum Restore {
    /// Verbatim copy of the stored bytes.
    Pass,
    /// Decode the ZN blob; the restored entry has this dtype/shape/size.
    Decode {
        st_dtype: &'static str,
        shape: Vec<u64>,
        len: u64,
    },
}

fn stream_write(writer: &mut AtomicWriter, bytes: &[u8], hooks: &Hooks) -> StResult<()> {
    // 4 MiB steps keep cancellation responsive on huge pass-through tensors.
    for chunk in bytes.chunks(4 * 1024 * 1024) {
        hooks.check_cancel()?;
        writer.write_all(chunk)?;
    }
    Ok(())
}

// Measurement note (2026-09-24, 2 vCPU / sha2-soft host): a PARALLEL hasher
// thread fed by a chunk channel was implemented and benchmarked — it made
// decompression SLOWER here (0.65 s vs 0.60 s for 64 MB: no spare core to
// overlap with, plus clone traffic) and grew peak RSS by the unbounded
// channel backlog (a K1 hazard on 12 GB models). The INLINE hasher below is
// the design of Plan §4.4.3 (zero extra I/O, zero extra memory); on SHA-NI
// hosts (the Plan's reference class) its serial cost is ~45 ms per 64 MB —
// negligible. Re-parallelising only pays with bounded queues AND spare
// cores; revisit measurement-driven if a reference-machine run says so.

/// Decompress `src` (.znn.safetensors) into `dst` (.safetensors) — the
/// native path of the legacy `decompress_safetensors`, with the Plan
/// §4.4.3 verification pipeline:
///
/// * `znn_neo_src_sha256` present → the restore is hashed INLINE (zero extra
///   I/O) and compared; a mismatch on a byte-exact-capable file KEEPS the
///   compressed source and retreats the restore to `<dst>.corrupt`;
/// * `znn_neo_exact="0"` sources downgrade a mismatch to the structural
///   guarantee (Plan §4.7.4) instead of failing on formatting;
/// * files without the key (official CLI / legacy) skip verification with a
///   logged note.
///
/// # Errors
/// Parse/codec/I-O failures, cancellation, infos⇄blob disagreements, and
/// verification failures (see above). Errors leave the source untouched and
/// no partial output behind.
pub fn decompress_file(
    src: &Path,
    dst: &Path,
    opts: &JobOpts,
    hooks: &Hooks,
) -> StResult<DecompressOutcome> {
    if dst.exists() {
        return Err(StError::Format(format!(
            "target already exists: {}",
            dst.display()
        )));
    }
    hooks.phase(Phase::Prepare);
    let (st, mmap) = StContainer::open(src).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "reading", src),
        other => other,
    })?;
    let total = u64::try_from(st.tensors.len()).unwrap_or(u64::MAX);
    if let Some(p) = hooks.progress {
        p.set_total(total.max(1));
    }

    let meta_lookup = |key: &str| -> Option<String> {
        st.metadata
            .as_ref()?
            .iter()
            .rev()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v.clone())
    };
    // `verify=false` (non-default) suppresses the inline hasher entirely —
    // the recorded digest is then ignored and the outcome says "skipped".
    let sha_recorded = meta_lookup(SRC_SHA_KEY);
    let sha_was_recorded = sha_recorded.is_some();
    let src_sha = if opts.verify { sha_recorded } else { None };
    let exact = meta_lookup(EXACT_KEY).as_deref() == Some("1");
    let meta_absent = meta_lookup(SRC_META_ABSENT_KEY).as_deref() == Some("1");
    let infos = match meta_lookup(METADATA_KEY) {
        Some(json) => parse_infos(&json)?,
        None => HashMap::new(),
    };

    // Planning pass: resolve every blob HEADER (cheap) so the restored
    // header — and with it the whole output layout — is known before any
    // payload is decoded (single streaming write pass).
    let mut plan: Vec<Restore> = Vec::with_capacity(st.tensors.len());
    for t in &st.tensors {
        let Some((info_dtype, info_shape)) = infos.get(&t.name) else {
            plan.push(Restore::Pass);
            continue;
        };
        if t.dtype != "U8" {
            return Err(StError::Format(format!(
                "tensor {}: listed in {METADATA_KEY} but stored as {} (expected a U8 vector) — the file is corrupt or was rewritten by an incompatible tool",
                t.name, t.dtype
            )));
        }
        let blob = st.data(&mmap, t)?;
        // header-only validation (the SAME checks decompress_tensor_into
        // will re-run at decode time — planning must never promise a tensor
        // the write pass cannot deliver)
        let info = inspect_tensor(blob)?;
        if info.torch_name != info_dtype {
            return Err(StError::Format(format!(
                "tensor {name}: {METADATA_KEY} records dtype {info_dtype:?} but the blob header says {other:?} — refusing to guess",
                name = t.name,
                other = info.torch_name
            )));
        }
        if shape_string(&info.shape) != *info_shape {
            return Err(StError::Format(format!(
                "tensor {name}: {METADATA_KEY} records shape {info_shape:?} but the blob header packs {packed:?} — refusing to guess",
                name = t.name,
                packed = info.shape
            )));
        }
        if info.len > opts.max_restore_bytes as u64 {
            return Err(StError::Format(format!(
                "tensor {}: blob declares {} bytes — above the {}-byte restore cap (hostile or corrupt file?)",
                t.name, info.len, opts.max_restore_bytes
            )));
        }
        plan.push(Restore::Decode {
            st_dtype: info.st_dtype,
            shape: info.shape,
            len: info.len,
        });
    }

    // The restored metadata: exactly what the ORIGINAL carried (Neo/ZipNN
    // bookkeeping stripped, order preserved). `None` when the compressed
    // file has no `__metadata__` at all (the reference writer OMITS the key
    // for None but writes `{}` for an empty map — both reproduced).
    let restored_meta: Option<Vec<(String, String)>> = st.metadata.as_ref().map(|m| {
        m.iter()
            .filter(|(k, _)| !BOOKKEEPING_KEYS.contains(&k.as_str()))
            .cloned()
            .collect()
    });
    // The source carried NO __metadata__ at all → the restored file must not
    // gain one (the reference writer OMITS the key for None but writes `{}`
    // for an empty map — legacy/official files lack the record, so an empty
    // filtered map restores as `{}`, matching the legacy path's output).
    let restored_meta = match restored_meta {
        Some(entries) if meta_absent && entries.is_empty() => None,
        other => other,
    };
    let owned: Vec<(String, String, Vec<u64>, u64, u64)> = {
        let mut v = Vec::with_capacity(st.tensors.len());
        let mut offset = 0u64;
        for (t, p) in st.tensors.iter().zip(&plan) {
            let (dtype, shape, len) = match p {
                Restore::Pass => (t.dtype.clone(), t.shape.clone(), t.len()),
                Restore::Decode {
                    st_dtype,
                    shape,
                    len,
                } => ((*st_dtype).to_owned(), shape.clone(), *len),
            };
            // checked cumulative offsets: a hostile file declaring many
            // capped-but-large tensors must ERROR on overflow, never wrap
            let end = offset.checked_add(len).ok_or_else(|| {
                StError::Format(
                    "restored file size overflows u64 (hostile blob headers?)".to_owned(),
                )
            })?;
            v.push((t.name.clone(), dtype, shape, offset, end));
            offset = end;
        }
        v
    };
    let entries: Vec<OutEntry> = owned
        .iter()
        .map(|(n, d, s, a, b)| OutEntry {
            name: n,
            dtype: d,
            shape: s,
            start: *a,
            end: *b,
        })
        .collect();
    let region = build_header_region(restored_meta.as_deref(), &entries);

    // Streaming write pass with the INLINE sha (hasher only when a recorded
    // digest exists to compare against — zero-cost otherwise).
    hooks.phase(Phase::Tensors);
    let mut writer = AtomicWriter::new(dst, src_sha.is_some()).map_err(|e| match e {
        StError::Io(io) => io_ctx(io, "creating the output for", dst),
        other => other,
    })?;
    let mut decoded_count = 0usize;
    // ONE grow-only restore buffer for the whole file (peak RAM O(largest
    // tensor) — the K1 budget; `resize` re-zeroes only the growth delta and
    // the decode overwrites every byte).
    let mut restore_buf: Vec<u8> = Vec::new();
    writer.write_all(&(region.len() as u64).to_le_bytes())?;
    writer.write_all(&region)?;
    for (t, p) in st.tensors.iter().zip(&plan) {
        let step = (|| -> StResult<()> {
            hooks.check_cancel()?;
            match p {
                Restore::Pass => {
                    let data = st.data(&mmap, t)?;
                    stream_write(&mut writer, data, hooks)
                }
                Restore::Decode { len, .. } => {
                    let blob = st.data(&mmap, t)?;
                    decompress_tensor_into(
                        blob,
                        &mut restore_buf,
                        opts.threads,
                        hooks.cancel,
                        opts.max_restore_bytes,
                    )?;
                    if restore_buf.len() as u64 != *len {
                        return Err(StError::Format(format!(
                            "tensor {}: decoded {} bytes but the plan declared {len}",
                            t.name,
                            restore_buf.len()
                        )));
                    }
                    stream_write(&mut writer, &restore_buf, hooks)?;
                    decoded_count += 1;
                    Ok(())
                }
            }
        })();
        if let Err(e) = step {
            writer.abort();
            return Err(e);
        }
        hooks.bump();
    }
    let digest = writer.finish()?;

    // Verification (Plan §4.4.3) — the tmp is durable at this point but NOT
    // yet renamed: a failed check keeps the compressed source and retreats
    // the restore to `.corrupt`.
    hooks.phase(Phase::Verify);
    let mut warnings: Vec<String> = Vec::new();
    let verified = match (src_sha.as_deref(), digest) {
        (Some(expected), Some(actual)) if actual == expected => Verified::Sha256,
        (Some(expected), Some(actual)) => {
            if exact {
                let corrupt = corrupt_path(dst);
                writer.reject_to(&corrupt)?;
                return Err(StError::Verification(format!(
                    "the restored file does not match znn_neo_src_sha256 (recorded {expected}, computed {actual}) — \
                     the compressed file was KEPT and the failed restore was moved to {} for diagnosis; \
                     the model may be corrupt (storage error, or the file changed behind Neo's back)",
                    corrupt.display()
                )));
            }
            // Non-canonical source (znn_neo_exact="0"): a byte difference is
            // EXPECTED (the restore is canonical, the source was not). Fall
            // back to the structural guarantee of Plan §4.7.4, re-checked
            // against the on-disk bytes.
            if let Err(e) = structural_check(writer.tmp_path(), &owned, restored_meta.as_deref()) {
                writer.abort();
                return Err(e);
            }
            warnings.push(format!(
                "byte-exact verification unavailable (the original file's header was not canonical, znn_neo_exact=0): \
                 structural verification passed — tensor data and metadata are identical, header formatting differs \
                 (restored sha {actual}, recorded {expected})"
            ));
            Verified::Structural
        }
        (Some(_), None) => {
            // unreachable: the hasher is enabled whenever a sha is recorded
            writer.abort();
            return Err(StError::Format(
                "internal: hasher produced no digest despite a recorded sha".to_owned(),
            ));
        }
        (None, _) => {
            // src_sha is None here, so either the file records no digest or
            // verification was switched off — say which, honestly.
            if sha_was_recorded {
                warnings.push(format!(
                    "{SRC_SHA_KEY} is recorded but verification was disabled via opts — \
                     the restore was NOT checked (Plan §4.4.3-2 defaults to ON)"
                ));
            } else {
                warnings.push(format!(
                    "no {SRC_SHA_KEY} in this file (compressed by the official ZipNN tooling or a pre-Neo version): \
                     byte-exact verification skipped (Plan §4.4.3-4)"
                ));
            }
            Verified::Skipped
        }
    };
    writer.commit()?;
    hooks.phase(Phase::Done);
    Ok(DecompressOutcome {
        stats: DecompressStats {
            tensors: st.tensors.len(),
            decompressed_tensors: decoded_count,
        },
        verified,
        warnings,
    })
}

/// `<dst>.corrupt` — the diagnostic retreat of a failed restore.
#[must_use]
pub fn corrupt_path(dst: &Path) -> PathBuf {
    let mut s = dst.as_os_str().to_os_string();
    s.push(CORRUPT_SUFFIX);
    PathBuf::from(s)
}

/// Parse the `znn_compressed_vectors` JSON value into name → (dtype, shape).
/// Tolerant of extra fields (forward compatibility), strict about the two
/// required ones — a malformed record is an error, never a silent
/// pass-through of Huffman-coded bytes (the legacy `json.loads` crashes
/// here too; Neo's message is actionable).
fn parse_infos(json: &str) -> StResult<HashMap<String, (String, String)>> {
    let mut out = HashMap::new();
    let mut j = Jiter::new(json.as_bytes());
    // keys are owned immediately (jiter ties &str lifetimes to the &mut
    // borrow — see safetensors_io::parse_header_json)
    let mut key: Option<String> = j.next_object().map_err(infos_err)?.map(str::to_owned);
    while let Some(name) = key.take() {
        let mut dtype: Option<String> = None;
        let mut shape: Option<String> = None;
        let mut inner: Option<String> = match j.next_object().map_err(infos_err)?.map(str::to_owned)
        {
            Some(k) => Some(k),
            None => {
                return Err(StError::Format(format!(
                    "{METADATA_KEY}[{name:?}] is not an object"
                )));
            }
        };
        while let Some(field) = inner.take() {
            match field.as_str() {
                "dtype" => dtype = Some(j.next_str().map_err(infos_err)?.to_owned()),
                "shape" => shape = Some(j.next_str().map_err(infos_err)?.to_owned()),
                _ => j.next_skip().map_err(infos_err)?,
            }
            inner = j.next_key().map_err(infos_err)?.map(str::to_owned);
        }
        let (Some(dtype), Some(shape)) = (dtype, shape) else {
            return Err(StError::Format(format!(
                "{METADATA_KEY}[{name:?}] lacks dtype/shape"
            )));
        };
        out.insert(name, (dtype, shape));
        key = j.next_key().map_err(infos_err)?.map(str::to_owned);
    }
    j.finish().map_err(infos_err)?;
    Ok(out)
}

fn infos_err(e: jiter::JiterError) -> StError {
    StError::Format(format!("malformed {METADATA_KEY} record: {e}"))
}

/// The Plan §4.7.4 minimum guarantee, re-checked against the ON-DISK bytes
/// (a fresh parse of the finished tmp): valid container, entries exactly as
/// planned (names/dtypes/shapes/dense offsets), metadata exactly as
/// planned. Catches write-level corruption of the header/layout for
/// non-canonical restores where the sha cannot be the judge.
fn structural_check(
    path: &Path,
    expect_entries: &[(String, String, Vec<u64>, u64, u64)],
    expect_meta: Option<&[(String, String)]>,
) -> StResult<()> {
    let (st, _mmap) = StContainer::open(path)?;
    if st.tensors.len() != expect_entries.len() {
        return Err(StError::Verification(format!(
            "structural check: {} tensors on disk, {} planned",
            st.tensors.len(),
            expect_entries.len()
        )));
    }
    for (disk, (name, dtype, shape, start, end)) in st.tensors.iter().zip(expect_entries) {
        if &disk.name != name
            || &disk.dtype != dtype
            || &disk.shape != shape
            || disk.start != *start
            || disk.end != *end
        {
            return Err(StError::Verification(format!(
                "structural check: tensor {name:?} on disk is ({:?}, {:?}, {}..{}) but ({dtype:?}, {shape:?}, {start}..{end}) was planned",
                disk.dtype, disk.shape, disk.start, disk.end
            )));
        }
    }
    match (st.metadata.as_deref(), expect_meta) {
        (None, None) => {}
        (Some(a), Some(b)) if a == b => {}
        (a, b) => {
            return Err(StError::Verification(format!(
                "structural check: metadata on disk ({} entries) differs from the plan ({} entries)",
                a.map_or(0, <[(_, _)]>::len),
                b.map_or(0, <[(_, _)]>::len)
            )));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::safetensors_io::{OutEntry, build_header_region};
    use crate::znn_tensor::compress_tensor;
    use std::sync::atomic::AtomicBool;

    struct TempDir(PathBuf);
    impl TempDir {
        fn new(tag: &str) -> Self {
            let mut p = std::env::temp_dir();
            p.push(format!(
                "mmneo-pipeline-{tag}-{}-{:?}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.subsec_nanos())
                    .unwrap_or(0)
            ));
            std::fs::create_dir_all(&p).unwrap();
            Self(p)
        }
        fn path(&self, name: &str) -> PathBuf {
            self.0.join(name)
        }
    }
    impl Drop for TempDir {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    /// Deterministic low-entropy bf16 bytes (compresses well).
    fn bf16_bytes(n: usize, seed: u32) -> Vec<u8> {
        let mut x = seed | 1;
        let mut out = Vec::with_capacity(n * 2);
        for _ in 0..n {
            x = x.wrapping_mul(1664525).wrapping_add(1013904223);
            let v: u16 = (0x3F80u32 | ((x >> 9) & 0x7F)) as u16;
            out.extend_from_slice(&v.to_le_bytes());
        }
        out
    }

    fn noisy_bytes(n: usize, seed: u32) -> Vec<u8> {
        let mut x = seed | 1;
        let mut out = Vec::with_capacity(n);
        for _ in 0..n {
            x = x.wrapping_mul(1664525).wrapping_add(1013904223);
            out.push((x >> 16) as u8);
        }
        out
    }

    /// Write a canonical safetensors file: (name, dtype, shape, bytes).
    fn write_st(
        path: &Path,
        metadata: Option<&[(String, String)]>,
        tensors: &[(&str, &str, Vec<u64>, Vec<u8>)],
    ) {
        let mut data = Vec::new();
        let mut entries = Vec::new();
        for (name, dtype, shape, bytes) in tensors {
            let start = data.len() as u64;
            data.extend_from_slice(bytes);
            entries.push((
                (*name).to_owned(),
                (*dtype).to_owned(),
                shape.clone(),
                start,
                data.len() as u64,
            ));
        }
        let outs: Vec<OutEntry> = entries
            .iter()
            .map(|(n, d, s, a, b)| OutEntry {
                name: n,
                dtype: d,
                shape: s,
                start: *a,
                end: *b,
            })
            .collect();
        let region = build_header_region(metadata, &outs);
        let mut file = Vec::new();
        file.extend_from_slice(&(region.len() as u64).to_le_bytes());
        file.extend_from_slice(&region);
        file.extend_from_slice(&data);
        std::fs::write(path, &file).unwrap();
    }

    fn corpus() -> Vec<(&'static str, &'static str, Vec<u64>, Vec<u8>)> {
        vec![
            (
                "enc.weight",
                "BF16",
                vec![256, 128],
                bf16_bytes(256 * 128, 7),
            ),
            ("enc.bias", "F32", vec![64], noisy_bytes(64 * 4, 11)),
            ("dec.weight", "F16", vec![128, 64], {
                let mut x = 3u32;
                let mut v = Vec::new();
                for _ in 0..128 * 64 {
                    x = x.wrapping_mul(1664525).wrapping_add(1013904223);
                    let h: u16 = (0x3C00u32 | ((x >> 10) & 0x1FF)) as u16;
                    v.extend_from_slice(&h.to_le_bytes());
                }
                v
            }),
            ("q.weight", "F8_E4M3", vec![512], {
                let mut x = 5u32;
                let mut v = Vec::new();
                for _ in 0..512 {
                    x = x.wrapping_mul(1664525).wrapping_add(1013904223);
                    v.push((0x38u32 | ((x >> 12) & 0x7)) as u8);
                }
                v
            }),
            ("tokens", "U8", vec![100], noisy_bytes(100, 13)), // pass-through
            ("idx", "I32", vec![10], vec![0u8; 40]),           // pass-through
            ("prec", "F64", vec![4], vec![0u8; 32]),           // out-of-band float
            ("scalar", "BF16", vec![], bf16_bytes(1, 17)),     // scalar shape []
        ]
    }

    fn meta(k: &str, v: &str) -> (String, String) {
        (k.to_owned(), v.to_owned())
    }

    fn read(path: &Path) -> Vec<u8> {
        std::fs::read(path).unwrap()
    }

    fn sha_of(bytes: &[u8]) -> String {
        use sha2::{Digest, Sha256};
        let mut h = Sha256::new();
        h.update(bytes);
        crate::safetensors_io::hex(&h.finalize())
    }

    #[test]
    fn compress_decompress_roundtrip_is_byte_exact() {
        let dir = TempDir::new("roundtrip");
        let src = dir.path("model.safetensors");
        let znn = dir.path("model.znn.safetensors");
        let back = dir.path("restored.safetensors");
        let metadata = vec![meta("format", "pt"), meta("lang", "日本語")];
        let original = {
            write_st(&src, Some(&metadata), &corpus());
            read(&src)
        };

        let progress = Progress::new(0);
        let hooks = Hooks {
            progress: Some(&progress),
            cancel: None,
        };
        let out = compress_file(&src, &znn, &JobOpts::default(), &hooks).expect("compress");
        assert!(out.exact, "canonical source must be flagged exact");
        assert_eq!(out.src_sha256, sha_of(&original));
        assert_eq!(out.stats.tensors, corpus().len());
        // compressible band: enc.weight(BF16), dec.weight(F16), q.weight(FP8)
        // always compress; enc.bias (F32, noisy mantissas) may or may not
        // beat the threshold; scalar/U8/I32/F64 always pass through
        assert!(
            (3..=4).contains(&out.stats.compressed_tensors),
            "compressed_tensors = {}",
            out.stats.compressed_tensors
        );
        assert_eq!(progress.snapshot().2, Phase::Done, "terminal phase reached");

        // compressed container structure
        let (cst, cmmap) = StContainer::open(&znn).expect("parse compressed");
        let cmeta: &[(String, String)] = cst.metadata.as_deref().expect("metadata present");
        let lookup = |k: &str| cmeta.iter().find(|(mk, _)| mk == k).map(|(_, v)| v.clone());
        assert_eq!(
            lookup(ORIGINAL_SIZE_KEY).unwrap(),
            original.len().to_string()
        );
        assert_eq!(lookup(SRC_SHA_KEY).unwrap(), sha_of(&original));
        assert_eq!(lookup(EXACT_KEY).unwrap(), "1");
        assert_eq!(lookup("format").unwrap(), "pt");
        assert_eq!(lookup("lang").unwrap(), "日本語");
        let infos = parse_infos(&lookup(METADATA_KEY).unwrap()).unwrap();
        assert_eq!(infos.len(), out.stats.compressed_tensors);
        // the header must sit at a fixed H_max region and parse cleanly
        assert!(!cst.canonical, "H_max padding is not canonical (expected)");
        // every compressed tensor is a U8 vector, pass-throughs keep dtype
        for t in &cst.tensors {
            if infos.contains_key(&t.name) {
                assert_eq!(t.dtype, "U8", "{}", t.name);
            }
        }
        let _ = &cmmap;

        // decompress → byte-exact restore
        let out2 = decompress_file(&znn, &back, &JobOpts::default(), &hooks).expect("decompress");
        assert_eq!(out2.verified, Verified::Sha256);
        assert_eq!(out2.stats.tensors, corpus().len());
        assert_eq!(
            out2.stats.decompressed_tensors,
            out.stats.compressed_tensors
        );
        assert_eq!(read(&back), original, "byte-exact restore");
    }

    #[test]
    fn no_metadata_and_empty_metadata_restore_distinguish() {
        let dir = TempDir::new("meta-none");
        // (a) source WITHOUT __metadata__ → restore must not gain one
        let src = dir.path("a.safetensors");
        let znn = dir.path("a.znn.safetensors");
        let back = dir.path("a.back.safetensors");
        let corpus_small = vec![("w", "BF16", vec![64, 32], bf16_bytes(64 * 32, 3))];
        let original = {
            write_st(&src, None, &corpus_small);
            read(&src)
        };
        let hooks = Hooks::default();
        compress_file(&src, &znn, &JobOpts::default(), &hooks).unwrap();
        decompress_file(&znn, &back, &JobOpts::default(), &hooks).unwrap();
        assert_eq!(read(&back), original);
        let (rst, _m) = StContainer::open(&back).unwrap();
        assert!(rst.metadata.is_none(), "no __metadata__ key gained");

        // (b) source WITH an EMPTY __metadata__ map → restore keeps `{}`
        let src = dir.path("b.safetensors");
        let znn = dir.path("b.znn.safetensors");
        let back = dir.path("b.back.safetensors");
        let original = {
            write_st(&src, Some(&[]), &corpus_small);
            read(&src)
        };
        compress_file(&src, &znn, &JobOpts::default(), &hooks).unwrap();
        decompress_file(&znn, &back, &JobOpts::default(), &hooks).unwrap();
        assert_eq!(read(&back), original);
        let (rst, _m) = StContainer::open(&back).unwrap();
        assert_eq!(rst.metadata.as_deref(), Some(&[][..]), "empty map kept");
    }

    #[test]
    fn noncanonical_source_downgrades_to_structural() {
        let dir = TempDir::new("noncanonical");
        let src = dir.path("loose.safetensors");
        let znn = dir.path("loose.znn.safetensors");
        let back = dir.path("loose.back.safetensors");
        // hand-built header: json.dumps-style spacing → non-canonical
        let data = bf16_bytes(1024, 9);
        let json = br#"{"w": {"dtype": "BF16", "shape": [64, 16], "data_offsets": [0, 2048]}}"#;
        let mut img = Vec::new();
        let padded = json.len().next_multiple_of(8);
        img.extend_from_slice(&(padded as u64).to_le_bytes());
        img.extend_from_slice(json);
        img.resize(8 + padded, b' ');
        img.extend_from_slice(&data);
        std::fs::write(&src, &img).unwrap();
        let original = read(&src);

        let hooks = Hooks::default();
        let out = compress_file(&src, &znn, &JobOpts::default(), &hooks).unwrap();
        assert!(!out.exact);
        assert!(out.warnings.iter().any(|w| w.contains("canonical")));

        let out2 = decompress_file(&znn, &back, &JobOpts::default(), &hooks).unwrap();
        assert_eq!(out2.verified, Verified::Structural);
        assert!(out2.warnings.iter().any(|w| w.contains("structural")));
        let restored = read(&back);
        assert_ne!(restored, original, "byte-exact is impossible here");
        // … but the tensor payload and the semantics are intact
        let (rst, rmmap) = StContainer::open(&back).unwrap();
        assert_eq!(rst.tensors.len(), 1);
        let tdata = rst.data(&rmmap, &rst.tensors[0]).unwrap();
        assert_eq!(tdata, &data[..]);
    }

    #[test]
    fn corrupted_blob_keeps_source_and_retreats_to_corrupt() {
        let dir = TempDir::new("corrupt");
        let src = dir.path("m.safetensors");
        let znn = dir.path("m.znn.safetensors");
        let back = dir.path("m.restored.safetensors");
        write_st(
            &src,
            Some(&[meta("format", "pt")]),
            &[("w", "BF16", vec![128, 64], bf16_bytes(128 * 64, 21))],
        );
        let original_znn_bytes = {
            let hooks = Hooks::default();
            compress_file(&src, &znn, &JobOpts::default(), &hooks).unwrap();
            read(&znn)
        };
        // flip a byte deep in the payload (a raw/huff0 piece of the blob) —
        // far past header+infos so the container still parses
        let mut tampered = original_znn_bytes.clone();
        let at = tampered.len() - 500;
        tampered[at] ^= 0xFF;
        std::fs::write(&znn, &tampered).unwrap();

        let hooks = Hooks::default();
        let err = decompress_file(&znn, &back, &JobOpts::default(), &hooks)
            .expect_err("must fail verification or decode");
        let msg = err.to_string();
        assert!(
            matches!(
                err,
                StError::Verification(_) | StError::Codec(_) | StError::Format(_)
            ),
            "clean error, got: {msg}"
        );
        // the compressed source is KEPT, the failed restore (if any) is a
        // .corrupt sibling — never a silent bad model, never a lost source
        assert_eq!(read(&znn), tampered, "compressed source kept");
        assert!(!back.exists(), "no unverified model file");
        let corrupt = corrupt_path(&back);
        if corrupt.exists() {
            // sha-verification failure path: the restore was completed but
            // did not match → retreated for diagnosis
            assert!(msg.contains("znn_neo_src_sha256"), "{msg}");
        }
        let _ = std::fs::remove_file(&corrupt);
    }

    #[test]
    fn cancellation_removes_partial_output() {
        let dir = TempDir::new("cancel");
        let src = dir.path("m.safetensors");
        let znn = dir.path("m.znn.safetensors");
        write_st(
            &src,
            None,
            &[
                ("a", "BF16", vec![512, 256], bf16_bytes(512 * 256, 5)),
                ("b", "BF16", vec![512, 256], bf16_bytes(512 * 256, 6)),
            ],
        );
        let cancel = AtomicBool::new(true); // cancelled before the first tensor
        let progress = Progress::new(0);
        let hooks = Hooks {
            progress: Some(&progress),
            cancel: Some(&cancel),
        };
        let err = compress_file(&src, &znn, &JobOpts::default(), &hooks).unwrap_err();
        assert!(matches!(err, StError::Cancelled), "{err:?}");
        assert!(!znn.exists());
        assert!(
            !crate::safetensors_io::tmp_sibling(&znn).exists(),
            "tmp cleaned"
        );
        assert_eq!(progress.snapshot().2, Phase::Tensors);
    }

    #[test]
    fn hmax_fallback_rewrite_produces_valid_files() {
        let dir = TempDir::new("hmax");
        let src = dir.path("m.safetensors");
        let znn = dir.path("m.znn.safetensors");
        let back = dir.path("m.back.safetensors");
        let original = {
            write_st(&src, Some(&[meta("k", "v")]), &corpus());
            read(&src)
        };
        let hooks = Hooks::default();
        // force a too-small bound: the defensive rewrite path must still
        // produce a perfectly valid, byte-exact-restoring container
        let opts = JobOpts {
            hmax_slack: -64,
            ..JobOpts::default()
        };
        let out = compress_file(&src, &znn, &opts, &hooks).unwrap();
        assert!(out.exact);
        let out2 = decompress_file(&znn, &back, &JobOpts::default(), &hooks).unwrap();
        assert_eq!(out2.verified, Verified::Sha256);
        assert_eq!(read(&back), original);
        // and the rewritten header is canonical (no H_max padding any more)
        let (cst, _m) = StContainer::open(&znn).unwrap();
        assert!(
            !cst.canonical,
            "metadata differs from source (Neo keys) — but region is exact"
        );
        let _ = std::fs::metadata(crate::safetensors_io::tmp_sibling(&znn));
    }

    #[test]
    fn paranoid_mode_verifies_before_rename() {
        let dir = TempDir::new("paranoid");
        let src = dir.path("m.safetensors");
        let znn = dir.path("m.znn.safetensors");
        let original = {
            write_st(&src, None, &corpus());
            read(&src)
        };
        let hooks = Hooks::default();
        let opts = JobOpts {
            paranoid: true,
            ..JobOpts::default()
        };
        let out = compress_file(&src, &znn, &opts, &hooks).unwrap();
        assert!(out.exact);
        assert!(
            !dir.path("m.znn.safetensors.verify.tmp").exists(),
            "verify file cleaned"
        );
        // the artifact decompresses byte-exactly (paranoid already proved it)
        let back = dir.path("m.back.safetensors");
        decompress_file(&znn, &back, &JobOpts::default(), &hooks).unwrap();
        assert_eq!(read(&back), original);
    }

    #[test]
    fn legacy_style_files_without_neo_keys_skip_verification() {
        let dir = TempDir::new("legacy-file");
        // Build a "legacy/official" compressed file: infos + blobs but NO
        // znn_neo_src_sha256 / exact keys (as pip-zipnn or pre-Neo files).
        let src = dir.path("plain.safetensors");
        write_st(
            &src,
            None,
            &[("w", "BF16", vec![64, 32], bf16_bytes(64 * 32, 31))],
        );
        let (st, mmap) = StContainer::open(&src).unwrap();
        let scheme = scheme_for_st_dtype("BF16").unwrap();
        let data = st.data(&mmap, &st.tensors[0]).unwrap();
        let blob = compress_tensor(&scheme, data, &[64, 32], 0, None).unwrap();
        let infos = py_dumps_compressed_vectors(&[(
            "w".to_owned(),
            "bfloat16".to_owned(),
            "[64, 32]".to_owned(),
        )]);
        let znn = dir.path("plain.znn.safetensors");
        write_st(
            &znn,
            Some(&[(METADATA_KEY.to_owned(), infos)]),
            &[("w", "U8", vec![blob.len() as u64], blob)],
        );
        let back = dir.path("plain.back.safetensors");
        let hooks = Hooks::default();
        let out = decompress_file(&znn, &back, &JobOpts::default(), &hooks).unwrap();
        assert_eq!(out.verified, Verified::Skipped);
        assert!(out.warnings.iter().any(|w| w.contains("skipped")));
        assert_eq!(out.stats.decompressed_tensors, 1);
        // Official/legacy files carry NO record of whether the source had a
        // (possibly empty) __metadata__ map, so the restore follows the
        // legacy path's output: `"__metadata__":{}` is added. Tensor bytes
        // and every other semantic must match exactly.
        let (orig, omap) = StContainer::open(&src).unwrap();
        let (rest, rmap) = StContainer::open(&back).unwrap();
        assert_eq!(orig.tensors, rest.tensors);
        assert_eq!(
            orig.data(&omap, &orig.tensors[0]).unwrap(),
            rest.data(&rmap, &rest.tensors[0]).unwrap()
        );
        assert_eq!(rest.metadata.as_deref(), Some(&[][..]));
    }

    #[test]
    fn infos_blob_disagreements_are_errors() {
        let dir = TempDir::new("infos-bad");
        let src = dir.path("m.safetensors");
        write_st(
            &src,
            None,
            &[("w", "BF16", vec![64, 32], bf16_bytes(64 * 32, 41))],
        );
        let hooks = Hooks::default();
        let znn = dir.path("m.znn.safetensors");
        compress_file(&src, &znn, &JobOpts::default(), &hooks).unwrap();

        // rewrite the infos dtype to a wrong (but valid) value
        let patch = |mutate: &dyn Fn(&str) -> String, tag: &str| {
            let (st, mmap) = StContainer::open(&znn).unwrap();
            let mut meta: Vec<(String, String)> = st
                .metadata
                .clone()
                .unwrap()
                .into_iter()
                .map(|(k, v)| {
                    if k == METADATA_KEY {
                        (k, mutate(&v))
                    } else {
                        (k, v)
                    }
                })
                .collect();
            meta.sort_by(|a, b| a.0.cmp(&b.0));
            let _ = &mut meta;
            let entries: Vec<OutEntry> = st
                .tensors
                .iter()
                .map(|t| OutEntry {
                    name: &t.name,
                    dtype: &t.dtype,
                    shape: &t.shape,
                    start: t.start,
                    end: t.end,
                })
                .collect();
            let region = build_header_region(Some(&meta), &entries);
            let mut img = Vec::new();
            img.extend_from_slice(&(region.len() as u64).to_le_bytes());
            img.extend_from_slice(&region);
            let data_start = st.data_start;
            img.extend_from_slice(&mmap[data_start..]);
            let p = dir.path(tag);
            std::fs::write(&p, &img).unwrap();
            p
        };
        let bad_dtype = patch(
            &|v: &str| v.replace("bfloat16", "float16 "),
            "bad-dtype.znn.safetensors",
        );
        let back = dir.path("x.back.safetensors");
        let err = decompress_file(&bad_dtype, &back, &JobOpts::default(), &hooks).unwrap_err();
        assert!(err.to_string().contains("dtype"), "{err}");

        let bad_shape = patch(
            &|v: &str| v.replace("[64, 32]", "[64, 31]").to_owned(),
            "bad-shape.znn.safetensors",
        );
        let err = decompress_file(&bad_shape, &back, &JobOpts::default(), &hooks).unwrap_err();
        assert!(err.to_string().contains("shape"), "{err}");

        // malformed infos JSON
        let bad_json = patch(&|_: &str| "{oops".to_owned(), "bad-json.znn.safetensors");
        let err = decompress_file(&bad_json, &back, &JobOpts::default(), &hooks).unwrap_err();
        assert!(err.to_string().contains(METADATA_KEY), "{err}");
        assert!(!back.exists());
    }

    #[test]
    fn verify_opt_out_skips_the_check() {
        let dir = TempDir::new("verify-off");
        let src = dir.path("m.safetensors");
        write_st(&src, Some(&[meta("format", "pt")]), &corpus());
        let znn = dir.path("m.znn.safetensors");
        let hooks = Hooks::default();
        compress_file(&src, &znn, &JobOpts::default(), &hooks).unwrap();
        // default (verify ON) -> sha256
        let back = dir.path("m.v1.back.safetensors");
        let out = decompress_file(&znn, &back, &JobOpts::default(), &hooks).unwrap();
        assert_eq!(out.verified, Verified::Sha256);
        // verify=false -> skipped WITH an honest warning
        let back2 = dir.path("m.v0.back.safetensors");
        let opts = JobOpts {
            verify: false,
            ..JobOpts::default()
        };
        let out = decompress_file(&znn, &back2, &opts, &hooks).unwrap();
        assert_eq!(out.verified, Verified::Skipped);
        assert!(out.warnings.iter().any(|w| w.contains("disabled via opts")));
        assert_eq!(read(&back), read(&back2), "same bytes either way");
    }

    #[test]
    fn destination_exists_is_refused() {
        let dir = TempDir::new("dst-exists");
        let src = dir.path("m.safetensors");
        write_st(&src, None, &[("w", "BF16", vec![8], bf16_bytes(8, 1))]);
        let znn = dir.path("m.znn.safetensors");
        std::fs::write(&znn, b"sentinel").unwrap();
        let hooks = Hooks::default();
        let err = compress_file(&src, &znn, &JobOpts::default(), &hooks).unwrap_err();
        assert!(err.to_string().contains("already exists"));
        assert_eq!(read(&znn), b"sentinel", "never touched");
    }

    #[test]
    fn recompressing_a_restored_file_never_doubles_neo_keys() {
        let dir = TempDir::new("recompress");
        let src = dir.path("m.safetensors");
        let original = {
            write_st(&src, Some(&[meta("format", "pt")]), &corpus());
            read(&src)
        };
        let hooks = Hooks::default();
        let znn = dir.path("m.znn.safetensors");
        compress_file(&src, &znn, &JobOpts::default(), &hooks).unwrap();
        let back = dir.path("m.back.safetensors");
        decompress_file(&znn, &back, &JobOpts::default(), &hooks).unwrap();
        // compress the RESTORED file again
        let znn2 = dir.path("m2.znn.safetensors");
        let out = compress_file(&back, &znn2, &JobOpts::default(), &hooks).unwrap();
        assert!(out.exact);
        let (cst, _m) = StContainer::open(&znn2).unwrap();
        let cmeta = cst.metadata.clone().unwrap();
        let count = |k: &str| cmeta.iter().filter(|(mk, _)| mk == k).count();
        for k in BOOKKEEPING_KEYS {
            assert!(count(k) <= 1, "{k} appears {} times", count(k));
        }
        assert_eq!(count("format"), 1, "source metadata survived both cycles");
        // and it still restores byte-exactly
        let back2 = dir.path("m2.back.safetensors");
        let out2 = decompress_file(&znn2, &back2, &JobOpts::default(), &hooks).unwrap();
        assert_eq!(out2.verified, Verified::Sha256);
        assert_eq!(read(&back2), original);
    }
}
