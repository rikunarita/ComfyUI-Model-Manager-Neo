"""ComfyUI singleton stubs (folder_paths / server.PromptServer / comfy.utils).

Imported by tests/conftest.py (pytest) and by scripts/bench (bench harnesses)
BEFORE any extension module is loaded. The stubbed semantics mirror
comfyanonymous/ComfyUI master — re-verified against the upstream sources on
2026-09-23 (no guessing):

* ``folder_paths.supported_pt_extensions`` — the real default set
  ``{'.ckpt', '.pt', '.pt2', '.bin', '.pth', '.safetensors', '.pkl', '.sft'}``
  plus the ``.gguf`` / ``.znn`` additions the extension's ``__init__.py``
  performs;
* ``folder_paths.get_folder_paths(name)`` -> ``folder_names_and_paths[name][0][:]``;
* ``folder_paths.filter_files_extensions(files, exts)`` — sorted suffix filter;
* ``comfy.utils.safetensors_header(path, max_size)`` — header bytes or None
  (verbatim upstream semantics, plus a defensive short-read guard: upstream
  raises ``struct.error`` on a <8-byte file, this stub returns None; both are
  caught by the callers' ``except Exception`` and map to the same result);
* ``server.PromptServer.instance`` with ``.routes`` and async ``.send_json``.
"""

from __future__ import annotations

import sys
import types


def install() -> None:
    if "folder_paths" in sys.modules and getattr(sys.modules["folder_paths"], "_mmneo_stub", False):
        return

    folder_paths = types.ModuleType("folder_paths")
    folder_paths._mmneo_stub = True  # type: ignore[attr-defined]
    # ComfyUI master default + the extension __init__.py additions.
    folder_paths.supported_pt_extensions = {
        ".ckpt",
        ".pt",
        ".pt2",
        ".bin",
        ".pth",
        ".safetensors",
        ".pkl",
        ".sft",
        ".gguf",
        ".znn",
    }
    folder_paths.folder_names_and_paths = {}

    def get_folder_paths(folder_name: str) -> list[str]:
        return folder_paths.folder_names_and_paths[folder_name][0][:]

    def add_model_folder_path(folder_name: str, full_folder_path: str) -> None:
        values = folder_paths.folder_names_and_paths.setdefault(folder_name, ([], set()))
        if full_folder_path not in values[0]:
            values[0].append(full_folder_path)

    def filter_files_extensions(files, extensions):
        # Verbatim semantics of folder_paths.filter_files_extensions (ComfyUI master).
        import os

        if len(extensions) == 0:
            return sorted(files)
        return sorted(f for f in files if os.path.splitext(f)[-1].lower() in extensions)

    folder_paths.get_folder_paths = get_folder_paths  # type: ignore[attr-defined]
    folder_paths.add_model_folder_path = add_model_folder_path  # type: ignore[attr-defined]
    folder_paths.filter_files_extensions = filter_files_extensions  # type: ignore[attr-defined]
    sys.modules["folder_paths"] = folder_paths

    comfy = types.ModuleType("comfy")
    comfy.__path__ = []  # type: ignore[attr-defined]
    comfy_utils = types.ModuleType("comfy.utils")

    def safetensors_header(safetensors_path: str, max_size: int = 100 * 1024 * 1024):
        # Verbatim semantics of comfy.utils.safetensors_header (ComfyUI master),
        # with a defensive guard for files shorter than the 8-byte prefix.
        import struct

        with open(safetensors_path, "rb") as f:
            header = f.read(8)
            if len(header) < 8:
                return None
            length_of_header = struct.unpack("<Q", header)[0]
            if length_of_header > max_size:
                return None
            return f.read(length_of_header)

    comfy_utils.safetensors_header = safetensors_header  # type: ignore[attr-defined]
    comfy.utils = comfy_utils  # type: ignore[attr-defined]
    sys.modules["comfy"] = comfy
    sys.modules["comfy.utils"] = comfy_utils

    server = types.ModuleType("server")

    class _Routes:
        """Collector mirroring aiohttp's RouteTableDef decorator surface."""

        def __init__(self) -> None:
            self.handlers: dict[tuple[str, str], object] = {}

        def _reg(self, method: str, path: str):
            def deco(fn):
                self.handlers[(method, path)] = fn
                return fn

            return deco

        def get(self, path: str):
            return self._reg("GET", path)

        def post(self, path: str):
            return self._reg("POST", path)

        def put(self, path: str):
            return self._reg("PUT", path)

        def delete(self, path: str):
            return self._reg("DELETE", path)

    class _PromptServer:
        instance = None

        def __init__(self) -> None:
            self.routes = _Routes()
            self.sent: list[tuple] = []

        async def send_json(self, event, data, sid=None) -> None:
            self.sent.append((event, data, sid))

    _PromptServer.instance = _PromptServer()
    server.PromptServer = _PromptServer  # type: ignore[attr-defined]
    sys.modules["server"] = server
