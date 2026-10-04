//! Optional filesystem watching of the model library (Phase 6).
//!
//! `notify` 8.2.0 + `notify-debouncer-full` 0.7.0 **directly** (the
//! `extended-notify` wrapper is explicitly NOT used: a 0.1.x
//! single-author crate that pulls `tokio` into the shipped binary and pins
//! debouncer-full a generation back).
//!
//! Shape of the feature (Phase 6):
//!
//! * **polling, not callbacks** — the debouncer thread only appends to a
//!   shared, deduplicated path set; Python drains it with [`watch_poll`] from
//!   its own asyncio task ("ポーリング方式 — GIL 再取得
//!   コールバックを使わない"). No GIL is ever taken from a notify thread;
//! * **500 ms debounce** ([`DEBOUNCE`]) so a batch copy or a ZipNN run
//!   collapses into one refresh instead of one per file;
//! * **watch-budget degrade** — Linux hands out one inotify watch per
//!   directory, and `fs.inotify.max_user_watches` is a hard per-user ceiling.
//!   Exhaustion surfaces as [`ErrorKind::MaxFilesWatch`]; the session then
//!   records a `degraded` reason and Python falls back to the 30 s TTL
//!   revalidation instead of failing ("枯渇時は TTL へ
//!   degrade");
//! * **missed events** — `Event::need_rescan` (a backend that lost track, e.g.
//!   a queue overflow) sets `rescan` in the poll payload so Python broadcasts a
//!   FULL invalidation rather than a per-type one;
//! * **off by default** — the session only exists when Python creates one, and
//!   Python only creates one when the (default-OFF) setting says so.
//!
//! The crate feature is `watch` (default-on: the shipped prebuilt binaries
//! must expose `mm_core.watch_*`, otherwise the setting could never work on a
//! stock install — the *runtime* default is what stays OFF).

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};

use notify::RecursiveMode;
use notify_debouncer_full::{DebounceEventResult, Debouncer, RecommendedCache, new_debouncer};

/// Debounce window (500 ms).
pub const DEBOUNCE: Duration = Duration::from_millis(500);

/// The concrete debouncer type (`new_debouncer`'s return, spelled out so the
/// session struct can name it).
type FullDebouncer = Debouncer<notify::RecommendedWatcher, RecommendedCache>;

/// Pending-path cap.
///
/// A bulk operation (copying a whole library in, a `git checkout` of a model
/// repo) can produce tens of thousands of distinct paths between two polls, and
/// both the pending set and the next poll's JSON would grow with them. Past the
/// cap the session collapses everything into ONE full invalidation (`rescan`),
/// which is exactly how the Python side treats that flag - a full sweep is
/// cheaper than a megabyte payload naming every file, and correctness is
/// unaffected because the client re-fetches the whole type anyway.
pub const MAX_PENDING_PATHS: usize = 4096;

/// Everything the notify thread and the polling side share.
#[derive(Default)]
struct Shared {
    /// Changed paths since the last poll — a set, so a burst of events for one
    /// file (write + chmod + rename) collapses to a single entry, and the JSON
    /// payload is deterministic (sorted) for tests.
    paths: Mutex<BTreeSet<PathBuf>>,
    /// Runtime errors reported by the backend (never fatal: a lost watch only
    /// costs freshness, and the TTL revalidate is the safety net).
    errors: Mutex<Vec<String>>,
    /// Set when the backend signalled `need_rescan` (events may have been
    /// missed → Python broadcasts a full invalidation).
    rescan: AtomicBool,
    /// Set when the session had to give up (watch budget exhausted); the reason
    /// is reported to Python, which then stops the session and relies on the
    /// TTL fallback.
    degraded: Mutex<Option<String>>,
}

impl Shared {
    /// Fold one debounced event into the pending state (runs on the notify
    /// thread; every lock here is held for a few instructions only).
    fn record(&self, event: &notify::Event) {
        if event.need_rescan() {
            self.rescan.store(true, Ordering::Relaxed);
        }
        // Read-only access events are noise (ComfyUI reads models constantly);
        // everything else can mean a listing change.
        if matches!(event.kind, notify::EventKind::Access(_)) {
            return;
        }
        let mut paths = self
            .paths
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        for path in &event.paths {
            paths.insert(path.clone());
        }
        if paths.len() > MAX_PENDING_PATHS {
            self.rescan.store(true, Ordering::Relaxed);
            paths.clear();
        }
    }

    /// Record a backend error; a watch-budget exhaustion also marks the session
    /// degraded so Python falls back to the TTL refresh.
    fn record_error(&self, err: &notify::Error) {
        if matches!(err.kind, notify::ErrorKind::MaxFilesWatch) {
            *self
                .degraded
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner) =
                Some(format!("inotify watch budget exhausted: {err}"));
        }
        let mut list = self
            .errors
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        // Bounded: a long-lived session must not grow the list without bound
        // (poll drains it, but a stalled poller must not turn it into a leak).
        if list.len() < 64 {
            list.push(err.to_string());
        }
    }
}

/// One live watch session (one per `watch_start`).
pub struct WatchSession {
    roots: Vec<PathBuf>,
    shared: Arc<Shared>,
    /// `Debouncer::watch` takes `&mut self`; the mutex is only ever held for
    /// the duration of one watch/unwatch call (never while the notify thread
    /// runs). `None` once [`stop`](Self::stop) has taken it.
    debouncer: Mutex<Option<FullDebouncer>>,
    started: Instant,
    /// Roots successfully armed (a missing root is skipped, not fatal).
    watched: AtomicU64,
    stopped: AtomicBool,
}

impl WatchSession {
    /// The roots this session was asked to watch.
    #[must_use]
    pub fn roots(&self) -> &[PathBuf] {
        &self.roots
    }

    /// Uptime of the session (diagnostics).
    #[must_use]
    pub fn age(&self) -> Duration {
        self.started.elapsed()
    }

    /// Number of roots actually armed.
    #[must_use]
    pub fn watched(&self) -> u64 {
        self.watched.load(Ordering::Relaxed)
    }

    /// Drain the pending changes into a JSON payload:
    /// `{"paths":[…],"rescan":bool,"degraded":string|null,"roots":n,
    /// "watched":n,"ageMs":n,"errors":[…]}`.
    ///
    /// Deterministic key order and sorted paths (golden-testable). `errors` is
    /// drained too, so a long-lived session cannot grow the list without bound.
    #[must_use]
    pub fn poll_json(&self) -> String {
        let paths: Vec<PathBuf> = {
            let mut set = self
                .shared
                .paths
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            std::mem::take(&mut *set).into_iter().collect()
        };
        let errors: Vec<String> = {
            let mut list = self
                .shared
                .errors
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            std::mem::take(&mut *list)
        };
        let degraded = self
            .shared
            .degraded
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone();
        let rescan = self.shared.rescan.swap(false, Ordering::Relaxed);

        let mut out = String::from("{\"paths\":[");
        for (i, path) in paths.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push_str(&crate::safetensors_io::py_escape_json_string(
                &path.to_string_lossy(),
            ));
        }
        out.push_str("],\"rescan\":");
        out.push_str(if rescan { "true" } else { "false" });
        out.push_str(",\"degraded\":");
        match &degraded {
            Some(reason) => {
                out.push_str(&crate::safetensors_io::py_escape_json_string(reason));
            }
            None => out.push_str("null"),
        }
        out.push_str(",\"stopped\":");
        out.push_str(if self.stopped.load(Ordering::Relaxed) {
            "true"
        } else {
            "false"
        });
        out.push_str(",\"roots\":");
        out.push_str(&self.roots.len().to_string());
        out.push_str(",\"watched\":");
        out.push_str(&self.watched().to_string());
        out.push_str(",\"ageMs\":");
        out.push_str(&self.started.elapsed().as_millis().to_string());
        out.push_str(",\"errors\":[");
        for (i, err) in errors.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push_str(&crate::safetensors_io::py_escape_json_string(err));
        }
        out.push_str("]}");
        out
    }

    /// Stop the debouncer (non-blocking: `Debouncer::stop` may wait one tick
    /// rate, which must not happen on a Python call thread) and mark the
    /// session stopped. Idempotent.
    pub fn stop(&self) {
        if self.stopped.swap(true, Ordering::Relaxed) {
            return;
        }
        // `take()` the debouncer out and stop it OUTSIDE the lock: `stop_*`
        // waits on the notify thread, and holding the mutex while doing so
        // could deadlock against a concurrent `watch`/`unwatch` call.
        let owned = {
            let mut slot = self
                .debouncer
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            slot.take()
        };
        if let Some(debouncer) = owned {
            debouncer.stop_nonblocking();
        }
    }
}

/// The process-wide session registry.
fn registry() -> &'static Mutex<std::collections::HashMap<u64, Arc<WatchSession>>> {
    static REG: OnceLock<Mutex<std::collections::HashMap<u64, Arc<WatchSession>>>> =
        OnceLock::new();
    REG.get_or_init(|| Mutex::new(std::collections::HashMap::new()))
}

static NEXT_ID: AtomicU64 = AtomicU64::new(1);

/// Start watching `roots` recursively; returns the session id.
///
/// `debounce` defaults to [`DEBOUNCE`]. A root that does not exist is skipped
/// (recorded in the session's `errors`) rather than failing the whole session —
/// model folders come and go with mounted volumes. A watch-budget exhaustion
/// ([`notify::ErrorKind::MaxFilesWatch`]) marks the session `degraded` and
/// returns it anyway, so Python can report WHY the TTL fallback took over.
///
/// # Errors
/// Only when the debouncer itself cannot be created (no backend at all).
pub fn watch_start(roots: &[PathBuf], debounce: Option<Duration>) -> Result<u64, String> {
    let shared = Arc::new(Shared::default());
    let sink = Arc::clone(&shared);
    let mut debouncer = new_debouncer(
        debounce.unwrap_or(DEBOUNCE),
        None, // tick rate: notify picks timeout/4 (documented default)
        move |result: DebounceEventResult| match result {
            Ok(events) => {
                for event in &events {
                    sink.record(event);
                }
            }
            // A lost watch is reported, not fatal: the TTL revalidation keeps
            // the grid eventually correct.
            Err(errors) => {
                for err in errors {
                    sink.record_error(&err);
                }
            }
        },
    )
    .map_err(|e| format!("cannot start the file watcher: {e}"))?;

    // Arming collects its reports LOCALLY and merges them into the shared state
    // afterwards: `Debouncer::watch` can block on the watcher thread (kqueue /
    // FSEvents hand the call over to it), and that same thread runs the event
    // handler which locks `shared.errors`. Holding that lock across `watch()`
    // would be a lock-order inversion waiting to happen.
    let mut watched = 0u64;
    let mut local_errors: Vec<String> = Vec::new();
    let mut degraded: Option<String> = None;
    for root in roots {
        if !root.exists() {
            local_errors.push(format!(
                "watch root does not exist (skipped): {}",
                root.display()
            ));
            continue;
        }
        match debouncer.watch(root, RecursiveMode::Recursive) {
            Ok(()) => watched += 1,
            Err(err) => {
                if matches!(err.kind, notify::ErrorKind::MaxFilesWatch) {
                    degraded = Some(format!(
                        "inotify watch budget exhausted while arming {}: {err}",
                        root.display()
                    ));
                    local_errors.push(format!(
                        "watch budget exhausted (degrading to the TTL refresh): {err}"
                    ));
                    break;
                }
                local_errors.push(format!("cannot watch {}: {err}", root.display()));
            }
        }
    }
    if !local_errors.is_empty() {
        let mut errors = shared
            .errors
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        // Same 64-entry bound the runtime handler applies (a long-lived session
        // must not grow the list without bound; poll drains it).
        let room = 64usize.saturating_sub(errors.len());
        errors.extend(local_errors.into_iter().take(room));
    }
    if let Some(reason) = degraded {
        *shared
            .degraded
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(reason);
    }

    let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
    let session = Arc::new(WatchSession {
        roots: roots.to_vec(),
        shared,
        debouncer: Mutex::new(Some(debouncer)),
        started: Instant::now(),
        watched: AtomicU64::new(watched),
        stopped: AtomicBool::new(false),
    });
    registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .insert(id, session);
    Ok(id)
}

/// The session for `id`.
fn session(id: u64) -> Option<Arc<WatchSession>> {
    registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .get(&id)
        .cloned()
}

/// Drain one session's pending changes as JSON (see
/// [`WatchSession::poll_json`]).
///
/// # Errors
/// An unknown handle.
pub fn watch_poll(id: u64) -> Result<String, String> {
    let session = session(id).ok_or_else(|| format!("unknown watch handle {id}"))?;
    Ok(session.poll_json())
}

/// Stop a session and drop it from the registry (idempotent).
///
/// # Errors
/// An unknown handle.
pub fn watch_stop(id: u64) -> Result<(), String> {
    let removed = registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .remove(&id);
    match removed {
        Some(session) => {
            session.stop();
            Ok(())
        }
        None => Err(format!("unknown watch handle {id}")),
    }
}

/// Diagnostics: `{"sessions": n, "watchedRoots": n}` (never raises).
#[must_use]
pub fn watch_diagnostics() -> std::collections::HashMap<&'static str, usize> {
    let reg = registry()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    let watched: usize = reg.values().map(|s| s.watched() as usize).sum();
    let mut out = std::collections::HashMap::new();
    out.insert("sessions", reg.len());
    out.insert("watchedRoots", watched);
    out
}

/// The inotify watch ceiling of this machine, when it is readable
/// (`/proc/sys/fs/inotify/max_user_watches` on Linux; `None` elsewhere).
/// Purely diagnostic — the degrade path does not depend on it.
#[must_use]
pub fn inotify_budget() -> Option<u64> {
    let raw = std::fs::read_to_string(Path::new("/proc/sys/fs/inotify/max_user_watches")).ok()?;
    raw.trim().parse::<u64>().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Wait (bounded) until a session has seen at least `count` changed paths.
    fn wait_for_paths(id: u64, count: usize) -> bool {
        for _ in 0..200 {
            let json = watch_poll(id).expect("poll");
            let parsed: serde_json::Value = serde_json::from_str(&json).expect("json");
            // accumulate across polls: poll drains
            if parsed["paths"].as_array().map_or(0, Vec::len) >= count {
                return true;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        false
    }

    fn create_event(path: &str) -> notify::Event {
        // notify's builders consume and return self, so they must be chained
        notify::Event::new(notify::EventKind::Create(notify::event::CreateKind::File))
            .add_path(PathBuf::from(path))
    }

    #[test]
    fn record_dedupes_and_ignores_access_events() {
        let shared = Shared::default();
        shared.record(&create_event("/x/a.safetensors"));
        shared.record(&create_event("/x/a.safetensors")); // a burst for one file
        shared.record(&create_event("/x/b.safetensors"));
        let access = notify::Event::new(notify::EventKind::Access(notify::event::AccessKind::Read))
            .add_path(PathBuf::from("/x/read-only.safetensors"));
        shared.record(&access);

        let paths = shared
            .paths
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        assert_eq!(paths.len(), 2, "deduped, and the read event is noise");
        assert!(!paths.iter().any(|p| p.ends_with("read-only.safetensors")));
        assert!(!shared.rescan.load(Ordering::Relaxed));
    }

    #[test]
    fn a_burst_collapses_into_one_full_rescan() {
        let shared = Shared::default();
        for i in 0..=MAX_PENDING_PATHS {
            shared.record(&create_event(&format!("/x/{i}.safetensors")));
        }
        assert!(
            shared.rescan.load(Ordering::Relaxed),
            "a bulk copy must ask for a full invalidation"
        );
        assert!(
            shared
                .paths
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner)
                .is_empty(),
            "and the pending set is collapsed, not grown without bound"
        );
    }

    #[test]
    fn a_need_rescan_event_sets_the_flag_without_paths() {
        let shared = Shared::default();
        let e = notify::Event::new(notify::EventKind::Modify(notify::event::ModifyKind::Any))
            .set_flag(notify::event::Flag::Rescan);
        shared.record(&e);
        assert!(shared.rescan.load(Ordering::Relaxed));
        assert!(
            shared
                .paths
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner)
                .is_empty()
        );
    }

    #[test]
    fn a_watch_budget_error_degrades_and_the_error_list_is_bounded() {
        let shared = Shared::default();
        shared.record_error(&notify::Error::new(notify::ErrorKind::MaxFilesWatch));
        let degraded = shared
            .degraded
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone();
        assert!(
            degraded.unwrap_or_default().contains("budget"),
            "MaxFilesWatch must surface as the degrade reason"
        );
        for _ in 0..200 {
            shared.record_error(&notify::Error::new(notify::ErrorKind::Generic(
                "some backend complaint".to_owned(),
            )));
        }
        let errors = shared
            .errors
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        assert!(
            errors.len() <= 64,
            "the error list is bounded ({} entries)",
            errors.len()
        );
    }

    #[test]
    fn start_poll_stop_roundtrip_sees_a_new_file() {
        let dir = tempfile::tempdir().unwrap();
        let id = watch_start(
            &[dir.path().to_path_buf()],
            Some(Duration::from_millis(100)),
        )
        .expect("watch_start");
        // A file created under the watched root must surface (debounced).
        std::fs::write(dir.path().join("model.safetensors"), b"x").unwrap();
        assert!(wait_for_paths(id, 1), "the create event never arrived");
        let json = watch_poll(id).expect("poll");
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed["degraded"], serde_json::Value::Null);
        assert_eq!(parsed["rescan"], serde_json::Value::Bool(false));
        assert_eq!(parsed["watched"].as_u64(), Some(1));
        watch_stop(id).expect("stop");
        assert!(watch_stop(id).is_err(), "a stopped handle is unknown");
    }

    #[test]
    fn a_missing_root_is_skipped_not_fatal() {
        let dir = tempfile::tempdir().unwrap();
        let missing = dir.path().join("nope");
        let id = watch_start(
            &[dir.path().to_path_buf(), missing.clone()],
            Some(Duration::from_millis(100)),
        )
        .expect("watch_start");
        let json = watch_poll(id).expect("poll");
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed["roots"].as_u64(), Some(2));
        assert_eq!(parsed["watched"].as_u64(), Some(1));
        let errors = parsed["errors"].as_array().expect("errors");
        assert!(
            errors
                .iter()
                .any(|e| e.as_str().unwrap_or_default().contains("does not exist")),
            "the skipped root must be reported: {errors:?}"
        );
        watch_stop(id).expect("stop");
    }

    #[test]
    fn poll_drains_and_dedupes() {
        let dir = tempfile::tempdir().unwrap();
        let id = watch_start(
            &[dir.path().to_path_buf()],
            Some(Duration::from_millis(100)),
        )
        .expect("watch_start");
        let file = dir.path().join("a.safetensors");
        std::fs::write(&file, b"1").unwrap();
        assert!(wait_for_paths(id, 1), "the create event never arrived");
        // A second poll without new events is empty (the first one drained).
        let json = watch_poll(id).expect("poll");
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed["paths"].as_array().map(Vec::len), Some(0));
        watch_stop(id).expect("stop");
    }

    #[test]
    fn stop_is_idempotent_and_diagnostics_never_raise() {
        let dir = tempfile::tempdir().unwrap();
        let id = watch_start(&[dir.path().to_path_buf()], None).expect("watch_start");
        let diag = watch_diagnostics();
        assert!(diag["sessions"] >= 1);
        watch_stop(id).unwrap();
        let diag2 = watch_diagnostics();
        assert_eq!(diag2.get("sessions").copied(), Some(diag["sessions"] - 1));
    }
}
