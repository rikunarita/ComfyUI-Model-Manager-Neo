//! L3 fuzz target 5/5: per-tensor ZN BLOB decoding (`znn_tensor` — the
//! Phase-2 surface for hostile `.znn.safetensors` payloads, Plan §4.4.2).
//! Exercises: the ZN header parse (version gate, magic, method, lossy,
//! input_format), the packed-shape decode, the dtype-code table (compat
//! band + explicit Phase-4 refusals), the shape×elem == original_len
//! consistency check, the ALLOCATION CAP (a consistent-lie header declaring
//! terabytes must error, never OOM), and the codec payload validation
//! through `combine_dtype_into`. Threads are pinned to 1 (no pool churn per
//! iteration). Every path must return Err — never panic, never hang.
#![no_main]

use libfuzzer_sys::fuzz_target;
use znn_codec::znn_tensor::{decompress_tensor_into, inspect_tensor};

fuzz_target!(|data: &[u8]| {
    // planning-pass surface (header-only validation)
    let _ = inspect_tensor(data);
    // decode surface with a SMALL cap: any blob claiming more than 1 MiB of
    // restored bytes must be refused by the cap, not allocated
    let mut out = Vec::new();
    let _ = decompress_tensor_into(data, &mut out, 1, None, 1024 * 1024);
});
