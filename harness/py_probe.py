#!/usr/bin/env python3
"""Python-only verification probe for ComfyUI-Model-Manager-Neo.

Runs the REAL extension backend (py/*.py routes) against stubbed ComfyUI
modules (harness/stubs) over real HTTP, and drives the full lifecycle:
model listing, hidden-file toggle, info read, edit/rename/preview/delete,
direct-link download (with sub-folder), pause/resume, task deletion, local
upload (incl. path-traversal rejection), preview serving, settings and the
Hugging Face guards.

Usage:  python3 harness/py_probe.py
Exit code 0 = every assertion passed.
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "harness" / "stubs"))

import folder_paths  # noqa: E402  (stub)
import server as server_stub  # noqa: E402  (stub)
from aiohttp import web  # noqa: E402

# Never let ambient credentials change the expected outcomes.
os.environ.pop("HF_TOKEN", None)
os.environ.pop("CIVITAI_API_KEY", None)

FAILURES: list[str] = []
PASSES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSES.append(name)
        print(f"  PASS  {name}")
    else:
        FAILURES.append(f"{name} {detail}")
        print(f"  FAIL  {name}  {detail}")


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------
TMP = Path(tempfile.mkdtemp(prefix="mmneo-probe-"))
CKPT = TMP / "models" / "checkpoints"
LORAS = TMP / "models" / "loras"
REMOTE = TMP / "remote"
for d in (CKPT, LORAS, REMOTE, CKPT / "sub", CKPT / "uploads"):
    d.mkdir(parents=True, exist_ok=True)

(CKPT / "sd_model.safetensors").write_bytes(b"SD" * 64)
(CKPT / "sub" / "nested_model.safetensors").write_bytes(b"NE" * 32)
(CKPT / ".hidden.safetensors").write_bytes(b"HI" * 16)
(LORAS / "some_lora.safetensors").write_bytes(b"LO" * 48)

# A real webp preview so the preview pipeline has something to serve.
from PIL import Image  # noqa: E402

_img = Image.new("RGB", (32, 32), (120, 80, 200))
_buf = io.BytesIO()
_img.save(_buf, "WEBP")
(CKPT / "sd_model.webp").write_bytes(_buf.getvalue())

(REMOTE / "remote_model.safetensors").write_bytes(b"RM" * 2048)  # ~4 KiB
SLOW_PAYLOAD = b"S" * (256 * 1024)

folder_paths.folder_names_and_paths = {
    "checkpoints": ([str(CKPT)], folder_paths.supported_pt_extensions),
    "loras": ([str(LORAS)], folder_paths.supported_pt_extensions),
}

# ---------------------------------------------------------------------------
# Import the extension (registers routes on the stub PromptServer)
# ---------------------------------------------------------------------------
spec = importlib.util.spec_from_file_location(
    "cmmn", REPO / "__init__.py", submodule_search_locations=[str(REPO)]
)
ext = importlib.util.module_from_spec(spec)
sys.modules["cmmn"] = ext
spec.loader.exec_module(ext)

serverInstance = server_stub.PromptServer.instance


# ---------------------------------------------------------------------------
# Local "remote" file server (fast + throttled + Range aware)
# ---------------------------------------------------------------------------
async def fast_file(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    return web.Response(body=(REMOTE / name).read_bytes())


async def slow_file(request: web.Request) -> web.StreamResponse:
    """Serves SLOW_PAYLOAD at ~64 KiB/s, honouring Range for resume."""
    start = 0
    rng = request.headers.get("Range")
    if rng and rng.startswith("bytes="):
        start = int(rng.split("=")[1].split("-")[0])
    resp = web.StreamResponse(status=206 if start else 200)
    if start:
        resp.headers["Content-Range"] = f"bytes {start}-{len(SLOW_PAYLOAD) - 1}/{len(SLOW_PAYLOAD)}"
    resp.headers["Content-Length"] = str(len(SLOW_PAYLOAD) - start)
    resp.content_type = "application/octet-stream"
    await resp.prepare(request)
    sent = start
    chunk = 8192
    while sent < len(SLOW_PAYLOAD):
        await resp.write(SLOW_PAYLOAD[sent : sent + chunk])
        sent += chunk
        await asyncio.sleep(0.12)
    await resp.write_eof()
    return resp


remote_app = web.Application()
remote_app.router.add_get("/files/{name}", fast_file)
remote_app.router.add_get("/slow/{name}", slow_file)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
BASE = "http://127.0.0.1:{port}"


async def main() -> None:
    app = web.Application()
    app.add_routes(serverInstance.routes)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[attr-defined]
    base = BASE.format(port=port)

    remote_runner = web.AppRunner(remote_app)
    await remote_runner.setup()
    remote_site = web.TCPSite(remote_runner, "127.0.0.1", 0)
    await remote_site.start()
    rport = remote_site._server.sockets[0].getsockname()[1]  # type: ignore[attr-defined]
    rbase = BASE.format(port=rport)

    import aiohttp

    session = aiohttp.ClientSession()

    async def get(path: str):
        async with session.get(f"{base}{path}") as r:
            return r.status, await r.json() if r.headers.get("Content-Type", "").startswith("application/json") else await r.read()

    async def post(path: str, **kw):
        async with session.post(f"{base}{path}", **kw) as r:
            return r.status, await r.json()

    async def put(path: str, **kw):
        async with session.put(f"{base}{path}", **kw) as r:
            return r.status, await r.json()

    async def delete(path: str):
        async with session.delete(f"{base}{path}") as r:
            return r.status, await r.json()

    def events(name: str):
        return [d for e, d in serverInstance.sent if e == name]

    try:
        # ---------------- model listing -----------------------------------
        _, folders = await get("/model-manager/models")
        check("P01 folders route", folders["success"] and set(folders["data"]) == {"checkpoints", "loras"})

        _, models = await get("/model-manager/models/checkpoints")
        names = {m["basename"] + m["extension"] for m in models["data"]}
        check("P02 hidden excluded by default", ".hidden.safetensors" not in names and "sd_model.safetensors" in names and "nested_model.safetensors" in names, str(names))
        preview_ok = any(
            m["basename"] == "sd_model" and m["preview"] == "/model-manager/preview/checkpoints/0/sd_model.webp"
            for m in models["data"]
        )
        check("P02b preview url resolved", preview_ok)

        serverInstance.user_manager.settings._data["ModelManager.Scan.IncludeHiddenFiles"] = True
        _, models2 = await get("/model-manager/models/checkpoints")
        names2 = {m["basename"] + m["extension"] for m in models2["data"]}
        check("P03 hidden included when enabled", ".hidden.safetensors" in names2, str(names2))
        serverInstance.user_manager.settings._data["ModelManager.Scan.IncludeHiddenFiles"] = False

        _, unknown = await get("/model-manager/models/nope")
        check("P22 unknown folder errors", unknown["success"] is False)

        # ---------------- model info / edit --------------------------------
        _, info = await get("/model-manager/model/checkpoints/0/sd_model.safetensors")
        check("P04 model info", info["success"] and info["data"]["metadata"] == {} and info["data"]["description"] is None)

        form = aiohttp.FormData()
        form.add_field("description", "# hello probe")
        _, upd = await put("/model-manager/model/checkpoints/0/sd_model.safetensors", data=form)
        check("P05 description saved", upd["success"] and (CKPT / "sd_model.md").read_text() == "# hello probe")

        form = aiohttp.FormData()
        form.add_field("type", "checkpoints")
        form.add_field("pathIndex", "0")
        form.add_field("fullname", "renamed_model.safetensors")
        _, upd = await put("/model-manager/model/checkpoints/0/sd_model.safetensors", data=form)
        check(
            "P06 rename moves file + description",
            upd["success"] and (CKPT / "renamed_model.safetensors").exists() and (CKPT / "renamed_model.md").exists(),
        )

        form = aiohttp.FormData()
        form.add_field("previewFile", "undefined")
        _, upd = await put("/model-manager/model/checkpoints/0/renamed_model.safetensors", data=form)
        check("P07 preview sentinel removes preview", upd["success"] and not (CKPT / "renamed_model.webp").exists() and not (CKPT / "sd_model.webp").exists())

        form = aiohttp.FormData()
        form.add_field("previewFile", io.BytesIO(_buf.getvalue()), filename="p.webp", content_type="image/webp")
        _, upd = await put("/model-manager/model/checkpoints/0/renamed_model.safetensors", data=form)
        check("P08 preview upload saved", upd["success"] and (CKPT / "renamed_model.webp").exists())

        # BUG FIX regression: a preview may also arrive as a plain URL string
        # (the client-side fetch fallback). The backend must download it
        # server-side, where CORS does not exist.
        (REMOTE / "preview.webp").write_bytes(_buf.getvalue())
        form = aiohttp.FormData()
        form.add_field("previewFile", f"{rbase}/files/preview.webp")
        _, upd = await put(
            "/model-manager/model/checkpoints/0/sub/nested_model.safetensors", data=form
        )
        check(
            "P08b preview fetched server-side from URL",
            upd["success"] and (CKPT / "sub" / "nested_model.webp").exists(),
        )

        # ---------------- preview serving ----------------------------------
        status, body = await get("/model-manager/preview/checkpoints/0/renamed_model.safetensors")
        check("P16 preview served as webp", status == 200 and body[:4] == b"RIFF")
        status, body = await get("/model-manager/preview/checkpoints/0/does_not_exist.safetensors")
        check(
            "P16b missing preview falls back to the glass NO-PREVIEW.svg",
            status == 200 and b"<svg" in body[:400],
        )
        status, body = await get("/model-manager/preview/download/no-preview.png")
        check(
            "P16c download preview fallback is the svg artwork",
            status == 200 and b"<svg" in body[:400],
        )

        # ---------------- traversal guards ----------------------------------
        _, trav = await get("/model-manager/model/checkpoints/0/..%2F..%2F..%2Fetc%2Fpasswd")
        check("P23 traversal blocked on model route", trav["success"] is False)

        # ---------------- direct-link download with subfolder ---------------
        form = aiohttp.FormData()
        form.add_field("type", "checkpoints")
        form.add_field("pathIndex", "0")
        form.add_field("fullname", "remote_model.safetensors")
        form.add_field("subFolder", "downloaded")
        form.add_field("sizeBytes", str((REMOTE / "remote_model.safetensors").stat().st_size))
        form.add_field("description", "# from probe")
        form.add_field("downloadPlatform", "Direct Link")
        form.add_field("downloadUrl", f"{rbase}/files/remote_model.safetensors")
        form.add_field("previewFile", "")
        _, created = await post("/model-manager/model", data=form)
        check("P10 direct download task created", created["success"], str(created))
        task_id = created["data"]["taskId"]
        target = CKPT / "downloaded" / "remote_model.safetensors"
        deadline = time.time() + 20
        while time.time() < deadline and not target.exists():
            await asyncio.sleep(0.2)
        check("P10b download landed in subfolder", target.exists())
        # The completion path waits 1s between the move and the bookkeeping.
        await asyncio.sleep(1.6)
        check("P10c complete event pushed", any(t == task_id for t in events("complete_download_task")))
        check("P10d description moved next to model", (CKPT / "downloaded" / "remote_model.md").exists())
        check("P10e task file cleaned up", not (REPO / "downloads" / f"{task_id}.task").exists())

        # ---------------- pause / resume on a slow download ------------------
        form = aiohttp.FormData()
        form.add_field("type", "loras")
        form.add_field("pathIndex", "0")
        form.add_field("fullname", "slow_model.safetensors")
        form.add_field("sizeBytes", str(len(SLOW_PAYLOAD)))
        form.add_field("description", "slow")
        form.add_field("downloadPlatform", "Direct Link")
        form.add_field("downloadUrl", f"{rbase}/slow/slow_model.safetensors")
        form.add_field("previewFile", "")
        _, created = await post("/model-manager/model", data=form)
        slow_id = created["data"]["taskId"]
        await asyncio.sleep(1.2)
        _, tasks = await get("/model-manager/download/task")
        slow = next(t for t in tasks["data"] if t["taskId"] == slow_id)
        check("P11 slow task is doing", slow["status"] == "doing", str(slow["status"]))
        first = slow["downloadedSize"]
        check("P11b progress reported", first > 0, str(first))

        _, paused = await put(f"/model-manager/download/{slow_id}", json={"status": "pause"})
        await asyncio.sleep(0.8)
        _, tasks = await get("/model-manager/download/task")
        slow = next(t for t in tasks["data"] if t["taskId"] == slow_id)
        stopped_at = slow["downloadedSize"]
        check("P11c pause reports pause", paused["success"] and slow["status"] == "pause", str(slow["status"]))
        await asyncio.sleep(0.8)
        _, tasks = await get("/model-manager/download/task")
        slow = next(t for t in tasks["data"] if t["taskId"] == slow_id)
        check("P11d paused task makes no progress", slow["downloadedSize"] == stopped_at, f"{stopped_at} -> {slow['downloadedSize']}")

        _, resumed = await put(f"/model-manager/download/{slow_id}", json={"status": "resume"})
        check("P11e resume accepted", resumed["success"])
        deadline = time.time() + 30
        done = False
        while time.time() < deadline:
            _, tasks = await get("/model-manager/download/task")
            if not any(t["taskId"] == slow_id for t in tasks["data"]):
                done = True
                break
            await asyncio.sleep(0.3)
        check("P11f resumed task completes", done and (LORAS / "slow_model.safetensors").exists())
        check("P11g resumed file size correct", (LORAS / "slow_model.safetensors").stat().st_size == len(SLOW_PAYLOAD))

        # ---------------- delete a running task ------------------------------
        form = aiohttp.FormData()
        form.add_field("type", "loras")
        form.add_field("pathIndex", "0")
        form.add_field("fullname", "cancelled_model.safetensors")
        form.add_field("sizeBytes", str(len(SLOW_PAYLOAD)))
        form.add_field("description", "cancel me")
        form.add_field("downloadPlatform", "Direct Link")
        form.add_field("downloadUrl", f"{rbase}/slow/cancelled_model.safetensors")
        form.add_field("previewFile", "")
        _, created = await post("/model-manager/model", data=form)
        cancel_id = created["data"]["taskId"]
        await asyncio.sleep(1.0)
        _, deleted = await delete(f"/model-manager/download/{cancel_id}")
        await asyncio.sleep(1.2)
        _, tasks = await get("/model-manager/download/task")
        check("P12 task deleted", deleted["success"] and not any(t["taskId"] == cancel_id for t in tasks["data"]))
        check("P12b delete event pushed", cancel_id in events("delete_download_task"))

        # ---------------- local upload ----------------------------------------
        body = aiohttp.FormData()
        body.add_field("folder", str(CKPT / "uploads"))
        body.add_field("size", "6")
        body.add_field("file", io.BytesIO(b"UPLOAD"), filename="uploaded.safetensors", content_type="application/octet-stream")
        _, up = await post("/model-manager/upload", data=body)
        check("P13 local upload succeeds", up["success"] and (CKPT / "uploads" / "uploaded.safetensors").read_bytes() == b"UPLOAD")

        body = aiohttp.FormData()
        body.add_field("folder", str(TMP / "outside"))
        body.add_field("size", "6")
        body.add_field("file", io.BytesIO(b"EVIL!!"), filename="evil.safetensors", content_type="application/octet-stream")
        _, up = await post("/model-manager/upload", data=body)
        check("P14 upload outside model folders rejected", up["success"] is False and not (TMP / "outside" / "evil.safetensors").exists())

        boundary = "----mmneoprobeboundary"
        raw = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="folder"\r\n\r\n{CKPT}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="size"\r\n\r\n6\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="../../evil2.safetensors"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\nEVIL!!\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        async with session.post(
            f"{base}/model-manager/upload",
            data=raw,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        ) as r:
            up = await r.json()
        evil = list(TMP.rglob("evil2.safetensors"))
        check("P15 upload filename traversal rejected", up["success"] is False and not evil, str(up))

        # ---------------- misc routes ------------------------------------------
        _, exts = await get("/model-manager/supported-extensions")
        check("P17 supported extensions", exts["success"] and ".safetensors" in exts["data"])

        _, setres = await post("/model-manager/download/setting", json={"key": "civitai", "value": "a2V5LXZhbC1mb3ItcHJvYmU="})
        _, init = await post("/model-manager/download/init", json={})
        check("P18 api key stored + masked", setres["success"] and init["data"].get("civitai", "").startswith("key-"), str(init.get("data")))

        _, who = await get("/model-manager/hf/whoami")
        check("P19 hf whoami without token", who["success"] is False)
        _, hfu = await post("/model-manager/hf/upload", json={"type": "checkpoints", "pathIndex": 0, "fullname": "renamed_model.safetensors", "repoId": "x/y", "pathInRepo": "m.safetensors"})
        check("P20 hf upload without token", hfu["success"] is False and "token" in hfu["error"].lower())

        _, info_bad = await get("/model-manager/model-info?model-page=https://example.com/models/1")
        check("P21 unknown website rejected", info_bad["success"] is False)

        # ---------------- model delete ------------------------------------------
        _, dele = await delete("/model-manager/model/checkpoints/0/renamed_model.safetensors")
        check(
            "P09 delete removes model + preview + description",
            dele["success"]
            and not (CKPT / "renamed_model.safetensors").exists()
            and not (CKPT / "renamed_model.webp").exists()
            and not (CKPT / "renamed_model.md").exists(),
        )
    finally:
        await session.close()
        await runner.cleanup()
        await remote_runner.cleanup()
        shutil.rmtree(TMP, ignore_errors=True)
        # The backend keeps task files inside <extension>/downloads; never
        # leave probe artifacts in the working tree.
        shutil.rmtree(REPO / "downloads", ignore_errors=True)
        (REPO / "private.key").unlink(missing_ok=True)

    print(f"\n{len(PASSES)} passed, {len(FAILURES)} failed")
    if FAILURES:
        for f in FAILURES:
            print("  FAILED:", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
