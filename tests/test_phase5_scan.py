"""Phase 5 golden tests — the native Rust scan / hygiene / header / hash paths
must be byte-for-byte interchangeable with the pure-Python paths they replaced
(Phase 5 "現行 JSON 形状 golden テスト", header, hash).

Every test runs the SAME fixture through BOTH engines and asserts identical
output, so a drift in the Rust port (order, preview shape, front-matter parse,
hash notation, timestamp rounding) fails loudly. Phase 8 removed the
``MM_NATIVE`` switch; the Python implementations survive as the RESILIENCE
FALLBACK of the read paths (a native runtime failure degrades to them rather
than breaking the grid), so the engine selection here is injection-based
(``_set_engine``): the Python side forces ``native.core_if_enabled`` to None,
the native side runs the real prebuilt core — and the Python side doubles as
the executable reference the Rust port is golden-tested against. Tests that
need the built ``mm_core`` binary skip when it is absent (CI's verify job);
the native workflow's integration job runs them against the real artifact on
all three OSes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from harness import REPO_ROOT, import_ext, write_safetensors

# ---------------------------------------------------------------------------
# engine switching helpers (injection-based since Phase 8)
# ---------------------------------------------------------------------------


def _reset_native_loader():
    config = import_ext("config")
    config.extension_uri = str(REPO_ROOT)
    native = import_ext("native")
    native._module = None
    native._reason = None
    native._attempted = False
    return native


def _native_binary_present() -> bool:
    native = _reset_native_loader()
    tag = native.platform_tag()
    if tag is None:
        return False
    binary = REPO_ROOT / "native" / "native-bin" / tag
    if not binary.is_dir():
        return False
    return any(p.name.startswith("mm_core") and p.name.endswith((".so", ".pyd")) for p in binary.iterdir())


def _require_native():
    if not _native_binary_present():
        pytest.skip("native binary not built (scripts/build-native.sh)")
    _reset_native_loader()
    native = import_ext("native")
    if not native.load():
        pytest.skip(f"native core unavailable: {native.reason()}")
    return native.core()


def _set_engine(monkeypatch, mode: str):
    """Select the engine under test (the MM_NATIVE env switch is gone).

    ``"0"`` runs the pure-Python reference: ``native.core_if_enabled`` is
    forced to None, exactly the runtime degradation the read paths take when
    the core is unavailable. ``"1"`` restores the loader's real function and
    resets its attempt state so the prebuilt binary is (re-)loaded. Both
    setattr calls go through monkeypatch, so teardown restores the module.
    """
    native = import_ext("native")
    original = getattr(native, "_orig_core_if_enabled", None)
    if original is None:
        original = native.core_if_enabled
        native._orig_core_if_enabled = original
    if mode == "0":
        monkeypatch.setattr(native, "core_if_enabled", lambda: None)
    else:
        monkeypatch.setattr(native, "core_if_enabled", original)
    _reset_native_loader()


@pytest.fixture
def index_cache(tmp_path, monkeypatch):
    """Point the persistent scan index at a temp dir (keep REPO_ROOT clean)."""
    utils = import_ext("utils")
    cache = tmp_path / "idx-cache"
    cache.mkdir()
    monkeypatch.setattr(utils, "get_index_cache_dir", lambda: str(cache))
    return cache


# Windows NTFS materializes directory LastWriteTime lazily: two consecutive
# scans of a tree nobody touched can legitimately observe a few milliseconds
# of drift on FOLDER timestamps (native run #94: 1-3 ms, both directions;
# file timestamps are stamped on close and stay exact). The parity gate below
# therefore tolerates a small drift on folder-entry timestamps on Windows
# ONLY — every other field, every file timestamp, and the full comparison on
# POSIX stay byte-exact, so the golden keeps its strength where the OS
# guarantees stable values.
_FOLDER_TS_KEYS = ("createdAt", "updatedAt")
_FOLDER_TS_DRIFT_MS = 1500


def _assert_scan_parity(native, legacy, message):
    """Entry-for-entry golden comparison with the Windows folder-mtime carve-out."""
    assert len(native) == len(legacy), f"{message}: {len(native)} entries != {len(legacy)}"
    for got, want in zip(native, legacy, strict=True):
        if os.name == "nt" and got.get("isFolder") and want.get("isFolder"):
            for key in _FOLDER_TS_KEYS:
                drift = abs(got.get(key, 0) - want.get(key, 0))
                assert drift <= _FOLDER_TS_DRIFT_MS, f"{message}: folder {key} drifted {drift} ms"
            got = {k: v for k, v in got.items() if k not in _FOLDER_TS_KEYS}
            want = {k: v for k, v in want.items() if k not in _FOLDER_TS_KEYS}
        assert got == want, message


# ---------------------------------------------------------------------------
# A synthetic library exercising every scan branch: models with/without
# previews, a gallery, front-matter sidecars, sub-folders, an empty folder, a
# hidden model, an orphan sidecar and a non-model file.
# ---------------------------------------------------------------------------
def _build_library(root: Path) -> Path:
    ck = root / "checkpoints"
    (ck / "sub").mkdir(parents=True)
    (ck / "empty_dir").mkdir()

    # model_a: a real safetensors + primary preview + front-matter notes
    write_safetensors(
        ck / "model_a.safetensors",
        {"w": ("F32", [2, 2], b"\x00" * 16)},
        metadata={"format": "pt", "znn_neo_original_bytes": "16"},
    )
    (ck / "model_a.webp").write_bytes(b"preview-bytes")
    (ck / "model_a.md").write_text(
        "---\n"
        "modelPage: https://civitai.com/models/42\n"
        "website: civitai\n"
        "baseModel: SD 1.5\n"
        "hashes:\n"
        "  SHA256: deadbeefcafe0123\n"
        "---\n"
        "# Notes body\n",
        encoding="utf-8",
    )

    # model_b: no preview, no notes → NO_PREVIEW_URL, null site info
    write_safetensors(ck / "model_b.safetensors", {"w": ("BF16", [4], b"\x00" * 8)})

    # model_g: a gallery (two previews) → array preview field
    write_safetensors(ck / "model_g.safetensors", {"w": ("F16", [4], b"\x00" * 8)})
    (ck / "model_g.webp").write_bytes(b"g0")
    (ck / "model_g.preview.png").write_bytes(b"g1")

    # sub/model_c: a preview in a sub-folder
    write_safetensors(ck / "sub" / "model_c.safetensors", {"w": ("F32", [1], b"\x00" * 4)})
    (ck / "sub" / "model_c.preview.png").write_bytes(b"c-prev")
    # an orphan sidecar in sub (no model claims it) → hygiene orphan
    (ck / "sub" / "stray.webp").write_bytes(b"orphan")

    # a hidden model (skipped unless include_hidden) + a non-model file
    write_safetensors(ck / ".hidden.safetensors", {"w": ("F32", [1], b"\x00" * 4)})
    (ck / "readme.json").write_text("{}")
    return ck


# ---------------------------------------------------------------------------
# scan_models golden (native == legacy), both hidden modes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("include_hidden", [False, True])
def test_scan_models_native_matches_legacy(tmp_path, monkeypatch, index_cache, include_hidden):
    _require_native()
    import folder_paths

    ck = _build_library(tmp_path)
    folder_paths.folder_names_and_paths.clear()
    folder_paths.folder_names_and_paths["checkpoints"] = ([str(ck)], set(folder_paths.supported_pt_extensions))
    utils = import_ext("utils")
    utils._base_paths_signature = None
    utils._base_paths_cache = {}
    manager = import_ext("manager")
    mm = manager.ModelManager()

    _set_engine(monkeypatch, "0")
    legacy = mm.scan_models("checkpoints", include_hidden)
    _set_engine(monkeypatch, "1")
    native = mm.scan_models("checkpoints", include_hidden)

    _assert_scan_parity(native, legacy, "native scan_models must be entry-for-entry identical to the Python walk")
    # sanity: the fixture produced what we expect (so the golden is meaningful)
    names = {(e["subFolder"], e["basename"]) for e in legacy}
    assert ("", "model_a") in names
    assert ("sub", "model_c") in names
    assert ("", "empty_dir") in names
    assert (("", ".hidden") in names) == include_hidden


def test_scan_models_fields_are_correct(tmp_path, monkeypatch, index_cache):
    _require_native()
    import folder_paths

    ck = _build_library(tmp_path)
    folder_paths.folder_names_and_paths.clear()
    folder_paths.folder_names_and_paths["checkpoints"] = ([str(ck)], set(folder_paths.supported_pt_extensions))
    utils = import_ext("utils")
    utils._base_paths_signature = None
    utils._base_paths_cache = {}
    manager = import_ext("manager")
    _set_engine(monkeypatch, "1")
    result = manager.ModelManager().scan_models("checkpoints", False)
    by_base = {e["basename"]: e for e in result if not e["isFolder"]}

    a = by_base["model_a"]
    assert a["extension"] == ".safetensors"
    assert a["isFolder"] is False
    assert a["sizeBytes"] > 0
    assert a["preview"] == "/model-manager/preview/checkpoints/0/model_a.webp"
    assert a["modelPage"] == "https://civitai.com/models/42"
    assert a["modelPlatform"] == "civitai"
    assert a["modelBase"] == "SD 1.5"
    assert a["modelSha256"] == "DEADBEEFCAFE0123"  # upper-cased
    assert isinstance(a["createdAt"], int) and isinstance(a["updatedAt"], int)

    b = by_base["model_b"]
    assert b["preview"] == "/model-manager/no-preview.svg"
    assert b["modelPage"] is None and b["modelSha256"] is None

    g = by_base["model_g"]
    assert isinstance(g["preview"], list) and len(g["preview"]) == 2
    assert g["preview"][0].endswith("/model_g.webp")
    assert g["preview"][1].endswith("/model_g.preview.png")

    # a folder entry
    folders = {e["basename"]: e for e in result if e["isFolder"]}
    assert "empty_dir" in folders
    assert folders["empty_dir"]["preview"] is None
    assert folders["empty_dir"]["extension"] == ""
    assert folders["empty_dir"]["sizeBytes"] == 0


def test_scan_models_index_persists_frontmatter(tmp_path, monkeypatch, index_cache):
    """The persistent index caches front-matter across scans."""
    mm = _require_native()
    import folder_paths

    ck = _build_library(tmp_path)
    folder_paths.folder_names_and_paths.clear()
    folder_paths.folder_names_and_paths["checkpoints"] = ([str(ck)], set(folder_paths.supported_pt_extensions))
    utils = import_ext("utils")
    utils._base_paths_signature = None
    utils._base_paths_cache = {}
    manager = import_ext("manager")
    _set_engine(monkeypatch, "1")
    first = manager.ModelManager().scan_models("checkpoints", False)
    # the index snapshot file was written
    assert (index_cache / "mm-scan-index.bin").exists()
    # a second scan (index warm) returns the same result
    second = manager.ModelManager().scan_models("checkpoints", False)
    assert first == second
    # mm_core sees at least one cached index dir
    assert mm.phase5_diagnostics()["indexDirs"] >= 1


# ---------------------------------------------------------------------------
# scan_hygiene golden (native == legacy)
# ---------------------------------------------------------------------------
def test_scan_hygiene_native_matches_legacy(tmp_path, monkeypatch):
    _require_native()
    ck = _build_library(tmp_path)
    utils = import_ext("utils")
    import folder_paths

    folder_paths.folder_names_and_paths.clear()
    folder_paths.folder_names_and_paths["checkpoints"] = ([str(ck)], set(folder_paths.supported_pt_extensions))
    utils._base_paths_signature = None
    utils._base_paths_cache = {}
    manager = import_ext("manager")
    mm = manager.ModelManager()

    _set_engine(monkeypatch, "0")
    legacy = mm.scan_hygiene()
    _set_engine(monkeypatch, "1")
    native = mm.scan_hygiene()

    assert native == legacy, "native scan_hygiene must match the Python walk"
    orphan_names = {o["fullname"] for o in legacy["orphans"]}
    assert "sub/stray.webp" in orphan_names, "the unclaimed sidecar is an orphan"
    assert "model_a.webp" not in orphan_names, "a claimed preview is not an orphan"
    empty_names = {e["fullname"] for e in legacy["empty"]}
    assert "empty_dir" in empty_names


# ---------------------------------------------------------------------------
# safetensors header golden (get_model_metadata / get_model_tensors)
# ---------------------------------------------------------------------------
def test_header_native_matches_legacy(tmp_path, monkeypatch):
    _require_native()
    utils = import_ext("utils")
    path = tmp_path / "m.safetensors"
    write_safetensors(
        path,
        {
            "alpha.weight": ("BF16", [2, 2], b"\x01\x02\x03\x04\x05\x06\x07\x08"),
            "beta.bias": ("F32", [3], b"\x00" * 12),
        },
        metadata={"format": "pt", "author": "test", "znn_compressed_vectors": "{}"},
    )
    p = str(path)

    _set_engine(monkeypatch, "0")
    legacy_meta = utils.get_model_metadata(p)
    legacy_tensors = utils.get_model_tensors(p)
    _set_engine(monkeypatch, "1")
    native_meta = utils.get_model_metadata(p)
    native_tensors = utils.get_model_tensors(p)

    assert native_meta == legacy_meta == {"format": "pt", "author": "test", "znn_compressed_vectors": "{}"}
    assert native_tensors == legacy_tensors
    # exact tensor layout (name/dtype/shape), __metadata__ excluded
    got = {t["name"]: (t["dtype"], t["shape"]) for t in native_tensors}
    assert got == {"alpha.weight": ("BF16", [2, 2]), "beta.bias": ("F32", [3])}


def test_header_without_metadata_is_empty(tmp_path, monkeypatch):
    _require_native()
    utils = import_ext("utils")
    path = tmp_path / "nometa.safetensors"
    write_safetensors(path, {"w": ("F32", [1], b"\x00" * 4)}, metadata=None)
    _set_engine(monkeypatch, "1")
    assert utils.get_model_metadata(str(path)) == {}
    assert len(utils.get_model_tensors(str(path))) == 1


def test_non_safetensors_and_missing_file_degrade(tmp_path, monkeypatch):
    _require_native()
    utils = import_ext("utils")
    # a non-.safetensors name short-circuits to {}/[] on both engines
    _set_engine(monkeypatch, "1")
    assert utils.get_model_metadata(str(tmp_path / "x.ckpt")) == {}
    assert utils.get_model_tensors(str(tmp_path / "x.ckpt")) == []
    # a missing .safetensors file degrades (never raises)
    assert utils.get_model_metadata(str(tmp_path / "gone.safetensors")) == {}
    assert utils.get_model_tensors(str(tmp_path / "gone.safetensors")) == []


# ---------------------------------------------------------------------------
# hash golden (compute_hashes native == the Python reference notations)
# ---------------------------------------------------------------------------
def test_compute_hashes_native_matches_legacy(tmp_path, monkeypatch):
    _require_native()
    identify = import_ext("identify")
    path = tmp_path / "blob.bin"
    # span the AutoV1 window (1 MiB offset + 64 KiB) so the window logic is hit
    data = bytes((i * 37 + 11) % 256 for i in range(1024 * 1024 + 70000))
    path.write_bytes(data)
    p = str(path)

    _set_engine(monkeypatch, "0")
    legacy = identify.compute_hashes(p)
    _set_engine(monkeypatch, "1")
    native = identify.compute_hashes(p)

    # The four always-present notations must match exactly (Civitai golden).
    for k in ("SHA256", "AutoV2", "AutoV1", "CRC32"):
        assert native[k] == legacy[k], f"{k}: native {native[k]} != legacy {legacy[k]}"
    # BLAKE3: native always computes it; legacy only when the module is present.
    if "BLAKE3" in legacy:
        assert native["BLAKE3"] == legacy["BLAKE3"]
    assert "BLAKE3" in native
    # notation shapes
    assert len(native["SHA256"]) == 64 and native["SHA256"] == native["SHA256"].upper()
    assert len(native["AutoV2"]) == 10
    assert len(native["AutoV1"]) == 8
    assert len(native["CRC32"]) == 8


def test_incremental_hasher_matches_hash_file(tmp_path):
    """The download inline hasher (hasher_new/update/finalize) equals hash_file."""
    mm = _require_native()
    path = tmp_path / "inc.bin"
    data = os.urandom(3 * 1024 * 1024 + 12345)
    path.write_bytes(data)

    one_shot = json.loads(mm.hash_file(str(path), ["SHA256"]))
    handle = mm.hasher_new(["SHA256"])
    # feed in odd-sized chunks (the download loop's chunking is arbitrary)
    off = 0
    for size in (1, 999, 64 * 1024, 1024 * 1024):
        while off < len(data):
            end = min(off + size, len(data))
            mm.hasher_update(handle, data[off:end])
            off = end
            if off >= len(data):
                break
        if off >= len(data):
            break
    incremental = json.loads(mm.hasher_finalize(handle))
    assert incremental["SHA256"] == one_shot["SHA256"]
    # finalizing an unknown/consumed handle raises (no silent wrong digest)
    with pytest.raises(KeyError):
        mm.hasher_finalize(handle)


def test_hash_file_all_notations_cross_check(tmp_path):
    """hash_file's notations agree with an independent hashlib computation."""
    import binascii
    import hashlib
    import struct

    mm = _require_native()
    path = tmp_path / "x.bin"
    data = os.urandom(2 * 1024 * 1024 + 7)
    path.write_bytes(data)
    got = json.loads(mm.hash_file(str(path), ["SHA256", "AutoV2", "AutoV1", "CRC32"]))

    sha = hashlib.sha256(data).hexdigest().upper()
    win = data[0x100000 : 0x100000 + 0x10000]
    av1 = hashlib.sha256(win).hexdigest()[:8].upper()
    crc = binascii.crc32(data) & 0xFFFFFFFF
    crc_swapped = struct.unpack(">I", struct.pack("<I", crc))[0]
    assert got["SHA256"] == sha
    assert got["AutoV2"] == sha[:10]
    assert got["AutoV1"] == av1
    assert got["CRC32"] == f"{crc_swapped:08X}"


# ---------------------------------------------------------------------------
# Phase 5 audit regressions (found by the Phase-6 bug check)
# ---------------------------------------------------------------------------
def test_scan_repeated_base_path_prefix_keeps_the_subfolder(tmp_path, monkeypatch, index_cache):
    """A sub-folder that repeats the base path must not be stripped twice.

    The legacy walk derived the relative path with ``str.replace(prefix, "")``,
    which removes EVERY occurrence: with a base of ``<root>/models/checkpoints``
    and a model in ``<root>/models/checkpoints/models/checkpoints/``, the middle
    segments vanished, so `subFolder` (and with it the preview URL and the
    `fullname` used by rename/delete) described a different file. The native
    Rust scan always used `strip_prefix`; the Python walk now uses
    `removeprefix`, and this pins the two together.
    """
    # Golden test: BOTH engines must run, so it skips where the native binary is
    # absent (ci.yml's verify job) exactly like the other parity tests here.
    _require_native()
    import folder_paths

    ck = tmp_path / "models" / "checkpoints"
    nested = ck / "models" / "checkpoints"
    nested.mkdir(parents=True)
    write_safetensors(nested / "deep.safetensors", {"w": ("F32", [1], b"\x00" * 4)})
    (nested / "deep.webp").write_bytes(b"preview")

    folder_paths.folder_names_and_paths.clear()
    folder_paths.folder_names_and_paths["checkpoints"] = ([str(ck)], set(folder_paths.supported_pt_extensions))
    utils = import_ext("utils")
    utils._base_paths_signature = None
    utils._base_paths_cache = {}
    manager = import_ext("manager")
    mm = manager.ModelManager()

    _set_engine(monkeypatch, "0")
    legacy = mm.scan_models("checkpoints", False)
    _set_engine(monkeypatch, "1")
    native = mm.scan_models("checkpoints", False)

    _assert_scan_parity(native, legacy, "the two engines must agree on the repeated prefix")
    entry = next(e for e in legacy if e["basename"] == "deep")
    assert entry["subFolder"] == "models/checkpoints", entry["subFolder"]
    assert entry["preview"] == "/model-manager/preview/checkpoints/0/models/checkpoints/deep.webp"


@pytest.mark.parametrize("where", ["body", "value"])
def test_scan_survives_a_non_utf8_sidecar(tmp_path, monkeypatch, index_cache, where):
    """A corrupt `.md` sidecar degrades that ONE model, never the listing.

    The legacy reader decoded the head strictly and only caught OSError, so an
    invalid byte raised UnicodeDecodeError out of `get_file_info` and the whole
    `GET /models/{folder}` answered "Read models failed". The native Rust scan
    reads lossily. Both engines now decode with replacement characters, which
    this pins entry-for-entry.
    """
    _require_native()  # skips without a built artifact (ci.yml's verify job)
    import folder_paths

    ck = tmp_path / "checkpoints"
    ck.mkdir(parents=True)
    write_safetensors(ck / "m.safetensors", {"w": ("F32", [1], b"\x00" * 4)})
    if where == "body":
        # the invalid bytes sit AFTER the front-matter block: the 4096-char head
        # read still decodes them, which is what used to kill the whole listing
        value = b"https://civitai.com/models/1\n"
        sidecar = b"---\nmodelPage: " + value + b"website: civitai\n---\n# Notes\n\xff\xfe invalid\n"
    else:
        # the invalid bytes sit INSIDE a front-matter value
        value = b"https://civitai.com/\xff\xfe/9\n"
        sidecar = b"---\nmodelPage: " + value + b"website: civitai\n---\n# Notes\n"
    (ck / "m.md").write_bytes(sidecar)

    folder_paths.folder_names_and_paths.clear()
    folder_paths.folder_names_and_paths["checkpoints"] = ([str(ck)], set(folder_paths.supported_pt_extensions))
    utils = import_ext("utils")
    utils._base_paths_signature = None
    utils._base_paths_cache = {}
    manager = import_ext("manager")
    mm = manager.ModelManager()

    _set_engine(monkeypatch, "0")
    legacy = mm.scan_models("checkpoints", False)
    _set_engine(monkeypatch, "1")
    native = mm.scan_models("checkpoints", False)

    assert native == legacy, "a corrupt sidecar must not diverge between engines"
    entry = next(e for e in legacy if e["basename"] == "m")
    assert entry["modelPlatform"] == "civitai"
    if where == "body":
        assert entry["modelPage"] == "https://civitai.com/models/1"
    else:
        # the invalid bytes decode to replacement characters in BOTH engines
        assert entry["modelPage"] == "https://civitai.com/\ufffd\ufffd/9", entry["modelPage"]
