"""Shared helpers for the Phase 0 KPI baseline benchmarks (Agent/Plan.md §2.2).

The Neo backend lives inside ComfyUI: `py/utils.py` imports `comfy.utils` and
`folder_paths`, which only exist in a running ComfyUI process. To benchmark the
real code paths (`py/manager.py` scan, `py/utils.py` header parsing,
`py/compress.py` ZipNN flows, `py/identify.py` hashing) *unmodified*, this
module injects minimal, faithful stand-ins for the ComfyUI-side modules:

* `folder_paths.folder_names_and_paths` / `supported_pt_extensions` — the two
  attributes the backend actually reads (values come from ComfyUI's
  `folder_paths.py`; `supported_pt_extensions` mirrors its default set plus the
  two extensions `__init__.py` adds: `.gguf`, `.znn`).
* `comfy.utils.safetensors_header` — a verbatim copy of ComfyUI's current
  implementation (fetched from comfyanonymous/ComfyUI master, comfy/utils.py):
  read the 8-byte little-endian header length, guard it against `max_size`,
  return the raw header bytes.
* `server.PromptServer` — only `py/compress.py` touches it (websocket push);
  the benchmarks call the plain worker functions, not the routes, so a stub
  that records sends is enough.

Everything here is measurement scaffolding: it never ships inside the
extension and never alters the code under test.
"""

from __future__ import annotations

import os
import struct
import sys
import time
import types
from typing import Any, ClassVar

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ComfyUI's default supported_pt_extensions — verbatim from
# comfyanonymous/ComfyUI master folder_paths.py (re-verified 2026-09-23:
# {'.ckpt', '.pt', '.pt2', '.bin', '.pth', '.safetensors', '.pkl', '.sft'});
# the extension's __init__.py adds ".gguf" and ".znn" on top. Mirror both
# exactly: the scan bench measures the real extension filter.
SUPPORTED_PT_EXTENSIONS = {
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


def _safetensors_header(safetensors_path: str, max_size: int = 100 * 1024 * 1024) -> bytes | None:
    """Verbatim behaviour of ComfyUI comfy.utils.safetensors_header (master)."""
    with open(safetensors_path, "rb") as f:
        header = f.read(8)
        (length_of_header,) = struct.unpack("<Q", header)
        if length_of_header > max_size:
            return None
        return f.read(length_of_header)


def install_comfyui_stubs(
    model_roots: dict[str, list[str]] | None = None,
) -> None:
    """Insert `folder_paths` / `comfy.utils` / `server` stubs into sys.modules.

    Call BEFORE importing any `py.*` module of the extension.
    `model_roots` maps model type -> list of root directories (what ComfyUI's
    `folder_names_and_paths` provides; benchmarks point it at synthetic trees).
    """
    if model_roots is None:
        model_roots = {}

    if "folder_paths" not in sys.modules:
        folder_paths = types.ModuleType("folder_paths")
        # ComfyUI shape: {type: ([paths], extensions_set, None)}
        folder_paths.folder_names_and_paths = {  # type: ignore[attr-defined]
            name: ([str(p) for p in paths], set(SUPPORTED_PT_EXTENSIONS), None) for name, paths in model_roots.items()
        }
        folder_paths.supported_pt_extensions = set(SUPPORTED_PT_EXTENSIONS)  # type: ignore[attr-defined]
        first_root = next((str(p) for paths in model_roots.values() for p in paths), REPO_ROOT)
        folder_paths.models_dir = os.path.dirname(first_root)  # type: ignore[attr-defined]

        def _get_folder_paths(folder_name: str) -> list[str]:
            # ComfyUI folder_paths.get_folder_paths (minus the legacy mapping).
            return list(folder_paths.folder_names_and_paths[folder_name][0])  # type: ignore[attr-defined]

        def _filter_files_extensions(files: list[str], extensions: list[str]) -> list[str]:
            # ComfyUI folder_paths.filter_files_extensions (verbatim semantics).
            return sorted(filter(lambda a: os.path.splitext(a)[-1].lower() in extensions or not extensions, files))

        folder_paths.get_folder_paths = _get_folder_paths  # type: ignore[attr-defined]
        folder_paths.filter_files_extensions = _filter_files_extensions  # type: ignore[attr-defined]
        sys.modules["folder_paths"] = folder_paths

    if "comfy" not in sys.modules:
        comfy = types.ModuleType("comfy")
        comfy_utils = types.ModuleType("comfy.utils")
        comfy_utils.safetensors_header = _safetensors_header  # type: ignore[attr-defined]
        comfy.utils = comfy_utils  # type: ignore[attr-defined]
        sys.modules["comfy"] = comfy
        sys.modules["comfy.utils"] = comfy_utils

    if "server" not in sys.modules:
        server = types.ModuleType("server")

        class _Routes:
            """Decorator factory shaped like aiohttp's RouteTableDef.

            Benchmarks call the plain worker functions, never the routes;
            registration only has to not explode at import time.
            """

            def _register(self, *_args: Any, **_kwargs: Any):
                def decorator(fn: Any) -> Any:
                    return fn

                return decorator

            get = post = put = delete = head = _register

        class _PromptServer:
            sent: ClassVar[list[tuple[str, Any]]] = []
            routes = _Routes()

            @classmethod
            def send_sync(cls, event: str, data: Any) -> None:
                cls.sent.append((event, data))

            @classmethod
            async def send_json(cls, event: str, data: Any, sid: str | None = None) -> None:
                cls.sent.append((event, data))

        _PromptServer.instance = _PromptServer  # type: ignore[attr-defined]
        server.PromptServer = _PromptServer  # type: ignore[attr-defined]
        sys.modules["server"] = server


def import_extension() -> None:
    """Make `import py.<module>` work from anywhere (repo root on sys.path).

    Robustness note: the repository's ``py/`` has no ``__init__.py`` (it is a
    namespace package when imported as ``py``), and a regular module ALWAYS
    beats a namespace package regardless of ``sys.path`` order — so a stray
    top-level ``py.py`` in site-packages (the legacy ``py`` helper library
    that older pytest ecosystems install) silently shadows the backend and
    ``from py import manager`` dies with an ImportError. Pin the ``py`` name
    to the repository directory before anything can claim it.
    """
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    existing = sys.modules.get("py")
    expected_path = os.path.join(REPO_ROOT, "py")
    if existing is None or list(getattr(existing, "__path__", [])) != [expected_path]:
        pkg = types.ModuleType("py")
        pkg.__path__ = [expected_path]  # type: ignore[attr-defined]
        sys.modules["py"] = pkg


class PeakRSS:
    """Peak RSS of this process, via VmHWM of /proc/self/status (Linux).

    Accurate enough for the "about N times the input size" claims of Plan
    §1.2.2; the
    number is the kernel's own high-water mark, not a sampled estimate.
    """

    @staticmethod
    def kib() -> int:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1])
        return -1

    @staticmethod
    def mib() -> float:
        return PeakRSS.kib() / 1024.0


class Timer:
    """Monotonic wall-clock context manager."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def __enter__(self) -> Timer:
        self._t0 = time.monotonic()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.seconds = time.monotonic() - self._t0


def vendored_zipnn_on_path() -> None:
    """Put the vendored ZipNN package + prebuilt core on sys.path.

    Mirrors what py/compress.py ensure_zipnn() does on the happy path
    (prebuilt linux-x86_64 binary for the running CPython), without the
    pip/source-build fallbacks.
    """
    third_party = os.path.join(REPO_ROOT, "third_party")
    tag = "linux-x86_64"
    bin_dir = os.path.join(third_party, "zipnn-core-bin", tag)
    suffix = f"cpython-{sys.version_info.major}{sys.version_info.minor}"
    if not any(name.startswith(f"zipnn_core.{suffix}") for name in os.listdir(bin_dir)):
        raise RuntimeError(f"no prebuilt zipnn_core for {suffix} in {bin_dir}")
    for path in (third_party, bin_dir):
        if path not in sys.path:
            sys.path.append(path)
