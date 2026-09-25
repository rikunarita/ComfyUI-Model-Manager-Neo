//! Async job registry — the polling-based Python API of Plan §4.2.2:
//!
//! ```text
//! mm_core.zipnn_compress(src, dst, opts) -> handle
//! mm_core.zipnn_decompress(src, dst, opts) -> handle
//! mm_core.job_progress(handle) -> (done, total, phase)
//! mm_core.job_cancel(handle)   -> bool
//! mm_core.job_result(handle)   -> str   (completion-stats JSON)
//! mm_core.job_error(handle)    -> str | None
//! ```
//!
//! Design invariants (Plan §4.2.2):
//! * **no GIL round-trips from job threads** — jobs are pure-Rust threads
//!   (never touching `Python`), the asyncio side POLLS the atomic progress
//!   at ~10 Hz instead of the legacy `run_coroutine_threadsafe` callbacks;
//! * **panics never escape** — the pipeline runs inside `catch_unwind` and a
//!   panic becomes a regular job error (the workspace's `panic = "unwind"`
//!   profile is what makes this possible; `abort` is forbidden, Plan §3.3);
//! * **cancellation is cooperative** at tensor/chunk boundaries and the
//!   pipeline's `.tmp` guards remove partial output (Plan §4.2.2-4);
//! * handles are process-local u64 ids; terminal jobs are swept by age and
//!   registry-size caps so a long-lived ComfyUI process cannot leak.

use std::any::Any;
use std::collections::HashMap;
use std::panic::AssertUnwindSafe;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};

use pyo3::exceptions::{PyKeyError, PyRuntimeError};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::Serialize;
use znn_codec::pipeline::{
    self, CompressOutcome, DecompressOutcome, Hooks, JobOpts, Phase, Progress,
};

/// Terminal job state (JSON documents on success, message on failure).
enum Outcome {
    Done(String),
    Failed(String),
}

struct Job {
    progress: Progress,
    cancel: AtomicBool,
    outcome: Mutex<Option<Outcome>>,
    created: Instant,
}

impl Job {
    fn outcome(&self) -> Option<Outcome> {
        let guard = self
            .outcome
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        match &*guard {
            Some(Outcome::Done(s)) => Some(Outcome::Done(s.clone())),
            Some(Outcome::Failed(s)) => Some(Outcome::Failed(s.clone())),
            None => None,
        }
    }
}

static JOBS: OnceLock<Mutex<HashMap<u64, Arc<Job>>>> = OnceLock::new();
static NEXT_ID: AtomicU64 = AtomicU64::new(1);

fn registry() -> &'static Mutex<HashMap<u64, Arc<Job>>> {
    JOBS.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Sweep terminal jobs older than an hour, and enforce a hard registry cap
/// (oldest terminal jobs first) — a ComfyUI process compressing models for
/// weeks must not accumulate job states.
fn gc() {
    const MAX_AGE: Duration = Duration::from_secs(3600);
    const MAX_JOBS: usize = 4096;
    let mut map = registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    let now = Instant::now();
    map.retain(|_, job| {
        job.outcome
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .is_none()
            || now.duration_since(job.created) < MAX_AGE
    });
    while map.len() > MAX_JOBS {
        let oldest = map
            .iter()
            .filter(|(_, j)| {
                j.outcome
                    .lock()
                    .unwrap_or_else(std::sync::PoisonError::into_inner)
                    .is_some()
            })
            .min_by_key(|(_, j)| j.created)
            .map(|(id, _)| *id);
        match oldest {
            Some(id) => {
                map.remove(&id);
            }
            None => break, // all running — keep them (bounded by MAX_JOBS races)
        }
    }
}

/// The JSON shape of `job_result` for a compress job. `stats` is EXACTLY the
/// legacy ws payload (`originalBytes`/`compressedBytes`/`tensors`/
/// `compressedTensors` — golden-tested); the rest is Neo diagnostics the
/// Python layer logs but does not forward.
#[derive(Serialize)]
struct CompressResult<'a> {
    stats: CompressStatsJson,
    #[serde(rename = "srcSha256")]
    src_sha256: &'a str,
    exact: bool,
    warnings: &'a [String],
}

#[derive(Serialize)]
struct CompressStatsJson {
    #[serde(rename = "originalBytes")]
    original_bytes: u64,
    #[serde(rename = "compressedBytes")]
    compressed_bytes: u64,
    tensors: usize,
    #[serde(rename = "compressedTensors")]
    compressed_tensors: usize,
}

/// The JSON shape of `job_result` for a decompress job (`stats` mirrors the
/// legacy `{"tensors", "decompressedTensors"}` payload exactly).
#[derive(Serialize)]
struct DecompressResult<'a> {
    stats: DecompressStatsJson,
    verified: &'a str,
    warnings: &'a [String],
}

#[derive(Serialize)]
struct DecompressStatsJson {
    tensors: usize,
    #[serde(rename = "decompressedTensors")]
    decompressed_tensors: usize,
}

fn compress_json(o: &CompressOutcome) -> String {
    serde_json::to_string(&CompressResult {
        stats: CompressStatsJson {
            original_bytes: o.stats.original_bytes,
            compressed_bytes: o.stats.compressed_bytes,
            tensors: o.stats.tensors,
            compressed_tensors: o.stats.compressed_tensors,
        },
        src_sha256: &o.src_sha256,
        exact: o.exact,
        warnings: &o.warnings,
    })
    .expect("outcome serialises")
}

fn decompress_json(o: &DecompressOutcome) -> String {
    serde_json::to_string(&DecompressResult {
        stats: DecompressStatsJson {
            tensors: o.stats.tensors,
            decompressed_tensors: o.stats.decompressed_tensors,
        },
        verified: o.verified.as_str(),
        warnings: &o.warnings,
    })
    .expect("outcome serialises")
}

/// Human-readable job error (the string Python puts into the `zipnn_complete`
/// `error` field — the UI shows it verbatim, so it must be actionable).
fn error_text(e: &znn_codec::safetensors_io::StError) -> String {
    match e {
        znn_codec::safetensors_io::StError::Cancelled => "cancelled by user".to_owned(),
        other => other.to_string(),
    }
}

fn panic_text(payload: &Box<dyn Any + Send>) -> String {
    if let Some(s) = payload.downcast_ref::<&str>() {
        (*s).to_owned()
    } else if let Some(s) = payload.downcast_ref::<String>() {
        s.clone()
    } else {
        "unknown panic".to_owned()
    }
}

#[derive(Clone, Copy)]
enum Kind {
    Compress,
    Decompress,
}

/// Spawn a pipeline job on a dedicated thread; returns the handle.
fn spawn(kind: Kind, src: PathBuf, dst: PathBuf, opts: JobOpts) -> u64 {
    let job = Arc::new(Job {
        progress: Progress::new(1),
        cancel: AtomicBool::new(false),
        outcome: Mutex::new(None),
        created: Instant::now(),
    });
    let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
    registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .insert(id, Arc::clone(&job));
    gc();

    // A handle kept outside the thread closure so the spawn-failure branch
    // below can still record a terminal error on the job.
    let job_outer = Arc::clone(&job);
    let spawned = std::thread::Builder::new()
        .name(format!("mm-core-job-{id}"))
        .spawn(move || {
            let job_inner = Arc::clone(&job);
            let ran = std::panic::catch_unwind(AssertUnwindSafe(move || {
                let hooks = Hooks {
                    progress: Some(&job_inner.progress),
                    cancel: Some(&job_inner.cancel),
                };
                match kind {
                    Kind::Compress => pipeline::compress_file(&src, &dst, &opts, &hooks)
                        .map(|o| compress_json(&o)),
                    Kind::Decompress => pipeline::decompress_file(&src, &dst, &opts, &hooks)
                        .map(|o| decompress_json(&o)),
                }
            }));
            let outcome = match ran {
                Ok(Ok(json)) => Outcome::Done(json),
                Ok(Err(e)) => {
                    job.progress.set_phase(Phase::Failed);
                    Outcome::Failed(error_text(&e))
                }
                Err(payload) => {
                    job.progress.set_phase(Phase::Failed);
                    Outcome::Failed(format!(
                        "native job panicked (this is a bug — please report): {}",
                        panic_text(&payload)
                    ))
                }
            };
            *job.outcome
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(outcome);
        });
    if let Err(e) = spawned {
        // thread spawn failed (resource exhaustion): record a terminal error
        // instead of leaving Python polling a job that will never finish
        job_outer.progress.set_phase(Phase::Failed);
        *job_outer
            .outcome
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(Outcome::Failed(format!(
            "could not start the job thread: {e}"
        )));
    }
    id
}

/// Parse the `opts` dict (Plan §4.2.2 — unknown keys are ignored so older
/// binaries tolerate newer callers' option sets).
fn parse_opts(opts: Option<&Bound<'_, PyDict>>) -> JobOpts {
    let mut out = JobOpts::default();
    let Some(dict) = opts else { return out };
    // (let-chains are 1.88+; the MSRV floor is 1.85 — hence the combinators)
    if let Some(n) = dict
        .get_item("threads")
        .ok()
        .flatten()
        .and_then(|v| v.extract::<usize>().ok())
    {
        out.threads = n;
    }
    if let Some(b) = dict
        .get_item("paranoid")
        .ok()
        .flatten()
        .and_then(|v| v.extract::<bool>().ok())
    {
        out.paranoid = b;
    }
    if let Some(b) = dict
        .get_item("verify")
        .ok()
        .flatten()
        .and_then(|v| v.extract::<bool>().ok())
    {
        out.verify = b;
    }
    out
}

fn lookup(id: u64) -> PyResult<Arc<Job>> {
    registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .get(&id)
        .cloned()
        .ok_or_else(|| PyKeyError::new_err(format!("unknown job handle {id}")))
}

// ---------------------------------------------------------------------------
// Python-facing functions (wired into the #[pymodule] in lib.rs)
// ---------------------------------------------------------------------------

/// Start a compress job; returns its handle.
///
/// # Errors
/// `opts` of the wrong shape is tolerated (defaults); the handle is always
/// returned — failures surface through `job_error`.
pub fn zipnn_compress(src: &str, dst: &str, opts: Option<&Bound<'_, PyDict>>) -> u64 {
    spawn(
        Kind::Compress,
        PathBuf::from(src),
        PathBuf::from(dst),
        parse_opts(opts),
    )
}

/// Start a decompress job; returns its handle.
pub fn zipnn_decompress(src: &str, dst: &str, opts: Option<&Bound<'_, PyDict>>) -> u64 {
    spawn(
        Kind::Decompress,
        PathBuf::from(src),
        PathBuf::from(dst),
        parse_opts(opts),
    )
}

/// `(done, total, phase)` — phase is one of `prepare/tensors/write/verify/
/// done/failed`; `done`+`failed` are terminal.
///
/// The OUTCOME record is the sole terminal signal: the pipeline sets its
/// `Done` phase before the worker thread stores the outcome, so reporting
/// the raw phase would open a window where `job_progress` says done but
/// `job_result` is not readable yet (found by the Phase-2 bench harness).
/// While no outcome exists, a terminal pipeline phase is reported as
/// `verify` — the poller keeps spinning for the microseconds until the
/// outcome lands.
///
/// # Errors
/// Unknown handle.
pub fn job_progress(id: u64) -> PyResult<(u64, u64, String)> {
    let job = lookup(id)?;
    let (done, total, phase) = job.progress.snapshot();
    let outcome = job.outcome();
    let reported = match &outcome {
        Some(Outcome::Done(_)) => Phase::Done,
        Some(Outcome::Failed(_)) => Phase::Failed,
        None => match phase {
            Phase::Done | Phase::Failed => Phase::Verify,
            other => other,
        },
    };
    Ok((done, total, reported.as_str().to_owned()))
}

/// Request cooperative cancellation; True when the job was still running.
///
/// # Errors
/// Unknown handle.
pub fn job_cancel(id: u64) -> PyResult<bool> {
    let job = lookup(id)?;
    let running = job
        .outcome
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .is_none();
    job.cancel.store(true, Ordering::Relaxed);
    Ok(running)
}

/// The completion-stats JSON of a finished job.
///
/// # Errors
/// Unknown handle, job still running, or the job FAILED (the message rides
/// the exception; `job_error` returns it without raising).
pub fn job_result(id: u64) -> PyResult<String> {
    let job = lookup(id)?;
    match job.outcome() {
        Some(Outcome::Done(json)) => Ok(json),
        Some(Outcome::Failed(msg)) => Err(PyRuntimeError::new_err(msg)),
        None => Err(PyRuntimeError::new_err(format!(
            "job {id} has not finished"
        ))),
    }
}

/// The failure message of a finished job, `None` while running or on
/// success.
///
/// # Errors
/// Unknown handle.
pub fn job_error(id: u64) -> PyResult<Option<String>> {
    let job = lookup(id)?;
    Ok(match job.outcome() {
        Some(Outcome::Failed(msg)) => Some(msg),
        _ => None,
    })
}

#[cfg(test)]
mod tests {
    // The job API end-to-end (spawn → poll → result) runs from Python —
    // tests/test_phase2_* drive it against the built artifact (CI: the
    // native workflow's integration job). Here we cover the registry
    // primitives that do not need an interpreter.

    use super::*;

    #[test]
    fn unknown_handles_are_key_errors() {
        assert!(job_progress(u64::MAX).is_err());
        assert!(job_cancel(u64::MAX).is_err());
        assert!(job_result(u64::MAX).is_err());
        assert!(job_error(u64::MAX).is_err());
    }

    #[test]
    fn failed_jobs_report_error_and_raise_on_result() {
        // a source that does not exist → clean Format/Io error, no panic
        let id = zipnn_compress(
            "/nonexistent/mmneo/a.safetensors",
            "/nonexistent/mmneo/a.znn.safetensors",
            None,
        );
        // poll until terminal (bounded — the failure is immediate)
        for _ in 0..200 {
            let (_d, _t, phase) = job_progress(id).unwrap();
            if phase == "failed" || phase == "done" {
                break;
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        let err = job_error(id).unwrap().expect("failed job has an error");
        // io_ctx always names the operation and the path — the platform
        // message text differs (POSIX vs Win32), those two do not
        assert!(
            err.contains("reading") && err.contains("a.safetensors"),
            "{err}"
        );
        assert!(job_result(id).is_err(), "result on a failed job raises");
        assert_eq!(job_progress(id).unwrap().2, "failed");
    }

    #[test]
    fn opts_parse_ignores_garbage() {
        // parse_opts(None) = defaults; PyDict construction needs an
        // interpreter, so only the None arm is unit-tested here (the Python
        // suite covers dict forms).
        let o = parse_opts(None);
        assert_eq!(o.threads, 0);
        assert!(!o.paranoid);
    }
}
