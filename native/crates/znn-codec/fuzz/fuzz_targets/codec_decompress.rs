//! L3 fuzz target 3/3: the full payload decoder (`combine_dtype` — the
//! `zipnn_core` layer) against hostile payloads AND hostile parameters
//! (Plan §5.1 L3, §4.4.2). Exercises: chunkType validation, cumSizes
//! monotonicity/span checks, raw-slice length checks, huff0 sub-decoding,
//! plane join, the output cap, and the container-level entry point.
//! Single call per iteration; every path must return Err — never panic,
//! never allocate beyond the declared caps, never hang.
#![no_main]

use libfuzzer_sys::fuzz_target;
use znn_codec::codec::{combine_dtype, decompress_container, CoreParams};

fuzz_target!(|data: &[u8]| {
    if data.len() < 9 {
        return;
    }
    // adversarial-but-structured parameters (also legal combos: 1/2/4 planes,
    // modes 220/10, chunks 1..=512 KiB)
    let num_buf = match data[0] % 4 {
        0 => 1usize,
        1 => 2,
        _ => 4,
    };
    let chunk = (u32::from_le_bytes([data[3], data[4], data[4], data[3]]) as usize % (512 * 1024)) + 1;
    let params = CoreParams {
        num_buf,
        bit_reorder: data[1] & 3, // includes illegal values on purpose
        byte_reorder: data[2],    // includes illegal modes on purpose
        chunk,
        threshold: 0.95,
        threads: 0, // global pool; no per-iteration pool churn
    };
    let orig_len = u32::from_le_bytes([data[5], data[6], data[7], data[8]]) as usize % (256 * 1024);
    let max_output = 256 * 1024;
    let _ = combine_dtype(&data[9..], orig_len, &params, Some(max_output));
    // container path: rarely passes the ZN magic by chance — the committed
    // corpus seeds give the fuzzer valid containers to mutate from
    let _ = decompress_container(data, Some(max_output));
});
