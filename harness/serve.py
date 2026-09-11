#!/usr/bin/env python3
"""Serves the real extension backend + the built web bundle for the E2E run.

ComfyUI itself is stubbed (harness/stubs); the browser receives a page that
mocks `window.comfyAPI` and then loads the REAL production bundle from
`web/manager.js` + `web/style-*.css`, exactly like ComfyUI would.

Usage:  python3 harness/serve.py [--port PORT]
"""

from __future__ import annotations

import argparse
import os
import importlib.util
import io
import asyncio
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "harness" / "stubs"))

import folder_paths  # noqa: E402  (stub)
import server as server_stub  # noqa: E402  (stub)
from aiohttp import web  # noqa: E402
from PIL import Image  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="mmneo-e2e-"))
CKPT = TMP / "models" / "checkpoints"
LORAS = TMP / "models" / "loras"
VAE = TMP / "models" / "vae"
for d in (CKPT, LORAS, VAE):
    d.mkdir(parents=True, exist_ok=True)

_img = Image.new("RGB", (140, 180), (90, 140, 220))
_buf = io.BytesIO()
_img.save(_buf, "WEBP")
_preview = _buf.getvalue()

for name, directory in (("anima-aesthetic-v1", CKPT), ("novaAnimeAM_v40", LORAS), ("qwen_vae", VAE)):
    (directory / f"{name}.safetensors").write_bytes(b"MM" * 512)
    (directory / f"{name}.webp").write_bytes(_preview)
(CKPT / "sub").mkdir(exist_ok=True)
(CKPT / "sub" / "nested.safetensors").write_bytes(b"NN" * 128)

folder_paths.folder_names_and_paths = {
    "diffusion_models": ([str(CKPT)], folder_paths.supported_pt_extensions),
    "unet_gguf": ([str(LORAS)], folder_paths.supported_pt_extensions),
    "vae": ([str(VAE)], folder_paths.supported_pt_extensions),
}

REMOTE = TMP / "remote"
REMOTE.mkdir(parents=True, exist_ok=True)
(REMOTE / "remote_model.safetensors").write_bytes(b"RM" * 2048)


async def remote_file(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    target = REMOTE / name
    if not target.is_file():
        return web.Response(status=404)
    return web.Response(body=target.read_bytes())


async def remote_slow(request: web.Request) -> web.StreamResponse:
    payload = b"S" * (128 * 1024)
    resp = web.StreamResponse()
    resp.headers["Content-Length"] = str(len(payload))
    resp.content_type = "application/octet-stream"
    await resp.prepare(request)
    for i in range(0, len(payload), 8192):
        await resp.write(payload[i : i + 8192])
        await asyncio.sleep(0.05)
    await resp.write_eof()
    return resp


# Fake huggingface_hub so the HF upload route can be exercised offline. The
# real library exposes no per-chunk callback, and neither does the fake: the
# upload simply blocks for a few seconds inside the executor thread.
import time as _time
import types as _types

FAKE_HF: dict = {"uploads": [], "delay": 4.0}


class _FakeHfApi:
    def __init__(self, token=None, library_name=None):
        self.token = token

    def whoami(self):
        return {"name": "probe-user", "fullname": "Probe User"}

    def repo_exists(self, repo_id):
        return False

    def create_repo(self, repo_id, private=False, exist_ok=False):
        FAKE_HF.setdefault("repos", []).append((repo_id, private))
        return None

    def upload_file(self, *, path_or_fileobj, path_in_repo, repo_id, repo_type=None, token=None):
        _time.sleep(FAKE_HF["delay"])
        FAKE_HF["uploads"].append((repo_id, path_in_repo))
        return path_in_repo


_fake_hf_mod = _types.ModuleType("huggingface_hub")
_fake_hf_mod.HfApi = _FakeHfApi  # type: ignore[attr-defined]
_fake_hf_mod.__version__ = "0.99.0.fake"
_fake_hf_utils = _types.ModuleType("huggingface_hub.utils")


class _HfHubHTTPError(Exception):
    pass


_fake_hf_utils.HfHubHTTPError = _HfHubHTTPError
_fake_hf_utils.EntryNotFoundError = type("EntryNotFoundError", (Exception,), {})
_fake_hf_utils.RepositoryNotFoundError = type("RepositoryNotFoundError", (Exception,), {})
_fake_hf_utils.GatedRepoError = type("GatedRepoError", (Exception,), {})
_fake_hf_mod.utils = _fake_hf_utils
sys.modules.setdefault("huggingface_hub", _fake_hf_mod)
sys.modules.setdefault("huggingface_hub.utils", _fake_hf_utils)
sys.modules.setdefault("hf_xet", _types.ModuleType("hf_xet"))

spec = importlib.util.spec_from_file_location(
    "cmmn", REPO / "__init__.py", submodule_search_locations=[str(REPO)]
)
ext = importlib.util.module_from_spec(spec)
sys.modules["cmmn"] = ext
spec.loader.exec_module(ext)

serverInstance = server_stub.PromptServer.instance

WEB_DIR = Path(os.environ.get("MM_WEB_DIR", REPO / "web"))
CSS_NAME = next(p.name for p in WEB_DIR.glob("style-*.css"))

PAGE = """<!doctype html>
<html class="dark-theme">
<head>
<meta charset="utf-8">
<title>Model Manager Neo harness</title>
<link rel="stylesheet" href="/web/{css}">
<style>
  /* crude stand-in for the ComfyUI page chrome + palette variables */
  html {{ color-scheme: dark; }}
  html:not(.dark-theme) {{ color-scheme: light; }}
  body {{
    margin: 0; min-height: 100vh;
    background:
      radial-gradient(1200px 600px at 80% -10%, #23406b55, transparent),
      linear-gradient(160deg, #101418, #1a2028 60%, #101418);
    --comfy-menu-bg: #1c2128; --comfy-input-bg: #262b33;
    --fg-color: #e8eaed; --color-muted-foreground: #9aa2ad;
    --border-subtle: #ffffff14; --border-color: #565b63;
    --color-accent-primary: #6aa6ff; --primary-fg: #0b1220;
    --color-error: #ff5c5c; --color-green-500: #3ecf8e;
  }}
  html:not(.dark-theme) body {{
    background: linear-gradient(160deg, #f4f6fa, #e7ebf2 60%, #f4f6fa);
    --comfy-menu-bg: #f7f8fa; --comfy-input-bg: #ffffff;
    --fg-color: #20242a; --color-muted-foreground: #5b6470;
    --border-subtle: #00000014; --border-color: #b9c0ca;
    --color-accent-primary: #2f6fdb; --primary-fg: #ffffff;
    --color-error: #c93a3a; --color-green-500: #1d9e66;
  }}
</style>
<script>
  ;(() => {{
  const settings = {{}}
  const settingDefs = []
  const listeners = new Map()
  function $el(tag, props, children) {{
    const [name, ...classes] = tag.split('.')
    const el = document.createElement(name)
    if (classes.length) el.className = classes.join(' ')
    if (Array.isArray(props)) {{ children = props; props = null }}
    for (const [k, v] of Object.entries(props || {{}})) {{
      if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v)
      else if (k === 'style') Object.assign(el.style, v)
      else el[k] = v
    }}
    for (const child of children || []) el.appendChild(child)
    return el
  }}
  window.comfyAPI = {{
    app: {{
      app: {{
        registerExtension(ext) {{
          window.__registeredExtension = ext
          ext.setup?.()
        }},
        ui: {{
          settings: {{
            getSettingValue: (k) => settings[k],
            setSettingValue: (k, v) => {{ settings[k] = v }},
            addSetting: (def) => {{ settingDefs.push(def) }},
          }},
          menuContainer: document.createElement('div'),
        }},
        menu: {{ settingsGroup: {{ element: document.createElement('button') }} }},
        canvas: {{
          selected_nodes: {{}},
          canvas_mouse: [40, 40],
          selectNode() {{}},
          copyToClipboard() {{}},
        }},
        graph: {{ add() {{}} }},
        handleFile() {{}},
        clientPosToCanvasPos: (p) => p,
      }},
    }},
    api: {{
      api: {{
        fetchApi: (url, opts) => fetch(url, opts),
        addEventListener: (type, cb) => {{
          const wrap = (e) => cb(e)
          listeners.set(cb, wrap)
          window.addEventListener('mm:' + type, wrap)
        }},
        removeEventListener: (type, cb) => {{
          const wrap = listeners.get(cb)
          if (wrap) window.removeEventListener('mm:' + type, wrap)
          listeners.delete(cb)
        }},
        getSystemStats: async () => ({{ system: {{ os: 'linux' }} }}),
      }},
    }},
    ui: {{ $el }},
    button: {{
      ComfyButton: class ComfyButton {{
        constructor(options) {{
          this.options = options
          this.element = $el('button.comfy-button', {{ textContent: options.content || '' }})
          this.element.addEventListener('click', () => options.action?.())
        }}
      }},
    }},
  }}
  window.LiteGraph = {{
    createNode: () => ({{ widgets: [{{ type: 'combo', value: null }}], pos: [0, 0] }}),
  }}
  // ComfyUI's websocket bridge, emulated: server pushes arrive as
  // CustomEvents on window, exactly what window.comfyAPI.api.addEventListener
  // consumes in the real frontend.
  try {{
    const ws = new WebSocket(location.origin.replace(/^http/, 'ws') + '/ws')
    ws.onmessage = (ev) => {{
      const msg = JSON.parse(ev.data)
      window.dispatchEvent(new CustomEvent('mm:' + msg.type, {{ detail: msg.data }}))
    }}
  }} catch (e) {{
    /* no bridge, no events */
  }}
  }})()
</script>
</head>
<body>
<script type="module" src="/web/manager.js"></script>
</body>
</html>
"""


async def ws_bridge(request: web.Request) -> web.WebSocketResponse:
    """Stands in for ComfyUI's websocket: every send_json push is forwarded
    to the page, which re-dispatches it as a CustomEvent like the real
    frontend api does."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    serverInstance.sockets.add(ws)
    try:
        async for _ in ws:
            pass
    finally:
        serverInstance.sockets.discard(ws)
    return ws


async def harness_page(request: web.Request) -> web.Response:
    return web.Response(text=PAGE.format(css=CSS_NAME), content_type="text/html")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()

    app = web.Application()
    app.add_routes(serverInstance.routes)
    app.router.add_get("/harness", harness_page)
    app.router.add_get("/ws", ws_bridge)
    app.router.add_get("/remote/{name}", remote_file)
    app.router.add_get("/slow/{name}", remote_slow)
    app.router.add_get("/probe/hf", lambda r: web.json_response(FAKE_HF))
    app.router.add_get(
        "/probe/events",
        lambda r: web.json_response([e for e, _ in serverInstance.sent]),
    )
    app.router.add_static("/web", WEB_DIR)

    web.run_app(app, host="127.0.0.1", port=args.port, print=lambda *a: None)


if __name__ == "__main__":
    main()
