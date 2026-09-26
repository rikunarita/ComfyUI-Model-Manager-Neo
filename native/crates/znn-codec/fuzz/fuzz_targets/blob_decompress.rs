//! L3 fuzz target 5/5: per-tensor ZN BLOB decoding (`znn_tensor` — the
//! Phase-2 surface for hostile `.znn.safetensors` payloads, Plan §4.4.2).
//! Exercises: the ZN header parse (version gate, magic, method, lossy,
//! input_format), the packed-shape decode, the dtype-code table (compat
//! band + explicit Phase-4 refusals), the shape×elem == original_len
//! consistency check, the ALLOCATION CAP (a consistent-lie header declaring
//! terabytes must error, never OOM), and the codec payload validation
//! through `combine_dtype_into`. Threads are pinned to 1 (no pool churn per
//! iteration). Every path must return Err — never panic, never hang.
//!
//! The output buffer is a thread_local grow-only Vec — the same reuse
//! pattern the pipeline uses for K1 (see `pipeline.rs` / MEMO 2026-09-25).
//!
//! Root cause of the 2026-09-25 fuzz-long OOMs (runs 36088280583 AND the
//! re-run 36114455354, which still grew ~35 B/exec with a live heap of only
//! ~25 MB): `threads = 1` differs from the runner's `default_threads()`, so
//! `codec::with_threads` used to BUILD AND DESTROY a fresh rayon pool on
//! EVERY exec — one OS thread created/torn down per exec, whose sanitizer/
//! runtime metadata accumulates for the process lifetime. Not a memory-safety
//! bug; an artifact of per-call thread churn. `codec.rs` now caches one pool
//! per explicit thread count (regression test
//! `explicit_thread_counts_reuse_cached_pools`), so `threads = 1` here is a
//! stationary single worker and RSS stays flat.
#![no_main]

use libfuzzer_sys::fuzz_target;
use std::cell::RefCell;
use znn_codec::znn_tensor::{decompress_tensor_into, inspect_tensor};

thread_local! {
    /// Grow-only decode buffer (cleared+resized inside `decompress_tensor_into`).
    static OUT: RefCell<Vec<u8>> = const { RefCell::new(Vec::new()) };
}

fuzz_target!(|data: &[u8]| {
    // planning-pass surface (header-only validation)
    let _ = inspect_tensor(data);
    // decode surface with a SMALL cap: any blob claiming more than 1 MiB of
    // restored bytes must be refused by the cap, not allocated
    OUT.with(|out| {
        let _ = decompress_tensor_into(data, &mut out.borrow_mut(), 1, None, 1024 * 1024);
    });
});
