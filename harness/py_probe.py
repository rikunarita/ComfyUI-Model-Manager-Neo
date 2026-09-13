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
        no_prev = next(
            (m for m in models["data"] if m["basename"] == "nested_model"), None
        )
        check(
            "P02c models without preview point at the default svg",
            no_prev is not None and no_prev["preview"] == "/model-manager/no-preview.svg",
            str(no_prev and no_prev["preview"]),
        )

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
        check("P16b missing preview is a plain 404 (no fallback)", status == 404)
        status, body = await get("/model-manager/no-preview.svg")
        check(
            "P16c default no-preview artwork served verbatim",
            status == 200 and b"<svg" in body[:400],
        )
        status, body = await get("/model-manager/preview/download/no-preview.png")
        check("P16d download preview without file is 404", status == 404)

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

        # ---------------- folder prefixes in `fullname` -------------------------
        # The model editor accepts "sub/name.ext" as a file name now, so the
        # backend has to file the model into that sub-folder (creating it) while
        # still refusing to escape the model directory.
        form = aiohttp.FormData()
        form.add_field("type", "loras")
        form.add_field("pathIndex", "0")
        form.add_field("fullname", "deep/deeper/moved_lora.safetensors")
        _, moved = await put("/model-manager/model/loras/0/some_lora.safetensors", data=form)
        check(
            "P24 folder prefix in fullname files the model into a new sub-folder",
            moved["success"]
            and (LORAS / "deep" / "deeper" / "moved_lora.safetensors").exists()
            and not (LORAS / "some_lora.safetensors").exists(),
            str(moved),
        )

        form = aiohttp.FormData()
        form.add_field("type", "loras")
        form.add_field("pathIndex", "0")
        form.add_field("fullname", "../../escape.safetensors")
        _, esc = await put(
            "/model-manager/model/loras/0/deep/deeper/moved_lora.safetensors", data=form
        )
        check(
            "P25 folder prefix cannot escape the model directory",
            esc["success"] is False
            and not list(TMP.rglob("escape.safetensors"))
            and (LORAS / "deep" / "deeper" / "moved_lora.safetensors").exists(),
            str(esc),
        )

        # ---------------- defensive input handling ------------------------------
        # `int(None)` used to raise TypeError instead of a validation error.
        form = aiohttp.FormData()
        form.add_field("type", "checkpoints")
        form.add_field("fullname", "whatever.safetensors")
        form.add_field("sizeBytes", "1")
        form.add_field("downloadPlatform", "Direct Link")
        form.add_field("downloadUrl", f"{rbase}/files/remote_model.safetensors")
        _, noindex = await post("/model-manager/model", data=form)
        check(
            "P26 missing pathIndex is a validation error, not a crash",
            noindex["success"] is False and isinstance(noindex.get("error"), str),
            str(noindex),
        )

        # A task without a description used to die in `_download_complete` with
        # `TypeError: write() argument must be str, not None` - AFTER the file
        # had been downloaded, so it was stuck in downloads/ forever.
        form = aiohttp.FormData()
        form.add_field("type", "checkpoints")
        form.add_field("pathIndex", "0")
        form.add_field("fullname", "nodesc.safetensors")
        form.add_field("sizeBytes", str((REMOTE / "remote_model.safetensors").stat().st_size))
        form.add_field("downloadPlatform", "Direct Link")
        form.add_field("downloadUrl", f"{rbase}/files/remote_model.safetensors")
        form.add_field("previewFile", "")
        _, nodesc = await post("/model-manager/model", data=form)
        check("P27 task without description accepted", nodesc["success"], str(nodesc))
        nodesc_target = CKPT / "nodesc.safetensors"
        deadline = time.time() + 20
        while time.time() < deadline and not nodesc_target.exists():
            await asyncio.sleep(0.2)
        await asyncio.sleep(1.6)
        check(
            "P27b task without description still completes",
            nodesc_target.exists()
            and any(t == nodesc["data"]["taskId"] for t in events("complete_download_task")),
        )
        check(
            "P27c an empty notes file is written instead of crashing",
            (CKPT / "nodesc.md").exists(),
        )

        # ---------------- environment auto-fill (feature) --------------------
        # An empty private.key + a token in the environment must be adopted
        # (and persisted) exactly once; keys absent from the environment stay
        # untouched.
        import os as _os

        from cmmn.py import auth as _auth

        _os.environ["HF_TOKEN"] = "hf_env_token_1234567890"
        _auth.get_api_key()._store = {"civitai": None, "huggingface": None}
        _auth.get_api_key()._update()
        _, seeded = await post("/model-manager/download/init", json={})
        check(
            "P28 env-only token is adopted into private.key",
            seeded["success"]
            and seeded["data"].get("huggingface", "").startswith("hf_e")
            and seeded["data"].get("civitai") is None,
            str(seeded.get("data")),
        )
        _raw = (REPO / "private.key").read_text(encoding="utf-8")
        check(
            "P28b private.key is JSON (not pickle) and holds the seeded token",
            _raw.lstrip().startswith("{") and "hf_env_token_1234567890" in _raw,
        )
        _os.environ.pop("HF_TOKEN", None)
        _auth.get_api_key()._store = {"civitai": None, "huggingface": None}
        _auth.get_api_key()._update()

        # ---------------- cache headers (optimizations A-1 / B-2) ------------
        _st, _svg = await get("/model-manager/assets/folder-closed.svg")
        check("P29 svg artwork served", _st == 200 and _svg[:4] == b"<svg")
        import aiohttp as _aiohttp

        async with _aiohttp.ClientSession() as _sess:
            async with _sess.get(f"{base}/model-manager/assets/folder-closed.svg") as _r:
                _etag = _r.headers.get("ETag")
                _cc = _r.headers.get("Cache-Control")
                await _r.read()
            async with _sess.get(
                f"{base}/model-manager/assets/folder-closed.svg",
                headers={"If-None-Match": _etag or ""},
            ) as _r2:
                _st2 = _r2.status
        check(
            "P29b svg carries ETag + max-age and revalidates with 304",
            bool(_etag) and "max-age=" in (_cc or "") and _st2 == 304,
            f"{_etag} {_cc} {_st2}",
        )
        async with _aiohttp.ClientSession() as _sess:
            _purl = f"{base}/model-manager/preview/checkpoints/0/renamed_model.webp"
            async with _sess.get(_purl) as _r:
                _petag = _r.headers.get("ETag")
                _pcc = _r.headers.get("Cache-Control")
                await _r.read()
            async with _sess.get(_purl, headers={"If-None-Match": _petag or ""}) as _r2:
                _pst2 = _r2.status
        check(
            "P29c previews carry ETag + cache-control and revalidate with 304",
            bool(_petag) and "max-age=" in (_pcc or "") and _pst2 == 304,
            f"{_petag} {_pcc} {_pst2}",
        )

        # ---------------- multi-preview save (feature) -----------------------
        form = aiohttp.FormData()
        form.add_field("previewFile", io.BytesIO(_buf.getvalue()), filename="p.webp", content_type="image/webp")
        form.add_field("previewFile2", io.BytesIO(_buf.getvalue()), filename="p2.webp", content_type="image/webp")
        _, upd2 = await put("/model-manager/model/checkpoints/0/sub/nested_model.safetensors", data=form)
        check(
            "P30 both previews are stored under the naming scheme",
            upd2["success"]
            and (CKPT / "sub" / "nested_model.webp").exists()
            and (CKPT / "sub" / "nested_model.preview.webp").exists(),
            str(upd2),
        )
        _, models3 = await get("/model-manager/models/checkpoints")
        _nested = next(m for m in models3["data"] if m["basename"] == "nested_model")
        check(
            "P30b the model list exposes the gallery as two distinct urls",
            isinstance(_nested["preview"], list)
            and len(_nested["preview"]) == 2
            and _nested["preview"][0] != _nested["preview"][1],
            str(_nested["preview"]),
        )

        # ------------- ZipNN installer hardening (P34 series) ----------------
        # The reported production failure was `pip install zipnn` dying with a
        # bare "non-zero exit status 1" (no compiler / no Python.h / a 550 MB
        # torch re-download). These assertions pin the new behaviour.
        _compress = sys.modules["cmmn.py.compress"]
        _saved = {
            k: getattr(_compress, k)
            for k in (
                "_run_pip",
                "_zipnn_install_failed",
                "zipnn_available",
                "zipnn_installed",
                "ensure_zipnn",
            )
        }
        _saved_path = list(sys.path)
        _saved_modules = {k: sys.modules.get(k) for k in ("zipnn", "zipnn_core")}
        _cfg = sys.modules["cmmn.py.config"]
        _saved_uri = _cfg.extension_uri
        try:
            # P34: a failing pip run reports pip's own output, not just an exit
            # code. A dead index makes it fail fast and offline.
            try:
                _compress._run_pip(
                    [
                        "install",
                        "--index-url",
                        "http://127.0.0.1:9/simple",
                        "--retries",
                        "0",
                        "--timeout",
                        "2",
                        "zipnn",
                    ]
                )
                _p34 = ""
            except Exception as e:
                _p34 = str(e)
            check(
                "P34 a failed pip run surfaces pip's own output",
                "failed (exit" in _p34 and "pip install" in _p34 and len(_p34) > 60,
                _p34[:160],
            )

            # P34b/P34e: `--no-deps` first (never re-downloads torch) and the
            # gcc>=14 CFLAGS relaxation is passed to every attempt.
            _calls: list[tuple[list[str], dict | None]] = []
            _tmp_pkg = Path(tempfile.mkdtemp(prefix="mmneo-znn-"))
            (_tmp_pkg / "zipnn").mkdir()
            (_tmp_pkg / "zipnn" / "__init__.py").write_text(
                "raise ImportError(\"No module named 'torch'\")\n"
            )
            (_tmp_pkg / "zipnn_core.py").write_text("")
            sys.path.insert(0, str(_tmp_pkg))
            for _m in ("zipnn", "zipnn_core"):
                sys.modules.pop(_m, None)

            def _fake_pip(args, extra_env=None):
                _calls.append((list(args), dict(extra_env or {})))
                return "fake ok"

            _compress._run_pip = _fake_pip
            _compress._zipnn_install_failed = None
            try:
                _compress.ensure_zipnn()
                _p34b = "no error"
            except Exception as e:
                _p34b = str(e)
            _first = _calls[0][0] if _calls else []
            check(
                "P34b the first attempt is --no-deps (no torch re-download)",
                "--no-deps" in _first and "zipnn" in _first,
                str(_calls),
            )
            check(
                "P34b2 an installed-but-unimportable ZipNN stops the retries",
                len(_calls) == 1 and "cannot be imported" in _p34b and "torch" in _p34b,
                f"{_p34b[:200]} calls={_calls}",
            )
            check(
                "P34c the failure is cached (no second doomed build)",
                _compress._zipnn_install_failed is not None,
            )
            _n = len(_calls)
            try:
                _compress.ensure_zipnn()
            except Exception:
                pass
            check(
                "P34c2 a cached failure does not re-run pip",
                len(_calls) == _n,
                str(_calls),
            )
            check(
                "P34e every attempt relaxes the gcc>=14 default -Werror flags",
                all(
                    "-Wno-error=implicit-function-declaration" in env.get("CFLAGS", "")
                    for _, env in _calls
                )
                and len(_calls) > 0,
                str(_calls),
            )

            # The harness ships an importable zipnn *stub*, so from here on the
            # availability probes are forced off to exercise the install paths.
            _compress.zipnn_available = lambda: False
            _compress.zipnn_installed = lambda: False

            # P34f: a wheel dropped into assets/zipnn-wheels/ wins over PyPI.
            _ext_root = Path(tempfile.mkdtemp(prefix="mmneo-wheels-"))
            (_ext_root / "assets" / "zipnn-wheels").mkdir(parents=True)
            (_ext_root / "assets" / "zipnn-wheels" / "zipnn-9.9-py3-none-any.whl").write_bytes(
                b"PK\x03\x04fake"
            )
            _cfg.extension_uri = str(_ext_root)
            _calls.clear()
            _compress._zipnn_install_failed = None
            for _m in ("zipnn", "zipnn_core"):
                sys.modules.pop(_m, None)
            sys.path.remove(str(_tmp_pkg))
            try:
                _compress.ensure_zipnn()
            except Exception:
                pass
            check(
                "P34f a local wheel in assets/zipnn-wheels/ is tried first",
                bool(_calls)
                and str(_ext_root / "assets" / "zipnn-wheels") in " ".join(_calls[0][0]),
                str(_calls[:1]),
            )

            # P34g: when every strategy fails the message names the real cause
            # (here: missing Python headers) and the offline escape hatch.
            def _boom(args, extra_env=None):
                _calls.append((list(args), dict(extra_env or {})))
                raise RuntimeError(
                    "`pip install --no-deps zipnn` failed (exit 1):\n"
                    "csrc/data_manipulation_dtype16.c:1:10: fatal error: "
                    "Python.h: No such file or directory"
                )

            _compress._run_pip = _boom
            _calls.clear()
            _compress._zipnn_install_failed = None
            try:
                _compress.ensure_zipnn()
                _p34g = ""
                _p34g_exc: Exception | None = None
            except Exception as e:
                _p34g = str(e)
                _p34g_exc = e
            check(
                "P34g the failure message names the cause + the fix",
                "Python.h" in _p34g
                and "zipnn-wheels" in _p34g
                and "C compiler" in _p34g,
                _p34g[:200],
            )
            check(
                "P34h the failure is reported as an install failure (UI retry)",
                isinstance(_p34g_exc, _compress.ZipNNInstallError),
                type(_p34g_exc).__name__,
            )
            # P34i: the cache short-circuits, but an explicit retry (force)
            # runs the strategies again - otherwise fixing the toolchain would
            # need a ComfyUI restart.
            _calls.clear()
            _compress._zipnn_install_failed = ("cached failure", time.time())
            try:
                _compress.ensure_zipnn()
            except Exception:
                pass
            check("P34i a cached failure short-circuits pip", not _calls, str(_calls))
            try:
                _compress.ensure_zipnn(force=True)
            except Exception:
                pass
            check(
                "P34i2 force=True bypasses the cached failure",
                bool(_calls),
                str(_calls[:1]),
            )

            # P34k-P34o: the failure reported from the field - distutils execs
            # the compiler this Python was *built* with (Gentoo and friends
            # record a triplet name like `x86_64-pc-linux-gnu-gcc`), which can
            # be missing even when a usable `cc`/`gcc` exists. The installer
            # must substitute it via $CC, fold identical attempt failures into
            # one block, and name the compiler the build could not exec.
            _cc_bin = Path(tempfile.mkdtemp(prefix="mmneo-cc-"))
            (_cc_bin / "gcc").write_text("#!/bin/sh\nexit 0\n")
            (_cc_bin / "gcc").chmod(0o755)
            _saved_recorded = _compress._recorded_cc
            _saved_cc_patch = _compress._cc_env_patch
            _saved_env_path = os.environ.get("PATH")
            _saved_env_cc = os.environ.get("CC")
            _saved_env_cflags = os.environ.get("CFLAGS")
            try:
                os.environ["PATH"] = str(_cc_bin)
                os.environ.pop("CC", None)
                _compress._recorded_cc = lambda: "x86_64-pc-linux-gnu-gcc"
                _env, _note = _compress._cc_env_patch()
                check(
                    "P34k a missing recorded compiler is substituted via $CC",
                    _env.get("CC") == str(_cc_bin / "gcc")
                    and "x86_64-pc-linux-gnu-gcc" in (_note or ""),
                    f"{_env} {_note}",
                )
                _hint2 = _compress._build_prereq_hint() or ""
                check(
                    "P34l with a substitute found the warning stops claiming 'no C compiler'",
                    "no C compiler" not in _hint2,
                    _hint2[:200],
                )

                def _boom_cc(args, extra_env=None):
                    _calls.append((list(args), dict(extra_env or {})))
                    raise RuntimeError(
                        "`pip install --no-deps zipnn` failed (exit 1):\n"
                        "error: [Errno 2] No such file or directory: "
                        "'x86_64-pc-linux-gnu-gcc'"
                    )

                _compress._run_pip = _boom_cc
                _compress._cc_env_patch = lambda: ({}, None)  # nothing found
                _compress._zipnn_install_failed = None
                _calls.clear()
                try:
                    _compress.ensure_zipnn()
                    _p34m = ""
                except Exception as e:
                    _p34m = str(e)
                check(
                    "P34m identical attempt failures are folded into one block",
                    _p34m.count("failed (exit 1)") == 1
                    and "identical failure repeated for" in _p34m,
                    _p34m[:300],
                )
                check(
                    "P34n the message names the compiler distutils could not exec",
                    "The build tried to run `x86_64-pc-linux-gnu-gcc`" in _p34m,
                    _p34m[:300],
                )

                # P34o: _run_pip replaces $CC (a broken inherited value must
                # not be kept) while flag lists like CFLAGS are appended.
                import subprocess as _sp

                _real_run = _sp.run
                _spy_env: dict = {}

                def _spy_run(cmd, **kw):
                    _spy_env.update(kw.get("env") or {})
                    return _real_run(
                        [sys.executable, "-c", "pass"],
                        capture_output=True,
                        text=True,
                        env=kw.get("env"),
                    )

                _sp.run = _spy_run
                try:
                    os.environ["CC"] = "/broken/x86_64-pc-linux-gnu-gcc"
                    os.environ["CFLAGS"] = "-O0"
                    _saved["_run_pip"](
                        ["--version"], {"CC": "/usr/bin/cc", "CFLAGS": "-Wno-x"}
                    )
                finally:
                    _sp.run = _real_run
                check(
                    "P34o $CC is replaced (not appended) while CFLAGS is appended",
                    _spy_env.get("CC") == "/usr/bin/cc"
                    and _spy_env.get("CFLAGS", "").startswith("-O0")
                    and "-Wno-x" in _spy_env.get("CFLAGS", ""),
                    f"CC={_spy_env.get('CC')} CFLAGS={_spy_env.get('CFLAGS')}",
                )
            finally:
                _compress._recorded_cc = _saved_recorded
                _compress._cc_env_patch = _saved_cc_patch
                _compress._run_pip = _saved["_run_pip"]
                if _saved_env_path is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = _saved_env_path
                for _k, _v in (("CC", _saved_env_cc), ("CFLAGS", _saved_env_cflags)):
                    if _v is None:
                        os.environ.pop(_k, None)
                    else:
                        os.environ[_k] = _v
                shutil.rmtree(_cc_bin, ignore_errors=True)

            # P34j: an install failure is flagged so the UI can offer a retry.
            _compress._zipnn_install_failed = None

            def _no_install(force=False):
                raise _compress.ZipNNInstallError(
                    "ZipNN could not be installed on this machine"
                )

            _compress.ensure_zipnn = _no_install
            (CKPT / "znn_install_probe.safetensors").write_bytes(b"x")
            await post(
                "/model-manager/zipnn/compress",
                json={
                    "type": "checkpoints",
                    "pathIndex": 0,
                    "fullname": "znn_install_probe.safetensors",
                },
            )
            _deadline = time.time() + 10
            while time.time() < _deadline and not any(
                e == "zipnn_complete" and d.get("installFailed")
                for e, d in serverInstance.sent
            ):
                await asyncio.sleep(0.05)
            _payloads = [d for e, d in serverInstance.sent if e == "zipnn_complete"]
            check(
                "P34j an install failure is flagged for the UI retry",
                bool(_payloads) and _payloads[-1].get("installFailed") is True,
                str(_payloads[-1])[:160],
            )
            _compress.ensure_zipnn = _saved["ensure_zipnn"]
            (CKPT / "znn_install_probe.safetensors").unlink(missing_ok=True)
            # Drop the events this probe generated: the P32/P33 waits look for
            # "a zipnn_complete event", and a leftover install-failure event
            # would satisfy them before the real task finishes.
            serverInstance.sent[:] = [
                ev for ev in serverInstance.sent if "zipnn" not in ev[0]
            ]

            shutil.rmtree(_ext_root, ignore_errors=True)
            shutil.rmtree(_tmp_pkg, ignore_errors=True)
        finally:
            for k, v in _saved.items():
                setattr(_compress, k, v)
            sys.path[:] = _saved_path
            for k, v in _saved_modules.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
            _cfg.extension_uri = _saved_uri

        # ---------------- ZipNN compress / decompress -------------------------
        import safetensors.torch as stub_st
        from safetensors import StubTensor

        znn_model = CKPT / "znn_target.safetensors"
        stub_st.save_file(
            {"w": StubTensor("float32", [4096], b"\x00" * 4096 * 4)},
            str(znn_model),
            {"note": "zipnn probe"},
        )
        (CKPT / "znn_target.webp").write_bytes(_buf.getvalue())

        _, zbad = await post(
            "/model-manager/zipnn/compress",
            json={"type": "checkpoints", "pathIndex": 0, "fullname": "renamed_model.md"},
        )
        check("P31 non-safetensors rejected", zbad["success"] is False, str(zbad))

        _, zc = await post(
            "/model-manager/zipnn/compress",
            json={"type": "checkpoints", "pathIndex": 0, "fullname": "znn_target.safetensors"},
        )
        check("P31b compress accepted", zc["success"], str(zc))
        deadline = time.time() + 20
        while time.time() < deadline and not any(
            e == "zipnn_complete" for e, _ in serverInstance.sent
        ):
            await asyncio.sleep(0.1)
        check(
            "P32 compressed file replaced the original",
            (CKPT / "znn_target.znn.safetensors").exists() and not znn_model.exists(),
        )
        check(
            "P32b preview sidecar followed the rename",
            (CKPT / "znn_target.znn.webp").exists() and not (CKPT / "znn_target.webp").exists(),
        )
        check(
            "P32c completion event pushed",
            any(e == "zipnn_complete" for e, _ in serverInstance.sent),
        )
        _, models4 = await get("/model-manager/models/checkpoints")
        _z = next((m for m in models4["data"] if m["basename"] == "znn_target.znn"), None)
        check("P32d the compressed model shows up in the list", _z is not None)

        _, zd = await post(
            "/model-manager/zipnn/decompress",
            json={
                "type": "checkpoints",
                "pathIndex": 0,
                "fullname": "znn_target.znn.safetensors",
            },
        )
        check("P33 decompress accepted", zd["success"], str(zd))
        deadline = time.time() + 20
        seen = sum(1 for e, _ in serverInstance.sent if e == "zipnn_complete")
        while time.time() < deadline and sum(
            1 for e, _ in serverInstance.sent if e == "zipnn_complete"
        ) < seen + 1:
            await asyncio.sleep(0.1)
        check(
            "P33b decompressed file replaced the compressed one",
            znn_model.exists() and not (CKPT / "znn_target.znn.safetensors").exists(),
        )
        check(
            "P33c preview sidecar moved back",
            (CKPT / "znn_target.webp").exists()
            and not (CKPT / "znn_target.znn.webp").exists(),
        )

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
