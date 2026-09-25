//! Batch primitives (Phase 3, Plan §6.2): the mechanical halves of the
//! folder-batch flow — a parallel directory walk (`walk_models`, the
//! `os.walk` + name-filter + `sorted()` replacement) and the model sidecar
//! mover (`move_with_sidecars`, the `_sidecar_move` / `_delta_sidecar_move`
//! replacement).
//!
//! The BUNDLE SEMANTICS stay in Python (`py/compress.py`): which folder is
//! a bundle, where compressed output lands (`_bundle_dst_root`), where a
//! bundle empties back to (`_batch_restore_root` / `_decompress_target`) —
//! Plan §6.2 Phase 3: "バンドル意味論（`*_DeltaZNN`・type-root 内包・
//! legacy `_ZNN`）は Python 現行ロジックを維持". This module only walks and
//! moves, with every naming rule a faithful port of `py/utils.py` /
//! `py/compress.py` (constants arrive through [`WalkOpts`] so the Python
//! side stays the single source of truth).
//!
//! Walk semantics mirror `os.walk` exactly: hidden files are INCLUDED (no
//! ignore-file filtering of any kind), symlinked directories are never
//! descended into and never listed as files, unreadable directories are
//! skipped silently (`os.walk(onerror=None)`), and the result is sorted by
//! the same path strings Python would sort. The walk itself is parallel
//! (the `ignore` crate — Plan §3.7 first candidate), which is where the
//! network-storage libraries of Plan §1.2.2 #9 get their latency back.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use crate::pipeline::io_ctx;
use crate::safetensors_io::{StError, StResult};

/// Which file set a batch walk collects (the three Python walkers of
/// `py/compress.py`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WalkMode {
    /// `_walk_model_files(folder, "compress", skip_bundles)`: every plain
    /// `.safetensors` (already-`.znn.` files are skipped).
    Compress,
    /// `_walk_decompress_files(folder)`: every `.znn.safetensors` anywhere,
    /// plus `*_delta_*.znn` files whose PARENT folder carries the delta
    /// suffix (their `.neo-delta.json` sidecars travel implicitly).
    Decompress,
    /// `_batch_invariants_blockers(folder)`: supported model extensions the
    /// batch cannot convert (bundle sub-trees always pruned).
    Blockers,
}

/// Walk configuration — every string constant is passed IN from Python
/// (`py/utils.py` / `folder_paths` remain the single source of truth).
#[derive(Debug, Clone)]
pub struct WalkOpts<'a> {
    /// Which walker to mirror.
    pub mode: WalkMode,
    /// Prune bundle sub-trees (`Compress` only — `Blockers` always prunes,
    /// `Decompress` never does, exactly like the Python walkers).
    pub skip_bundles: bool,
    /// Bundle folder-name suffixes (`["_DeltaZNN", "_ZNN"]`).
    pub bundle_suffixes: &'a [String],
    /// The delta-folder suffix (`"_DeltaZNN"`).
    pub delta_folder_suffix: &'a str,
    /// `Blockers` only: `folder_paths.supported_pt_extensions`.
    pub extensions: &'a [String],
}

/// Python's `os.path.splitext` (the LAST dot at index > 0 starts the
/// extension; leading dots are part of the stem: `".md"` → `(".md", "")`).
fn py_splitext(name: &str) -> (&str, &str) {
    match name.rfind('.') {
        Some(i) if i > 0 => (&name[..i], &name[i..]),
        _ => (name, ""),
    }
}

fn is_bundle_name(name: &str, suffixes: &[String]) -> bool {
    suffixes
        .iter()
        .any(|s| !s.is_empty() && name.ends_with(s.as_str()))
}

/// Collect the batch file set under `root`, sorted by path string (the
/// legacy `sorted(found)` contract — the batch order never shifts between
/// runs). Unreadable directories are skipped silently like `os.walk`.
///
/// Non-UTF-8 file names are reported through `to_string_lossy` sorting but
/// returned as their original `PathBuf`s (a lossless round-trip for every
/// name the walk matched; matching itself is on the lossy form — the same
/// practical contract the JSON wire format imposes).
#[must_use]
pub fn walk_models(root: &Path, opts: &WalkOpts) -> Vec<PathBuf> {
    use ignore::WalkBuilder;
    use std::sync::mpsc;

    let prune_bundles = matches!(opts.mode, WalkMode::Blockers)
        || (opts.mode == WalkMode::Compress && opts.skip_bundles);

    let (tx, rx) = mpsc::channel::<(String, PathBuf)>();
    let mut builder = WalkBuilder::new(root);
    // Pure recursive walk: no hidden-file filtering, no ignore files
    // (os.walk sees everything), never follow directory symlinks.
    builder
        .standard_filters(false)
        .hidden(false)
        .follow_links(false)
        .require_git(false);
    if prune_bundles {
        let suffixes: Vec<String> = opts.bundle_suffixes.to_vec();
        builder.filter_entry(move |entry| {
            if entry.depth() == 0 {
                return true; // the walked root itself is never pruned
            }
            if !entry_is_dir(entry) {
                return true;
            }
            !is_bundle_name(&entry.file_name().to_string_lossy(), &suffixes)
        });
    }

    let mode = opts.mode;
    let delta_suffix: String = opts.delta_folder_suffix.to_owned();
    let name_filters = match mode {
        WalkMode::Compress => NameFilter::Compress,
        WalkMode::Decompress => NameFilter::Decompress(delta_suffix),
        WalkMode::Blockers => NameFilter::Blockers(opts.extensions.to_vec()),
    };

    builder.build_parallel().run(|| {
        let tx = tx.clone();
        let name_filters = name_filters.clone();
        Box::new(move |entry| {
            let Ok(entry) = entry else {
                return ignore::WalkState::Continue; // os.walk(onerror=None)
            };
            if entry.depth() == 0 || entry_is_dir(&entry) {
                return ignore::WalkState::Continue;
            }
            let path = entry.path().to_path_buf();
            let Some(name) = path.file_name() else {
                return ignore::WalkState::Continue;
            };
            let name = name.to_string_lossy().into_owned();
            if name_filters.matches(&name, &path) {
                let key = path.to_string_lossy().into_owned();
                let _ = tx.send((key, path));
            }
            ignore::WalkState::Continue
        })
    });
    drop(tx);

    let mut found: Vec<(String, PathBuf)> = rx.iter().collect();
    found.sort_by(|a, b| a.0.cmp(&b.0));
    found.into_iter().map(|(_, p)| p).collect()
}

/// `os.walk` puts symlinked DIRECTORIES into `dirnames` (never `filenames`)
/// and never descends into them; a symlink to a file IS a file candidate.
fn entry_is_dir(entry: &ignore::DirEntry) -> bool {
    match entry.file_type() {
        Some(ft) if ft.is_dir() => true,
        Some(ft) if ft.is_symlink() => entry.path().metadata().map(|m| m.is_dir()).unwrap_or(false),
        Some(_) => false,
        // d_type unknown (exotic filesystems): stat it
        None => entry.path().metadata().map(|m| m.is_dir()).unwrap_or(false),
    }
}

#[derive(Clone)]
enum NameFilter {
    Compress,
    Decompress(String),
    Blockers(Vec<String>),
}

impl NameFilter {
    fn matches(&self, name: &str, path: &Path) -> bool {
        match self {
            // plain `.safetensors`, never the already-compressed form
            Self::Compress => name.ends_with(".safetensors") && !name.ends_with(".znn.safetensors"),
            Self::Decompress(delta_suffix) => {
                if name.ends_with(".znn.safetensors") {
                    return true;
                }
                // `*_delta_*.znn` INSIDE a `*_DeltaZNN` folder (the file's
                // immediate parent — legacy `os.path.basename(root)`)
                name.ends_with(".znn")
                    && name.contains("_delta_")
                    && path
                        .parent()
                        .and_then(|p| p.file_name())
                        .is_some_and(|d| d.to_string_lossy().ends_with(delta_suffix.as_str()))
            }
            Self::Blockers(extensions) => {
                let ext = py_splitext(name).1;
                extensions.iter().any(|e| e == ext)
                    && !name.contains(".znn.")
                    && !name.ends_with(".safetensors")
                    && !name.ends_with(".znn")
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Sidecar moving (py/utils.py preview scheme + descriptions)
// ---------------------------------------------------------------------------

/// `py/utils.py PREVIEW_EXTENSIONS` (order = display priority within a slot).
pub const PREVIEW_EXTENSIONS: [&str; 8] = [
    ".webm", ".mp4", ".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
];

/// `py/utils.py _PREVIEW_SUFFIXES`: the primary preview, the historic
/// `.preview` second, then `.preview2` … `.preview19` (20 slots). Slot
/// suffix is the OUTER loop — the listing order contract of
/// `preview_candidates()`.
fn preview_slot_suffixes() -> Vec<String> {
    let mut v = Vec::with_capacity(20);
    v.push(String::new());
    v.push(".preview".to_owned());
    v.extend((2..20).map(|n| format!(".preview{n}")));
    v
}

/// Move every sidecar of `src` (preview slots + Markdown/txt notes) to the
/// matching names beside `dst` — the faithful Rust port of
/// `_delta_sidecar_move` (which also covers `_sidecar_move`: same-directory
/// moves are just the degenerate case).
///
/// Rules mirrored exactly:
/// * previews resolve against ONE listing of the source directory (the
///   20-slot × 8-extension candidate scheme, slot-major order);
/// * descriptions are the `.txt`/`.md` files (extension match is
///   case-insensitive like `folder_paths.filter_files_extensions`; the
///   destination KEEPS the original extension case) whose stem equals the
///   source stem, in sorted order;
/// * a sidecar moves only when the source EXISTS and the destination does
///   NOT (an existing destination is never overwritten);
/// * the destination directory is created on demand;
/// * the model file itself is NOT moved — the callers keep the legacy
///   ordering (artifact committed first, sidecars follow, the source model
///   is removed last — Plan §4.4.3-5).
///
/// # Errors
/// Rename failures (propagated like the legacy `os.rename` OSError — the
/// route fails and reports; already-moved sidecars stay moved, exactly the
/// legacy behaviour).
pub fn move_with_sidecars(src: &Path, dst: &Path) -> StResult<()> {
    let src_dir = src.parent().unwrap_or_else(|| Path::new("."));
    let dst_dir = dst.parent().unwrap_or_else(|| Path::new("."));
    let src_name = src
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .ok_or_else(|| {
            StError::Format(format!("sidecar move: {} has no file name", src.display()))
        })?;
    let dst_name = dst
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .ok_or_else(|| StError::Format(format!("sidecar move: {dst:?} has no file name")))?;
    let src_base = py_splitext(&src_name).0;
    let dst_base = py_splitext(&dst_name).0;

    // ONE directory listing (legacy get_dir_names + search_files both scan
    // the source dir; unreadable → empty set, like get_dir_names' except)
    let names: HashSet<String> = std::fs::read_dir(src_dir)
        .map(|rd| {
            rd.filter_map(Result::ok)
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .collect()
        })
        .unwrap_or_default();

    // previews: slot-major candidate order
    for suffix in preview_slot_suffixes() {
        for ext in PREVIEW_EXTENSIONS {
            let candidate = format!("{src_base}{suffix}{ext}");
            if names.contains(&candidate) {
                // legacy: `ext = preview[len(src_base):]` = suffix + ext
                let s = src_dir.join(&candidate);
                let d = dst_dir.join(format!("{dst_base}{suffix}{ext}"));
                move_if(&s, &d)?;
            }
        }
    }

    // descriptions: sorted (filter_files_extensions sorts), isfile-checked
    let mut descs: Vec<(String, String)> = names
        .iter()
        .filter_map(|name| {
            let (stem, ext) = py_splitext(name);
            if stem != src_base {
                return None;
            }
            if !matches!(ext.to_ascii_lowercase().as_str(), ".txt" | ".md") {
                return None;
            }
            Some((name.clone(), ext.to_owned()))
        })
        .collect();
    descs.sort();
    for (name, ext) in descs {
        let s = src_dir.join(&name);
        if !s.is_file() {
            continue; // search_files keeps plain files only
        }
        let d = dst_dir.join(format!("{dst_base}{ext}"));
        move_if(&s, &d)?;
    }
    Ok(())
}

fn move_if(s: &Path, d: &Path) -> StResult<()> {
    // legacy guard: exists(src) and not exists(dst) — never overwrite
    if s.exists() && !d.exists() {
        if let Some(parent) = d.parent() {
            std::fs::create_dir_all(parent).map_err(|e| io_ctx(e, "creating", parent))?;
        }
        std::fs::rename(s, d).map_err(|e| io_ctx(e, "moving", s))?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    struct TempDir(PathBuf);
    impl TempDir {
        fn new(tag: &str) -> Self {
            let mut p = std::env::temp_dir();
            p.push(format!(
                "mmneo-batch-{tag}-{}-{:?}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.subsec_nanos())
                    .unwrap_or(0)
            ));
            std::fs::create_dir_all(&p).unwrap();
            Self(p)
        }
        fn path(&self, name: &str) -> PathBuf {
            self.0.join(name)
        }
    }
    impl Drop for TempDir {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn touch(p: &Path) {
        if let Some(parent) = p.parent() {
            std::fs::create_dir_all(parent).unwrap();
        }
        std::fs::write(p, b"x").unwrap();
    }

    fn walk_opts<'a>(
        mode: WalkMode,
        skip_bundles: bool,
        suffixes: &'a [String],
        exts: &'a [String],
    ) -> WalkOpts<'a> {
        WalkOpts {
            mode,
            skip_bundles,
            bundle_suffixes: suffixes,
            delta_folder_suffix: "_DeltaZNN",
            extensions: exts,
        }
    }

    fn suffixes() -> [String; 2] {
        ["_DeltaZNN".to_owned(), "_ZNN".to_owned()]
    }

    fn names(paths: &[PathBuf], root: &Path) -> Vec<String> {
        paths
            .iter()
            .map(|p| {
                p.strip_prefix(root)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/")
            })
            .collect()
    }

    /// The library tree every walk test shares:
    /// ```text
    /// root/
    ///   a.safetensors            plain model
    ///   b.znn.safetensors        compressed
    ///   c.gguf                   blocker
    ///   .hidden.safetensors      hidden plain model (os.walk SEES it)
    ///   sub/d.safetensors        nested plain
    ///   sub/e.ckpt               nested blocker
    ///   X_DeltaZNN/x1.znn.safetensors     bundle content
    ///   X_DeltaZNN/ft_delta_X.znn         delta file
    ///   X_DeltaZNN/ft_delta_X.znn.neo-delta.json   sidecar (never listed)
    ///   Y_ZNN/y1.znn.safetensors          legacy bundle content
    ///   Y_ZNN/deep/z.znn.safetensors      nested inside legacy bundle
    /// ```
    fn library(dir: &TempDir) -> PathBuf {
        let root = dir.path("root");
        for rel in [
            "a.safetensors",
            "b.znn.safetensors",
            "c.gguf",
            ".hidden.safetensors",
            "sub/d.safetensors",
            "sub/e.ckpt",
            "X_DeltaZNN/x1.znn.safetensors",
            "X_DeltaZNN/ft_delta_X.znn",
            "X_DeltaZNN/ft_delta_X.znn.neo-delta.json",
            "Y_ZNN/y1.znn.safetensors",
            "Y_ZNN/deep/z.znn.safetensors",
        ] {
            touch(&root.join(rel));
        }
        root
    }

    #[test]
    fn compress_walk_matches_the_python_walker() {
        let dir = TempDir::new("walk-c");
        let root = library(&dir);
        let s = suffixes();
        let exts: Vec<String> = Vec::new();
        // skip_bundles=True (the route's call): bundle sub-trees pruned
        let got = walk_models(&root, &walk_opts(WalkMode::Compress, true, &s, &exts));
        assert_eq!(
            names(&got, &root),
            [".hidden.safetensors", "a.safetensors", "sub/d.safetensors"],
            "hidden files are included; bundles pruned; sorted"
        );
        // skip_bundles=False sees inside bundles too (nothing matches there,
        // but the walk must not error)
        let got = walk_models(&root, &walk_opts(WalkMode::Compress, false, &s, &exts));
        assert_eq!(
            names(&got, &root),
            [".hidden.safetensors", "a.safetensors", "sub/d.safetensors"]
        );
    }

    #[test]
    fn decompress_walk_matches_the_python_walker() {
        let dir = TempDir::new("walk-d");
        let root = library(&dir);
        let s = suffixes();
        let exts: Vec<String> = Vec::new();
        let got = walk_models(&root, &walk_opts(WalkMode::Decompress, false, &s, &exts));
        assert_eq!(
            names(&got, &root),
            [
                "X_DeltaZNN/ft_delta_X.znn",
                "X_DeltaZNN/x1.znn.safetensors",
                "Y_ZNN/deep/z.znn.safetensors",
                "Y_ZNN/y1.znn.safetensors",
                "b.znn.safetensors",
            ],
            "znn models everywhere + delta files inside *_DeltaZNN only; sorted"
        );
        // the sidecar JSON is never listed; a `_delta_*.znn` OUTSIDE a
        // bundle folder is not a delta candidate
        touch(&root.join("loose_delta_X.znn"));
        let got = walk_models(&root, &walk_opts(WalkMode::Decompress, false, &s, &exts));
        assert!(!names(&got, &root).contains(&"loose_delta_X.znn".to_owned()));
        // walking a BUNDLE ROOT directly still recognises its delta files
        // (the parent check is on the file's own directory)
        let got = walk_models(
            &root.join("X_DeltaZNN"),
            &walk_opts(WalkMode::Decompress, false, &s, &exts),
        );
        assert_eq!(
            names(&got, &root.join("X_DeltaZNN")),
            ["ft_delta_X.znn", "x1.znn.safetensors"]
        );
    }

    #[test]
    fn blockers_walk_matches_the_python_walker() {
        let dir = TempDir::new("walk-b");
        let root = library(&dir);
        let s = suffixes();
        let exts: Vec<String> = [".safetensors", ".gguf", ".ckpt", ".pt", ".bin", ".znn"]
            .map(str::to_owned)
            .to_vec();
        let got = walk_models(&root, &walk_opts(WalkMode::Blockers, false, &s, &exts));
        assert_eq!(
            names(&got, &root),
            ["c.gguf", "sub/e.ckpt"],
            "bundle sub-trees always pruned; .safetensors/.znn excluded"
        );
    }

    #[test]
    fn walk_of_missing_root_is_empty_like_os_walk() {
        let dir = TempDir::new("walk-missing");
        let s = suffixes();
        let exts: Vec<String> = Vec::new();
        let got = walk_models(
            &dir.path("nope"),
            &walk_opts(WalkMode::Compress, true, &s, &exts),
        );
        assert!(got.is_empty());
    }

    #[test]
    fn bundle_root_itself_is_never_pruned() {
        let dir = TempDir::new("walk-root-bundle");
        let root = dir.path("X_DeltaZNN");
        touch(&root.join("x1.znn.safetensors"));
        let s = suffixes();
        let exts: Vec<String> = Vec::new();
        // the batch decompress route walks the bundle folder itself
        let got = walk_models(&root, &walk_opts(WalkMode::Decompress, false, &s, &exts));
        assert_eq!(names(&got, &root), ["x1.znn.safetensors"]);
    }

    #[test]
    fn py_splitext_matches_python() {
        assert_eq!(py_splitext("model.safetensors"), ("model", ".safetensors"));
        assert_eq!(
            py_splitext("model.znn.safetensors"),
            ("model.znn", ".safetensors")
        );
        assert_eq!(py_splitext(".hidden"), (".hidden", ""));
        assert_eq!(py_splitext(".hidden.png"), (".hidden", ".png"));
        assert_eq!(py_splitext("noext"), ("noext", ""));
        assert_eq!(py_splitext("a.b.c"), ("a.b", ".c"));
        assert_eq!(py_splitext("ends-with-dot."), ("ends-with-dot", "."));
    }

    #[test]
    fn preview_scheme_is_slot_major_and_complete() {
        let s = preview_slot_suffixes();
        assert_eq!(s.len(), 20);
        assert_eq!(s[0], "");
        assert_eq!(s[1], ".preview");
        assert_eq!(s[2], ".preview2");
        assert_eq!(s[19], ".preview19");
        // 20 slots × 8 extensions = 160 candidates, slot-major
        let mut cands = Vec::new();
        for suf in &s {
            for ext in PREVIEW_EXTENSIONS {
                cands.push(format!("m{suf}{ext}"));
            }
        }
        assert_eq!(cands.len(), 160);
        assert_eq!(cands[0], "m.webm");
        assert_eq!(cands[8], "m.preview.webm");
        assert_eq!(cands[16], "m.preview2.webm");
    }

    fn sidecar_tree(dir: &TempDir) -> (PathBuf, PathBuf) {
        let src_dir = dir.path("src");
        let dst_dir = dir.path("dst/bundle");
        // a full gallery: primary + second + slot 3, mixed extensions,
        // notes in both cases, a lookalike that must NOT move
        touch(&src_dir.join("ft.safetensors"));
        touch(&src_dir.join("ft.webp")); // primary (slot "")
        touch(&src_dir.join("ft.preview.png")); // slot 1
        touch(&src_dir.join("ft.preview2.mp4")); // slot 2
        touch(&src_dir.join("ft.md"));
        touch(&src_dir.join("ft.TXT")); // case-insensitive extension match
        touch(&src_dir.join("ft.previewX.webp")); // NOT a valid slot
        touch(&src_dir.join("fts.webp")); // different stem — must not move
        touch(&src_dir.join("other.md")); // different stem — must not move
        (
            src_dir.join("ft.safetensors"),
            dst_dir.join("ft_delta_base.znn"),
        )
    }

    #[test]
    fn sidecars_move_cross_directory_with_renaming() {
        let dir = TempDir::new("move");
        let (src, dst) = sidecar_tree(&dir);
        std::fs::create_dir_all(dst.parent().unwrap()).unwrap();
        std::fs::write(&dst, b"delta").unwrap();
        move_with_sidecars(&src, &dst).unwrap();

        let dst_dir = dst.parent().unwrap();
        for name in [
            "ft_delta_base.webp",
            "ft_delta_base.preview.png",
            "ft_delta_base.preview2.mp4",
            "ft_delta_base.md",
            "ft_delta_base.TXT", // extension case preserved
        ] {
            assert!(dst_dir.join(name).exists(), "{name} moved");
        }
        let src_dir = src.parent().unwrap();
        for name in [
            "ft.webp",
            "ft.preview.png",
            "ft.preview2.mp4",
            "ft.md",
            "ft.TXT",
        ] {
            assert!(!src_dir.join(name).exists(), "{name} gone from source");
        }
        // non-sidecars stay put
        assert!(src_dir.join("ft.previewX.webp").exists());
        assert!(src_dir.join("fts.webp").exists());
        assert!(src_dir.join("other.md").exists());
        // the model itself is NOT moved by the primitive
        assert!(src.exists());
    }

    #[test]
    fn existing_destinations_are_never_overwritten() {
        let dir = TempDir::new("move-clash");
        let (src, dst) = sidecar_tree(&dir);
        std::fs::create_dir_all(dst.parent().unwrap()).unwrap();
        std::fs::write(&dst, b"delta").unwrap();
        // a pre-existing destination preview blocks its own move only
        std::fs::write(dst.parent().unwrap().join("ft_delta_base.webp"), b"KEEP").unwrap();
        move_with_sidecars(&src, &dst).unwrap();
        assert_eq!(
            std::fs::read(dst.parent().unwrap().join("ft_delta_base.webp")).unwrap(),
            b"KEEP"
        );
        assert!(
            src.parent().unwrap().join("ft.webp").exists(),
            "source kept"
        );
        // the rest still moved
        assert!(
            dst.parent()
                .unwrap()
                .join("ft_delta_base.preview.png")
                .exists()
        );
    }

    #[test]
    fn same_directory_move_renames_in_place() {
        let dir = TempDir::new("move-same");
        let d = dir.path("lib");
        touch(&d.join("m.safetensors"));
        touch(&d.join("m.webp"));
        touch(&d.join("m.md"));
        // the single-file route's rename: m.safetensors → m.znn.safetensors
        let src = d.join("m.safetensors");
        let dst = d.join("m.znn.safetensors");
        std::fs::rename(&src, &dst).unwrap(); // the model move itself
        move_with_sidecars(&src, &dst).unwrap();
        // NOTE: called with the pre-rename src name like _sidecar_move does
        assert!(d.join("m.znn.webp").exists());
        assert!(d.join("m.znn.md").exists());
        assert!(!d.join("m.webp").exists());
    }

    #[test]
    fn missing_source_sidecars_are_fine() {
        let dir = TempDir::new("move-none");
        let src = dir.path("s/ft.safetensors");
        let dst = dir.path("d/ft_delta_base.znn");
        touch(&src);
        std::fs::create_dir_all(dst.parent().unwrap()).unwrap();
        std::fs::write(&dst, b"x").unwrap();
        move_with_sidecars(&src, &dst).unwrap(); // no sidecars at all → no-op
        // an unreadable source dir degrades to "no sidecars" (get_dir_names)
        let ghost = dir.path("nowhere/ft.safetensors");
        move_with_sidecars(&ghost, &dst).unwrap();
    }
}
