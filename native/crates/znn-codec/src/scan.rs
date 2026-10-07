//! Library scan + hygiene scan (Phase 5).
//!
//! The Rust port of `py/manager.py ModelManager.scan_models()` and
//! `scan_hygiene()`: a PARALLEL directory walk (`rayon`, the `ignore`
//! family) that resolves previews against a zero-stat directory name set,
//! parses the `.md` front-matter (through the persistent [`SiteIndex`]),
//! stats each entry and serialises the EXACT JSON shape the current Python
//! route returns — so the frontend needs no change and the two engines are
//! golden-identical ("現行 JSON 形状 golden テスト").
//!
//! Faithfulness notes (every rule mirrors the Python it replaces):
//! * **entry set** — a file is collected iff its `os.path.splitext` extension
//!   is in `supported_pt_extensions` (a CASE-SENSITIVE membership test, exactly
//!   like `folder_paths`); directories are always collected (and recursed);
//!   hidden (`.`-prefixed) entries are skipped unless `include_hidden`, but
//!   their NAMES still land in the directory's name set (preview resolution
//!   sees them — `manager.py` adds the name before the hidden `continue`);
//! * **symlinks** — `scan_models` FOLLOWS directory symlinks (the Python
//!   recursion calls `os.scandir(entry.path)`, which follows), with a
//!   canonical-path `visited` guard so a cyclic symlink cannot hang the walk
//!   (a robustness improvement; the Python recursion would `RecursionError`).
//!   `scan_hygiene` does NOT follow them (it mirrors `os.walk(followlinks=False)`);
//! * **preview** — the 20-slot × 8-extension candidate scheme
//!   (`batch::preview_candidate_names`, the single source shared with the
//!   sidecar mover), resolved against the directory name set: none →
//!   `NO_PREVIEW_URL`, one → a bare string, many → an array (the historic
//!   single-vs-gallery shape consumers compare with `===`);
//! * **front-matter** — `_model_site_info_of`'s 4 KB head read + the
//!   `\A---\r?\n(.*?)\r?\n---\r?\n` block + the exact shape checks
//!   (`modelPage` must start with `http`; the others are stored UNTRIMMED but
//!   only when their `.strip()` is non-empty; `SHA256` is upper-cased);
//! * **timestamps** — `createdAt = round(st_ctime_ns / 1e6)`,
//!   `updatedAt = round(st_mtime_ns / 1e6)`, reproducing Python's
//!   round-half-to-even float division bit-for-bit (`f64::round_ties_even`);
//! * **order** — entries are sorted by `(pathIndex, path)` so the listing is
//!   fully deterministic between refreshes ("安定順序"); the
//!   Python reference sorts identically, so the two agree entry-for-entry.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use rayon::prelude::*;
use serde::Serialize;
use yaml_rust2::YamlLoader;

use crate::batch::{preview_candidate_names, py_splitext};
use crate::index::{SiteIndex, SiteRecord};

// ---------------------------------------------------------------------------
// Options (every naming constant arrives from Python — py/utils.py and
// folder_paths stay the single source of truth).
// ---------------------------------------------------------------------------

/// Configuration of one [`scan_models`] call (one model type).
pub struct ScanOpts {
    /// The model type name (the `type` field of every entry, and the preview
    /// URL segment).
    pub model_type: String,
    /// The type's base folders, in `pathIndex` order (`folder_names_and_paths`).
    pub roots: Vec<PathBuf>,
    /// Include `.`-prefixed entries (the `model_list.include_hidden_files`
    /// setting).
    pub include_hidden: bool,
    /// `folder_paths.supported_pt_extensions` (case-sensitive membership).
    pub extensions: HashSet<String>,
    /// `utils.NO_PREVIEW_URL` (`/model-manager/no-preview.svg`).
    pub no_preview_url: String,
    /// The preview route prefix (`/model-manager/preview`).
    pub preview_url_prefix: String,
    /// The persistent front-matter cache. `None` = parse every
    /// sidecar each scan (still correct, just not cached across restarts).
    pub index: Option<Arc<SiteIndex>>,
}

/// Configuration of one [`scan_hygiene`] call (all model types).
pub struct HygieneOpts {
    /// `resolve_model_base_paths()` as an ORDERED list (the type iteration
    /// order of `folder_names_and_paths`), so the report groups by type exactly
    /// like the Python walk.
    pub base_paths: Vec<(String, Vec<PathBuf>)>,
    /// `folder_paths.supported_pt_extensions`.
    pub extensions: HashSet<String>,
}

// ---------------------------------------------------------------------------
// JSON wire shapes (field order = the Python dict insertion order; serde_json
// writes struct fields in declaration order, so the two match).
// ---------------------------------------------------------------------------

/// One entry of the `GET /models/{folder}` listing.
#[derive(Serialize, Debug, Clone, PartialEq)]
#[serde(rename_all = "camelCase")]
struct ScanEntry {
    #[serde(rename = "type")]
    model_type: String,
    sub_folder: String,
    is_folder: bool,
    basename: String,
    extension: String,
    path_index: usize,
    size_bytes: u64,
    /// `null` (folder), a bare string (0 or 1 preview) or an array (gallery) —
    /// the historic single-vs-list shape.
    preview: serde_json::Value,
    model_page: Option<String>,
    model_platform: Option<String>,
    model_sha256: Option<String>,
    model_base: Option<String>,
    created_at: i64,
    updated_at: i64,
}

/// One orphaned sidecar of the hygiene report.
#[derive(Serialize, Debug, Clone, PartialEq)]
#[serde(rename_all = "camelCase")]
struct Orphan {
    #[serde(rename = "type")]
    model_type: String,
    path_index: usize,
    fullname: String,
    size_bytes: u64,
}

/// One empty folder of the hygiene report.
#[derive(Serialize, Debug, Clone, PartialEq)]
#[serde(rename_all = "camelCase")]
struct EmptyFolder {
    #[serde(rename = "type")]
    model_type: String,
    path_index: usize,
    fullname: String,
    size_bytes: u64,
}

/// The `GET /model-manager/hygiene` payload.
#[derive(Serialize, Debug, Clone, PartialEq)]
struct HygieneReport {
    orphans: Vec<Orphan>,
    empty: Vec<EmptyFolder>,
}

// ---------------------------------------------------------------------------
// Path helpers (faithful ports of py/utils.py normalize_path / splitext).
// ---------------------------------------------------------------------------

/// `os.sep → "/"` (Windows path strings use `\`; the wire format is always
/// forward-slashed). The bases arrive already `normpath`-clean from
/// `resolve_model_base_paths`, and walk paths are `base.join(name)`, so no
/// `.`/`..`/duplicate-separator collapsing is needed (it would be identity).
fn normalize_seps(s: &str) -> String {
    if s.contains('\\') {
        s.replace('\\', "/")
    } else {
        s.to_owned()
    }
}

/// `os.path.dirname` / `os.path.basename` of a forward-slashed relative path.
fn split_rel(rel: &str) -> (&str, &str) {
    match rel.rsplit_once('/') {
        Some((dir, file)) => (dir, file),
        None => ("", rel),
    }
}

/// `(st_ctime_ns, st_mtime_ns)` — matching Python's `st_ctime_ns`/`st_mtime_ns`
/// on EVERY platform (Linux/macOS `ctime` via the OS-specific `MetadataExt`;
/// Windows `ctime` IS the creation time, so `created()`).
#[cfg(target_os = "linux")]
fn stat_times_ns(meta: &fs::Metadata) -> (i64, i64) {
    use std::os::linux::fs::MetadataExt;
    (
        meta.st_ctime()
            .wrapping_mul(1_000_000_000)
            .wrapping_add(meta.st_ctime_nsec()),
        meta.st_mtime()
            .wrapping_mul(1_000_000_000)
            .wrapping_add(meta.st_mtime_nsec()),
    )
}
#[cfg(target_os = "macos")]
fn stat_times_ns(meta: &fs::Metadata) -> (i64, i64) {
    use std::os::macos::fs::MetadataExt;
    (
        meta.st_ctime()
            .wrapping_mul(1_000_000_000)
            .wrapping_add(meta.st_ctime_nsec()),
        meta.st_mtime()
            .wrapping_mul(1_000_000_000)
            .wrapping_add(meta.st_mtime_nsec()),
    )
}
#[cfg(not(any(target_os = "linux", target_os = "macos")))]
fn stat_times_ns(meta: &fs::Metadata) -> (i64, i64) {
    // Windows: Python's st_ctime is the CREATION time; other non-linux/macos
    // unix (not a CI target) fall back to modified() for both — the scan stays
    // correct, only the created/modified distinction is approximate there.
    let to_ns = |t: std::io::Result<std::time::SystemTime>| -> i64 {
        t.ok()
            .and_then(|s| s.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_nanos() as i64)
            .unwrap_or(0)
    };
    #[cfg(windows)]
    let c = to_ns(meta.created());
    #[cfg(not(windows))]
    let c = to_ns(meta.modified());
    let m = to_ns(meta.modified());
    (c, m)
}

/// `round(ns / 1e6)` bit-for-bit as CPython computes it (`py/manager.py`:
/// `round(stat.st_ctime_ns / 1000000)` for createdAt/updatedAt).
///
/// CPython's `int / int` is a CORRECTLY ROUNDED f64 of the exact rational
/// quotient, and `round()` on that float is half-to-even. The naive
/// `(ns as f64) / 1e6` is NOT the same: epoch nanoseconds exceed 2^53, so
/// `ns as f64` first quantises to a 256 ns grid and the half-to-even decision
/// flips for quotients within ~1.3e-4 of a `.5` boundary — about 1 in 10,000
/// timestamps off by one ms (the 2026-10-07 macOS CI golden-parity flake in
/// `test_scan_survives_a_non_utf8_sidecar`: updatedAt …337 vs …338).
///
/// The integer split below is provably identical to CPython for every i64:
/// `q` (|q| < 2^53) and `r` (< 1e6) are exact in f64; the inner rounding of
/// `r/1e6` (≤ 2^-54) can never move the sum across the outer f64 grid's
/// decision midpoints because `r/1e6` sits ≥ 1/(1e6·2^13) away from every
/// midpoint (its denominator 1e6 shares only 2^6 with the 2^13 grid, and an
/// odd numerator can never cancel that); the one exact tie `r == 500_000`
/// forms `q + 0.5`, itself exact in f64, where both paths round half-to-even.
/// `div_euclid`/`rem_euclid` floor like Python's `divmod`, so negative `ns`
/// (pre-epoch mtimes) round identically too. Cross-checked against CPython on
/// 3M random values (modern-epoch, negative, small and 2^53-boundary ranges)
/// plus the i64 extremes: zero divergence (the naive form: 41).
fn ns_to_ms(ns: i64) -> i64 {
    let q = ns.div_euclid(1_000_000);
    let r = ns.rem_euclid(1_000_000);
    ((q as f64) + (r as f64) / 1_000_000.0).round_ties_even() as i64
}

// ---------------------------------------------------------------------------
// The parallel walk (scan_models)
// ---------------------------------------------------------------------------

struct RawEntry {
    path: PathBuf,
    /// `normalize_seps(path)` — the sort key (matches Python's
    /// `normalize_path(entry.path)`), also reused to derive the relative path.
    norm: String,
    path_index: usize,
}

struct Walker<'a> {
    opts: &'a ScanOpts,
    entries: Mutex<Vec<RawEntry>>,
    dir_names: Mutex<HashMap<PathBuf, HashSet<String>>>,
    /// Canonical paths of directories entered through a SYMLINK (cycle guard).
    visited_symlink_targets: Mutex<HashSet<PathBuf>>,
}

impl<'a> Walker<'a> {
    fn walk(&self, dir: &Path, path_index: usize) {
        let rd = match fs::read_dir(dir) {
            Ok(rd) => rd,
            Err(_) => return, // unreadable / vanished → empty, like os.path.exists guard
        };
        let mut names: HashSet<String> = HashSet::new();
        let mut local: Vec<RawEntry> = Vec::new();
        let mut subdirs: Vec<(PathBuf, bool)> = Vec::new(); // (path, is_symlink)

        for entry in rd.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            names.insert(name.clone()); // EVERY name (hidden too) — preview resolution sees it
            if !self.opts.include_hidden && name.starts_with('.') {
                continue; // hidden: in the name set, but not an entry (and not recursed)
            }
            let path = entry.path();
            // DirEntry.is_file()/is_dir() FOLLOW symlinks; file_type() does not.
            let is_symlink = entry.file_type().map(|t| t.is_symlink()).unwrap_or(false);
            let meta = fs::metadata(&path); // follows symlinks
            let is_file = meta.as_ref().map(|m| m.is_file()).unwrap_or(false);
            let is_dir = meta.as_ref().map(|m| m.is_dir()).unwrap_or(false);
            if is_file {
                let ext = py_splitext(&name).1;
                if self.opts.extensions.contains(ext) {
                    local.push(RawEntry {
                        norm: normalize_seps(&path.to_string_lossy()),
                        path,
                        path_index,
                    });
                }
            } else {
                // Non-file (directory, symlink-to-dir, or a broken symlink):
                // collected as a FOLDER entry, recursed only when a real dir.
                local.push(RawEntry {
                    norm: normalize_seps(&path.to_string_lossy()),
                    path: path.clone(),
                    path_index,
                });
                if is_dir {
                    subdirs.push((path, is_symlink));
                }
            }
        }

        self.dir_names
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .insert(dir.to_path_buf(), names);
        self.entries
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .extend(local);

        subdirs.par_iter().for_each(|(sd, is_symlink)| {
            if *is_symlink {
                // Cycle / diamond guard for symlinked directories: enter a
                // given real target only once.
                let Ok(canon) = sd.canonicalize() else {
                    return; // broken symlink-to-dir: metadata said is_dir, but canon failed → skip
                };
                let fresh = self
                    .visited_symlink_targets
                    .lock()
                    .unwrap_or_else(std::sync::PoisonError::into_inner)
                    .insert(canon);
                if !fresh {
                    return;
                }
            }
            self.walk(sd, path_index);
        });
    }
}

/// Scan one model type into the listing JSON (the `GET /models/{folder}` body).
///
/// Returns a JSON array string in the exact shape the Python route returns;
/// an internal serialisation failure (impossible for these plain types)
/// degrades to `[]` rather than panicking.
#[must_use]
pub fn scan_models(opts: &ScanOpts) -> String {
    let walker = Walker {
        opts,
        entries: Mutex::new(Vec::new()),
        dir_names: Mutex::new(HashMap::new()),
        visited_symlink_targets: Mutex::new(HashSet::new()),
    };
    // Seed the symlink-target guard with the roots so a symlink back to a root
    // is skipped (never re-walked).
    {
        let mut visited = walker
            .visited_symlink_targets
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        for root in &opts.roots {
            if let Ok(c) = root.canonicalize() {
                visited.insert(c);
            }
        }
    }

    for (path_index, root) in opts.roots.iter().enumerate() {
        if !root.exists() {
            continue; // `if not os.path.exists(base_path): continue`
        }
        walker.walk(root, path_index);
    }

    let (mut entries, dir_names) = (
        std::mem::take(
            &mut *walker
                .entries
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner),
        ),
        std::mem::take(
            &mut *walker
                .dir_names
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner),
        ),
    );
    // Deterministic order: (pathIndex, path) — matches the Python reference's
    // per-base sort (安定順序).
    entries.sort_by(|a, b| {
        a.path_index
            .cmp(&b.path_index)
            .then_with(|| a.norm.cmp(&b.norm))
    });

    let base_prefixes: Vec<String> = opts
        .roots
        .iter()
        .map(|r| format!("{}/", normalize_seps(&r.to_string_lossy())))
        .collect();

    let results: Vec<ScanEntry> = entries
        .par_iter()
        .filter_map(|e| {
            let base_prefix = base_prefixes
                .get(e.path_index)
                .map(String::as_str)
                .unwrap_or("");
            process_entry(e, base_prefix, &dir_names, opts)
        })
        .collect();

    serde_json::to_string(&results).unwrap_or_else(|_| "[]".to_owned())
}

/// Build one entry (stat + preview + front-matter). `None` when the path
/// vanished or cannot be stat'd (the Python `os.path.exists` / `stat` guards).
fn process_entry(
    e: &RawEntry,
    base_prefix: &str,
    dir_names: &HashMap<PathBuf, HashSet<String>>,
    opts: &ScanOpts,
) -> Option<ScanEntry> {
    let meta = fs::metadata(&e.path).ok()?; // follows symlinks; gone/broken → skip
    let is_file = meta.is_file();

    let rel = e.norm.strip_prefix(base_prefix).unwrap_or(&e.norm);
    let (sub_folder, filename) = split_rel(rel);
    let (basename, extension) = if is_file {
        let (b, x) = py_splitext(filename);
        (b.to_owned(), x.to_owned())
    } else {
        (filename.to_owned(), String::new())
    };

    let parent = e.path.parent().unwrap_or_else(|| Path::new(""));
    let empty = HashSet::new();
    let names = dir_names.get(parent).unwrap_or(&empty);

    let preview = if is_file {
        resolve_preview(names, &basename, sub_folder, e.path_index, opts)
    } else {
        serde_json::Value::Null
    };
    let (model_page, model_platform, model_sha256, model_base) = if is_file {
        site_info(names, &basename, parent, opts)
    } else {
        (None, None, None, None)
    };

    let (ctime_ns, mtime_ns) = stat_times_ns(&meta);
    Some(ScanEntry {
        model_type: opts.model_type.clone(),
        sub_folder: sub_folder.to_owned(),
        is_folder: !is_file,
        basename,
        extension,
        path_index: e.path_index,
        size_bytes: if is_file { meta.len() } else { 0 },
        preview,
        model_page,
        model_platform,
        model_sha256,
        model_base,
        created_at: ns_to_ms(ctime_ns),
        updated_at: ns_to_ms(mtime_ns),
    })
}

/// `previews_in_names` → the preview field (null for a folder is handled by
/// the caller): `NO_PREVIEW_URL` when nothing matches, a bare string for one,
/// an array for a gallery.
fn resolve_preview(
    names: &HashSet<String>,
    basename: &str,
    sub_folder: &str,
    path_index: usize,
    opts: &ScanOpts,
) -> serde_json::Value {
    let present: Vec<String> = preview_candidate_names(basename)
        .into_iter()
        .filter(|c| names.contains(c))
        .collect();
    if present.is_empty() {
        return serde_json::Value::String(opts.no_preview_url.clone());
    }
    let urls: Vec<String> = present
        .iter()
        .map(|pn| {
            let rel = if sub_folder.is_empty() {
                pn.clone()
            } else {
                format!("{sub_folder}/{pn}")
            };
            format!(
                "{}/{}/{}/{}",
                opts.preview_url_prefix, opts.model_type, path_index, rel
            )
        })
        .collect();
    if urls.len() == 1 {
        serde_json::Value::String(urls.into_iter().next().expect("len 1"))
    } else {
        serde_json::Value::Array(urls.into_iter().map(serde_json::Value::String).collect())
    }
}

// ---------------------------------------------------------------------------
// Front-matter (the _model_site_info_of port) + the persistent index
// ---------------------------------------------------------------------------

/// `(modelPage, modelPlatform, modelSha256, modelBase)` of a model's `.md`
/// sidecar, or all-`None` when there is no sidecar / it does not parse.
fn site_info(
    names: &HashSet<String>,
    basename: &str,
    parent: &Path,
    opts: &ScanOpts,
) -> (
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
) {
    let md_name = format!("{basename}.md");
    if !names.contains(&md_name) {
        return (None, None, None, None);
    }
    let md_path = parent.join(&md_name);
    let Ok(meta) = fs::metadata(&md_path) else {
        return (None, None, None, None);
    };
    let (_ctime, mtime_ns) = stat_times_ns(&meta);
    let size = meta.len();

    // Persistent cache hit (validity = the same (mtime_ns, size) as _SITE_CACHE).
    if let Some(index) = &opts.index {
        if let Some(rec) = index.lookup(&md_path, mtime_ns, size) {
            return (rec.page, rec.platform, rec.sha, rec.base);
        }
    }

    let parsed = parse_frontmatter(&md_path);
    if let Some(index) = &opts.index {
        index.insert(
            md_path,
            SiteRecord {
                mtime_ns,
                size,
                page: parsed.0.clone(),
                platform: parsed.1.clone(),
                sha: parsed.2.clone(),
                base: parsed.3.clone(),
            },
        );
    }
    parsed
}

/// Read up to `max_chars` UTF-8 characters from the head of a file (Python's
/// `f.read(4096)` with `encoding="utf-8"`). Invalid UTF-8 degrades lossily
/// instead of raising (Python's `UnicodeDecodeError` would escape
/// `_model_site_info_of` and crash the scan — a latent bug we do not port).
fn read_head_chars(path: &Path, max_chars: usize) -> Option<String> {
    use std::io::Read;
    let mut f = fs::File::open(path).ok()?;
    // Worst case 4 bytes/char; +8 slack so the max_chars-th character is whole.
    let cap = max_chars.saturating_mul(4).saturating_add(8);
    let mut buf = vec![0u8; cap];
    let mut filled = 0;
    while filled < buf.len() {
        match f.read(&mut buf[filled..]) {
            Ok(0) => break,
            Ok(n) => filled += n,
            Err(ref e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(_) => break,
        }
    }
    buf.truncate(filled);
    let s = String::from_utf8_lossy(&buf);
    Some(s.chars().take(max_chars).collect())
}

/// Extract the YAML body of a `---\n…\n---\n` front-matter block, mirroring
/// `_MODEL_PAGE_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)`: the
/// capture is the MINIMAL text before the first `\r?\n---\r?\n` that follows
/// the opening `---\r?\n`.
fn extract_frontmatter_yaml(head: &str) -> Option<&str> {
    let after_open = head
        .strip_prefix("---\r\n")
        .or_else(|| head.strip_prefix("---\n"))?;
    let bytes = after_open.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        // Try to match `\r?\n---\r?\n` starting at i (i = end of the capture).
        let mut j = i;
        if bytes[j] == b'\r' {
            j += 1;
        }
        if j >= bytes.len() || bytes[j] != b'\n' {
            i += 1;
            continue;
        }
        j += 1;
        if !bytes[j..].starts_with(b"---") {
            i += 1;
            continue;
        }
        j += 3;
        if j < bytes.len() && bytes[j] == b'\r' {
            j += 1;
        }
        if j < bytes.len() && bytes[j] == b'\n' {
            return Some(&after_open[..i]); // minimal capture
        }
        // A `---` not followed by a newline is not the closing fence; keep going.
        i += 1;
    }
    None
}

/// Parse the four front-matter values, applying the EXACT shape checks of
/// `_model_site_info_of` (values are stored untrimmed except SHA256 which is
/// upper-cased; the `.strip()`/`startswith` tests only gate whether they are
/// kept).
fn parse_frontmatter(
    path: &Path,
) -> (
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
) {
    let none = (None, None, None, None);
    let Some(head) = read_head_chars(path, 4096) else {
        return none;
    };
    let Some(yaml_src) = extract_frontmatter_yaml(&head) else {
        return none;
    };
    let docs = match YamlLoader::load_from_str(yaml_src) {
        Ok(d) => d,
        Err(_) => return none, // PyYAML `except Exception: return None`
    };
    let Some(doc) = docs.first() else {
        return none;
    };
    // yaml-rust2 coerces scalars like PyYAML's safe_load; `.as_str()` is Some
    // only for a genuine string, matching Python's `isinstance(x, str)`.
    let page = doc["modelPage"]
        .as_str()
        .filter(|s| s.starts_with("http"))
        .map(str::to_owned);
    let platform = doc["website"]
        .as_str()
        .filter(|s| !s.trim().is_empty())
        .map(str::to_owned);
    let sha = doc["hashes"]["SHA256"]
        .as_str()
        .filter(|s| !s.trim().is_empty())
        .map(|s| s.to_uppercase());
    let base = doc["baseModel"]
        .as_str()
        .filter(|s| !s.trim().is_empty())
        .map(str::to_owned);
    (page, platform, sha, base)
}

// ---------------------------------------------------------------------------
// Hygiene scan (the scan_hygiene port; os.walk(followlinks=False) semantics)
// ---------------------------------------------------------------------------

/// The preview/notes extensions that make a file a SIDECAR for the orphan test
/// (`utils.PREVIEW_EXTENSIONS` + `.md`/`.txt`). Compared case-sensitively for
/// previews (the Python `ext in PREVIEW_EXTENSIONS`) and by suffix for notes.
const PREVIEW_EXT_SET: &[&str] = &[
    ".webm", ".mp4", ".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
];

fn is_sidecar_name(name: &str) -> bool {
    let ext = py_splitext(name).1;
    PREVIEW_EXT_SET.contains(&ext) || name.ends_with(".md") || name.ends_with(".txt")
}

/// Local-only hygiene sweep: orphaned sidecars and empty folders
/// ("衛生スキャン … も同一 walk 基盤で Rust 化"). Name-set based — no hashing,
/// no network. The report groups by type (the `base_paths` order) and is sorted
/// deterministically within a type so the two engines agree.
#[must_use]
pub fn scan_hygiene(opts: &HygieneOpts) -> String {
    let mut orphans: Vec<Orphan> = Vec::new();
    let mut empty: Vec<EmptyFolder> = Vec::new();

    for (model_type, bases) in &opts.base_paths {
        for (index, base) in bases.iter().enumerate() {
            if !base.is_dir() {
                continue;
            }
            walk_hygiene(
                base,
                base,
                model_type,
                index,
                &opts.extensions,
                &mut orphans,
                &mut empty,
            );
        }
    }
    // Deterministic order (the Python os.walk order is FS-dependent): sort by
    // (type, pathIndex, fullname). The Python reference sorts identically.
    orphans.sort_by(|a, b| {
        a.model_type
            .cmp(&b.model_type)
            .then(a.path_index.cmp(&b.path_index))
            .then(a.fullname.cmp(&b.fullname))
    });
    empty.sort_by(|a, b| {
        a.model_type
            .cmp(&b.model_type)
            .then(a.path_index.cmp(&b.path_index))
            .then(a.fullname.cmp(&b.fullname))
    });

    let report = HygieneReport { orphans, empty };
    serde_json::to_string(&report).unwrap_or_else(|_| r#"{"orphans":[],"empty":[]}"#.to_owned())
}

/// Recursive `os.walk(followlinks=False)` over one base: `rel` is the
/// forward-slashed path of `dir` relative to `base` ("" for the base itself).
fn walk_hygiene(
    dir: &Path,
    base: &Path,
    model_type: &str,
    index: usize,
    extensions: &HashSet<String>,
    orphans: &mut Vec<Orphan>,
    empty: &mut Vec<EmptyFolder>,
) {
    let Ok(rd) = fs::read_dir(dir) else {
        return;
    };
    let mut filenames: Vec<String> = Vec::new();
    let mut dirnames: Vec<(PathBuf, bool)> = Vec::new(); // (path, is_symlink)

    for entry in rd.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        let path = entry.path();
        // os.walk classifies by is_dir() (FOLLOWS symlinks); a symlink-to-dir
        // lands in dirnames but is NOT descended (followlinks=False).
        let is_symlink = entry.file_type().map(|t| t.is_symlink()).unwrap_or(false);
        let is_dir = fs::metadata(&path).map(|m| m.is_dir()).unwrap_or(false);
        if is_dir {
            dirnames.push((path, is_symlink));
        } else {
            filenames.push(name);
        }
    }

    let rel = relative_to(dir, base);

    // Model files + their bases.
    let mut model_files: HashSet<String> = HashSet::new();
    let mut model_bases: HashSet<String> = HashSet::new();
    for name in &filenames {
        let ext = py_splitext(name).1;
        if extensions.contains(ext) {
            model_files.insert(name.clone());
            model_bases.insert(py_splitext(name).0.to_owned());
        }
    }
    // Claimed sidecar names: every preview candidate + .md + .txt per base.
    let mut candidates: HashSet<String> = HashSet::new();
    for mb in &model_bases {
        candidates.extend(preview_candidate_names(mb));
        candidates.insert(format!("{mb}.md"));
        candidates.insert(format!("{mb}.txt"));
    }
    // Orphans: sidecars no model claims (hidden files are never sidecars).
    for name in &filenames {
        if name.starts_with('.') {
            continue;
        }
        if !is_sidecar_name(name) || candidates.contains(name) || model_files.contains(name) {
            continue;
        }
        let fullname = if rel.is_empty() {
            name.clone()
        } else {
            format!("{rel}/{name}")
        };
        let size = fs::metadata(dir.join(name)).map(|m| m.len()).unwrap_or(0);
        orphans.push(Orphan {
            model_type: model_type.to_owned(),
            path_index: index,
            fullname,
            size_bytes: size,
        });
    }
    // Empty folder: a non-root directory with neither model files nor subdirs.
    if !rel.is_empty() && model_files.is_empty() && dirnames.is_empty() {
        empty.push(EmptyFolder {
            model_type: model_type.to_owned(),
            path_index: index,
            fullname: rel.clone(),
            size_bytes: 0,
        });
    }

    // Recurse into real (non-symlink) subdirectories, in a stable order.
    let mut subdirs: Vec<&(PathBuf, bool)> = dirnames.iter().filter(|(_, sym)| !sym).collect();
    subdirs.sort_by(|a, b| a.0.cmp(&b.0));
    for (sd, _) in subdirs {
        walk_hygiene(sd, base, model_type, index, extensions, orphans, empty);
    }
}

/// `os.path.relpath(dir, base)` normalised to forward slashes ("" for the base
/// itself, which is `relpath == "."`). Both are absolute walk paths, so `dir`
/// is `base` or lives under it.
fn relative_to(dir: &Path, base: &Path) -> String {
    let d = normalize_seps(&dir.to_string_lossy());
    let b = normalize_seps(&base.to_string_lossy());
    if d == b {
        return String::new(); // relpath(base, base) == "." → ""
    }
    let prefix = if b.ends_with('/') {
        b.clone()
    } else {
        format!("{b}/")
    };
    let rel = d.strip_prefix(&prefix).unwrap_or(&d);
    if rel == "." || rel.is_empty() {
        String::new()
    } else {
        rel.to_owned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn exts() -> HashSet<String> {
        [".safetensors", ".ckpt", ".gguf"]
            .iter()
            .map(|s| s.to_string())
            .collect()
    }

    fn scan_opts(root: &Path, include_hidden: bool) -> ScanOpts {
        ScanOpts {
            model_type: "checkpoints".to_owned(),
            roots: vec![root.to_path_buf()],
            include_hidden,
            extensions: exts(),
            no_preview_url: "/model-manager/no-preview.svg".to_owned(),
            preview_url_prefix: "/model-manager/preview".to_owned(),
            index: None,
        }
    }

    fn touch(p: &Path) {
        if let Some(parent) = p.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(p, b"x").unwrap();
    }

    fn entries(json: &str) -> Vec<serde_json::Value> {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn scans_files_folders_previews_and_order() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("checkpoints");
        touch(&root.join("b.safetensors"));
        touch(&root.join("a.safetensors"));
        touch(&root.join("a.webp")); // primary preview of a
        touch(&root.join("sub/c.safetensors"));
        touch(&root.join("notes.txt")); // not a model, not a claimed sidecar → ignored by scan
        fs::create_dir_all(root.join("emptydir")).unwrap();

        let json = scan_models(&scan_opts(&root, false));
        let list = entries(&json);
        // sorted by path: a.safetensors, a.webp is NOT a model (no ext match),
        // b.safetensors, emptydir, sub, sub/c.safetensors
        let names: Vec<String> = list
            .iter()
            .map(|e| {
                let sf = e["subFolder"].as_str().unwrap();
                let bn = e["basename"].as_str().unwrap();
                let ex = e["extension"].as_str().unwrap();
                if sf.is_empty() {
                    format!("{bn}{ex}")
                } else {
                    format!("{sf}/{bn}{ex}")
                }
            })
            .collect();
        assert_eq!(
            names,
            [
                "a.safetensors",
                "b.safetensors",
                "emptydir",
                "sub",
                "sub/c.safetensors"
            ],
            "a.webp/notes.txt are not models; folders included; sorted by path"
        );
        // a.safetensors has a preview (a.webp) → a bare string URL
        let a = &list[0];
        assert_eq!(a["isFolder"], false);
        assert_eq!(
            a["preview"].as_str().unwrap(),
            "/model-manager/preview/checkpoints/0/a.webp"
        );
        // b.safetensors has none → NO_PREVIEW_URL
        assert_eq!(
            list[1]["preview"].as_str().unwrap(),
            "/model-manager/no-preview.svg"
        );
        // a folder entry
        let emptydir = list.iter().find(|e| e["basename"] == "emptydir").unwrap();
        assert_eq!(emptydir["isFolder"], true);
        assert!(emptydir["preview"].is_null());
        assert_eq!(emptydir["extension"].as_str().unwrap(), "");
        assert_eq!(emptydir["sizeBytes"], 0);
    }

    #[test]
    fn hidden_files_are_skipped_but_still_resolve_previews() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("checkpoints");
        touch(&root.join("m.safetensors"));
        touch(&root.join("m.webp")); // a HIDDEN preview still counts (name set has it)
        touch(&root.join(".hidden.safetensors"));

        // include_hidden = false: the hidden model is skipped, m.webp resolves
        let json = scan_models(&scan_opts(&root, false));
        let list = entries(&json);
        assert_eq!(list.len(), 1, "only m.safetensors");
        assert_eq!(list[0]["basename"].as_str().unwrap(), "m");
        assert_eq!(
            list[0]["preview"].as_str().unwrap(),
            "/model-manager/preview/checkpoints/0/m.webp"
        );

        // include_hidden = true: the hidden model appears too
        let json2 = scan_models(&scan_opts(&root, true));
        let list2 = entries(&json2);
        assert_eq!(list2.len(), 2);
    }

    #[test]
    fn gallery_previews_become_an_array() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("checkpoints");
        touch(&root.join("m.safetensors"));
        touch(&root.join("m.webp")); // slot 0
        touch(&root.join("m.preview.png")); // slot 1
        let json = scan_models(&scan_opts(&root, false));
        let list = entries(&json);
        let m = list.iter().find(|e| e["basename"] == "m").unwrap();
        let arr = m["preview"].as_array().expect("gallery → array");
        assert_eq!(arr.len(), 2);
        assert!(arr[0].as_str().unwrap().ends_with("/m.webp"));
        assert!(arr[1].as_str().unwrap().ends_with("/m.preview.png"));
    }

    #[test]
    fn frontmatter_is_parsed_with_the_exact_python_shape_checks() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("checkpoints");
        touch(&root.join("m.safetensors"));
        fs::write(
            root.join("m.md"),
            "---\nmodelPage: https://civitai.com/models/1\nwebsite: civitai\nbaseModel: SD 1.5\nhashes:\n  SHA256: abcdef0123\n---\nbody\n",
        )
        .unwrap();
        let json = scan_models(&scan_opts(&root, false));
        let m = entries(&json)
            .into_iter()
            .find(|e| e["basename"] == "m")
            .unwrap();
        assert_eq!(
            m["modelPage"].as_str().unwrap(),
            "https://civitai.com/models/1"
        );
        assert_eq!(m["modelPlatform"].as_str().unwrap(), "civitai");
        assert_eq!(m["modelBase"].as_str().unwrap(), "SD 1.5");
        assert_eq!(
            m["modelSha256"].as_str().unwrap(),
            "ABCDEF0123",
            "upper-cased"
        );
    }

    #[test]
    fn frontmatter_shape_checks_reject_non_http_and_blank() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("checkpoints");
        touch(&root.join("m.safetensors"));
        // modelPage not starting with http → None; website blank → None
        fs::write(
            root.join("m.md"),
            "---\nmodelPage: civitai.com/models/1\nwebsite: '   '\nbaseModel: SDXL\n---\n",
        )
        .unwrap();
        let json = scan_models(&scan_opts(&root, false));
        let m = entries(&json)
            .into_iter()
            .find(|e| e["basename"] == "m")
            .unwrap();
        assert!(m["modelPage"].is_null(), "no http prefix → null");
        assert!(m["modelPlatform"].is_null(), "blank website → null");
        assert_eq!(m["modelBase"].as_str().unwrap(), "SDXL");
    }

    #[test]
    fn frontmatter_without_a_closing_fence_is_not_parsed() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("checkpoints");
        touch(&root.join("m.safetensors"));
        fs::write(root.join("m.md"), "---\nmodelPage: https://x\n").unwrap(); // no closing ---\n
        let json = scan_models(&scan_opts(&root, false));
        let m = entries(&json)
            .into_iter()
            .find(|e| e["basename"] == "m")
            .unwrap();
        assert!(m["modelPage"].is_null());
    }

    #[test]
    fn index_caches_frontmatter_and_survives_a_rescan() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("checkpoints");
        touch(&root.join("m.safetensors"));
        fs::write(
            root.join("m.md"),
            "---\nmodelPage: https://civitai.com/models/9\nwebsite: civitai\n---\n",
        )
        .unwrap();
        let index = Arc::new(SiteIndex::ephemeral());
        let mut opts = scan_opts(&root, false);
        opts.index = Some(index.clone());
        let json = scan_models(&opts);
        let m = entries(&json)
            .into_iter()
            .find(|e| e["basename"] == "m")
            .unwrap();
        assert_eq!(
            m["modelPage"].as_str().unwrap(),
            "https://civitai.com/models/9"
        );
        assert_eq!(index.len(), 1, "the sidecar was cached");
        // rescan: served from the cache (same result)
        let json2 = scan_models(&opts);
        let m2 = entries(&json2)
            .into_iter()
            .find(|e| e["basename"] == "m")
            .unwrap();
        assert_eq!(
            m2["modelPage"].as_str().unwrap(),
            "https://civitai.com/models/9"
        );
    }

    #[test]
    fn missing_root_and_nonexistent_base_are_skipped() {
        let dir = tempfile::tempdir().unwrap();
        let missing = dir.path().join("nope");
        let opts = scan_opts(&missing, false);
        assert_eq!(scan_models(&opts), "[]");
        // multiple roots, one missing: pathIndex is the enumerate position
        let real = dir.path().join("checkpoints");
        touch(&real.join("m.safetensors"));
        let mut opts2 = scan_opts(&missing, false);
        opts2.roots = vec![missing.clone(), real.clone()];
        let list = entries(&scan_models(&opts2));
        assert_eq!(list.len(), 1);
        assert_eq!(list[0]["pathIndex"], 1, "the real root is pathIndex 1");
    }

    #[test]
    fn hygiene_finds_orphans_and_empty_folders() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("checkpoints");
        touch(&root.join("m.safetensors"));
        touch(&root.join("m.webp")); // claimed preview → not an orphan
        touch(&root.join("stray.png")); // orphan (no model claims it)
        touch(&root.join("loose.md")); // orphan notes
        touch(&root.join("sub/orphan2.webp")); // orphan inside a subfolder
        fs::create_dir_all(root.join("emptydir")).unwrap(); // empty folder
        fs::create_dir_all(root.join("sub")).unwrap();

        let opts = HygieneOpts {
            base_paths: vec![("checkpoints".to_owned(), vec![root.clone()])],
            extensions: exts(),
        };
        let report: serde_json::Value = serde_json::from_str(&scan_hygiene(&opts)).unwrap();
        let orphan_names: Vec<String> = report["orphans"]
            .as_array()
            .unwrap()
            .iter()
            .map(|o| o["fullname"].as_str().unwrap().to_owned())
            .collect();
        assert!(orphan_names.contains(&"stray.png".to_owned()));
        assert!(orphan_names.contains(&"loose.md".to_owned()));
        assert!(orphan_names.contains(&"sub/orphan2.webp".to_owned()));
        assert!(
            !orphan_names.contains(&"m.webp".to_owned()),
            "claimed preview is not an orphan"
        );
        let empty_names: Vec<String> = report["empty"]
            .as_array()
            .unwrap()
            .iter()
            .map(|o| o["fullname"].as_str().unwrap().to_owned())
            .collect();
        assert!(empty_names.contains(&"emptydir".to_owned()));
        // Python's rule is `not model_files and not dirnames`: "sub" holds only
        // an orphaned sidecar (no MODEL file, no sub-dir), so it IS reported
        // empty — matching scan_hygiene exactly (the orphan is listed too).
        assert!(empty_names.contains(&"sub".to_owned()));
        assert!(
            !empty_names.contains(&"".to_owned()),
            "the root is never reported empty"
        );
    }

    #[test]
    fn hygiene_ignores_hidden_and_non_sidecar_files() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("checkpoints");
        touch(&root.join(".hidden.png")); // hidden → never an orphan
        touch(&root.join("data.json")); // not a sidecar extension → not an orphan
        let opts = HygieneOpts {
            base_paths: vec![("checkpoints".to_owned(), vec![root.clone()])],
            extensions: exts(),
        };
        let report: serde_json::Value = serde_json::from_str(&scan_hygiene(&opts)).unwrap();
        assert!(report["orphans"].as_array().unwrap().is_empty());
    }

    #[test]
    fn extract_frontmatter_matches_the_regex() {
        assert_eq!(
            extract_frontmatter_yaml("---\na: 1\n---\nbody"),
            Some("a: 1")
        );
        assert_eq!(
            extract_frontmatter_yaml("---\r\na: 1\r\n---\r\nbody"),
            Some("a: 1")
        );
        assert_eq!(
            extract_frontmatter_yaml("---\na: 1\nb: 2\n---\n"),
            Some("a: 1\nb: 2")
        );
        // no closing fence → None
        assert_eq!(extract_frontmatter_yaml("---\na: 1\n"), None);
        // not a front-matter block → None
        assert_eq!(extract_frontmatter_yaml("just text\n"), None);
        // minimal capture: the FIRST closing fence wins
        assert_eq!(
            extract_frontmatter_yaml("---\na: 1\n---\n---\nb: 2\n---\n"),
            Some("a: 1")
        );
    }

    #[test]
    fn ns_to_ms_matches_python_round() {
        // Verified against CPython round(st_ctime_ns/1e6) on a live stat.
        assert_eq!(ns_to_ms(1_790_488_207_276_544_538), 1_790_488_207_277);
        // round-half-to-even at the ms boundary
        assert_eq!(ns_to_ms(1_500_000), 2); // 1.5 → 2 (even)
        assert_eq!(ns_to_ms(500_000), 0); // 0.5 → 0 (even)
        assert_eq!(ns_to_ms(2_500_000), 2); // 2.5 → 2 (even)
        assert_eq!(ns_to_ms(1_400_000), 1); // 1.4 → 1
        assert_eq!(ns_to_ms(1_600_000), 2); // 1.6 → 2

        // Regression vectors for the 2026-10-07 macOS CI golden-parity flake:
        // epoch ns exceed 2^53, where the former `(ns as f64) / 1e6` quantised
        // to a 256 ns grid and flipped the half-to-even decision near `.5`
        // boundaries (~1 in 10,000 timestamps). Every expected value below is
        // CPython's `round(ns / 1000000)`; the three epoch-scale vectors each
        // diverged under the old formula (…777/…778 rounded UP to …338,
        // …221 rounded DOWN to …954 — the direction observed in CI).
        assert_eq!(ns_to_ms(1_791_356_884_337_499_777), 1_791_356_884_337);
        assert_eq!(ns_to_ms(1_791_356_884_337_499_778), 1_791_356_884_337);
        assert_eq!(ns_to_ms(1_707_307_865_954_500_221), 1_707_307_865_955);

        // Negative ns (pre-epoch mtimes): div_euclid/rem_euclid floor like
        // Python's divmod, ties stay half-to-even toward the even neighbour.
        assert_eq!(ns_to_ms(-1), 0);
        assert_eq!(ns_to_ms(-500_000), 0); // -0.5 → -0 (even)
        assert_eq!(ns_to_ms(-1_500_000), -2); // -1.5 → -2 (even)
        assert_eq!(ns_to_ms(0), 0);

        // i64 extremes: |q| < 2^53 keeps the quotient part exact in f64.
        assert_eq!(ns_to_ms(i64::MAX), 9_223_372_036_855);
        assert_eq!(ns_to_ms(i64::MIN), -9_223_372_036_855);
    }

    #[test]
    fn py_splitext_relative_path_helpers() {
        assert_eq!(
            split_rel("sub/dir/m.safetensors"),
            ("sub/dir", "m.safetensors")
        );
        assert_eq!(split_rel("m.safetensors"), ("", "m.safetensors"));
        assert_eq!(normalize_seps("a\\b\\c"), "a/b/c");
        assert_eq!(normalize_seps("a/b/c"), "a/b/c");
    }
}
