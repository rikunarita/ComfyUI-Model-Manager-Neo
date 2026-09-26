//! L3 fuzz target 6/6: the file-level DELTA restore core (`delta.rs` — the
//! Phase-3 surface for hostile `.znn` delta artifacts and hostile sidecars).
//! Exercises: the streaming container-chain walk (`[24:32]` sizes, bounds,
//! truncation), the single-container legacy branch, per-container
//! `original_len` caps against the KNOWN base-rendering length (allocation
//! bombs must Err, never resize), the huff0/plane payload validation
//! through `combine_dtype_into`, the header-alignment padding math
//! (hostile `basePad`/`ftPad` up to 64 KiB — including `ftPad > header
//! length` underflow), and the streaming un-padder state machine. Every
//! path must return Err or a bounded Ok — never panic, never OOM.
//!
//! Input layout (the harness derives BOTH sides of the restore from one
//! blob so mutations explore matching/near-matching pairs):
//!
//! ```text
//! [0..2]  basePad          u16 LE (sidecar)
//! [2..4]  ftPad            u16 LE (sidecar)
//! [4..6]  split hint       u16 LE → base_data = rest[..hint % rest.len()]
//! [6..]   base_data ‖ delta file bytes
//! ```
//!
//! The base "model" is that data behind a fixed 64-byte safetensors header
//! (the delta flow never parses the header JSON — only its LENGTH matters,
//! exactly like the production code). Threads are pinned to 1, which after
//! the pool-cache fix (`codec.rs CUSTOM_POOLS`) is a stationary single
//! worker — no per-exec thread churn (the run-36114455354 OOM lesson).
#![no_main]

use libfuzzer_sys::fuzz_target;

/// The fixed 64-byte header JSON (54-byte body + 10 spaces) of the
/// synthetic base.
const BASE_HEADER: &[u8; 64] =
    b"{\"w\":{\"dtype\":\"F32\",\"shape\":[1],\"data_offsets\":[0,4]}}          ";

fuzz_target!(|data: &[u8]| {
    if data.len() < 6 {
        return;
    }
    let base_pad = u16::from_le_bytes([data[0], data[1]]) as u64;
    let ft_pad = u16::from_le_bytes([data[2], data[3]]) as u64;
    let rest = &data[6..];
    let hint = u16::from_le_bytes([data[4], data[5]]) as usize;
    let split = if rest.is_empty() {
        0
    } else {
        hint % rest.len()
    };
    let base_data = &rest[..split];
    let delta = &rest[split..];

    // base image = [u64 64][64-byte header][base_data]
    let mut base_img = Vec::with_capacity(72 + base_data.len());
    base_img.extend_from_slice(&64u64.to_le_bytes());
    base_img.extend_from_slice(BASE_HEADER);
    base_img.extend_from_slice(base_data);

    // the restore must answer (Ok bounded | Err) — the base rendering caps
    // every allocation; 1 MiB output cap as a harness belt-and-braces bound
    let _ = znn_codec::delta::delta_restore_fuzz(delta, &base_img, base_pad, ft_pad, 1024 * 1024);
});
