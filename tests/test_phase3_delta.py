"""Phase 3 (L4) / Phase 8: delta route/batch goldens (single path).

The Phase-3 contract, kept verbatim after the Phase-8 removal of the legacy
vendored C core (the native Rust pipeline is the only engine):

* ``POST /model-manager/zipnn/delta-{compress,decompress}`` keep the historic
  ws contract (phase vocabulary ``prepare/delta/done``, ``zipnn_complete``
  with ``kind: "delta"``, stats ``originalBytes``/``compressedBytes``), and
  the historic ERROR WORDING reaches the UI verbatim;
* the compressor writes the official STREAMING delta form (cross-validation
  against the official pip zipnn 0.5.4 lives in the L5 CI gate,
  ``scripts/l5/official_cross.py`` — the transition-era cross-path tests
  against the vendored C core were retired together with it);
* the ``.neo-delta.json`` sidecar keeps ``basePad``/``ftPad`` and gains
  ``ftSha256`` (restore verification, ``.corrupt`` retreat);
* the Appendix-C SEGFAULT class (padded total % 256 KiB ∈ {1,2,3} — the C
  core died on it, Phase 0 BENCH §4.3 proved the then-production path
  reached it) round-trips through the production route byte-exactly (K5);
* the folder batch (``batch-folder``) produces the correct bundle tree
  (bundles, sidecar moves, delta restores, stats), with the walk and
  sidecar-move primitives golden-compared against independent Python
  reference walkers living in THIS file;
* delta tasks are cancellable through the cancel route.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import os
import struct
import time

import pytest
from harness import (
    REPO_ROOT,
    FakeRequest,
    import_ext,
    json_body,
    sha256_file,
    synth_bf16,
    synth_f32,
    write_safetensors,
)

DELTA_COMPRESS_ROUTE = ("POST", "/model-manager/zipnn/delta-compress")
DELTA_DECOMPRESS_ROUTE = ("POST", "/model-manager/zipnn/delta-decompress")
BATCH_ROUTE = ("POST", "/model-manager/zipnn/batch-folder")
CANCEL_ROUTE = ("POST", "/model-manager/zipnn/cancel")

_PROGRESS_KEYS = {"taskId", "progress", "phase", "mode"}
_COMPLETE_KEYS = {"taskId", "mode", "kind", "ok", "stats", "fullname"}
_DELTA_STATS_KEYS = {"originalBytes", "compressedBytes"}


# ---------------------------------------------------------------------------
# helpers (same conventions as test_phase2_routes.py)
# ---------------------------------------------------------------------------
def _compress_mod():
    return import_ext("compress")


def _reset_native_loader() -> object:
    config = import_ext("config")
    config.extension_uri = str(REPO_ROOT)
    native = import_ext("native")
    native._module = None
    native._reason = None
    native._attempted = False
    return native


def _native_core_or_skip():
    if not _native_binary_present():
        pytest.skip("native binary not built (scripts/build-native.sh)")
    _reset_native_loader()
    compress = _compress_mod()
    mm = compress.native_core()
    if mm is None:
        pytest.skip(f"native core unavailable: {import_ext('native').reason()}")
    return mm


def _native_binary_present() -> bool:
    native = _reset_native_loader()
    tag = native.platform_tag()
    if tag is None:
        return False
    binary = REPO_ROOT / "native" / "native-bin" / tag
    if not binary.is_dir():
        return False
    return any(p.name.startswith("mm_core") and p.name.endswith((".so", ".pyd")) for p in binary.iterdir())


async def _wait_task(compress, task_id: str, timeout: float = 180.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = compress.ZIPNN_TASKS.get(task_id)
        status = (entry or {}).get("status")
        if status in ("complete", "error"):
            return status
        await asyncio.sleep(0.02)
    raise TimeoutError(f"zipnn task {task_id} stuck: {compress.ZIPNN_TASKS.get(task_id)}")


async def _post(prompt_server, route, body: dict):
    compress = _compress_mod()
    compress.ZipNNRoutes().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[route]
    response = await handler(FakeRequest(body=body))
    return compress, json_body(response)


def _events(prompt_server) -> list[tuple]:
    return list(prompt_server.sent)


def _delta_pair(model_lib, base_name="base", ft_name="ft", *, drift: int = 4096, ft_meta=None):
    """A base + fine-tune pair with identical tensor layout (delta-able) and
    DIFFERENT metadata (the headers differ in length → the padding path is
    exercised, like every real fine-tune)."""
    ck = model_lib / "checkpoints"
    base_tensors = {
        "b": ("F32", [32], _f32(32, 2)),
        "w": ("BF16", [128, 64], synth_bf16(128 * 64, 1, low_entropy=True)),
    }
    write_safetensors(ck / f"{base_name}.safetensors", base_tensors, {"format": "pt", "notes": "the base model"})
    ft_tensors = {
        "b": ("F32", [32], _f32(32, 2)),
        "w": ("BF16", [128, 64], _drifted(synth_bf16(128 * 64, 1, low_entropy=True), drift)),
    }
    write_safetensors(
        ck / f"{ft_name}.safetensors",
        ft_tensors,
        ft_meta if ft_meta is not None else {"format": "pt"},
    )
    return ck / f"{base_name}.safetensors", ck / f"{ft_name}.safetensors"


def _f32(n: int, seed: int) -> bytes:
    return synth_f32(n, seed, low_entropy=True)


def _drifted(data: bytes, n: int) -> bytes:
    out = bytearray(data)
    for i in range(min(n, len(out))):
        out[i] ^= 0x3C
    return bytes(out)


def _raw_st_image(header_len: int, data: bytes) -> bytes:
    """A raw safetensors-shaped image with an EXACT header length (space
    padding — valid JSON whitespace). The delta flow never parses the JSON,
    so tests can pin the total length arithmetically (the SEGFAULT-class
    fixtures need exact `% 256 KiB` remainders)."""
    base_json = b'{"weight":{"dtype":"F32","shape":[4],"data_offsets":[0,16]}}'
    assert header_len >= len(base_json)
    header = base_json + b" " * (header_len - len(base_json))
    return struct.pack("<Q", header_len) + header + data


def _assert_delta_contract(events, task_id: str, mode: str):
    """The golden ws contract of a successful delta run (legacy phases:
    prepare → delta… → done; zipnn_complete with kind=delta)."""
    assert events, "no events were sent"
    names = [e[0] for e in events]
    assert names[0] == "update_zipnn_progress"
    assert names[-1] == "zipnn_complete"
    assert names[-2] == "update_zipnn_progress"

    first = events[0][1]
    assert set(first) == _PROGRESS_KEYS
    assert first == {"taskId": task_id, "progress": 0.0, "phase": "prepare", "mode": mode}

    last_progress = events[-2][1]
    assert set(last_progress) == _PROGRESS_KEYS
    assert last_progress["progress"] == 100.0
    assert last_progress["phase"] == "done"
    assert last_progress["mode"] == mode

    complete = events[-1][1]
    assert set(complete) == _COMPLETE_KEYS, complete.keys()
    assert complete["taskId"] == task_id
    assert complete["mode"] == mode
    assert complete["kind"] == "delta"
    assert complete["ok"] is True
    assert set(complete["stats"]) == _DELTA_STATS_KEYS, complete["stats"]

    prev = -1.0
    for name, data, _sid in events:
        if name != "update_zipnn_progress":
            continue
        assert set(data) == _PROGRESS_KEYS
        assert data["phase"] in ("prepare", "delta", "done"), data
        assert data["mode"] == mode
        assert 0.0 <= data["progress"] <= 100.0
        assert data["progress"] >= prev - 1e-9
        prev = data["progress"]


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


def test_native_core_exposes_the_phase3_api():
    mm = _native_core_or_skip()
    for fn in ("zipnn_delta_compress", "zipnn_delta_decompress", "walk_models", "move_with_sidecars"):
        assert hasattr(mm, fn), f"mm_core.{fn} missing (api_version={mm.api_version()})"
    # The Phase 3 surface is still present at api_version 6 (Phase 5/6/7 ADDED the
    # scan/hash functions; it did not remove the delta/batch ones).
    assert mm.api_version() == 6


# ---------------------------------------------------------------------------
# delta route — native golden
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_delta_roundtrip_native_golden(prompt_server, model_lib, monkeypatch):
    _native_core_or_skip()
    base, ft = _delta_pair(model_lib)
    ft_sha = sha256_file(ft)
    base_size, ft_size = base.stat().st_size, ft.stat().st_size
    # sidecars of the fine-tune must travel with the delta and come back
    (base.parent / "ft.webp").write_bytes(b"img")
    (base.parent / "ft.md").write_text("# notes")

    compress, payload = await _post(
        prompt_server,
        DELTA_COMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "baseFullname": "base.safetensors", "fullname": "ft.safetensors"},
    )
    assert payload["success"] is True, payload
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete", _events(prompt_server)
    _assert_delta_contract(_events(prompt_server), task_id, "compress")
    assert "handle" in compress.ZIPNN_TASKS[task_id], "delta tasks are cancellable"

    delta_dir = model_lib / "checkpoints" / "base_DeltaZNN"
    delta = delta_dir / "ft_delta_base.znn"
    sidecar = delta_dir / "ft_delta_base.znn.neo-delta.json"
    assert delta.is_file() and sidecar.is_file()
    assert not ft.exists(), "the redundant fine-tune was removed"
    assert base.is_file(), "the base is untouched"
    # sidecars followed the delta with their rename
    assert (delta_dir / "ft_delta_base.webp").is_file()
    assert (delta_dir / "ft_delta_base.md").is_file()
    assert not (base.parent / "ft.webp").exists() and not (base.parent / "ft.md").exists()

    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert set(meta) == {"basePad", "ftPad", "ftSha256"}, meta
    assert meta["ftSha256"] == ft_sha, "sidecar records the ORIGINAL ft digest"
    assert isinstance(meta["basePad"], int) and isinstance(meta["ftPad"], int)
    # the base header is the longer one → the FT got padded
    assert meta["ftPad"] > 0 and meta["basePad"] == 0

    stats = _events(prompt_server)[-1][1]["stats"]
    # legacy contract: originalBytes = the PADDED rendering length =
    # 8 + max(header lens) + data len = the LONGER of the two input files
    assert stats["originalBytes"] == max(base_size, ft_size), stats
    assert stats["compressedBytes"] == delta.stat().st_size
    # native output = the official STREAMING form (header byte 13 MSB set)
    with open(delta, "rb") as f:
        head = f.read(32)
    assert head[:2] == b"ZN" and head[13] & 0x80, "streaming delta container"
    assert head[9] == 1, "delta_compressed_type=byte"

    # decompress back through the route
    prompt_server.sent.clear()
    compress, payload = await _post(
        prompt_server,
        DELTA_DECOMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": "base_DeltaZNN/ft_delta_base.znn"},
    )
    assert payload["success"] is True, payload
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete", _events(prompt_server)
    _assert_delta_contract(_events(prompt_server), task_id, "decompress")

    restored = model_lib / "checkpoints" / "ft.safetensors"
    assert sha256_file(restored) == ft_sha, "delta round trip must be byte-exact"
    assert not delta.exists() and not sidecar.exists(), "delta + sidecar retired"
    assert not delta_dir.exists(), "the emptied bundle folder is gone"
    assert (restored.parent / "ft.webp").is_file() and (restored.parent / "ft.md").is_file()
    dstats = _events(prompt_server)[-1][1]["stats"]
    assert dstats["originalBytes"] == restored.stat().st_size


# ---------------------------------------------------------------------------
# cross-path compatibility (transition period runs BOTH engines)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delta_segfault_class_totals_roundtrip_native(prompt_server, model_lib, monkeypatch):
    """Padded totals ≡ 1/2/3 (mod 256 KiB): the vendored C core SEGFAULTs
    (demonstrated against the C core; Phase 0 proved the legacy delta route
    reaches it with real files). The native route must complete — byte-exactly."""
    _native_core_or_skip()
    ck = model_lib / "checkpoints"
    header_len = 64
    for k in (1, 2, 3):
        total = 262_144 + k
        data_len = total - 8 - header_len
        data = os.urandom(data_len)
        ft_data = bytearray(data)
        for i in range(min(64, data_len)):
            ft_data[i] ^= 0xA5
        base_img = _raw_st_image(header_len, data)
        ft_img = _raw_st_image(header_len, bytes(ft_data))
        assert len(base_img) % 262_144 == k, "fixture arithmetic"

        name = f"segv{k}"
        (ck / f"{name}-base.safetensors").write_bytes(base_img)
        (ck / f"{name}-ft.safetensors").write_bytes(ft_img)
        ft_sha = hashlib.sha256(ft_img).hexdigest()

        compress, payload = await _post(
            prompt_server,
            DELTA_COMPRESS_ROUTE,
            {
                "type": "checkpoints",
                "pathIndex": 0,
                "baseFullname": f"{name}-base.safetensors",
                "fullname": f"{name}-ft.safetensors",
            },
        )
        assert payload["success"] is True, payload
        task_id = payload["data"]["taskId"]
        assert await _wait_task(compress, task_id, timeout=60) == "complete", (k, _events(prompt_server))

        prompt_server.sent.clear()
        compress, payload = await _post(
            prompt_server,
            DELTA_DECOMPRESS_ROUTE,
            {
                "type": "checkpoints",
                "pathIndex": 0,
                "fullname": f"{name}-base_DeltaZNN/{name}-ft_delta_{name}-base.znn",
            },
        )
        assert payload["success"] is True, payload
        task_id = payload["data"]["taskId"]
        assert await _wait_task(compress, task_id, timeout=60) == "complete", (k, _events(prompt_server))
        restored = ck / f"{name}-ft.safetensors"
        assert sha256_file(restored) == ft_sha, f"k={k}: byte-exact"


# ---------------------------------------------------------------------------
# error wording (UI contract) + integrity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delta_data_size_mismatch_error_is_the_legacy_wording(prompt_server, model_lib, monkeypatch):
    _native_core_or_skip()
    ck = model_lib / "checkpoints"
    write_safetensors(ck / "mb.safetensors", {"w": ("BF16", [64], synth_bf16(64, 1))}, {"format": "pt"})
    write_safetensors(ck / "mf.safetensors", {"w": ("BF16", [128], synth_bf16(128, 2))}, {"format": "pt"})

    compress, payload = await _post(
        prompt_server,
        DELTA_COMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "baseFullname": "mb.safetensors", "fullname": "mf.safetensors"},
    )
    assert payload["success"] is True
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "error"
    complete = [e for e in _events(prompt_server) if e[0] == "zipnn_complete"][-1][1]
    assert complete["ok"] is False
    assert complete["error"] == (
        "the two models have different tensor data sizes (128 vs 256 bytes): "
        "delta compression only works between a base and a fine-tune with the "
        "exact same architecture and tensor layout"
    ), complete["error"]


@pytest.mark.asyncio
async def test_delta_sha_mismatch_keeps_delta_and_retreats_to_corrupt(prompt_server, model_lib, monkeypatch):
    _native_core_or_skip()
    _base, _ft = _delta_pair(model_lib, "vb", "vft")
    compress, payload = await _post(
        prompt_server,
        DELTA_COMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "baseFullname": "vb.safetensors", "fullname": "vft.safetensors"},
    )
    assert await _wait_task(compress, payload["data"]["taskId"]) == "complete"

    delta_dir = model_lib / "checkpoints" / "vb_DeltaZNN"
    delta = delta_dir / "vft_delta_vb.znn"
    sidecar = delta_dir / "vft_delta_vb.znn.neo-delta.json"
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    meta["ftSha256"] = "0" * 64  # the base "changed behind Neo's back"
    sidecar.write_text(json.dumps(meta), encoding="utf-8")
    delta_bytes = delta.read_bytes()

    prompt_server.sent.clear()
    compress, payload = await _post(
        prompt_server,
        DELTA_DECOMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": "vb_DeltaZNN/vft_delta_vb.znn"},
    )
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "error"
    complete = [e for e in _events(prompt_server) if e[0] == "zipnn_complete"][-1][1]
    assert "ftSha256" in complete["error"] and ".corrupt" in complete["error"], complete["error"]
    assert delta.read_bytes() == delta_bytes, "the delta file is KEPT"
    assert not (model_lib / "checkpoints" / "vft.safetensors").exists()
    corrupts = list((model_lib / "checkpoints").glob("vft.safetensors.corrupt"))
    assert corrupts, "the failed restore retreated to .corrupt"


@pytest.mark.asyncio
async def test_delta_paranoid_mode_native(prompt_server, model_lib, monkeypatch):
    _native_core_or_skip()
    monkeypatch.setenv("MM_ZNN_PARANOID", "1")
    _base, ft = _delta_pair(model_lib, "pb", "pft")
    ft_sha = sha256_file(ft)
    compress, payload = await _post(
        prompt_server,
        DELTA_COMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "baseFullname": "pb.safetensors", "fullname": "pft.safetensors"},
    )
    assert await _wait_task(compress, payload["data"]["taskId"], timeout=120) == "complete", _events(prompt_server)
    prompt_server.sent.clear()
    compress, payload = await _post(
        prompt_server,
        DELTA_DECOMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": "pb_DeltaZNN/pft_delta_pb.znn"},
    )
    assert await _wait_task(compress, payload["data"]["taskId"]) == "complete"
    assert sha256_file(model_lib / "checkpoints" / "pft.safetensors") == ft_sha


@pytest.mark.asyncio
async def test_delta_cancel_native(prompt_server, model_lib, monkeypatch):
    _native_core_or_skip()
    # a pair big enough that an immediate cancel usually lands mid-run;
    # both outcomes are valid but must be CONSISTENT (Phase-2 pattern)
    ck = model_lib / "checkpoints"
    big = synth_bf16(8 * 1024 * 1024, 8, low_entropy=False)
    write_safetensors(ck / "cb.safetensors", {"w": ("BF16", [8192, 1024], big)}, {"format": "pt"})
    write_safetensors(ck / "cf.safetensors", {"w": ("BF16", [8192, 1024], _drifted(big, 400_000))}, {"format": "pt"})

    compress, payload = await _post(
        prompt_server,
        DELTA_COMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "baseFullname": "cb.safetensors", "fullname": "cf.safetensors"},
    )
    assert payload["success"] is True
    task_id = payload["data"]["taskId"]
    _c, cancel_payload = await _post(prompt_server, CANCEL_ROUTE, {"taskId": task_id})
    status = await _wait_task(compress, task_id, timeout=120)
    if cancel_payload["success"] and cancel_payload["data"]["wasRunning"]:
        assert status == "error"
        complete = [e for e in _events(prompt_server) if e[0] == "zipnn_complete"][-1][1]
        assert complete["ok"] is False and "cancel" in complete["error"].lower()
        delta = ck / "cb_DeltaZNN" / "cf_delta_cb.znn"
        assert not delta.exists(), "a cancelled compress leaves no artifact"
        assert not (ck / "cb_DeltaZNN" / "cf_delta_cb.znn.tmp").exists()
        assert (ck / "cf.safetensors").exists(), "the fine-tune survives a cancelled compress"
    else:
        assert status == "complete"


# ---------------------------------------------------------------------------
# batch primitives — golden parity against the Python twins
# ---------------------------------------------------------------------------


def _batch_tree(model_lib):
    """A folder tree exercising every walker branch (bundles, hidden files,
    nested dirs, delta files + sidecars, blockers, legacy `_ZNN`)."""
    import folder_paths

    root = model_lib / "checkpoints"
    files = [
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
        "loose_delta_X.znn",
    ]
    for rel in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    folder_paths.folder_names_and_paths["checkpoints"] = (
        [str(root)],
        {".safetensors", ".gguf", ".ckpt", ".pt", ".bin", ".znn"},
    )
    utils = import_ext("utils")
    utils._base_paths_signature = None
    utils._base_paths_cache = {}
    return root


# Independent Python reference walkers (the contract the Rust walk_models
# must satisfy — verbatim semantics of the Phase-3 Python twins that Phase 8
# retired from py/compress.py; kept HERE so the golden parity survives the
# single-path switch and pins the Rust walk against an executable spec).
def _ref_walk_compress(folder: str) -> list[str]:
    compress_mod = _compress_mod()
    found: list[str] = []
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if not compress_mod._is_bundle_dir_name(d)]
        for name in names:
            if name.endswith(compress_mod.SAFE_SUFFIX) and not name.endswith(compress_mod.ZNN_SUFFIX):
                found.append(os.path.join(root, name))
    return sorted(found)


def _ref_walk_decompress(folder: str) -> list[str]:
    compress_mod = _compress_mod()
    utils = import_ext("utils")
    found: list[str] = []
    for root, _dirs, names in os.walk(folder):
        in_delta_folder = os.path.basename(root).endswith(utils.DELTA_FOLDER_SUFFIX)
        for name in names:
            if name.endswith(compress_mod.ZNN_SUFFIX) or (
                in_delta_folder and name.endswith(".znn") and "_delta_" in name
            ):
                found.append(os.path.join(root, name))
    return sorted(found)


def _ref_walk_blockers(folder: str) -> list[str]:
    import folder_paths

    compress_mod = _compress_mod()
    blockers: list[str] = []
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if not compress_mod._is_bundle_dir_name(d)]
        for name in names:
            extension = os.path.splitext(name)[1]
            if (
                extension in folder_paths.supported_pt_extensions
                and ".znn." not in name
                and not name.endswith(compress_mod.SAFE_SUFFIX)
                and not name.endswith(".znn")
            ):
                blockers.append(os.path.join(root, name))
    return sorted(blockers)


def test_walk_models_matches_the_reference_walkers(model_lib):
    mm = _native_core_or_skip()
    compress = _compress_mod()
    root = _batch_tree(model_lib)

    import folder_paths

    opts_common = {
        "bundleSuffixes": [compress.utils.DELTA_FOLDER_SUFFIX, compress.utils.ZNN_FOLDER_SUFFIX],
        "deltaFolderSuffix": compress.utils.DELTA_FOLDER_SUFFIX,
    }
    # compress walker
    got = json.loads(mm.walk_models(str(root), {"mode": "compress", "skipBundles": True, **opts_common}))
    want = _ref_walk_compress(str(root))
    assert got == want, (got, want)
    # decompress walker
    got = json.loads(mm.walk_models(str(root), {"mode": "decompress", **opts_common}))
    want = _ref_walk_decompress(str(root))
    assert got == want, (got, want)
    # blockers walker
    got = json.loads(
        mm.walk_models(
            str(root),
            {"mode": "blockers", "extensions": sorted(folder_paths.supported_pt_extensions), **opts_common},
        )
    )
    want = _ref_walk_blockers(str(root))
    assert got == want, (got, want)
    assert got and all(g.endswith((".gguf", ".ckpt")) for g in got)


def test_walk_models_releases_the_gil(tmp_path):
    """Long-running APIs must not hold the GIL (design invariant).

    The batch routes call ``walk_models`` from ``cpu_executor`` threads; a
    GIL-holding walk would freeze the ComfyUI event loop (WebSocket
    progress included) for the whole scan — the very class of bug Quick
    Win A1 removed for the model-info route. Mechanical check: a busy
    Python counter thread can only advance WHILE the walk runs if the
    walk released the GIL (the main thread holds it otherwise, and the
    few bytecodes between the snapshots cannot hit the 5 ms switch
    interval)."""
    mm = _native_core_or_skip()
    root = tmp_path / "lib"
    for d in range(150):
        sub = root / f"sub{d:03d}"
        sub.mkdir(parents=True)
        for f in range(10):
            (sub / f"m{f}.safetensors").write_bytes(b"x")

    import threading

    counter = itertools.count()
    last = -1
    stop = threading.Event()

    def spin():
        nonlocal last
        while not stop.is_set():
            last = next(counter)

    t = threading.Thread(target=spin, daemon=True)
    t.start()
    try:
        c0 = last
        got = json.loads(mm.walk_models(str(root), {"mode": "compress"}))
        c1 = last
    finally:
        stop.set()
        t.join(timeout=5)
    assert len(got) == 150 * 10, "sanity: the walk found every file"
    assert c1 > c0, (
        "the counter thread made no progress during walk_models — the GIL was held "
        "for the whole walk (GIL-discipline violation)"
    )


def test_move_with_sidecars_matches_the_python_mover(model_lib):
    mm = _native_core_or_skip()
    compress = _compress_mod()
    root = model_lib / "checkpoints"

    def build(sub: str):
        d = root / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / "ft.safetensors").write_bytes(b"m")
        (d / "ft.webp").write_bytes(b"primary")
        (d / "ft.preview.png").write_bytes(b"second")
        (d / "ft.preview2.mp4").write_bytes(b"third")
        (d / "ft.preview19.bmp").write_bytes(b"last slot")
        (d / "ft.md").write_text("# notes")
        (d / "ft.TXT").write_text("upper")
        (d / "ft.previewX.webp").write_bytes(b"not a slot")
        (d / "fts.webp").write_bytes(b"other stem")
        (d / "other.md").write_text("other")
        return d

    def listing(d):
        return sorted((p.name, p.read_bytes()) for p in d.rglob("*") if p.is_file())

    # python mover
    src_a = build("py") / "ft.safetensors"
    dst_a = root / "py-bundle" / "ft_delta_base.znn"
    dst_a.parent.mkdir(parents=True, exist_ok=True)
    dst_a.write_bytes(b"d")
    compress._delta_sidecar_move(str(src_a), str(dst_a))
    # rust mover
    src_b = build("rs") / "ft.safetensors"
    dst_b = root / "rs-bundle" / "ft_delta_base.znn"
    dst_b.parent.mkdir(parents=True, exist_ok=True)
    dst_b.write_bytes(b"d")
    mm.move_with_sidecars(str(src_b), str(dst_b))

    py_state = listing(dst_a.parent) + [(f"src/{n}", b) for n, b in listing(src_a.parent)]
    rs_state = listing(dst_b.parent) + [(f"src/{n}", b) for n, b in listing(src_b.parent)]
    assert py_state == rs_state, (py_state, rs_state)
    moved = {n for n, _ in listing(dst_b.parent)}
    assert moved == {
        "ft_delta_base.znn",
        "ft_delta_base.webp",
        "ft_delta_base.preview.png",
        "ft_delta_base.preview2.mp4",
        "ft_delta_base.preview19.bmp",
        "ft_delta_base.md",
        "ft_delta_base.TXT",
    }


# ---------------------------------------------------------------------------
# folder batch — native path, identical behaviour QA (Phase 3)
# ---------------------------------------------------------------------------


def _tree_state(root):
    return sorted(
        (str(p.relative_to(root)).replace(os.sep, "/"), hashlib.sha256(p.read_bytes()).hexdigest())
        for p in root.rglob("*")
        if p.is_file()
    )


@pytest.mark.asyncio
async def test_batch_folder_native_roundtrip(prompt_server, model_lib, monkeypatch):
    _native_core_or_skip()
    ck = model_lib / "checkpoints"

    # three models (one nested) + sidecars
    def models(tag: str):
        w1 = ("BF16", [256, 128], synth_bf16(256 * 128, 1, low_entropy=True))
        w2 = ("BF16", [256, 128], synth_bf16(256 * 128, 2, low_entropy=True))
        write_safetensors(ck / f"{tag}-m1.safetensors", {"w": w1}, {"format": "pt"})
        write_safetensors(ck / f"{tag}-m2.safetensors", {"w": w2}, {"format": "pt", "x": "y"})
        sub = ck / f"{tag}-sub"
        sub.mkdir()
        write_safetensors(sub / f"{tag}-m3.safetensors", {"w": ("F32", [128], _f32(128, 3))}, {"format": "pt"})
        (ck / f"{tag}-m1.webp").write_bytes(b"img")
        (ck / f"{tag}-m1.md").write_text("# n")

    models("n")
    before = _tree_state(ck)

    # ---- batch compress (type root → bundle INSIDE itself) ----
    compress, payload = await _post(
        prompt_server, BATCH_ROUTE, {"mode": "compress", "type": "checkpoints", "pathIndex": 0, "folder": "."}
    )
    assert payload["success"] is True, payload
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete", _events(prompt_server)
    complete = _events(prompt_server)[-1][1]
    assert complete["kind"] == "folder" and complete["mode"] == "compress"
    # The backend reports slash-normalized paths on every platform
    # (utils.normalize_path); str(Path) only agrees with that on POSIX, so
    # normalize the expectation the same way the tree-state helper above does.
    assert complete["stats"] == {"files": 3, "folder": str(ck / "checkpoints_DeltaZNN").replace(os.sep, "/")}

    bundle = ck / "checkpoints_DeltaZNN"
    assert (bundle / "n-m1.znn.safetensors").is_file()
    assert (bundle / "n-m2.znn.safetensors").is_file()
    assert (bundle / "n-sub" / "n-m3.znn.safetensors").is_file()
    # sidecars follow the COMPRESSED name (splitext of `n-m1.znn.safetensors`
    # = `n-m1.znn`) — the legacy `_delta_sidecar_move` semantics
    assert (bundle / "n-m1.znn.webp").is_file() and (bundle / "n-m1.znn.md").is_file()
    assert not (ck / "n-m1.safetensors").exists()
    assert not (ck / "n-sub").exists(), "emptied dirs are pruned"
    assert ck.is_dir(), "the type root itself stays"

    # ---- batch decompress (auto direction) ----
    prompt_server.sent.clear()
    compress, payload = await _post(
        prompt_server,
        BATCH_ROUTE,
        {"mode": "auto", "type": "checkpoints", "pathIndex": 0, "folder": "checkpoints_DeltaZNN"},
    )
    assert payload["success"] is True, payload
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete", _events(prompt_server)
    complete = _events(prompt_server)[-1][1]
    assert complete["kind"] == "folder" and complete["mode"] == "decompress"
    assert complete["stats"]["files"] == 3

    assert _tree_state(ck) == before, "batch round trip restores the tree byte-exactly"


@pytest.mark.asyncio
async def test_batch_compress_collects_in_place_compressed_models(prompt_server, model_lib, monkeypatch):
    """Option 1 (2026-10-02): in-place `.znn.safetensors` outside bundle
    sub-trees MOVE into the batch bundle (no re-compression), so no compressed
    straggler folder survives beside the bundle and the round trip stays
    byte-exact."""
    mm = _native_core_or_skip()
    compress_mod = _compress_mod()
    ck = model_lib / "checkpoints"

    def seed_inplace(folder, tag):
        folder.mkdir(parents=True, exist_ok=True)
        src = folder / f"{tag}.safetensors"
        write_safetensors(src, {"w": ("BF16", [256, 128], synth_bf16(256 * 128, 7, low_entropy=True))})
        plain_hash = hashlib.sha256(src.read_bytes()).hexdigest()
        dst = folder / f"{tag}.znn.safetensors"
        compress_mod._run_native_job_sync(
            mm, None, lambda: mm.zipnn_compress(str(src), str(dst), {"threads": 0, "paranoid": False}), "seed"
        )
        src.unlink()
        return dst, plain_hash

    # plain model at the root + an in-place compressed one inside a subfolder
    write_safetensors(ck / "p.safetensors", {"w": ("BF16", [256, 128], synth_bf16(256 * 128, 8, low_entropy=True))})
    p_hash = hashlib.sha256((ck / "p.safetensors").read_bytes()).hexdigest()
    inplace, seed_hash = seed_inplace(ck / "Anime", "a")
    (ck / "Anime" / "a.znn.webp").write_bytes(b"img")
    webp_hash = hashlib.sha256((ck / "Anime" / "a.znn.webp").read_bytes()).hexdigest()

    compress, payload = await _post(
        prompt_server, BATCH_ROUTE, {"mode": "compress", "type": "checkpoints", "pathIndex": 0, "folder": "."}
    )
    assert payload["success"] is True, payload
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete", _events(prompt_server)
    complete = _events(prompt_server)[-1][1]
    assert complete["stats"]["files"] == 2, complete["stats"]

    bundle = ck / "checkpoints_DeltaZNN"
    assert (bundle / "p.znn.safetensors").is_file()
    assert (bundle / "Anime" / "a.znn.safetensors").is_file(), "in-place model moved into the bundle"
    assert (bundle / "Anime" / "a.znn.webp").is_file(), "sidecars follow the moved model"
    assert not (ck / "Anime").exists(), "the emptied subfolder is pruned"
    assert not inplace.exists()

    # round trip: auto on the bundle decompresses every bundle member back to
    # plain models - the moved in-place file included: it is bundle CONTENT
    # now, so it restores as the plain model it was seeded from (sidecar
    # re-based onto the plain name). The tree therefore converges to the
    # all-plain form, not to the mixed pre-batch form.
    prompt_server.sent.clear()
    compress, payload = await _post(
        prompt_server,
        BATCH_ROUTE,
        {"mode": "auto", "type": "checkpoints", "pathIndex": 0, "folder": "checkpoints_DeltaZNN"},
    )
    assert payload["success"] is True, payload
    assert await _wait_task(compress, payload["data"]["taskId"]) == "complete", _events(prompt_server)
    state = dict(_tree_state(ck))
    assert state == {
        "p.safetensors": p_hash,
        "Anime/a.safetensors": seed_hash,
        "Anime/a.webp": webp_hash,
    }, state


@pytest.mark.asyncio
async def test_batch_auto_on_legacy_in_place_root_still_decompresses_in_place(prompt_server, model_lib, monkeypatch):
    """The Option-1 collect set must NOT flip the documented legacy route: a
    type root holding ONLY in-place compressed models auto-resolves to
    decompress-in-place (no bundle is created)."""
    mm = _native_core_or_skip()
    compress_mod = _compress_mod()
    ck = model_lib / "checkpoints"
    src = ck / "legacy.safetensors"
    write_safetensors(src, {"w": ("BF16", [256, 128], synth_bf16(256 * 128, 9, low_entropy=True))})
    znn = ck / "legacy.znn.safetensors"
    compress_mod._run_native_job_sync(
        mm, None, lambda: mm.zipnn_compress(str(src), str(znn), {"threads": 0, "paranoid": False}), "seed"
    )
    src.unlink()

    compress, payload = await _post(
        prompt_server, BATCH_ROUTE, {"mode": "auto", "type": "checkpoints", "pathIndex": 0, "folder": "."}
    )
    assert payload["success"] is True, payload
    assert await _wait_task(compress, payload["data"]["taskId"]) == "complete", _events(prompt_server)
    complete = _events(prompt_server)[-1][1]
    assert complete["mode"] == "decompress", complete
    assert (ck / "legacy.safetensors").is_file()
    assert not (ck / "checkpoints_DeltaZNN").exists(), "legacy in-place roots decompress where they are"


@pytest.mark.asyncio
async def test_batch_compress_inplace_only_subfolder_moves_to_bundle(prompt_server, model_lib, monkeypatch):
    """Explicit compress on a non-root folder whose only content is in-place
    compressed models: they move into the sibling bundle (Option 1), the
    emptied folder is pruned."""
    mm = _native_core_or_skip()
    compress_mod = _compress_mod()
    ck = model_lib / "checkpoints"
    sub = ck / "sub"
    sub.mkdir()
    src = sub / "s.safetensors"
    write_safetensors(src, {"w": ("BF16", [256, 128], synth_bf16(256 * 128, 10, low_entropy=True))})
    compress_mod._run_native_job_sync(
        mm,
        None,
        lambda: mm.zipnn_compress(str(src), str(sub / "s.znn.safetensors"), {"threads": 0, "paranoid": False}),
        "seed",
    )
    src.unlink()

    compress, payload = await _post(
        prompt_server, BATCH_ROUTE, {"mode": "compress", "type": "checkpoints", "pathIndex": 0, "folder": "sub"}
    )
    assert payload["success"] is True, payload
    assert await _wait_task(compress, payload["data"]["taskId"]) == "complete", _events(prompt_server)
    bundle = ck / "sub_DeltaZNN"
    assert (bundle / "s.znn.safetensors").is_file()
    assert not sub.exists(), "the emptied subfolder is pruned"


@pytest.mark.asyncio
async def test_batch_folder_with_delta_files_native(prompt_server, model_lib, monkeypatch):
    """A bundle holding a delta file batch-decompresses through the native
    delta job (base resolved beside the bundle, sidecar removed)."""
    _native_core_or_skip()
    _base, ft = _delta_pair(model_lib, "bb", "bff")
    ft_sha = sha256_file(ft)

    compress, payload = await _post(
        prompt_server,
        DELTA_COMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "baseFullname": "bb.safetensors", "fullname": "bff.safetensors"},
    )
    assert await _wait_task(compress, payload["data"]["taskId"]) == "complete"

    prompt_server.sent.clear()
    compress, payload = await _post(
        prompt_server,
        BATCH_ROUTE,
        {"mode": "decompress", "type": "checkpoints", "pathIndex": 0, "folder": "bb_DeltaZNN"},
    )
    assert payload["success"] is True, payload
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete", _events(prompt_server)
    restored = model_lib / "checkpoints" / "bff.safetensors"
    assert sha256_file(restored) == ft_sha
    assert not (model_lib / "checkpoints" / "bb_DeltaZNN").exists()
