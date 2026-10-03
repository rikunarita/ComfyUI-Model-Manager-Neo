"""Plan Phase 8: the distribution invariants — single path, version sync,
licence inheritance, no third_party residue.

Phase 8 completes the migration: the vendored C core (``third_party/``) and
the ``MM_NATIVE`` switch are gone, the prebuilt ``mm_core`` under
``native/native-bin/`` is the single engine, and the release is PREPARED by
synchronising the version across pyproject / package.json / web/version.yaml
(the publish itself — GitHub Release, tag, registry, the dev→main merge — is
the user's job, Plan §6.3). These tests pin the invariants that can silently
regress:

* requirements.txt (the runtime contract ComfyUI / ComfyUI-Manager reads)
  equals pyproject's ``[project].dependencies`` (the documented one-way sync);
* the version triple is in sync (the vite plugin regenerates web/version.yaml
  from pyproject at build time, so a drift means a stale committed bundle);
* no third_party residue: the tree is gone and no runtime module mentions it;
* the MM_NATIVE switch is really gone: nothing in ``py/`` reads the variable
  and the loader exposes no mode API;
* ``native/NOTICE`` inherits the ZipNN (MIT) and FiniteStateEntropy (BSD-2)
  licence texts verbatim and attributes zenwebp (AGPL-3.0) — the inheritance
  the third_party removal was conditioned on (Plan §8);
* ``.gitignore`` re-includes the shipped native-bin binaries (without the
  negation the publish job's commit would silently contain nothing) and the
  publish job stays main-only.
"""

from __future__ import annotations

import json
import re
import tomllib

from harness import REPO_ROOT


def _pyproject() -> dict:
    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def test_requirements_matches_pyproject_dependencies():
    """The runtime contract (requirements.txt) is the pyproject dependency
    list, comment lines aside — the documented one-way sync (Plan T4 note /
    Phase 8 "pyproject / requirements 整理"). A drift would mean Manager
    installs something the metadata does not declare (or vice versa)."""
    deps = _pyproject()["project"]["dependencies"]
    lines = [
        line.strip()
        for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert lines == list(deps), (lines, deps)


def test_version_triple_is_in_sync():
    """pyproject == package.json == web/version.yaml (the committed bundle's
    stamp). The vite plugin writes version.yaml FROM pyproject at build time,
    so a mismatch means web/ was not rebuilt after a version bump — exactly
    the kind of release-prep drift Phase 8's version sync must not ship."""
    py_version = _pyproject()["project"]["version"]
    pkg = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == py_version, (pkg["version"], py_version)
    stamp = (REPO_ROOT / "web" / "version.yaml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*(\S+)\s*$", stamp, re.MULTILINE)
    assert match, f"web/version.yaml has no version line: {stamp!r}"
    assert match.group(1) == py_version, (match.group(1), py_version)


def test_third_party_is_gone_and_unreferenced():
    """The vendored C core tree no longer exists and no runtime module (or the
    extension entry point) mentions it — a leftover sys.path push would try to
    load binaries that no longer ship."""
    assert not (REPO_ROOT / "third_party").exists(), "third_party/ must be removed in Phase 8"
    sources = [REPO_ROOT / "__init__.py", *sorted((REPO_ROOT / "py").glob("*.py"))]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert "third_party" not in text, f"{path.name} still references third_party"


def test_mm_native_switch_is_gone():
    """Nothing in py/ reads MM_NATIVE any more and the loader exposes no mode
    API — the switch's removal must be complete, not just defaulted."""
    for path in sorted((REPO_ROOT / "py").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert 'environ.get("MM_NATIVE"' not in text, f"{path.name} still reads MM_NATIVE"
        assert 'environ["MM_NATIVE"]' not in text, f"{path.name} still reads MM_NATIVE"
    from harness import import_ext

    native = import_ext("native")
    assert not hasattr(native, "native_mode"), "the loader's mode API must be gone"
    assert "mode" not in native.diagnostics(), "diagnostics must not report a mode any more"


def test_notice_inherits_the_licence_texts():
    """native/NOTICE carries what third_party/'s licence files carried: the
    ZipNN MIT text, the FiniteStateEntropy BSD-2 text and the zenwebp AGPL
    attribution (Plan §8 — the condition of the removal)."""
    notice = (REPO_ROOT / "native" / "NOTICE").read_text(encoding="utf-8")
    # ZipNN (MIT) — the verbatim upstream text
    assert "MIT License" in notice
    assert "Permission is hereby granted, free of charge" in notice
    assert "International Business Machines" in notice
    # FiniteStateEntropy (BSD-2-Clause, Yann Collet)
    assert "Yann Collet" in notice
    assert "Redistribution and use in source and binary forms" in notice
    # zenwebp (AGPL-3.0-only OR Imazen commercial)
    assert "zenwebp" in notice and "AGPL-3.0" in notice and "Imazen" in notice


def test_binary_ignores_stay_and_the_publisher_force_adds():
    """The *.so ignore must STAY (a dev/PR worktree may never commit a local
    debug build by accident) while the publish job is the single authorised
    writer and force-adds the release artifacts — `git add -f` is what makes
    the K16 fresh-clone story work despite the ignore (tracked files clone
    regardless). A negation pattern instead would re-expose every local build
    to `git add -A`."""
    ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "!third_party" not in ignore, "the third_party negations must be gone"
    assert "!native/native-bin" not in ignore, "native-bin must stay ignored in dev worktrees"
    workflow = (REPO_ROOT / ".github" / "workflows" / "native.yml").read_text(encoding="utf-8")
    assert "git add -f native/native-bin" in workflow


def test_publish_job_is_main_only():
    """The native-bin publisher runs ONLY on main pushes (dev/PR runs are
    verification-only; a tag checkout is detached and must never be pushed
    to) — pinned as text so a trigger edit cannot quietly widen it."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "native.yml").read_text(encoding="utf-8")
    assert "publish-native-bin:" in workflow
    assert "github.event_name == 'push' && github.ref == 'refs/heads/main'" in workflow
    # the binaries it ships are content-classified (the download-artifact
    # layout is not guaranteed to carry the <tag> segment) and all four
    # platforms are verified present before the commit
    assert "cannot classify artifact" in workflow
    assert "is missing or empty" in workflow


def test_no_legacy_engine_residue_in_compress():
    """py/compress.py is the single-path engine wrapper: none of the vendored
    install machinery (ensure_zipnn and friends) may come back — the route
    contract tests exercise the native job API exclusively."""
    import ast

    tree = ast.parse((REPO_ROOT / "py" / "compress.py").read_text(encoding="utf-8"))
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)}
    banned = {
        "ensure_zipnn",
        "zipnn_available",
        "zipnn_installed",
        "compress_safetensors",
        "decompress_safetensors",
        "delta_compress_files",
        "delta_decompress_file",
        "_build_core_from_source",
        "_cleanup_targets",
    }
    assert not (names & banned), f"legacy engine functions resurrected: {sorted(names & banned)}"
    # and the module never imports the vendored package
    text = (REPO_ROOT / "py" / "compress.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+zipnn\b", text, re.MULTILINE)
