//! Phase 5 bindings — scan / hygiene / safetensors header / hashing
//! (Plan §4.2.2, §4.7, §4.8‑B1/B2).
//!
//! These are SYNCHRONOUS, GIL-released calls (like `walk_models`): the routes
//! run them inside executors, and releasing the GIL keeps the ComfyUI event
//! loop responsive during a multi-thousand-file walk or a multi-gigabyte hash
//! (Plan §4.2.2 invariant 2 — a held GIL would freeze the websocket progress
//! stream for the whole operation, the exact class of bug Quick Win A1 and the
//! Phase-3 `walk_models` GIL fix removed).
//!
//! Two process-wide registries live here:
//! * the persistent front-matter [`SiteIndex`] (one per index directory, shared
//!   across every `scan_models` call so the cache survives both the per-type
//!   scans of one refresh and process restarts — Plan §4.7.1‑3);
//! * the incremental hashers (`hasher_new`/`update`/`finalize`) the download
//!   loop feeds chunk by chunk for inline Civitai verification (Plan §4.8‑B1,
//!   K7 — the finished download's SHA256 is known without a full re-read).

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use pyo3::exceptions::{PyKeyError, PyRuntimeError};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use znn_codec::hash::MultiHasher;
use znn_codec::index::SiteIndex;
use znn_codec::scan::{HygieneOpts, ScanOpts};

/// The B4-unified safetensors header cap (32 MiB) — `get_model_metadata` and
/// `get_model_tensors` both used to guard at different sizes (1 MiB silently
/// emptied large MoE `__metadata__`; 32 MiB for tensors). One cap now.
const HEADER_CAP: u64 = 32 * 1024 * 1024;

// ---------------------------------------------------------------------------
// Persistent front-matter index registry (one SiteIndex per directory).
// ---------------------------------------------------------------------------

fn index_registry() -> &'static Mutex<HashMap<PathBuf, Arc<SiteIndex>>> {
    static REG: OnceLock<Mutex<HashMap<PathBuf, Arc<SiteIndex>>>> = OnceLock::new();
    REG.get_or_init(|| Mutex::new(HashMap::new()))
}

/// The shared index for `dir` (created + loaded on first use). The scan updates
/// it in place and saves it (a no-op when clean), so the cache is warm for the
/// next refresh AND the next process (Plan §4.7.1‑3).
fn index_for(dir: &Path) -> Arc<SiteIndex> {
    let key = dir.to_path_buf();
    let mut reg = index_registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    reg.entry(key.clone())
        .or_insert_with(|| Arc::new(SiteIndex::open(Some(&key))))
        .clone()
}

// ---------------------------------------------------------------------------
// Incremental hasher registry (download inline verification).
// ---------------------------------------------------------------------------

/// A hasher handle → the streaming hasher. Bounded: an abandoned download that
/// never finalises would otherwise leak its (small) hasher state, so the
/// registry evicts the oldest handles past a cap (the download flow is the only
/// user and finalises promptly; the cap is pure insurance).
const MAX_HASHERS: usize = 4096;

fn hasher_registry() -> &'static Mutex<HashMap<u64, MultiHasher>> {
    static REG: OnceLock<Mutex<HashMap<u64, MultiHasher>>> = OnceLock::new();
    REG.get_or_init(|| Mutex::new(HashMap::new()))
}

static NEXT_HASHER: AtomicU64 = AtomicU64::new(1);

// ---------------------------------------------------------------------------
// Python-facing functions (wired into the #[pymodule] in lib.rs).
// ---------------------------------------------------------------------------

/// Scan one model type into the listing JSON (the `GET /models/{folder}` body).
///
/// `model_type` is the type name; `roots` are its base folders (in `pathIndex`
/// order). `opts`: `includeHidden` (bool), `extensions` (list[str] —
/// `folder_paths.supported_pt_extensions`), `noPreviewUrl` (str),
/// `previewUrlPrefix` (str), `indexDir` (str, optional — enables the persistent
/// front-matter cache). Synchronous; the GIL is released for the walk.
///
/// # Errors
/// None — every `opts` field degrades to a default, and the walk cannot fail
/// (an unreadable directory is skipped, a vanished entry dropped), so this
/// returns the JSON directly (clippy `unnecessary_wraps`: no `Err` arm exists).
pub fn scan_models(
    py: Python<'_>,
    model_type: &str,
    roots: Vec<String>,
    opts: Option<&Bound<'_, PyDict>>,
) -> String {
    let get_bool = |k: &str| -> bool {
        opts.and_then(|d| d.get_item(k).ok().flatten())
            .and_then(|v| v.extract::<bool>().ok())
            .unwrap_or(false)
    };
    let get_str = |k: &str| -> String {
        opts.and_then(|d| d.get_item(k).ok().flatten())
            .and_then(|v| v.extract::<String>().ok())
            .unwrap_or_default()
    };
    let extensions: HashSet<String> = opts
        .and_then(|d| d.get_item("extensions").ok().flatten())
        .and_then(|v| v.extract::<Vec<String>>().ok())
        .unwrap_or_default()
        .into_iter()
        .collect();
    let include_hidden = get_bool("includeHidden");
    let no_preview_url = get_str("noPreviewUrl");
    let preview_url_prefix = get_str("previewUrlPrefix");
    let index_dir = get_str("indexDir");

    let model_type = model_type.to_owned();
    let roots: Vec<PathBuf> = roots.into_iter().map(PathBuf::from).collect();

    // The index must be resolved (and its Arc cloned) BEFORE detaching: the
    // registry lock is a plain std Mutex, safe to touch GIL-free, but grabbing
    // the Arc here keeps the detach closure free of any Python borrow.
    let index = if index_dir.is_empty() {
        None
    } else {
        Some(index_for(Path::new(&index_dir)))
    };

    py.detach(move || {
        let scan_opts = ScanOpts {
            model_type,
            roots,
            include_hidden,
            extensions,
            no_preview_url,
            preview_url_prefix,
            index: index.clone(),
        };
        let out = znn_codec::scan::scan_models(&scan_opts);
        // Persist the front-matter cache (a no-op when nothing changed). A save
        // failure is an optimisation loss, never a scan failure — log via the
        // returned value's success, so swallow it here (the index stays usable
        // in memory this process).
        if let Some(idx) = &index {
            let _ = idx.save();
        }
        out
    })
}

/// The local hygiene report (orphaned sidecars + empty folders) as JSON — the
/// `GET /model-manager/hygiene` body. `base_paths` is
/// `resolve_model_base_paths()` as an ordered `{type: [roots]}`; `extensions` is
/// `supported_pt_extensions`. Synchronous; the GIL is released for the walk.
///
/// # Errors
/// A `base_paths` shape the caller must fix.
pub fn scan_hygiene(
    py: Python<'_>,
    base_paths: &Bound<'_, PyDict>,
    extensions: Vec<String>,
) -> PyResult<String> {
    // Extract the ordered {type: [paths]} while holding the GIL (PyDict
    // iteration preserves insertion order, matching folder_names_and_paths).
    let mut ordered: Vec<(String, Vec<PathBuf>)> = Vec::new();
    for (k, v) in base_paths.iter() {
        let name: String = k.extract()?;
        let paths: Vec<String> = v.extract()?;
        ordered.push((name, paths.into_iter().map(PathBuf::from).collect()));
    }
    let extensions: HashSet<String> = extensions.into_iter().collect();
    let json = py.detach(move || {
        let opts = HygieneOpts {
            base_paths: ordered,
            extensions,
        };
        znn_codec::scan::scan_hygiene(&opts)
    });
    Ok(json)
}

/// The digested safetensors header (`{"metadata": {…}, "tensors": […]}`) for
/// the model-detail display functions (Plan §4.7.3 / B4). Header-only (no data
/// validation), jiter-parsed (K11), 32 MiB cap. Synchronous; the GIL is
/// released for the read+parse.
///
/// # Errors
/// A file that is not a readable safetensors header (the Python caller turns
/// this into `{}`/`[]`, matching the legacy `safetensors_header(...) is None`).
pub fn safetensors_header(py: Python<'_>, path: &str) -> PyResult<String> {
    let path = PathBuf::from(path);
    py.detach(move || {
        znn_codec::safetensors_io::header_display_json(&path, HEADER_CAP)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    })
}

/// Hash a whole file in one pass; returns the requested notations as a JSON
/// object (`{"SHA256": "…", "AutoV2": …, "AutoV1": …, "CRC32": …,
/// "BLAKE3": …}` — only the requested ones). `algos` defaults to the four
/// Civitai notations identify needs. Synchronous; the GIL is released for the
/// read (K8: 5 notations, one pass).
///
/// # Errors
/// A file that cannot be read.
pub fn hash_file(py: Python<'_>, path: &str, algos: Option<Vec<String>>) -> PyResult<String> {
    let path = PathBuf::from(path);
    let algos = algos.unwrap_or_else(|| {
        ["SHA256", "AutoV2", "AutoV1", "CRC32", "BLAKE3"]
            .iter()
            .map(|s| (*s).to_owned())
            .collect()
    });
    let map = py.detach(move || {
        znn_codec::hash::hash_file(&path, &algos)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    })?;
    // A BTreeMap serialises as a JSON OBJECT with deterministic (sorted) keys
    // — the Python side json.loads it back into a dict (key order is irrelevant
    // there, but sorted bytes are stable for any raw comparison).
    let ordered: std::collections::BTreeMap<&String, &String> = map.iter().collect();
    serde_json::to_string(&ordered)
        .map_err(|e| PyRuntimeError::new_err(format!("hash result does not serialise: {e}")))
}

/// Start an incremental hasher for `algos`; returns its handle. The download
/// loop feeds it each written chunk (`hasher_update`) and finalises at the end
/// (`hasher_finalize`) — the inline Civitai verification of Plan §4.8‑B1 (K7:
/// no full re-read of a finished download).
///
/// # Errors
/// None — the registry evicts past its cap rather than refusing a handle, so
/// this always succeeds (clippy `unnecessary_wraps`: no `Err` arm exists).
pub fn hasher_new(algos: Option<Vec<String>>) -> u64 {
    let algos = algos.unwrap_or_else(|| vec!["SHA256".to_owned()]);
    let hasher = MultiHasher::new(&algos);
    let id = NEXT_HASHER.fetch_add(1, Ordering::Relaxed);
    let mut reg = hasher_registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    // Evict the oldest handles past the cap (insurance against abandoned
    // downloads that never finalise).
    while reg.len() >= MAX_HASHERS {
        let oldest = reg.keys().min().copied();
        match oldest {
            Some(k) => {
                reg.remove(&k);
            }
            None => break,
        }
    }
    reg.insert(id, hasher);
    id
}

/// Feed the next chunk (in file order) to a hasher. The chunk is borrowed as
/// `&[u8]` (a `PyBytes` crosses the boundary zero-copy — Plan §4.2.2). Fast
/// enough to run under the GIL (the download loop holds it per chunk anyway).
///
/// # Errors
/// An unknown handle.
pub fn hasher_update(handle: u64, chunk: &[u8]) -> PyResult<()> {
    let mut reg = hasher_registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    let hasher = reg
        .get_mut(&handle)
        .ok_or_else(|| PyKeyError::new_err(format!("unknown hasher handle {handle}")))?;
    hasher.update(chunk);
    Ok(())
}

/// Finalise a hasher and remove it; returns the notations as a JSON object
/// (same shape as `hash_file`).
///
/// # Errors
/// An unknown handle.
pub fn hasher_finalize(handle: u64) -> PyResult<String> {
    let hasher = {
        let mut reg = hasher_registry()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        reg.remove(&handle)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown hasher handle {handle}")))?
    };
    let map = hasher.finalize();
    let ordered: std::collections::BTreeMap<&String, &String> = map.iter().collect();
    serde_json::to_string(&ordered)
        .map_err(|e| PyRuntimeError::new_err(format!("hash result does not serialise: {e}")))
}

/// Diagnostics for the settings/about surface: the index entry count and the
/// live hasher count (never raises).
pub fn phase5_diagnostics() -> HashMap<&'static str, usize> {
    let indexes = index_registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    let hashers = hasher_registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    let mut out = HashMap::new();
    out.insert("indexDirs", indexes.len());
    out.insert("liveHashers", hashers.len());
    out
}
