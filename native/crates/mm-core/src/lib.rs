//! `mm_core` — the PyO3 extension module of ComfyUI-Model-Manager-Neo
//! (Plan §4.2).
//!
//! API surface by phase (Plan §4.2.2):
//!
//! * Phase 0 — availability/version handshake (`api_version`, `core_version`),
//! * **Phase 2 — the ZipNN safetensors jobs**: `zipnn_compress` /
//!   `zipnn_decompress` (async, polling-based: `job_progress` /
//!   `job_cancel` / `job_result` / `job_error`) with the end-to-end
//!   integrity pipeline of Plan §4.4.3 (source sha recording, default-ON
//!   verification, `.corrupt` retreat, paranoid mode),
//! * Phase 3 — the delta jobs + batch primitives (`api_version` 3),
//! * Phase 4 — NO surface change: the dtype extension (all 22 safetensors
//!   dtypes, Neo band 128–146) lives inside `znn-codec`; the `api_version`
//!   stays 3 (the `/zipnn/inspect` route is pure Python),
//! * Phase 5 — scan / index / hash.
//!
//! Binding facts (Plan §3.2, §3.3):
//!
//! * **abi3-py310**: one binary per platform covers CPython 3.10 and newer,
//! * long-running APIs never hold the GIL — jobs run on dedicated Rust
//!   threads and the Python side polls atomics (Plan §4.3),
//! * `panic = "unwind"` (workspace release profile): panics are caught at the
//!   PyO3 boundary — and inside job threads via `catch_unwind` — and surface
//!   as Python exceptions / job errors, never `abort`, which would kill the
//!   whole ComfyUI process,
//! * large payloads cross the boundary as **paths**, not buffers (Plan §4.3).

// The native core keeps the crate unsafe-free (the single reviewed `unsafe`
// of the workspace lives in znn-codec's mmap boundary, documented there).
#![deny(unsafe_code)]

use pyo3::prelude::*;

mod jobs;
mod phase5;

/// Version of the Python-facing API surface (Plan §4.2.2 `api_version()`).
/// Bumped whenever the surface changes incompatibly; `py/native.py` checks it
/// after import.
///
/// * 1 — Phase 0: version handshake only,
/// * 2 — Phase 2: the ZipNN safetensors job API (compress/decompress +
///   progress/cancel/result/error). `py/compress.py` calls these directly,
///   so a v1 binary must NOT pass the loader handshake of a v2 backend.
/// * 3 — Phase 3: the delta jobs (`zipnn_delta_compress` /
///   `zipnn_delta_decompress`) + the batch primitives (`walk_models` /
///   `move_with_sidecars`). The delta routes call these directly, so a v2
///   binary must NOT pass the loader handshake of a v3 backend (exact-range
///   check in `py/native.py`).
/// * 4 — Phase 5: the scan / hygiene / header / hash surface (`scan_models`,
///   `scan_hygiene`, `safetensors_header`, `hash_file`, `hasher_new` /
///   `hasher_update` / `hasher_finalize`) + the persistent front-matter index.
///   `py/manager.py` / `py/utils.py` / `py/identify.py` / `py/download.py` call
///   these directly, so a v3 binary must NOT pass the loader handshake of a v4
///   backend (exact-range check in `py/native.py`).
const API_VERSION: u32 = 4;

/// `"x.y.z+commit"` — the crate version plus the git commit the binary was
/// built from (embedded by `build.rs`, Plan §4.2.2 `core_version()`).
fn core_version_string() -> String {
    format!(
        "{}+{}",
        env!("CARGO_PKG_VERSION"),
        env!("MM_CORE_COMMIT_HASH")
    )
}

/// The native core of ComfyUI-Model-Manager-Neo.
///
/// Built with the CPython Stable ABI (abi3-py310): this single binary serves
/// CPython 3.10 and newer. Phase 2 exposed the ZipNN safetensors jobs,
/// Phase 3 the delta jobs + batch primitives; Phase 4 extended the dtype
/// coverage INSIDE the codec (no new functions — `api_version` stayed 3);
/// Phase 5 (`api_version` 4) adds the scan / hygiene / safetensors-header /
/// hash surface (`scan_models`, `scan_hygiene`, `safetensors_header`,
/// `hash_file`, `hasher_new`/`update`/`finalize`) + the persistent front-matter
/// index (the later phases of the refresh plan, Agent/Plan.md).
#[pymodule]
mod mm_core {
    use pyo3::prelude::*;
    use pyo3::types::PyDict;

    #[pyfunction]
    fn api_version() -> u32 {
        super::API_VERSION
    }

    #[pyfunction]
    fn core_version() -> String {
        super::core_version_string()
    }

    /// Compress `src` (.safetensors) into `dst` (.znn.safetensors) as an
    /// async job; returns the handle. `opts` (all optional): `threads`
    /// (0 = auto), `paranoid` (bool — re-decode + verify before rename).
    #[pyfunction]
    #[pyo3(signature = (src, dst, opts=None))]
    fn zipnn_compress(src: &str, dst: &str, opts: Option<&Bound<'_, PyDict>>) -> u64 {
        super::jobs::zipnn_compress(src, dst, opts)
    }

    /// Decompress `src` (.znn.safetensors) into `dst` (.safetensors) as an
    /// async job; returns the handle. `opts`: `threads`.
    #[pyfunction]
    #[pyo3(signature = (src, dst, opts=None))]
    fn zipnn_decompress(src: &str, dst: &str, opts: Option<&Bound<'_, PyDict>>) -> u64 {
        super::jobs::zipnn_decompress(src, dst, opts)
    }

    /// Delta-compress `ft` against `base` into `out` (+ `.neo-delta.json`
    /// sidecar with `ftSha256`) as an async job; returns the handle.
    /// `opts`: `threads`, `paranoid` (re-decode + verify before rename).
    #[pyfunction]
    #[pyo3(signature = (base, ft, out, opts=None))]
    fn zipnn_delta_compress(
        base: &str,
        ft: &str,
        out: &str,
        opts: Option<&Bound<'_, PyDict>>,
    ) -> u64 {
        super::jobs::zipnn_delta_compress(base, ft, out, opts)
    }

    /// Restore the fine-tune from `base` + `delta` into `out` as an async
    /// job; returns the handle. `meta` is the parsed sidecar dict
    /// (`basePad`/`ftPad`/`ftSha256` — missing keys degrade like the legacy
    /// reader); `opts`: `threads`, `verify` (default true).
    #[pyfunction]
    #[pyo3(signature = (base, delta, out, meta=None, opts=None))]
    fn zipnn_delta_decompress(
        base: &str,
        delta: &str,
        out: &str,
        meta: Option<&Bound<'_, PyDict>>,
        opts: Option<&Bound<'_, PyDict>>,
    ) -> u64 {
        super::jobs::zipnn_delta_decompress(base, delta, out, meta, opts)
    }

    /// The parallel batch walk (`mode`: "compress"/"decompress"/
    /// "blockers"); returns a JSON array of paths in the legacy sorted
    /// order. Synchronous — routes call it from executors — with the GIL
    /// released for the walk itself (Plan §4.2.2 invariant 2).
    #[pyfunction]
    #[pyo3(signature = (root, opts=None))]
    fn walk_models(
        py: Python<'_>,
        root: &str,
        opts: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<String> {
        super::jobs::walk_models(py, root, opts)
    }

    /// Move every sidecar of `src` (previews + notes) beside `dst`.
    /// Synchronous (GIL released); the model file itself is NOT moved.
    #[pyfunction]
    fn move_with_sidecars(py: Python<'_>, src: &str, dst: &str) -> PyResult<()> {
        super::jobs::move_with_sidecars(py, src, dst)
    }

    /// Scan one model type into the listing JSON (the `GET /models/{folder}`
    /// body). `roots` are the type's base folders (pathIndex order); `opts`:
    /// `includeHidden`, `extensions`, `noPreviewUrl`, `previewUrlPrefix`,
    /// `indexDir`. Synchronous — the GIL is released for the parallel walk
    /// (Plan §4.2.2 invariant 2).
    #[pyfunction]
    #[pyo3(signature = (model_type, roots, opts=None))]
    fn scan_models(
        py: Python<'_>,
        model_type: &str,
        roots: Vec<String>,
        opts: Option<&Bound<'_, PyDict>>,
    ) -> String {
        super::phase5::scan_models(py, model_type, roots, opts)
    }

    /// The local hygiene report (orphaned sidecars + empty folders) as JSON.
    /// `base_paths` is `resolve_model_base_paths()` (ordered `{type: [roots]}`),
    /// `extensions` is `supported_pt_extensions`. Synchronous (GIL released).
    #[pyfunction]
    #[pyo3(signature = (base_paths, extensions))]
    fn scan_hygiene(
        py: Python<'_>,
        base_paths: &Bound<'_, PyDict>,
        extensions: Vec<String>,
    ) -> PyResult<String> {
        super::phase5::scan_hygiene(py, base_paths, extensions)
    }

    /// The digested safetensors header (`{"metadata": {…}, "tensors": […]}`)
    /// for the model-detail display (Plan §4.7.3 / B4). Header-only, jiter,
    /// 32 MiB cap. Synchronous (GIL released). Raises on a non-safetensors /
    /// unreadable / oversized header (the caller degrades to `{}`/`[]`).
    #[pyfunction]
    fn safetensors_header(py: Python<'_>, path: &str) -> PyResult<String> {
        super::phase5::safetensors_header(py, path)
    }

    /// Hash a whole file in one pass; returns the requested notations as a JSON
    /// object (SHA256 / AutoV2 / AutoV1 / CRC32 / BLAKE3 — Plan §4.8‑B2, K8).
    /// `algos` defaults to all five. Synchronous (GIL released for the read).
    #[pyfunction]
    #[pyo3(signature = (path, algos=None))]
    fn hash_file(py: Python<'_>, path: &str, algos: Option<Vec<String>>) -> PyResult<String> {
        super::phase5::hash_file(py, path, algos)
    }

    /// Start an incremental hasher (download inline verification, Plan
    /// §4.8‑B1 / K7); returns its handle. Feed it each written chunk with
    /// `hasher_update`, then `hasher_finalize` for the digest JSON.
    #[pyfunction]
    #[pyo3(signature = (algos=None))]
    fn hasher_new(algos: Option<Vec<String>>) -> u64 {
        super::phase5::hasher_new(algos)
    }

    /// Feed the next chunk (borrowed zero-copy) to a hasher handle.
    #[pyfunction]
    fn hasher_update(handle: u64, chunk: &[u8]) -> PyResult<()> {
        super::phase5::hasher_update(handle, chunk)
    }

    /// Finalise + remove a hasher handle; returns the digest JSON.
    #[pyfunction]
    fn hasher_finalize(handle: u64) -> PyResult<String> {
        super::phase5::hasher_finalize(handle)
    }

    /// Phase 5 diagnostics: `{"indexDirs": n, "liveHashers": n}` (the
    /// settings/about surface and bug reports).
    #[pyfunction]
    fn phase5_diagnostics() -> std::collections::HashMap<&'static str, usize> {
        super::phase5::phase5_diagnostics()
    }

    /// `(done, total, phase)` of a job; phase ∈ {prepare, tensors, write,
    /// verify, delta, done, failed} — `done`/`failed` are terminal.
    #[pyfunction]
    fn job_progress(handle: u64) -> PyResult<(u64, u64, String)> {
        super::jobs::job_progress(handle)
    }

    /// Request cooperative cancellation; True when the job was still running.
    #[pyfunction]
    fn job_cancel(handle: u64) -> PyResult<bool> {
        super::jobs::job_cancel(handle)
    }

    /// Completion-stats JSON (`{"stats": …, "verified": …, "warnings": […]}`)
    /// — raises `RuntimeError` while the job is running or if it failed.
    #[pyfunction]
    fn job_result(handle: u64) -> PyResult<String> {
        super::jobs::job_result(handle)
    }

    /// The failure message of a finished job; None while running or on success.
    #[pyfunction]
    fn job_error(handle: u64) -> PyResult<Option<String>> {
        super::jobs::job_error(handle)
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn core_version_carries_the_commit_suffix() {
        let version = super::core_version_string();
        assert!(version.starts_with(env!("CARGO_PKG_VERSION")));
        let (_, commit) = version.split_once('+').expect("x.y.z+commit");
        assert!(!commit.is_empty());
    }

    #[test]
    fn api_version_matches_the_loader_contract() {
        // py/native.py pins MIN_API_VERSION..MAX_API_VERSION — keep the two
        // sides in lockstep (the loader test suite asserts the same range).
        assert_eq!(super::API_VERSION, 4);
    }
}
