"""Plan Phase 2 (L4): route/ws contract golden tests + cross-path parity.

The Phase-2 switchover contract (Plan §6.2):
``POST /model-manager/zipnn/{compress,decompress}`` must emit the IDENTICAL
websocket event sequence and stats shapes on both code paths —
``MM_NATIVE=0`` (legacy vendored C core) and the native Rust pipeline — so
the frontend needs no changes at all. These tests pin:

* the exact event names / payload key sets / phase vocabulary / stats keys
  (golden assertions, both paths);
* cross-path file compatibility: native-compressed files decompress through
  the legacy path and vice versa (the transition period runs BOTH);
* blob-level parity: for the same source, both paths store byte-identical
  per-tensor ZN payloads and identical ``znn_compressed_vectors`` values
  (the codec's L2 byte-identity, re-proved through the production routes);
* the cancel route (native cooperative cancel; legacy refusal);
* the startup ``.tmp``/``.corrupt`` cleanup sweep (Plan §4.4.4).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import pytest
from harness import (
    REPO_ROOT,
    FakeRequest,
    import_ext,
    json_body,
    read_safetensors,
    sha256_file,
    synth_bf16,
    synth_f32,
    write_safetensors,
)

COMPRESS_ROUTE = ("POST", "/model-manager/zipnn/compress")
DECOMPRESS_ROUTE = ("POST", "/model-manager/zipnn/decompress")
CANCEL_ROUTE = ("POST", "/model-manager/zipnn/cancel")

_PROGRESS_KEYS = {"taskId", "progress", "phase", "mode"}
_COMPLETE_KEYS = {"taskId", "mode", "ok", "stats", "fullname"}
_COMPRESS_STATS_KEYS = {"originalBytes", "compressedBytes", "tensors", "compressedTensors"}
_DECOMPRESS_STATS_KEYS = {"tensors", "decompressedTensors"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _compress_mod():
    return import_ext("compress")


def _reset_native_loader() -> object:
    """py/native with pristine attempt state + the repo's native-bin dir."""
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
    suffixes = (".so", ".pyd")
    return any(p.name.startswith("mm_core") and p.name.endswith(suffixes) for p in binary.iterdir())


def _legacy_available() -> bool:
    """The vendored ZipNN C path works here (linux-x86_64 + matching CPython).

    Probes cheaply FIRST: without torch/numpy/safetensors the legacy path
    cannot run at all, and calling ``ensure_zipnn()`` anyway would kick off
    a pointless multi-minute C source build on foreign platforms (CI sets
    ``MMNEO_SKIP_LEGACY=1`` for the same reason)."""
    if os.environ.get("MMNEO_SKIP_LEGACY", "").strip().lower() in ("1", "on", "true", "yes"):
        return False
    try:
        import numpy  # noqa: F401
        import safetensors  # noqa: F401
        import torch  # noqa: F401
    except Exception:
        return False
    compress = _compress_mod()
    try:
        compress.ensure_zipnn()
        return compress.zipnn_available()
    except Exception:
        return False


async def _wait_task(compress, task_id: str, timeout: float = 180.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = compress.ZIPNN_TASKS.get(task_id)
        status = (entry or {}).get("status")
        if status in ("complete", "error"):
            return status
        await asyncio.sleep(0.02)
    raise TimeoutError(f"zipnn task {task_id} stuck: {compress.ZIPNN_TASKS.get(task_id)}")


async def _post_zipnn(prompt_server, route, body: dict):
    compress = _compress_mod()
    compress.ZipNNRoutes().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[route]
    response = await handler(FakeRequest(body=body))
    payload = json_body(response)
    return compress, payload


def _events(prompt_server) -> list[tuple]:
    return list(prompt_server.sent)


def _make_model(model_lib, name="model", *, metadata=None, sort_keys=False, big=False):
    """A fixture in TORCH-CANONICAL order (dtype alignment descending, then
    name — the reference serializer's order): the LEGACY round trip only
    restores byte-exactly when the source is already in that order (its
    save_file re-sorts), while the native path preserves ANY order. Tests
    that assert legacy byte-exactness rely on this layout."""
    path = model_lib / "checkpoints" / f"{name}.safetensors"
    if big:
        tensors = {
            "n": ("F32", [16], synth_f32(16, 5, low_entropy=True)),
            "w0": ("BF16", [1024, 512], synth_bf16(1024 * 512, 3, low_entropy=True)),
            "w1": ("BF16", [1024, 512], synth_bf16(1024 * 512, 4, low_entropy=True)),
        }
    else:
        tensors = {
            "b": ("F32", [32], synth_f32(32, 2, low_entropy=True)),
            "w": ("BF16", [128, 64], synth_bf16(128 * 64, 1, low_entropy=True)),
        }
    write_safetensors(path, tensors, metadata if metadata is not None else {"format": "pt"}, sort_keys=sort_keys)
    return path


def _assert_progress_contract(events, task_id: str, mode: str, stats_keys: set[str]):
    """The golden ws contract for a successful single-file run."""
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
    assert last_progress["taskId"] == task_id
    assert last_progress["progress"] == 100.0
    assert last_progress["phase"] == "done"
    assert last_progress["mode"] == mode

    complete = events[-1][1]
    assert set(complete) == _COMPLETE_KEYS, complete.keys()
    assert complete["taskId"] == task_id
    assert complete["mode"] == mode
    assert complete["ok"] is True
    assert complete["fullname"]
    assert set(complete["stats"]) == stats_keys, complete["stats"]

    # every intermediate progress event: right keys, right vocab, monotone
    prev = -1.0
    for name, data, _sid in events:
        if name != "update_zipnn_progress":
            continue
        assert set(data) == _PROGRESS_KEYS
        assert data["phase"] in ("prepare", "tensors", "done")
        assert data["mode"] == mode
        assert 0.0 <= data["progress"] <= 100.0
        assert data["progress"] >= prev - 1e-9
        prev = data["progress"]


# ---------------------------------------------------------------------------
# golden ws contract — legacy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_compress_decompress_legacy_golden(prompt_server, model_lib, monkeypatch):
    if not _legacy_available():
        pytest.skip("vendored ZipNN C core unavailable on this platform")
    monkeypatch.setenv("MM_NATIVE", "0")
    src = _make_model(model_lib, "legacy-golden")
    original_sha = sha256_file(src)
    znn_name = "legacy-golden.znn.safetensors"

    compress, payload = await _post_zipnn(
        prompt_server,
        COMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": "legacy-golden.safetensors"},
    )
    assert payload["success"] is True, payload
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete"
    _assert_progress_contract(_events(prompt_server), task_id, "compress", _COMPRESS_STATS_KEYS)
    stats = _events(prompt_server)[-1][1]["stats"]
    assert stats["tensors"] == 2

    znn_path = model_lib / "checkpoints" / znn_name
    assert znn_path.exists() and not src.exists(), "original replaced by the .znn file"

    # decompress back (fresh event log)
    prompt_server.sent.clear()
    compress, payload = await _post_zipnn(
        prompt_server,
        DECOMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": znn_name},
    )
    assert payload["success"] is True, payload
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete"
    _assert_progress_contract(_events(prompt_server), task_id, "decompress", _DECOMPRESS_STATS_KEYS)
    restored = model_lib / "checkpoints" / "legacy-golden.safetensors"
    assert sha256_file(restored) == original_sha, "legacy round trip must be byte-exact"


# ---------------------------------------------------------------------------
# golden ws contract — native path (same golden, both paths)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_compress_decompress_native_golden(prompt_server, model_lib, monkeypatch):
    if not _native_binary_present():
        pytest.skip("native binary not built (scripts/build-native.sh)")
    _reset_native_loader()
    monkeypatch.setenv("MM_NATIVE", "1")  # REQUIRE the native path (no silent fallback)
    src = _make_model(model_lib, "native-golden")
    original_sha = sha256_file(src)
    znn_name = "native-golden.znn.safetensors"

    compress, payload = await _post_zipnn(
        prompt_server,
        COMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": "native-golden.safetensors"},
    )
    assert payload["success"] is True, payload
    task_id = payload["data"]["taskId"]
    status = await _wait_task(compress, task_id)
    assert status == "complete", _events(prompt_server)
    _assert_progress_contract(_events(prompt_server), task_id, "compress", _COMPRESS_STATS_KEYS)
    # the native task registered its job handle (cancel route support)
    assert "handle" in compress.ZIPNN_TASKS[task_id]

    znn_path = model_lib / "checkpoints" / znn_name
    assert znn_path.exists() and not src.exists()
    header, _ = read_safetensors(znn_path)
    meta = header["__metadata__"]
    assert meta["znn_neo_src_sha256"] == original_sha
    assert meta["znn_neo_exact"] == "1"

    prompt_server.sent.clear()
    compress, payload = await _post_zipnn(
        prompt_server,
        DECOMPRESS_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": znn_name},
    )
    assert payload["success"] is True, payload
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete"
    _assert_progress_contract(_events(prompt_server), task_id, "decompress", _DECOMPRESS_STATS_KEYS)
    restored = model_lib / "checkpoints" / "native-golden.safetensors"
    assert sha256_file(restored) == original_sha, "native round trip must be byte-exact"


# ---------------------------------------------------------------------------
# cross-path compatibility (the MM_NATIVE transition period, Plan §5.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_path_native_compress_legacy_decompress(prompt_server, model_lib, monkeypatch):
    if not _native_binary_present():
        pytest.skip("native binary not built")
    if not _legacy_available():
        pytest.skip("vendored ZipNN C core unavailable")
    _reset_native_loader()
    monkeypatch.setenv("MM_NATIVE", "1")
    src = _make_model(model_lib, "x2l", sort_keys=True)  # sorted ⇒ legacy restore is byte-exact too
    original_sha = sha256_file(src)

    compress, payload = await _post_zipnn(
        prompt_server, COMPRESS_ROUTE, {"type": "checkpoints", "pathIndex": 0, "fullname": "x2l.safetensors"}
    )
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete"

    monkeypatch.setenv("MM_NATIVE", "0")
    prompt_server.sent.clear()
    compress, payload = await _post_zipnn(
        prompt_server, DECOMPRESS_ROUTE, {"type": "checkpoints", "pathIndex": 0, "fullname": "x2l.znn.safetensors"}
    )
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete"
    restored = model_lib / "checkpoints" / "x2l.safetensors"
    header, tensors = read_safetensors(restored)
    assert sha256_file(restored) == original_sha, "legacy must restore a native file byte-exactly (sorted source)"
    # no Neo bookkeeping leaked into the restored metadata
    for key in ("znn_neo_src_sha256", "znn_neo_exact", "znn_neo_src_meta_absent", "znn_neo_original_bytes"):
        assert key not in header.get("__metadata__", {})
    assert tensors


@pytest.mark.asyncio
async def test_cross_path_legacy_compress_native_decompress(prompt_server, model_lib, monkeypatch):
    if not _native_binary_present():
        pytest.skip("native binary not built")
    if not _legacy_available():
        pytest.skip("vendored ZipNN C core unavailable")
    monkeypatch.setenv("MM_NATIVE", "0")
    src = _make_model(model_lib, "l2x")
    _hdr, original_tensors = read_safetensors(src)

    compress, payload = await _post_zipnn(
        prompt_server, COMPRESS_ROUTE, {"type": "checkpoints", "pathIndex": 0, "fullname": "l2x.safetensors"}
    )
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete"
    znn_path = model_lib / "checkpoints" / "l2x.znn.safetensors"
    legacy_header, _ = read_safetensors(znn_path)
    assert "znn_neo_src_sha256" not in legacy_header.get("__metadata__", {}), "legacy files carry no sha"

    _reset_native_loader()
    monkeypatch.setenv("MM_NATIVE", "1")
    prompt_server.sent.clear()
    compress, payload = await _post_zipnn(
        prompt_server, DECOMPRESS_ROUTE, {"type": "checkpoints", "pathIndex": 0, "fullname": "l2x.znn.safetensors"}
    )
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete"
    restored = model_lib / "checkpoints" / "l2x.safetensors"
    _rh, restored_tensors = read_safetensors(restored)
    # byte-exactness is impossible here (legacy files record no sha and torch
    # re-sorts), but the SEMANTIC content must match exactly
    assert restored_tensors == original_tensors


def test_blob_parity_both_paths_store_identical_bytes(tmp_path, monkeypatch):
    """For one source, legacy and native compression must store
    byte-identical per-tensor ZN blobs and an identical infos record — the
    L2 byte-identity of the codec, re-proved through the two production
    compressors (legacy = vendored C via zipnn.py, native = Rust pipeline)."""
    if not _native_binary_present():
        pytest.skip("native binary not built")
    if not _legacy_available():
        pytest.skip("vendored ZipNN C core unavailable")

    src = tmp_path / "parity.safetensors"
    write_safetensors(
        src,
        {
            "bf": ("BF16", [256, 128], synth_bf16(256 * 128, 21, low_entropy=True)),
            "f32": ("F32", [128, 64], synth_f32(128 * 64, 22, low_entropy=True)),
            "f16": ("F16", [128, 64], __import__("harness").synth_f16(128 * 64, 23, low_entropy=True)),
            "fp8": ("F8_E4M3", [512], __import__("harness").synth_fp8(512, 24, low_entropy=True)),
            "u8": ("U8", [100], bytes(range(100))),
        },
        {"format": "pt"},
        sort_keys=True,
    )

    # legacy
    compress = _compress_mod()
    legacy_out = tmp_path / "parity.legacy.znn.safetensors"
    stats_legacy = compress.compress_safetensors(str(src), str(legacy_out), lambda *_: None)

    # native
    native = _reset_native_loader()
    monkeypatch.delenv("MM_NATIVE", raising=False)
    sys.modules.pop("mm_core", None)
    assert native.load(), native.reason()
    mm = native.core()
    native_out = tmp_path / "parity.native.znn.safetensors"
    handle = mm.zipnn_compress(str(src), str(native_out), None)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        _d, _t, phase = mm.job_progress(handle)
        if phase in ("done", "failed"):
            break
        time.sleep(0.01)
    assert phase == "done", mm.job_error(handle)
    stats_native = json.loads(mm.job_result(handle))["stats"]

    lh, lt = read_safetensors(legacy_out)
    nh, nt = read_safetensors(native_out)
    lmeta, nmeta = lh["__metadata__"], nh["__metadata__"]

    # the infos record is byte-identical (Python json.dumps parity)
    assert lmeta["znn_compressed_vectors"] == nmeta["znn_compressed_vectors"]
    # the legacy-only size key matches too
    assert lmeta["znn_neo_original_bytes"] == nmeta["znn_neo_original_bytes"]
    infos = json.loads(nmeta["znn_compressed_vectors"])

    # every stored tensor — compressed blobs AND pass-throughs — is
    # byte-identical between the two files
    assert set(lt) == set(nt)
    for name in lt:
        assert lt[name][2] == nt[name][2], f"tensor {name} bytes differ between paths"
        assert lt[name][0] == nt[name][0]
    assert set(infos) <= set(nt)

    # stats parity (same counting rules on both paths)
    assert stats_legacy == stats_native, (stats_legacy, stats_native)


# ---------------------------------------------------------------------------
# cancel route + startup cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_route_native(prompt_server, model_lib, monkeypatch):
    if not _native_binary_present():
        pytest.skip("native binary not built")
    _reset_native_loader()
    monkeypatch.setenv("MM_NATIVE", "1")
    _make_model(model_lib, "cancel-me", big=True)

    compress, payload = await _post_zipnn(
        prompt_server, COMPRESS_ROUTE, {"type": "checkpoints", "pathIndex": 0, "fullname": "cancel-me.safetensors"}
    )
    assert payload["success"] is True
    task_id = payload["data"]["taskId"]
    # cancel immediately — on a very fast machine the job may already be
    # done; both outcomes are valid but must be CONSISTENT
    _c, cancel_payload = await _post_zipnn(prompt_server, CANCEL_ROUTE, {"taskId": task_id})
    status = await _wait_task(compress, task_id)
    if cancel_payload["success"] and cancel_payload["data"]["wasRunning"]:
        assert status == "error"
        complete = [e for e in _events(prompt_server) if e[0] == "zipnn_complete"][-1][1]
        assert complete["ok"] is False
        assert "cancel" in complete["error"].lower()
        assert not (model_lib / "checkpoints" / "cancel-me.znn.safetensors").exists()
        assert not (model_lib / "checkpoints" / "cancel-me.znn.safetensors.tmp").exists()
    else:
        assert status == "complete"

    # unknown task id
    _c, bad = await _post_zipnn(prompt_server, CANCEL_ROUTE, {"taskId": "deadbeef"})
    assert bad["success"] is False and "unknown" in bad["error"]


@pytest.mark.asyncio
async def test_cancel_route_rejects_legacy_tasks(prompt_server, model_lib, monkeypatch):
    if not _legacy_available():
        pytest.skip("vendored ZipNN C core unavailable")
    monkeypatch.setenv("MM_NATIVE", "0")
    _make_model(model_lib, "legacy-cancel")
    compress, payload = await _post_zipnn(
        prompt_server, COMPRESS_ROUTE, {"type": "checkpoints", "pathIndex": 0, "fullname": "legacy-cancel.safetensors"}
    )
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete"
    _c, cancel_payload = await _post_zipnn(prompt_server, CANCEL_ROUTE, {"taskId": task_id})
    assert cancel_payload["success"] is False
    assert "legacy" in cancel_payload["error"]


@pytest.mark.asyncio
async def test_native_required_but_missing_fails_cleanly(prompt_server, model_lib, monkeypatch, tmp_path):
    """MM_NATIVE=1 with no binary: the task fails with the loader's reason —
    never a silent fallback to the C path (Plan §5.4)."""
    compress = _compress_mod()
    config = import_ext("config")
    saved_uri = config.extension_uri
    native = import_ext("native")
    saved_state = (native._module, native._reason, native._attempted)
    try:
        config.extension_uri = str(tmp_path)  # no native-bin under here
        native._module, native._reason, native._attempted = None, None, False
        sys.modules.pop("mm_core", None)
        monkeypatch.setenv("MM_NATIVE", "1")
        _make_model(model_lib, "req-missing")
        compress.ZipNNRoutes().add_routes(prompt_server.routes)
        handler = prompt_server.routes.handlers[COMPRESS_ROUTE]
        response = await handler(
            FakeRequest(body={"type": "checkpoints", "pathIndex": 0, "fullname": "req-missing.safetensors"})
        )
        payload = json_body(response)
        assert payload["success"] is True  # the task starts, then fails
        task_id = payload["data"]["taskId"]
        assert await _wait_task(compress, task_id) == "error"
        complete = [e for e in _events(prompt_server) if e[0] == "zipnn_complete"][-1][1]
        assert complete["ok"] is False
        assert "MM_NATIVE=1" in complete["error"]
        # the source is untouched
        assert (model_lib / "checkpoints" / "req-missing.safetensors").exists()
    finally:
        config.extension_uri = saved_uri
        native._module, native._reason, native._attempted = saved_state
        sys.modules.pop("mm_core", None)


def test_startup_cleanup_sweeps_tmp_and_reports_corrupt(model_lib):
    compress = _compress_mod()
    checkpoints = model_lib / "checkpoints"
    old = time.time() - 3600
    fresh = time.time()

    stale_tmp = checkpoints / "a.znn.safetensors.tmp"
    stale_tmp.write_bytes(b"partial")
    os.utime(stale_tmp, (old, old))
    fresh_tmp = checkpoints / "b.safetensors.tmp"
    fresh_tmp.write_bytes(b"in-flight?")
    os.utime(fresh_tmp, (fresh, fresh))
    corrupt = checkpoints / "c.safetensors.corrupt"
    corrupt.write_bytes(b"diagnostic")
    unrelated = checkpoints / "notes.tmp"  # not a ZipNN name → untouched
    unrelated.write_bytes(b"mine")
    os.utime(unrelated, (old, old))

    utils = import_ext("utils")
    report = compress.cleanup_stray_files()
    # the sweep reports slash-normalized paths (the backend's reporting form
    # on every OS) — compare normalized
    assert utils.normalize_path(str(stale_tmp)) in report["removed"]
    assert fresh_tmp.exists(), "young .tmp files may belong to a live run"
    assert utils.normalize_path(str(corrupt)) in report["corrupt"] and corrupt.exists(), ".corrupt files are kept"
    assert unrelated.exists(), "foreign .tmp files are never touched"
    assert not stale_tmp.exists()
