//! JSON parser decision micro-benchmark (Plan §6.2 Phase 0):
//! **jiter 0.17 vs simd-json 0.18** (`serde_json` 1.0 rides along as the
//! neutral reference) on an ~8 MB MoE safetensors header.
//!
//! The requirement under test is the Plan §3.7 one: the winner must parse the
//! header of a **read-only mmap** without mutating it ("非破壊借用解析").
//! jiter borrows `&[u8]` directly; simd-json is an in-place parser, so it
//! needs a fresh owned copy of the input on every parse — the copy is
//! included in its measured time, because that is the real cost of using it
//! from an mmap-based reader.
//!
//! The parse task mirrors what `py/utils.py get_model_tensors()` does with a
//! header (Plan §1.2.2 #10, K11): walk every tensor entry, read its `dtype`
//! string and its `shape` array, and reduce them to a checksum.
//!
//! Usage: `json-bench <header.json> [iterations]`
//! (generate the input with `scripts/bench/gen_synthetic.py --moe-header`).
//!
//! This crate is a benchmark, never distributed (like `znn-cli`).

use std::{env, fs, process, time::Duration, time::Instant};

/// Order-independent digest of the walk: every parser must agree on it.
#[derive(Debug, Default, PartialEq, Eq)]
struct Summary {
    tensors: u64,
    dims: u64,
    checksum: u64,
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: json-bench <header.json> [iterations]");
        process::exit(2);
    }
    let path = &args[1];
    let data = match fs::read(path) {
        Ok(data) => data,
        Err(err) => {
            eprintln!("cannot read {path}: {err}");
            process::exit(1);
        }
    };
    // A JSON header is nowhere near 2^52 bytes; the f64 rounding is
    // irrelevant for a benchmark readout.
    #[allow(clippy::cast_precision_loss)]
    let mib = data.len() as f64 / (1024.0 * 1024.0);
    let iters: u32 = args
        .get(2)
        .and_then(|v| v.parse().ok())
        .unwrap_or_else(|| default_iters(mib));
    println!(
        "json-bench: {path} = {len} bytes ({mib:.2} MiB), {iters} iterations per parser (+1 warmup)",
        len = data.len()
    );

    let jiter_sum = bench("jiter", &data, iters, || jiter_walk(&data));
    let simd_sum = bench("simd-json", &data, iters, || simd_walk(&data));
    let serde_sum = bench("serde_json", &data, iters, || serde_walk(&data));

    println!("\ndigests: jiter={jiter_sum:?}");
    println!("         simd-json={simd_sum:?}");
    println!("         serde_json={serde_sum:?}");
    if jiter_sum != simd_sum || jiter_sum != serde_sum {
        eprintln!("MISMATCH: the parsers disagree on the header digest");
        process::exit(1);
    }
    println!("all parsers agree ✓");
}

/// Roughly 64 MiB worth of parses, clamped to a sane range.
fn default_iters(mib: f64) -> u32 {
    let clamped = (64.0 / mib).clamp(3.0, 51.0);
    // clamp() above bounds the value to [3, 51] before the casts.
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    let iters = clamped as u32;
    iters
}

fn bench<F>(name: &str, data: &[u8], iters: u32, mut parse: F) -> Summary
where
    F: FnMut() -> Summary,
{
    let mut summary = parse(); // warmup (also populates the page cache)
    let mut times: Vec<Duration> = Vec::with_capacity(iters as usize);
    for _ in 0..iters {
        let started = Instant::now();
        summary = parse();
        times.push(started.elapsed());
    }
    times.sort_unstable();
    let min = times[0];
    let median = times[times.len() / 2];
    let mean = times.iter().sum::<Duration>() / iters;
    // See main(): the f64 conversion of a file size is precision-safe here.
    #[allow(clippy::cast_precision_loss)]
    let mib = data.len() as f64 / (1024.0 * 1024.0);
    let per_sec = mib / median.as_secs_f64();
    println!(
        "{name:10} min {min:>9.3?}  median {median:>9.3?}  mean {mean:>9.3?}  ({per_sec:7.1} MiB/s median)"
    );
    summary
}

/// jiter: streaming walk over the borrowed, immutable input (no copy).
///
/// Object iteration protocol (verified against jiter 0.17 source):
/// `next_object()` consumes the opening `{` and the FIRST key; subsequent
/// keys come from `next_key()`, which returns `None` at the closing `}`.
/// Arrays work the same way via `next_array()` + `array_step()`.
fn jiter_walk(data: &[u8]) -> Summary {
    let mut j = jiter::Jiter::new(data);
    let mut out = Summary::default();
    let mut key = j
        .next_object()
        .expect("top-level object")
        .expect("non-empty header");
    loop {
        if key == "__metadata__" {
            j.next_skip().expect("valid metadata value");
        } else {
            out.tensors += 1;
            out.checksum = out.checksum.wrapping_add(key.len() as u64);
            jiter_walk_tensor(&mut j, &mut out);
        }
        match j.next_key().expect("valid object") {
            Some(next) => key = next,
            None => break,
        }
    }
    j.finish().expect("no trailing data");
    out
}

fn jiter_walk_tensor(j: &mut jiter::Jiter<'_>, out: &mut Summary) {
    let mut field = j
        .next_object()
        .expect("tensor entry object")
        .expect("non-empty tensor entry");
    loop {
        match field {
            "dtype" => {
                let dtype = j.next_str().expect("dtype string");
                out.checksum = out.checksum.wrapping_add(dtype.len() as u64);
            }
            "shape" => {
                if let Some(mut peek) = j.next_array().expect("shape array") {
                    loop {
                        let dim = match j.known_int(peek).expect("shape integer") {
                            jiter::NumberInt::Int(v) => v,
                            // Shapes never exceed i64; the big-int variant
                            // cannot occur in a safetensors header.
                            jiter::NumberInt::BigInt(_) => 0,
                        };
                        out.dims += 1;
                        out.checksum = out.checksum.wrapping_add(dim.unsigned_abs());
                        match j.array_step().expect("valid array") {
                            Some(next) => peek = next,
                            None => break,
                        }
                    }
                }
            }
            // data_offsets and anything else: validate + skip.
            _ => j.next_skip().expect("valid value"),
        }
        match j.next_key().expect("tensor entry") {
            Some(next) => field = next,
            None => break,
        }
    }
}

/// simd-json: in-place parser — every run needs its own mutable copy of the
/// read-only input, and that copy is part of the measured cost.
fn simd_walk(data: &[u8]) -> Summary {
    use simd_json::prelude::{ValueAsArray, ValueAsObject, ValueAsScalar, ValueObjectAccess};

    let mut buf = data.to_vec();
    let value = simd_json::to_borrowed_value(&mut buf).expect("valid json");
    let mut out = Summary::default();
    let object = value.as_object().expect("top-level object");
    for (key, entry) in object {
        // Borrowed-object keys are plain &str slices into the (copied) input.
        if *key == "__metadata__" {
            continue;
        }
        out.tensors += 1;
        out.checksum = out.checksum.wrapping_add(key.len() as u64);
        if let Some(dtype) = entry.get("dtype").and_then(|v| v.as_str()) {
            out.checksum = out.checksum.wrapping_add(dtype.len() as u64);
        }
        if let Some(shape) = entry.get("shape").and_then(|v| v.as_array()) {
            for dim in shape {
                out.dims += 1;
                out.checksum = out
                    .checksum
                    .wrapping_add(dim.as_i64().unwrap_or(0).unsigned_abs());
            }
        }
    }
    out
}

/// `serde_json` reference: full DOM from the borrowed input (no copy).
fn serde_walk(data: &[u8]) -> Summary {
    let value: serde_json::Value = serde_json::from_slice(data).expect("valid json");
    let mut out = Summary::default();
    let object = value.as_object().expect("top-level object");
    for (key, entry) in object {
        if key == "__metadata__" {
            continue;
        }
        out.tensors += 1;
        out.checksum = out.checksum.wrapping_add(key.len() as u64);
        if let Some(dtype) = entry.get("dtype").and_then(|v| v.as_str()) {
            out.checksum = out.checksum.wrapping_add(dtype.len() as u64);
        }
        if let Some(shape) = entry.get("shape").and_then(|v| v.as_array()) {
            for dim in shape {
                out.dims += 1;
                out.checksum = out
                    .checksum
                    .wrapping_add(dim.as_i64().unwrap_or(0).unsigned_abs());
            }
        }
    }
    out
}
