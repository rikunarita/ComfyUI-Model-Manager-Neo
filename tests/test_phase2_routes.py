"""Plan Phase 2 (L4) / Phase 8: route/ws contract golden tests (single path).

The Phase-2 switchover contract (Plan §6.2), kept verbatim after the Phase-8
removal of the legacy vendored C core and the ``MM_NATIVE`` switch:
``POST /model-manager/zipnn/{compress,decompress}`` emits the SAME websocket
event sequence and stats shapes the frontend has always consumed — the native
Rust pipeline is now the only engine. These tests pin:

* the exact event names / payload key sets / phase vocabulary / stats keys
  (golden assertions through the production routes, byte-exact round trip);
* the cancel route (cooperative native cancel; a task with no submitted job
  is refused cleanly);
* an unavailable native core fails the task with the loader's actionable
  reason — never a silent fallback (there is no other engine any more);
* the startup ``.tmp``/``.corrupt`` cleanup sweep (Plan §4.4.4).

Cross-engine compatibility with the OFFICIAL zipnn lives in the L5 CI gate
(``scripts/l5/official_cross.py`` against pip zipnn 0.5.4) — the transition-
era legacy-path parity tests were retired together with the legacy path.
"""

from __future__ import annotations

import asyncio
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
    name — the reference serializer's order). The native round trip preserves
    ANY order byte-exactly; the canonical layout keeps the fixtures faithful
    to what torch itself writes."""
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
# golden ws contract — the native single path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_compress_decompress_native_golden(prompt_server, model_lib):
    if not _native_binary_present():
        pytest.skip("native binary not built (scripts/build-native.sh)")
    _reset_native_loader()
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
# cancel route + startup cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_route_native(prompt_server, model_lib):
    if not _native_binary_present():
        pytest.skip("native binary not built")
    _reset_native_loader()
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
async def test_cancel_route_rejects_a_task_without_a_job(prompt_server):
    """A task registered but whose native job was never submitted (the window
    between task creation and the worker's ``zipnn_compress`` call, or an
    already-finished task whose handle was popped) is refused cleanly — the
    Phase-8 replacement of the old legacy-path refusal."""
    compress = _compress_mod()
    compress.ZipNNRoutes().add_routes(prompt_server.routes)
    compress.ZIPNN_TASKS["no-job"] = {"mode": "compress", "status": "running", "src": "x", "dst": "y"}
    try:
        _c, cancel_payload = await _post_zipnn(prompt_server, CANCEL_ROUTE, {"taskId": "no-job"})
        assert cancel_payload["success"] is False
        assert "no cancellable native job" in cancel_payload["error"]
    finally:
        compress.ZIPNN_TASKS.pop("no-job", None)


@pytest.mark.asyncio
async def test_missing_core_fails_the_task_with_the_loader_reason(prompt_server, model_lib, tmp_path):
    """Phase 8: no binary -> the single-file task fails with the loader's
    actionable reason (never a silent fallback — there is no other engine),
    and the batch route refuses IMMEDIATELY (no task is created for a run
    that could only fail)."""
    compress = _compress_mod()
    config = import_ext("config")
    saved_uri = config.extension_uri
    native = import_ext("native")
    saved_state = (native._module, native._reason, native._attempted)
    try:
        config.extension_uri = str(tmp_path)  # no native-bin under here
        native._module, native._reason, native._attempted = None, None, False
        sys.modules.pop("mm_core", None)
        _make_model(model_lib, "req-missing")
        compress.ZipNNRoutes().add_routes(prompt_server.routes)

        # single-file route: the task starts, then fails with the reason
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
        assert "the native core is unavailable" in complete["error"]
        assert "native-bin directory missing" in complete["error"]
        # the source is untouched
        assert (model_lib / "checkpoints" / "req-missing.safetensors").exists()

        # batch route: an immediate request-level error, no task at all
        _b, batch_payload = await _post_zipnn(
            prompt_server,
            ("POST", "/model-manager/zipnn/batch-folder"),
            {"mode": "compress", "type": "checkpoints", "pathIndex": 0, "folder": "."},
        )
        assert batch_payload["success"] is False
        assert "the native core is unavailable" in batch_payload["error"]
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
