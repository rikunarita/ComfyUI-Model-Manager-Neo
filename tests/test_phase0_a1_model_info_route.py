"""Plan §4.8-A1 / §1.2.2 issue 6: the model-detail route must not block the loop.

Regression test for the Quick Win A1 fix: ``GET /model-manager/model/...``
used to call ``ModelManager.get_model_info`` inline on the event loop, so a
multi-megabyte MoE header parse froze the whole server (websockets
included). The fix hands the call to the IO executor - this test asserts
(a) the work runs on an ``mm-io`` pool thread and (b) the event loop keeps
servicing other coroutines while it runs.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from harness import FakeRequest, import_ext, json_body

ROUTE = ("GET", "/model-manager/model/{type}/{index}/{filename:.*}")


def _make_model(model_lib):
    from harness import synth_f32, write_safetensors

    path = model_lib / "checkpoints" / "detail.safetensors"
    write_safetensors(
        path,
        {"weight": ("F32", [4, 4], synth_f32(16))},
        metadata={"format": "pt"},
    )
    return path


@pytest.mark.asyncio
async def test_model_info_runs_off_loop(prompt_server, model_lib):
    manager = import_ext("manager")
    _make_model(model_lib)

    manager.ModelManager().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[ROUTE]

    observed: dict[str, str] = {}

    def slow_info(self, model_path: str):
        observed["thread"] = threading.current_thread().name
        time.sleep(0.4)
        return {"metadata": {}, "description": None, "tensors": []}

    original = manager.ModelManager.get_model_info
    manager.ModelManager.get_model_info = slow_info  # type: ignore[method-assign]

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.02)

    tick_task = asyncio.create_task(ticker())
    try:
        request = FakeRequest(match_info={"type": "checkpoints", "index": "0", "filename": "detail.safetensors"})
        response = await handler(request)
    finally:
        tick_task.cancel()
        manager.ModelManager.get_model_info = original  # type: ignore[method-assign]

    body = json_body(response)
    assert body["success"] is True
    # (a) executed on the dedicated IO pool, not the loop thread
    assert observed["thread"].startswith("mm-io"), observed
    # (b) the loop kept ticking during the 0.4 s sleep (>=5 ticks of 20 ms)
    assert ticks >= 5, ticks


@pytest.mark.asyncio
async def test_model_info_real_payload(prompt_server, model_lib):
    """Unpatched: the route returns metadata/description/tensors."""
    manager = import_ext("manager")
    _make_model(model_lib)
    manager.ModelManager().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[ROUTE]

    request = FakeRequest(match_info={"type": "checkpoints", "index": "0", "filename": "detail.safetensors"})
    body = json_body(await handler(request))
    assert body["success"] is True
    data = body["data"]
    assert data["metadata"] == {"format": "pt"}
    assert data["description"] is None
    assert data["tensors"] == [{"name": "weight", "dtype": "F32", "shape": [4, 4]}]


@pytest.mark.asyncio
async def test_model_info_missing_file_is_error_not_crash(prompt_server, model_lib):
    manager = import_ext("manager")
    manager.ModelManager().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[ROUTE]

    request = FakeRequest(match_info={"type": "checkpoints", "index": "0", "filename": "ghost.safetensors"})
    body = json_body(await handler(request))
    assert body["success"] is False
    assert "not found" in body["error"]
