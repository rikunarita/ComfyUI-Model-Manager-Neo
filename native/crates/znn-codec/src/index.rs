//! Persistent front-matter index (Phase 5, Plan §4.7.1‑3 / §4.8‑B3).
//!
//! The library scan re-reads every model's `.md` sidecar header on every
//! refresh to recover `modelPage` / `website` / `hashes.SHA256` / `baseModel`
//! (the four values that drive the "open model page" logo, the duplicate
//! warning and the download-dialog base-model check). `py/manager.py` already
//! caches that parse against `(mtime_ns, size)` in `_SITE_CACHE`, but the
//! cache is **process-local**: every ComfyUI restart pays the full re-parse of
//! the whole library again (the "it takes ~20 s until the grid settles" cost
//! on network storage — Plan §1.2.2 #9).
//!
//! This module makes that cache **persistent** (Plan §4.7.1‑3): a `bincode`
//! snapshot of `(path, mtime_ns, size) → parsed 4-tuple`, guarded by a `blake3`
//! checksum and swapped in atomically (tempfile → fsync → rename, Plan §4.4.4).
//! It is pure *derived* data: a missing / corrupt / checksum-mismatched /
//! stale-entry snapshot is never an error — the affected entries simply miss
//! and are re-parsed, and a wholly unreadable file starts an empty index that
//! the next scan repopulates (Plan §7 R7 "常に派生データ → 自動全再構築").
//!
//! Design notes:
//! * the index is keyed by the sidecar's absolute path; validity is the
//!   `(mtime_ns, size)` pair, exactly like `_SITE_CACHE` (a touched sidecar
//!   re-parses, an untouched one is a hit across restarts);
//! * interior mutability (`RwLock`) so a single process-wide index can be
//!   shared by the parallel scan (`rayon`) — hits take a read lock, a miss
//!   parses OUTSIDE the lock and then upgrades to write;
//! * the on-disk generation counter is bumped on every save so a future
//!   differential payload (`?since=<gen>`, Plan §4.7.2‑3) has a handle.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, RwLock};

use bincode::{Decode, Encode};

use crate::safetensors_io::{fsync_dir, tmp_sibling};

/// On-disk magic — a format tag so an unrelated file at the index path is
/// never mistaken for a snapshot (it would fail the checksum anyway, but the
/// magic gives a cheaper, clearer reject).
const MAGIC: &[u8; 8] = b"MMIDX001";
/// blake3 digest length.
const CHECKSUM_LEN: usize = 32;

/// The four front-matter values the scan recovers, plus the validity stamp.
///
/// `Option<String>` mirrors `py/manager.py _model_site_info_of`'s parsed
/// tuple: a value is `None` when the key is absent OR fails the same shape
/// check Python applies (e.g. `modelPage` must be a string starting with
/// `http`). Encoding is `bincode` (compact, schema-less — the struct IS the
/// schema), so adding a field later changes the layout and an old snapshot
/// fails to decode → empty index → full re-parse (the intended graceful
/// degradation, never a wrong value).
#[derive(Encode, Decode, Clone, Debug, Default, PartialEq, Eq)]
pub struct SiteRecord {
    /// `st_mtime_ns` of the sidecar when it was parsed (validity stamp).
    pub mtime_ns: i64,
    /// `st_size` of the sidecar when it was parsed (validity stamp).
    pub size: u64,
    /// `modelPage` (only when it is a string starting with `http`).
    pub page: Option<String>,
    /// `website` → the platform name (non-empty string).
    pub platform: Option<String>,
    /// `hashes.SHA256`, upper-cased (non-empty string).
    pub sha: Option<String>,
    /// `baseModel` (non-empty string).
    pub base: Option<String>,
}

/// The serialised snapshot: a generation counter + the entries as an owned
/// `Vec` (bincode has no map type; a vec of pairs round-trips deterministically
/// once sorted, which also makes the on-disk bytes stable for a given state).
#[derive(Encode, Decode)]
struct Snapshot {
    generation: u64,
    entries: Vec<(String, SiteRecord)>,
}

/// A process-wide, optionally persistent front-matter cache.
///
/// Cheap to clone-by-reference (`Arc<SiteIndex>`); the scan takes `&SiteIndex`
/// and the registry in `mm-core` owns the single instance per index directory.
pub struct SiteIndex {
    map: RwLock<HashMap<PathBuf, SiteRecord>>,
    /// Snapshot file (`…/mm-scan-index.bin`); `None` = memory-only (tests, or
    /// when Python passes no index directory).
    file: Option<PathBuf>,
    /// Set when an entry was inserted/refreshed since the last save, so
    /// `save()` is a no-op on a read-only scan (no needless rewrite/fsync).
    dirty: AtomicBool,
    generation: Mutex<u64>,
}

impl SiteIndex {
    /// Open (or start) the index for `dir`.
    ///
    /// `dir` is the extension-data directory Python owns (Plan §4.7.1‑3
    /// "拡張データ dir"); the snapshot lives at `dir/mm-scan-index.bin`. A
    /// `None` dir yields a memory-only index. Any load failure (missing file,
    /// bad magic, checksum mismatch, decode error) degrades to an EMPTY index
    /// — derived data is always rebuildable (Plan §7 R7), so a corrupt snapshot
    /// is never surfaced as an error.
    #[must_use]
    pub fn open(dir: Option<&Path>) -> Self {
        let file = dir.map(|d| d.join("mm-scan-index.bin"));
        let (map, generation) = match &file {
            Some(path) => Self::load(path).unwrap_or_default(),
            None => (HashMap::new(), 0),
        };
        Self {
            map: RwLock::new(map),
            file,
            dirty: AtomicBool::new(false),
            generation: Mutex::new(generation),
        }
    }

    /// A memory-only index (tests; no persistence).
    #[must_use]
    pub fn ephemeral() -> Self {
        Self {
            map: RwLock::new(HashMap::new()),
            file: None,
            dirty: AtomicBool::new(false),
            generation: Mutex::new(0),
        }
    }

    /// The cached record for `path` when its `(mtime_ns, size)` still match —
    /// the exact validity rule of `_SITE_CACHE`. `None` on a miss or a stale
    /// stamp (the caller then re-parses and calls [`insert`](Self::insert)).
    #[must_use]
    pub fn lookup(&self, path: &Path, mtime_ns: i64, size: u64) -> Option<SiteRecord> {
        let map = self
            .map
            .read()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let hit = map.get(path)?;
        if hit.mtime_ns == mtime_ns && hit.size == size {
            Some(hit.clone())
        } else {
            None
        }
    }

    /// Record a freshly-parsed sidecar (marks the index dirty for the next
    /// [`save`](Self::save)).
    pub fn insert(&self, path: PathBuf, rec: SiteRecord) {
        {
            let mut map = self
                .map
                .write()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            map.insert(path, rec);
        }
        self.dirty.store(true, Ordering::Relaxed);
    }

    /// Number of cached entries (diagnostics / tests).
    #[must_use]
    pub fn len(&self) -> usize {
        self.map
            .read()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .len()
    }

    /// True when empty (clippy `len`/`is_empty` pairing).
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// The current generation counter (0 for a fresh/memory-only index).
    #[must_use]
    pub fn generation(&self) -> u64 {
        *self
            .generation
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    /// Persist the snapshot atomically when dirty (Plan §4.4.4: tempfile →
    /// fsync → rename → dir fsync). A no-op when memory-only or clean. Save
    /// failures are swallowed (with the reason returned for logging) — the
    /// index is an optimisation, never a correctness dependency, so a full or
    /// read-only data directory must not fail a scan.
    ///
    /// # Errors
    /// Only reports I/O failures for logging; the caller decides (the scan
    /// logs and continues).
    pub fn save(&self) -> std::io::Result<()> {
        let Some(path) = self.file.clone() else {
            return Ok(()); // memory-only
        };
        if !self.dirty.swap(false, Ordering::Relaxed) {
            return Ok(()); // nothing changed since the last save
        }
        // Snapshot the map under the read lock, then serialise outside it.
        let entries: Vec<(String, SiteRecord)> = {
            let map = self
                .map
                .read()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            let mut v: Vec<(String, SiteRecord)> = map
                .iter()
                .map(|(k, v)| (k.to_string_lossy().into_owned(), v.clone()))
                .collect();
            // Sort for deterministic bytes (a given state always serialises
            // identically — nice for diffing and for blake3 stability).
            v.sort_by(|a, b| a.0.cmp(&b.0));
            v
        };
        let generation = {
            let mut g = self
                .generation
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            *g = g.wrapping_add(1);
            *g
        };
        let snapshot = Snapshot {
            generation,
            entries,
        };
        let config = bincode::config::standard();
        let payload = bincode::encode_to_vec(&snapshot, config).map_err(|e| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("index encode: {e}"),
            )
        })?;
        let checksum = blake3::hash(&payload);

        let mut bytes = Vec::with_capacity(MAGIC.len() + CHECKSUM_LEN + 8 + payload.len());
        bytes.extend_from_slice(MAGIC);
        bytes.extend_from_slice(checksum.as_bytes());
        bytes.extend_from_slice(&(payload.len() as u64).to_le_bytes());
        bytes.extend_from_slice(&payload);

        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let tmp = tmp_sibling(&path);
        {
            let mut f = std::fs::File::create(&tmp)?;
            f.write_all(&bytes)?;
            f.sync_all()?; // durability before the rename (Plan §4.4.4)
        }
        std::fs::rename(&tmp, &path)?;
        if let Some(parent) = path.parent() {
            let _ = fsync_dir(parent); // best-effort: the rename is the commit point
        }
        Ok(())
    }

    /// Load a snapshot; `None`-ish failures yield an empty index. Returns the
    /// entries and the stored generation.
    fn load(path: &Path) -> Option<(HashMap<PathBuf, SiteRecord>, u64)> {
        let mut bytes = Vec::new();
        std::fs::File::open(path)
            .ok()?
            .read_to_end(&mut bytes)
            .ok()?;
        if bytes.len() < MAGIC.len() + CHECKSUM_LEN + 8 || &bytes[..MAGIC.len()] != MAGIC {
            return None; // not ours (or truncated) → rebuild
        }
        let mut off = MAGIC.len();
        let stored: [u8; CHECKSUM_LEN] = bytes[off..off + CHECKSUM_LEN].try_into().ok()?;
        off += CHECKSUM_LEN;
        let len_bytes: [u8; 8] = bytes[off..off + 8].try_into().ok()?;
        off += 8;
        let payload_len = u64::from_le_bytes(len_bytes) as usize;
        if payload_len != bytes.len() - off {
            return None; // length header disagrees with the file → rebuild
        }
        let payload = &bytes[off..];
        if blake3::hash(payload).as_bytes() != &stored {
            return None; // checksum mismatch (corruption) → rebuild (Plan §7 R7)
        }
        let config = bincode::config::standard();
        let (snapshot, _read): (Snapshot, usize) =
            bincode::decode_from_slice(payload, config).ok()?;
        let map = snapshot
            .entries
            .into_iter()
            .map(|(k, v)| (PathBuf::from(k), v))
            .collect();
        Some((map, snapshot.generation))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rec(mtime: i64, size: u64, page: &str) -> SiteRecord {
        SiteRecord {
            mtime_ns: mtime,
            size,
            page: Some(page.to_owned()),
            platform: Some("civitai".to_owned()),
            sha: Some("ABCD".to_owned()),
            base: Some("SD 1.5".to_owned()),
        }
    }

    #[test]
    fn lookup_requires_an_exact_mtime_and_size_match() {
        let idx = SiteIndex::ephemeral();
        let p = PathBuf::from("/lib/m.md");
        idx.insert(p.clone(), rec(100, 42, "https://x"));
        assert_eq!(
            idx.lookup(&p, 100, 42).map(|r| r.page),
            Some(Some("https://x".to_owned()))
        );
        // a stale stamp misses (the sidecar changed) → caller re-parses
        assert!(idx.lookup(&p, 101, 42).is_none());
        assert!(idx.lookup(&p, 100, 43).is_none());
        assert!(
            idx.lookup(&PathBuf::from("/lib/other.md"), 100, 42)
                .is_none()
        );
    }

    #[test]
    fn round_trips_through_disk_with_a_checksum() {
        let dir = tempfile::tempdir().unwrap();
        let idx = SiteIndex::open(Some(dir.path()));
        idx.insert(PathBuf::from("/lib/a.md"), rec(1, 10, "https://a"));
        idx.insert(PathBuf::from("/lib/b.md"), rec(2, 20, "https://b"));
        assert_eq!(idx.len(), 2);
        idx.save().unwrap();
        assert!(dir.path().join("mm-scan-index.bin").exists());

        // reopen: the entries survive the restart (the whole point of B3)
        let reloaded = SiteIndex::open(Some(dir.path()));
        assert_eq!(reloaded.len(), 2);
        assert_eq!(
            reloaded
                .lookup(Path::new("/lib/a.md"), 1, 10)
                .map(|r| r.page),
            Some(Some("https://a".to_owned()))
        );
        assert!(reloaded.generation() >= 1, "generation advanced on save");

        // a clean reopen does not rewrite (not dirty)
        let before = std::fs::read(dir.path().join("mm-scan-index.bin")).unwrap();
        reloaded.save().unwrap();
        let after = std::fs::read(dir.path().join("mm-scan-index.bin")).unwrap();
        assert_eq!(before, after, "a clean index save is a no-op");
    }

    #[test]
    fn a_corrupt_snapshot_rebuilds_empty_never_errors() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("mm-scan-index.bin");
        // garbage that is not even our magic
        std::fs::write(&path, b"not an index at all, definitely not").unwrap();
        let idx = SiteIndex::open(Some(dir.path()));
        assert!(
            idx.is_empty(),
            "unreadable snapshot → empty index (Plan §7 R7)"
        );

        // a valid-magic-but-corrupt payload also degrades to empty
        let mut bad = Vec::new();
        bad.extend_from_slice(MAGIC);
        bad.extend_from_slice(&[0u8; CHECKSUM_LEN]); // wrong checksum
        bad.extend_from_slice(&0u64.to_le_bytes());
        std::fs::write(&path, &bad).unwrap();
        let idx2 = SiteIndex::open(Some(dir.path()));
        assert!(idx2.is_empty(), "checksum mismatch → empty index");
    }

    #[test]
    fn truncated_snapshot_rebuilds_empty() {
        let dir = tempfile::tempdir().unwrap();
        let idx = SiteIndex::open(Some(dir.path()));
        idx.insert(PathBuf::from("/lib/a.md"), rec(1, 10, "https://a"));
        idx.save().unwrap();
        let path = dir.path().join("mm-scan-index.bin");
        let full = std::fs::read(&path).unwrap();
        // chop the payload so the length header disagrees
        std::fs::write(&path, &full[..full.len() - 3]).unwrap();
        let idx2 = SiteIndex::open(Some(dir.path()));
        assert!(idx2.is_empty(), "length mismatch → empty index");
    }

    #[test]
    fn memory_only_index_never_touches_disk() {
        let idx = SiteIndex::open(None);
        idx.insert(PathBuf::from("/lib/a.md"), rec(1, 10, "https://a"));
        assert!(idx.save().is_ok(), "memory-only save is a harmless no-op");
        assert_eq!(
            idx.generation(),
            0,
            "memory-only never advances the on-disk generation"
        );
    }
}
