//! Phase 6 bindings — the display tensor tree + the optional library watcher
//! (Plan §4.7.3 "テンソルツリー事前グループ化", §4.7.2‑2 `watch_roots`).
//!
//! Both surfaces follow the crate's boundary rules (Plan §4.2.2): paths and
//! JSON strings cross the boundary (never buffers), long or blocking work runs
//! with the GIL released, and nothing calls back into Python — the watcher is
//! **polled** (`watch_poll`) from the Python asyncio task, exactly like the
//! compression jobs' progress atomics.

use std::path::PathBuf;
use std::time::Duration;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

/// The B4-unified safetensors header cap (32 MiB) — the tree is built from the
/// same header parse as `safetensors_header`, so it enforces the same cap.
const HEADER_CAP: u64 = 32 * 1024 * 1024;

/// The display tensor tree of a safetensors file, pre-grouped in Rust
/// (`{"v":1,"nodes":[[segment,childCount,tensorCount,totalCount,totalParams],…],
/// "leaves":[tensorIndex,…]}` — pre-order, root first; the leaf indices address
/// the `tensors` array of `safetensors_header` for the SAME file).
///
/// Synchronous; the GIL is released for the read + parse + fold (an 8 MB MoE
/// header with ~65k tensors is the workload this exists for — the frontend used
/// to spend ~0.7 s folding it in JS, Plan §4.7.3 / BENCH §11).
///
/// # Errors
/// The same failures as `safetensors_header` (unreadable / oversized /
/// truncated / invalid header) — the Python caller degrades to the frontend's
/// own JS grouping.
pub fn safetensors_tensor_tree(py: Python<'_>, path: &str) -> PyResult<String> {
    let path = PathBuf::from(path);
    py.detach(move || {
        znn_codec::safetensors_io::tensor_tree_json(&path, HEADER_CAP)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    })
}

/// Start watching `roots` recursively; returns the session handle.
///
/// `opts` (all optional): `debounceMs` (default 500 — Plan §4.7.2‑2). A root
/// that does not exist is skipped and reported in the session's `errors` (a
/// model volume that is not mounted yet must not fail the whole watcher); a
/// watch-budget exhaustion marks the session `degraded`, which is how the
/// Python side learns to fall back to the TTL refresh.
///
/// The GIL is held only for the argument conversion: arming inotify watches
/// walks the directory tree, so it runs detached.
///
/// # Errors
/// A watcher that cannot be created at all (no backend).
pub fn watch_start(
    py: Python<'_>,
    roots: Vec<String>,
    opts: Option<&Bound<'_, PyDict>>,
) -> PyResult<u64> {
    let roots: Vec<PathBuf> = roots.into_iter().map(PathBuf::from).collect();
    let debounce_ms = opts
        .and_then(|d| d.get_item("debounceMs").ok().flatten())
        .and_then(|v| v.extract::<u64>().ok());
    let debounce = debounce_ms.map(Duration::from_millis);
    py.detach(move || {
        znn_codec::watch::watch_start(&roots, debounce).map_err(PyRuntimeError::new_err)
    })
}

/// Drain one session's pending changes as JSON:
/// `{"paths":[…],"rescan":bool,"degraded":string|null,"stopped":bool,
/// "roots":n,"watched":n,"ageMs":n,"errors":[…]}`.
///
/// Cheap (a mutex swap + a small JSON build) and non-blocking, so the Python
/// task can poll it every few hundred milliseconds without an executor.
///
/// # Errors
/// An unknown handle.
pub fn watch_poll(handle: u64) -> PyResult<String> {
    znn_codec::watch::watch_poll(handle).map_err(PyRuntimeError::new_err)
}

/// Stop a session and drop it (idempotent at the Python level: an unknown
/// handle raises, a second stop of the same handle therefore does too — the
/// caller treats that as "already stopped").
///
/// # Errors
/// An unknown handle.
pub fn watch_stop(handle: u64) -> PyResult<()> {
    znn_codec::watch::watch_stop(handle).map_err(PyRuntimeError::new_err)
}

/// Diagnostics for the settings/about surface: `{"sessions": n,
/// "watchedRoots": n, "inotifyBudget": n|null}` (never raises).
pub fn watch_diagnostics(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let out = PyDict::new(py);
    for (key, value) in znn_codec::watch::watch_diagnostics() {
        out.set_item(key, value)?;
    }
    out.set_item("inotifyBudget", znn_codec::watch::inotify_budget())?;
    Ok(out)
}
