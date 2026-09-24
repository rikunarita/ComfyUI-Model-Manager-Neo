//! `znn-cli` — developer CLI for the native core (Plan §4.2.1: "検証用 CLI
//! (配布しない)").
//!
//! Subcommands:
//! * `identity` — the Phase-0 scaffold report (kept for continuity);
//! * `core-compress` / `core-decompress` — single-shot mirrors of the C
//!   `zipnn_core` / `combine_dtype` ABIs (same parameters, same payload
//!   layout) for manual checks against the bundled prebuilt C core;
//! * `bench` — steal-gated in-process timing (the L2 speed-gate counterpart
//!   of the Python harness's in-memory C loops);
//! * `batch` — the workhorse of the L2 golden-diff harness
//!   (`scripts/l2/golden_diff.py`): reads a JSONL manifest, runs every
//!   operation in ONE process (no per-case spawn overhead for the ≥10,000
//!   case suites), and writes JSONL results. A case that would make the C
//!   core SEGFAULT must show up here as `status:"ok"` or `status:"err"` —
//!   a panicked/aborted process is the harness's CRASH signal (Plan §5.1 L2).
//!
//! Never distributed; not part of any release artifact.

use std::path::{Path, PathBuf};

use clap::{Parser, Subcommand};
use serde::{Deserialize, Serialize};
use znn_codec::codec::{self, CoreParams};

#[derive(Parser)]
#[command(
    name = "znn-cli",
    about = "Developer CLI for the znn-codec native core (never distributed)",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Print the codec identity report (Phase 0 scaffold behaviour)
    Identity,
    /// Mirror of the C `zipnn_core`: compress IN → OUT (header + payload)
    CoreCompress {
        /// Input file (raw bytes, e.g. a tensor's bytearray)
        input: PathBuf,
        /// Output file (header + C-layout payload)
        output: PathBuf,
        #[command(flatten)]
        params: ParamsArgs,
        /// Header prefix to embed (default: 32 zero bytes, like the C tests).
        /// Bytes [24:32] are overwritten with the result size (C behaviour).
        #[arg(long)]
        header: Option<PathBuf>,
    },
    /// Mirror of the C `combine_dtype`: decompress payload IN → OUT
    CoreDecompress {
        /// Input file: the payload (bytes AFTER the 32-byte header, i.e.
        /// what `zipnn.py` passes to `combine_dtype`)
        input: PathBuf,
        /// Output file (raw bytes)
        output: PathBuf,
        /// Original (uncompressed) length — the C ABI takes it explicitly
        #[arg(long)]
        orig_len: usize,
        /// Cap for the output allocation (hostile-input guard); defaults to
        /// the codec's built-in bound
        #[arg(long)]
        max_output: Option<usize>,
        #[command(flatten)]
        params: ParamsArgs,
    },
    /// Steal-gated in-process timing bench (the L2 speed gate)
    Bench {
        /// Input file: raw bytes for `compress`, a C-layout PAYLOAD for
        /// `decompress`
        input: PathBuf,
        #[arg(long, default_value = "both")]
        op: String,
        #[arg(long, default_value_t = 3)]
        runs: usize,
        /// decompress only: original length
        #[arg(long)]
        orig_len: Option<usize>,
        /// emit JSON results to this path (default: stdout)
        #[arg(long)]
        json_out: Option<PathBuf>,
        #[command(flatten)]
        params: ParamsArgs,
    },
    /// Run a JSONL manifest of operations in one process (L2 harness)
    Batch {
        /// Manifest file: one JSON object per line
        manifest: PathBuf,
        /// Results file: one JSON object per line (same order)
        results: PathBuf,
    },
    /// Phase 2: compress a .safetensors file into .znn.safetensors (the
    /// native pipeline of py/compress.py, without Python)
    StCompress {
        /// Source .safetensors file
        input: PathBuf,
        /// Destination .znn.safetensors file
        output: PathBuf,
        /// Re-decode + sha-verify the artifact before renaming (Plan §4.4.3-4)
        #[arg(long)]
        paranoid: bool,
        /// Codec worker threads (0 = pool default)
        #[arg(long, default_value_t = 0)]
        threads: usize,
        /// Write the outcome JSON (stats/warnings/exact/sha) to this path
        #[arg(long)]
        json_out: Option<PathBuf>,
    },
    /// Phase 2: decompress a .znn.safetensors file (verified restore)
    StDecompress {
        /// Source .znn.safetensors file
        input: PathBuf,
        /// Destination .safetensors file
        output: PathBuf,
        /// Codec worker threads (0 = pool default)
        #[arg(long, default_value_t = 0)]
        threads: usize,
        /// Write the outcome JSON (stats/verified/warnings) to this path
        #[arg(long)]
        json_out: Option<PathBuf>,
    },
}

#[derive(clap::Args)]
struct ParamsArgs {
    /// Number of byte planes (1=fp8, 2=f16/bf16, 4=f32)
    #[arg(long, default_value_t = 4)]
    num_buf: usize,
    /// `bits_mode`: 1 = sign/exponent reorder
    #[arg(long, default_value_t = 1)]
    bits: u8,
    /// `bytes_mode`: 220 (4-plane) / 10 (2-plane, 1-plane)
    #[arg(long, default_value_t = 220)]
    mode: u8,
    /// Chunk size in bytes (production: 262144; fp8: 131072)
    #[arg(long, default_value_t = 262144)]
    chunk: usize,
    /// Compression threshold (production 0.95; 0 forces raw planes — the
    /// golden layout dump mode)
    #[arg(long, default_value_t = 0.95)]
    threshold: f64,
    /// Worker threads (0 = pool default = min(parallelism, 16), like the
    /// Python layer's threads=min(cpu,16))
    #[arg(long, default_value_t = 0)]
    threads: usize,
}

impl ParamsArgs {
    fn params(&self) -> CoreParams {
        CoreParams {
            num_buf: self.num_buf,
            bit_reorder: self.bits,
            byte_reorder: self.mode,
            chunk: self.chunk,
            threshold: self.threshold,
            threads: self.threads,
        }
    }
}

// ---------------------------------------------------------------------------
// batch manifest protocol
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct BatchOp {
    id: String,
    /// "compress" | "decompress"
    op: String,
    input: PathBuf,
    output: PathBuf,
    #[serde(default)]
    num_buf: Option<usize>,
    #[serde(default)]
    bits: Option<u8>,
    #[serde(default)]
    mode: Option<u8>,
    #[serde(default)]
    chunk: Option<usize>,
    #[serde(default)]
    threshold: Option<f64>,
    #[serde(default)]
    threads: Option<usize>,
    /// decompress only: original length (the harness always passes it)
    #[serde(default)]
    orig_len: Option<usize>,
    /// compress only: header file (defaults to 32 zero bytes)
    #[serde(default)]
    header: Option<PathBuf>,
    #[serde(default)]
    max_output: Option<usize>,
}

#[derive(Serialize)]
struct BatchResult {
    id: String,
    status: String, // "ok" | "err"
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    out_len: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    in_len: Option<usize>,
}

fn op_params(op: &BatchOp) -> CoreParams {
    CoreParams {
        num_buf: op.num_buf.unwrap_or(4),
        bit_reorder: op.bits.unwrap_or(1),
        byte_reorder: op.mode.unwrap_or(220),
        chunk: op.chunk.unwrap_or(262_144),
        threshold: op.threshold.unwrap_or(0.95),
        threads: op.threads.unwrap_or(0),
    }
}

fn run_batch_op(op: &BatchOp) -> Result<usize, String> {
    let params = op_params(op);
    let input =
        std::fs::read(&op.input).map_err(|e| format!("read {}: {e}", op.input.display()))?;
    match op.op.as_str() {
        "compress" => {
            let header = match &op.header {
                Some(p) => std::fs::read(p).map_err(|e| format!("read header: {e}"))?,
                None => vec![0u8; 32],
            };
            let out = codec::zipnn_core(&header, &input, &params).map_err(|e| e.to_string())?;
            let len = out.len();
            std::fs::write(&op.output, &out).map_err(|e| format!("write: {e}"))?;
            Ok(len)
        }
        "decompress" => {
            let orig_len = op.orig_len.ok_or("decompress op requires orig_len")?;
            let out = codec::combine_dtype(&input, orig_len, &params, op.max_output)
                .map_err(|e| e.to_string())?;
            let len = out.len();
            std::fs::write(&op.output, &out).map_err(|e| format!("write: {e}"))?;
            Ok(len)
        }
        other => Err(format!("unknown op {other}")),
    }
}

fn run_batch(manifest: &PathBuf, results: &PathBuf) -> i32 {
    let text = match std::fs::read_to_string(manifest) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("error: read manifest: {e}");
            return 2;
        }
    };
    let mut out_lines = Vec::new();
    let mut n_err = 0usize;
    for line in text.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let op: BatchOp = match serde_json::from_str(line) {
            Ok(op) => op,
            Err(e) => {
                eprintln!("error: bad manifest line: {e}");
                return 2;
            }
        };
        let in_len = std::fs::metadata(&op.input)
            .map(|m| usize::try_from(m.len()).unwrap_or(usize::MAX))
            .ok();
        let result = match run_batch_op(&op) {
            Ok(out_len) => BatchResult {
                id: op.id,
                status: "ok".into(),
                error: None,
                out_len: Some(out_len),
                in_len,
            },
            Err(e) => {
                n_err += 1;
                BatchResult {
                    id: op.id,
                    status: "err".into(),
                    error: Some(e),
                    out_len: None,
                    in_len,
                }
            }
        };
        out_lines.push(serde_json::to_string(&result).expect("serialize"));
    }
    if let Err(e) = std::fs::write(results, out_lines.join("\n") + "\n") {
        eprintln!("error: write results: {e}");
        return 2;
    }
    eprintln!("batch: {} ops, {n_err} returned err", out_lines.len());
    // exit 0 even when cases errored (an ERROR is a legitimate, recorded
    // outcome — e.g. Appendix-C inputs; only process-level failures like
    // panics/aborts signal a crash to the harness)
    0
}

// ---------------------------------------------------------------------------
// single-shot compress / decompress
// ---------------------------------------------------------------------------

fn run(
    input: &PathBuf,
    output: &PathBuf,
    params: &CoreParams,
    header: Option<&PathBuf>,
    orig_len: Option<usize>,
    max_output: Option<usize>,
) -> Result<(), String> {
    let data = std::fs::read(input).map_err(|e| format!("read {}: {e}", input.display()))?;
    let out = if let Some(orig_len) = orig_len {
        codec::combine_dtype(&data, orig_len, params, max_output).map_err(|e| e.to_string())?
    } else {
        let header_bytes = match header {
            Some(p) => std::fs::read(p).map_err(|e| format!("read header: {e}"))?,
            None => vec![0u8; 32],
        };
        codec::zipnn_core(&header_bytes, &data, params).map_err(|e| e.to_string())?
    };
    std::fs::write(output, &out).map_err(|e| format!("write {}: {e}", output.display()))?;
    eprintln!("wrote {} bytes → {}", out.len(), output.display());
    Ok(())
}

// ---------------------------------------------------------------------------
// steal-gated bench (the L2 speed-gate Rust side)
// ---------------------------------------------------------------------------

/// Host-steal ticks (/proc/stat cpu line, field 8) — the ground truth for
/// hypervisor interference. Linux-only; elsewhere gating is disabled.
#[cfg(target_os = "linux")]
fn steal_ticks() -> Option<u64> {
    let stat = std::fs::read_to_string("/proc/stat").ok()?;
    for line in stat.lines() {
        if let Some(rest) = line.strip_prefix("cpu ") {
            return rest.split_whitespace().nth(7)?.parse::<u64>().ok();
        }
    }
    None
}

#[cfg(not(target_os = "linux"))]
fn steal_ticks() -> Option<u64> {
    None
}

fn median(mut xs: Vec<f64>) -> f64 {
    xs.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let n = xs.len();
    if n == 0 {
        f64::NAN
    } else if n % 2 == 1 {
        xs[n / 2]
    } else {
        xs[n / 2 - 1].midpoint(xs[n / 2])
    }
}

// Timing math only ever handles small positive magnitudes (wall seconds,
// cpu counts, MiB) — the pedantic cast lints are noise here.
#[allow(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    clippy::cast_precision_loss
)]
/// Steal-gated timing loop: repeats `f` until `runs` CLEAN samples are
/// collected (host steal under ~5% of the window's CPU-tick capacity — the
/// same rule the Python side of the L2 speed gate applies), so both sides
/// are measured under identical, interference-free conditions.
fn timed_clean<F: FnMut() -> Result<(), String>>(
    runs: usize,
    mut f: F,
) -> Result<Vec<f64>, String> {
    let ncpu = std::thread::available_parallelism().map_or(1u64, |n| n.get() as u64);
    let mut times = Vec::with_capacity(runs);
    let mut attempts = 0;
    while times.len() < runs && attempts < runs * 25 {
        attempts += 1;
        let s0 = steal_ticks();
        let t0 = std::time::Instant::now();
        f()?;
        let dt = t0.elapsed().as_secs_f64();
        let s1 = steal_ticks();
        let dirty = match (s0, s1) {
            (Some(a), Some(b)) => {
                // 5% of the window's tick capacity (100 ticks/s per cpu)
                let budget = ((dt * 5.0) as u64).saturating_mul(ncpu).max(1);
                b.saturating_sub(a) > budget
            }
            _ => false, // no /proc/stat → gating disabled
        };
        if dirty {
            std::thread::sleep(std::time::Duration::from_millis(60));
        } else {
            times.push(dt);
        }
    }
    if times.is_empty() {
        return Err("no clean measurement window (host too busy) — rerun".to_owned());
    }
    Ok(times)
}

#[allow(clippy::cast_precision_loss)] // sizes far below 2^52 in this dev tool
fn mib(bytes: usize) -> f64 {
    bytes as f64 / (1024.0 * 1024.0)
}

#[derive(Serialize)]
struct BenchResult {
    op: String,
    bytes: usize,
    runs: usize,
    best_seconds: f64,
    median_seconds: f64,
    mbs: f64,
    median_mbs: f64,
    out_len: usize,
    roundtrip_ok: Option<bool>,
}

fn bench_compress(
    data: &[u8],
    runs: usize,
    params: &CoreParams,
) -> Result<(BenchResult, Vec<u8>), String> {
    let header = vec![0u8; 32];
    let mut last: Vec<u8> = Vec::new();
    let times = timed_clean(runs, || {
        last = codec::zipnn_core(&header, data, params).map_err(|e| e.to_string())?;
        Ok(())
    })?;
    let out_len = last.len();
    // correctness witness: decompress the final output once
    let rt =
        codec::combine_dtype(&last[32..], data.len(), params, None).map_err(|e| e.to_string())?;
    let best = times.iter().copied().fold(f64::MAX, f64::min);
    let med = median(times);
    Ok((
        BenchResult {
            op: "compress".into(),
            bytes: data.len(),
            runs,
            best_seconds: best,
            median_seconds: med,
            mbs: mib(data.len()) / best,
            median_mbs: mib(data.len()) / med,
            out_len,
            roundtrip_ok: Some(rt == data),
        },
        last[32..].to_vec(),
    ))
}

fn bench_decompress(
    pay: &[u8],
    orig: usize,
    runs: usize,
    params: &CoreParams,
) -> Result<BenchResult, String> {
    let times = timed_clean(runs, || {
        codec::combine_dtype(pay, orig, params, None).map_err(|e| e.to_string())?;
        Ok(())
    })?;
    let best = times.iter().copied().fold(f64::MAX, f64::min);
    let med = median(times);
    Ok(BenchResult {
        op: "decompress".into(),
        bytes: orig,
        runs,
        best_seconds: best,
        median_seconds: med,
        mbs: mib(orig) / best,
        median_mbs: mib(orig) / med,
        out_len: orig,
        roundtrip_ok: None,
    })
}

/// In-process best-of-N timing (no per-run I/O): the fair counterpart of
/// the C harness's in-memory `time.perf_counter()` loops.
fn bench(
    input: &PathBuf,
    op: &str,
    runs: usize,
    orig_len: Option<usize>,
    json_out: Option<&PathBuf>,
    params: &CoreParams,
) -> Result<(), String> {
    let data = std::fs::read(input).map_err(|e| format!("read {}: {e}", input.display()))?;
    let runs = runs.max(1);
    let mut results = Vec::new();
    let mut payload: Option<Vec<u8>> = None;
    if op == "compress" || op == "both" {
        let (row, pay) = bench_compress(&data, runs, params)?;
        results.push(row);
        payload = Some(pay);
    }
    if op == "decompress" || op == "both" {
        let pay = payload.unwrap_or_else(|| data.clone()); // `input` IS the payload
        let orig = orig_len.unwrap_or(data.len());
        results.push(bench_decompress(&pay, orig, runs, params)?);
    }
    let text = serde_json::to_string_pretty(&results).map_err(|e| e.to_string())?;
    match json_out {
        Some(p) => std::fs::write(p, text).map_err(|e| format!("write: {e}"))?,
        None => println!("{text}"),
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Phase 2: the safetensors pipeline (manual QA / bench driver)
// ---------------------------------------------------------------------------

fn run_st_compress(
    input: &Path,
    output: &Path,
    paranoid: bool,
    threads: usize,
    json_out: Option<&PathBuf>,
) -> Result<(), String> {
    use znn_codec::pipeline::{Hooks, JobOpts, Progress, compress_file};
    let progress = Progress::new(1);
    let hooks = Hooks {
        progress: Some(&progress),
        cancel: None,
    };
    let opts = JobOpts {
        threads,
        paranoid,
        ..JobOpts::default()
    };
    let t0 = std::time::Instant::now();
    let out = compress_file(input, output, &opts, &hooks).map_err(|e| e.to_string())?;
    let dt = t0.elapsed().as_secs_f64();
    let doc = serde_json::json!({
        "op": "st-compress",
        "input": input.display().to_string(),
        "output": output.display().to_string(),
        "seconds": dt,
        "stats": {
            "originalBytes": out.stats.original_bytes,
            "compressedBytes": out.stats.compressed_bytes,
            "tensors": out.stats.tensors,
            "compressedTensors": out.stats.compressed_tensors,
        },
        "srcSha256": out.src_sha256,
        "exact": out.exact,
        "paranoid": paranoid,
        "warnings": out.warnings,
        "outputSize": std::fs::metadata(output).map_or(0, |m| m.len()),
    });
    let text = serde_json::to_string_pretty(&doc).map_err(|e| e.to_string())?;
    match json_out {
        Some(p) => std::fs::write(p, text).map_err(|e| format!("write: {e}"))?,
        None => println!("{text}"),
    }
    Ok(())
}

fn run_st_decompress(
    input: &Path,
    output: &Path,
    threads: usize,
    json_out: Option<&PathBuf>,
) -> Result<(), String> {
    use znn_codec::pipeline::{Hooks, JobOpts, Progress, decompress_file};
    let progress = Progress::new(1);
    let hooks = Hooks {
        progress: Some(&progress),
        cancel: None,
    };
    let opts = JobOpts {
        threads,
        ..JobOpts::default()
    };
    let t0 = std::time::Instant::now();
    let out = decompress_file(input, output, &opts, &hooks).map_err(|e| e.to_string())?;
    let dt = t0.elapsed().as_secs_f64();
    let doc = serde_json::json!({
        "op": "st-decompress",
        "input": input.display().to_string(),
        "output": output.display().to_string(),
        "seconds": dt,
        "stats": {
            "tensors": out.stats.tensors,
            "decompressedTensors": out.stats.decompressed_tensors,
        },
        "verified": out.verified.as_str(),
        "warnings": out.warnings,
        "outputSize": std::fs::metadata(output).map_or(0, |m| m.len()),
    });
    let text = serde_json::to_string_pretty(&doc).map_err(|e| e.to_string())?;
    match json_out {
        Some(p) => std::fs::write(p, text).map_err(|e| format!("write: {e}"))?,
        None => println!("{text}"),
    }
    Ok(())
}

// ---------------------------------------------------------------------------

fn identity() -> i32 {
    println!(
        "znn-cli {version} (znn-codec: magic {magic:?}, header {header} B, \
         huff0 block max {block} B, tableLog max {log_max} / default {log_default}, \
         default chunk {chunk} B)",
        version = env!("CARGO_PKG_VERSION"),
        magic = znn_codec::ZNN_MAGIC,
        header = znn_codec::HEADER_LEN,
        block = znn_codec::HUF_BLOCKSIZE_MAX,
        log_max = znn_codec::HUF_TABLELOG_MAX,
        log_default = znn_codec::HUF_TABLELOG_DEFAULT,
        chunk = znn_codec::DEFAULT_CHUNK,
    );
    0
}

fn main() {
    let cli = Cli::parse();
    let code = match cli.command {
        Command::Identity => identity(),
        Command::CoreCompress {
            input,
            output,
            params,
            header,
        } => match run(
            &input,
            &output,
            &params.params(),
            header.as_ref(),
            None,
            None,
        ) {
            Ok(()) => 0,
            Err(e) => {
                eprintln!("error: {e}");
                1
            }
        },
        Command::CoreDecompress {
            input,
            output,
            orig_len,
            max_output,
            params,
        } => match run(
            &input,
            &output,
            &params.params(),
            None,
            Some(orig_len),
            max_output,
        ) {
            Ok(()) => 0,
            Err(e) => {
                eprintln!("error: {e}");
                1
            }
        },
        Command::Bench {
            input,
            op,
            runs,
            orig_len,
            json_out,
            params,
        } => match bench(
            &input,
            &op,
            runs,
            orig_len,
            json_out.as_ref(),
            &params.params(),
        ) {
            Ok(()) => 0,
            Err(e) => {
                eprintln!("error: {e}");
                1
            }
        },
        Command::Batch { manifest, results } => run_batch(&manifest, &results),
        Command::StCompress {
            input,
            output,
            paranoid,
            threads,
            json_out,
        } => match run_st_compress(&input, &output, paranoid, threads, json_out.as_ref()) {
            Ok(()) => 0,
            Err(e) => {
                eprintln!("error: {e}");
                1
            }
        },
        Command::StDecompress {
            input,
            output,
            threads,
            json_out,
        } => match run_st_decompress(&input, &output, threads, json_out.as_ref()) {
            Ok(()) => 0,
            Err(e) => {
                eprintln!("error: {e}");
                1
            }
        },
    };
    std::process::exit(code);
}
