//! `mm_core` — the PyO3 extension module of ComfyUI-Model-Manager-Neo
//! (Plan §4.2).
//!
//! Phase 0 (Plan §6.2) provides only the availability/version surface of the
//! Python API (Plan §4.2.2); the compression, scan and hash APIs land in the
//! later phases:
//!
//! * Phase 1 — `znn-codec` format core (pure Rust, no Python dependency),
//! * Phase 2 — `zipnn_compress` / `zipnn_decompress` async jobs + the
//!   `py/compress.py` switchover,
//! * Phase 3–5 — delta, dtype extension, scan / index / hash.
//!
//! Binding facts (Plan §3.2, §3.3):
//!
//! * **abi3-py310**: one binary per platform covers CPython 3.10 and newer,
//! * long-running APIs release the GIL via `py.allow_threads()` (Phase 2+),
//! * `panic = "unwind"` (workspace release profile): panics are caught at the
//!   PyO3 boundary and surface as Python exceptions — never `abort`, which
//!   would kill the whole ComfyUI process,
//! * large payloads cross the boundary as **paths**, not buffers (Plan §4.3).

// Phase 0 needs no `unsafe` at all; keep it denied so any future introduction
// is a conscious, reviewed change (with `// SAFETY:` comments, Plan §3.4.2).
#![deny(unsafe_code)]

use pyo3::prelude::*;

/// Version of the Python-facing API surface (Plan §4.2.2 `api_version()`).
/// Bumped whenever the surface changes incompatibly; `py/native.py` checks it
/// after import.
const API_VERSION: u32 = 1;

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
/// CPython 3.10 and newer. Phase 0 exposes only the availability/version
/// surface; the ZipNN compression, scan and hash APIs follow in the later
/// phases of the refresh plan (Agent/Plan.md).
#[pymodule]
mod mm_core {
    use pyo3::prelude::*;

    #[pyfunction]
    fn api_version() -> u32 {
        super::API_VERSION
    }

    #[pyfunction]
    fn core_version() -> String {
        super::core_version_string()
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
}
