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
//! * Phase 3–5 — delta, dtype extension, scan / index / hash.
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
const API_VERSION: u32 = 3;

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
/// Phase 3 the delta jobs + batch primitives; the dtype extension and the
/// scan/hash APIs follow in the later phases of the refresh plan
/// (Agent/Plan.md).
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
    /// order. Synchronous — routes call it from executors.
    #[pyfunction]
    #[pyo3(signature = (root, opts=None))]
    fn walk_models(root: &str, opts: Option<&Bound<'_, PyDict>>) -> PyResult<String> {
        super::jobs::walk_models(root, opts)
    }

    /// Move every sidecar of `src` (previews + notes) beside `dst`.
    /// Synchronous; the model file itself is NOT moved.
    #[pyfunction]
    fn move_with_sidecars(src: &str, dst: &str) -> PyResult<()> {
        super::jobs::move_with_sidecars(src, dst)
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
        assert_eq!(super::API_VERSION, 3);
    }
}
