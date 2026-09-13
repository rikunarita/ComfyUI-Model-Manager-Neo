"""ZipNN compression / decompression for local safetensors models.

The tensor-by-tensor algorithm below is a faithful, non-interactive port of the
official reference scripts of the ZipNN project
(`scripts/zipnn_compress_safetensors.py` / `scripts/zipnn_decompress_safetensors.py`,
https://github.com/zipnn/zipnn, version 0.5.4):

* floating point tensors are compressed with ``ZipNN(input_format="torch",
  method=COMPRESSION_METHOD)`` and stored as ``uint8`` vectors;
* non floating point tensors are copied through untouched;
* per-tensor ``dtype``/``shape`` are recorded in the file metadata under
  ``znn_compressed_vectors`` (``zipnn.util_safetensors.METADATA_KEY``);
* a tensor whose compressed form is not smaller is left uncompressed;
* the compressed file is named ``<base>.znn.safetensors`` - the exact suffix the
  official scripts (and ``zipnn_safetensors()`` loaders) expect.

ZipNN is an OPTIONAL dependency: PyPI ships no Linux wheels for it, so it is
built from source and must never be forced onto every ComfyUI installation. It
is therefore installed on demand (with an explicit confirmation in the UI) the
first time the feature is used.
"""

import asyncio
import os
import uuid
from typing import Any, Callable, Optional

from aiohttp import web

from . import config
from . import utils

ZNN_SUFFIX = ".znn.safetensors"
SAFE_SUFFIX = ".safetensors"

# task_id -> bookkeeping, same shape as the HF upload tasks
ZIPNN_TASKS: dict[str, dict] = {}

ProgressCb = Callable[[int, int, str], None]


def is_safetensors(name: str) -> bool:
    return name.endswith(SAFE_SUFFIX)


def is_compressed_name(name: str) -> bool:
    return name.endswith(ZNN_SUFFIX)


def zipnn_installed() -> bool:
    """True when the ZipNN files exist on disk (without importing them).

    ``importlib.invalidate_caches()`` matters here: ZipNN is installed by a
    *subprocess* after this interpreter has already scanned site-packages, so
    without it a successful install can still look absent.
    """
    import importlib.util

    importlib.invalidate_caches()
    try:
        return (
            importlib.util.find_spec("zipnn") is not None
            and importlib.util.find_spec("zipnn_core") is not None
        )
    except Exception:
        return False


def zipnn_available() -> bool:
    try:
        import importlib

        importlib.invalidate_caches()
        import zipnn  # noqa: F401
        import zipnn_core  # noqa: F401

        return True
    except Exception:
        return False


# ZipNN ships no Linux wheels: `pip install zipnn` compiles a C extension from
# the sdist. Modern toolchains (gcc >= 14, clang >= 16) turn a few historical C
# patterns into hard errors by default (-Werror=implicit-function-declaration,
# -Werror=incompatible-pointer-types), which made the build die with a bare
# "exit status 1". Relaxing exactly those diagnostics keeps every real error
# visible while letting the official sources build.
_ZIPNN_BUILD_CFLAGS = (
    "-Wno-error=implicit-function-declaration "
    "-Wno-implicit-function-declaration "
    "-Wno-error=incompatible-pointer-types "
    "-Wno-incompatible-pointer-types "
    "-Wno-error=int-conversion "
    "-Wno-int-conversion"
)

# Optional escape hatch for offline / air-gapped machines: drop platform
# wheels into this directory and they are preferred over PyPI.
_ZIPNN_WHEEL_DIR = "zipnn-wheels"

# A failed install is remembered so that hammering the button does not re-run a
# doomed multi-minute build - but only for a while: the user may fix their
# toolchain, and the UI offers an explicit retry (`force`).
_ZIPNN_INSTALL_TTL = 300.0
_zipnn_install_failed: tuple[str, float] | None = None


class ZipNNInstallError(RuntimeError):
    """The optional ZipNN dependency could not be installed on this host."""


_PKG_MANAGER_HINTS = {
    "debian": "sudo apt-get install -y build-essential python3-dev",
    "ubuntu": "sudo apt-get install -y build-essential python3-dev",
    "linuxmint": "sudo apt-get install -y build-essential python3-dev",
    "pop": "sudo apt-get install -y build-essential python3-dev",
    "fedora": "sudo dnf install -y gcc gcc-c++ python3-devel",
    "rhel": "sudo dnf install -y gcc gcc-c++ python3-devel",
    "centos": "sudo dnf install -y gcc gcc-c++ python3-devel",
    "rocky": "sudo dnf install -y gcc gcc-c++ python3-devel",
    "almalinux": "sudo dnf install -y gcc gcc-c++ python3-devel",
    "arch": "sudo pacman -S --needed base-devel",
    "manjaro": "sudo pacman -S --needed base-devel",
    "opensuse": "sudo zypper install -y gcc gcc-c++ python3-devel",
    "opensuse-leap": "sudo zypper install -y gcc gcc-c++ python3-devel",
    "alpine": "sudo apk add build-base python3-dev",
    "gentoo": "sudo emerge --ask sys-devel/gcc",
}


def _distro_id() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("ID="):
                    return line.split("=", 1)[1].strip().strip('"').lower()
    except OSError:
        pass
    return ""


def _python_headers_missing() -> bool:
    """True when Python.h cannot be found for the *base* interpreter."""
    import sys
    import sysconfig

    short = sysconfig.get_config_var("py_version_short") or ""
    candidates = [sysconfig.get_paths().get("include", "")]
    base = getattr(sys, "base_prefix", sys.prefix)
    candidates += [
        os.path.join(base, "include"),
        os.path.join(base, "include", f"python{short}"),
        os.path.join(base, "include", f"python{short}m"),
    ]
    return not any(
        c and os.path.exists(os.path.join(c, "Python.h")) for c in candidates
    )


def _build_prereq_hint() -> str | None:
    """Explain *why* a source build would fail, with the command that fixes it.

    PyPI ships no Linux wheel for ZipNN, so `pip install zipnn` compiles a C
    extension. The two overwhelmingly common reasons that fails are a missing
    compiler and missing Python headers (`fatal error: Python.h: No such file
    or directory`) - neither is visible in a bare "exit status 1".
    """
    import shutil
    import sys
    import sysconfig

    missing: list[str] = []
    cc = (
        shutil.which(os.environ.get("CC", ""))
        if os.environ.get("CC")
        else None
    ) or shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not cc:
        missing.append("no C compiler (cc/gcc/clang) on PATH")
    if _python_headers_missing():
        missing.append(
            f"no Python headers (Python.h not found for {sysconfig.get_paths().get('include')})"
        )
    if not missing:
        return None

    if sys.platform == "darwin":
        fix = "xcode-select --install"
    else:
        fix = _PKG_MANAGER_HINTS.get(_distro_id(), "")
    if os.environ.get("CONDA_PREFIX"):
        fix = (fix + "  |  conda: ").strip("  |  ") + (
            "conda install -y -c conda-forge cxx-compiler"
        )
    hint = "Build prerequisites look incomplete: " + "; ".join(missing) + "."
    if fix:
        hint += f" Fix it with: {fix}"
    return hint


def _ensure_pip() -> None:
    """venvs created with `--without-pip` (or broken upgrades) have no pip."""
    import subprocess
    import sys

    probe = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        subprocess.run(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            capture_output=True,
            text=True,
        )


def _run_pip(args: list[str], extra_env: dict[str, str] | None = None) -> str:
    """Run a pip invocation, returning its output or raising with its tail.

    The previous implementation used ``subprocess.run(..., check=True)`` without
    capturing anything, so a failed build surfaced as a bare
    "returned non-zero exit status 1" with no way to tell *why*.
    """
    import subprocess
    import sys

    env = os.environ.copy()
    for key, value in (extra_env or {}).items():
        env[key] = f"{env.get(key, '')} {value}".strip()
    proc = subprocess.run(
        [sys.executable, "-m", "pip", *args],
        capture_output=True,
        text=True,
        env=env,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(
            f"`pip {' '.join(args)}` failed (exit {proc.returncode}):\n"
            + "\n".join(output.strip().splitlines()[-25:])
        )
    return output


def _zipnn_import_error() -> str | None:
    """Why ``import zipnn`` fails, or None when it works."""
    if zipnn_available():
        return None
    try:
        import zipnn  # noqa: F401
    except Exception as e:  # pragma: no cover - depends on the host env
        return f"{type(e).__name__}: {e}"
    return "zipnn_core extension not importable"


def ensure_zipnn(force: bool = False) -> None:
    """Install ZipNN on first use (opt-in: it compiles from source on Linux).

    Strategies, in order - the first that yields an importable ZipNN wins:

    1. a wheel placed in ``assets/zipnn-wheels/`` (offline / air-gapped hosts);
    2. ``pip install --no-deps zipnn`` - ComfyUI venvs always ship numpy,
       safetensors and torch, and resolving them again makes pip pull a
       ~550 MB torch wheel for no reason;
    3. a full ``pip install zipnn`` (dependencies actually missing);
    4. ``pip install --no-build-isolation zipnn`` (hosts whose build isolation
       cannot reach PyPI), after making sure the build backends exist.

    Every attempt is compiled with a few ``-Wno-error=...`` flags: gcc >= 14 and
    clang >= 16 default ``implicit-function-declaration`` /
    ``incompatible-pointer-types`` to hard errors, which made ZipNN 0.5.4's C
    sources fail to build on modern toolchains. Failures carry the tail of pip's
    own output plus a host-specific prerequisite hint, and are cached for
    :data:`_ZIPNN_INSTALL_TTL` seconds so repeated presses do not re-run a
    doomed build (``force=True``, used by the UI retry, bypasses the cache).
    """
    global _zipnn_install_failed
    import time

    if zipnn_available():
        _zipnn_install_failed = None
        return
    if _zipnn_install_failed and not force:
        message, at = _zipnn_install_failed
        if time.time() - at < _ZIPNN_INSTALL_TTL:
            raise ZipNNInstallError(message)
        _zipnn_install_failed = None

    utils.print_info("Installing zipnn (first use of the ZipNN feature)...")
    _ensure_pip()
    hint = _build_prereq_hint()
    if hint:
        utils.print_info(f"  warning: {hint}")
    cflags = {"CFLAGS": _ZIPNN_BUILD_CFLAGS}
    wheel_dir = utils.join_path(config.extension_uri, "assets", _ZIPNN_WHEEL_DIR)
    errors: list[str] = []

    attempts: list[tuple[str, list[str]]] = []
    wheels = (
        sorted(w for w in os.listdir(wheel_dir) if w.endswith(".whl"))
        if os.path.isdir(wheel_dir)
        else []
    )
    if wheels:
        attempts.append(("local wheel", ["install", "--no-deps", os.path.join(wheel_dir, wheels[-1])]))
    attempts.append(("no-deps", ["install", "--no-deps", "zipnn"]))
    attempts.append(("full", ["install", "zipnn"]))
    attempts.append(("no-build-isolation", ["install", "--no-build-isolation", "zipnn"]))

    for label, args in attempts:
        try:
            if label == "no-build-isolation":
                _run_pip(["install", "setuptools", "wheel", "numpy", "safetensors", "torch"])
            utils.print_info(f"  trying: pip {' '.join(args)} ({label})")
            _run_pip(args, cflags)
        except Exception as e:
            errors.append(f"[{label}] {e}")
            continue
        if zipnn_available():
            _zipnn_install_failed = None
            return
        if zipnn_installed():
            # Built fine, but something it imports is missing (torch /
            # safetensors / numpy). Re-installing would not help - and would
            # needlessly re-download a ~550 MB torch wheel.
            message = (
                f"ZipNN was installed but cannot be imported: {_zipnn_import_error()}"
            )
            _zipnn_install_failed = (message, time.time())
            utils.print_error(message)
            raise ZipNNInstallError(message)

    message = (
        "ZipNN could not be installed on this machine. PyPI ships no Linux "
        "wheels for it, so it has to be built from source, which needs a C "
        "compiler and the Python headers (Python.h). "
        + (hint + " " if hint else "")
        + "Alternatively drop a prebuilt wheel into `assets/zipnn-wheels/`. "
        "Details:\n"
        + "\n".join(errors[-4:])
    )
    _zipnn_install_failed = (message, time.time())
    utils.print_error(message)
    raise ZipNNInstallError(message)


def _sidecar_move(old_model: str, new_model: str) -> None:
    """Move previews + notes from one model file to another (same directory)."""
    directory = os.path.dirname(old_model)
    names = utils.get_dir_names(directory)
    old_base = os.path.splitext(os.path.basename(old_model))[0]
    new_base = os.path.splitext(os.path.basename(new_model))[0]
    for preview in utils.previews_in_names(names, old_base):
        ext = preview[len(old_base):]
        src = utils.join_path(directory, preview)
        dst = utils.join_path(directory, f"{new_base}{ext}")
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)
    for desc in utils.get_model_all_descriptions(old_model):
        src = utils.join_path(directory, desc)
        dst = utils.join_path(directory, f"{new_base}{os.path.splitext(desc)[1]}")
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)


def compress_safetensors(src: str, dst: str, progress: ProgressCb) -> dict[str, Any]:
    """Compress `src` (.safetensors) into `dst` (.znn.safetensors)."""
    from safetensors import safe_open
    from safetensors.torch import save_file
    from zipnn import ZipNN
    from zipnn.util_header import EnumFormat
    from zipnn.util_safetensors import (
        COMPRESSION_METHOD,
        COMPRESSED_DTYPE,
        build_compressed_tensor_info,
        set_compressed_tensors_metadata,
    )
    from zipnn.util_torch import zipnn_is_floating_point

    tensors: dict[str, Any] = {}
    infos: dict[str, Any] = {}
    original_bytes = 0
    compressed_bytes = 0

    with safe_open(src, "pt", "cpu") as f:
        keys = list(f.keys())
        total = max(1, len(keys))
        for index, name in enumerate(keys):
            tensor = f.get_tensor(name)
            if not zipnn_is_floating_point(EnumFormat.TORCH.value, tensor, tensor.dtype):
                tensors[name] = tensor
                size = tensor.element_size() * tensor.nelement()
                original_bytes += size
                compressed_bytes += size
                progress(index + 1, total, "tensors")
                continue
            infos[name] = build_compressed_tensor_info(tensor)
            znn = ZipNN(
                input_format="torch",
                bytearray_dtype=tensor.dtype,
                method=COMPRESSION_METHOD,
            )
            uncompressed_size = tensor.element_size() * tensor.nelement()
            original_bytes += uncompressed_size
            compressed_buf = znn.compress(tensor)
            if len(compressed_buf) >= uncompressed_size:
                # Not worth it: keep the tensor as-is (official behaviour).
                tensors[name] = tensor
                compressed_bytes += uncompressed_size
            else:
                import torch

                tensors[name] = torch.frombuffer(compressed_buf, dtype=COMPRESSED_DTYPE)
                compressed_bytes += len(compressed_buf)
            progress(index + 1, total, "tensors")
        metadata = f.metadata()

    set_compressed_tensors_metadata(infos, metadata)
    tmp_dst = f"{dst}.tmp"
    save_file(tensors, tmp_dst, metadata)
    os.replace(tmp_dst, dst)
    return {
        "originalBytes": original_bytes,
        "compressedBytes": compressed_bytes,
        "tensors": len(keys),
        "compressedTensors": len(infos),
    }


def decompress_safetensors(src: str, dst: str, progress: ProgressCb) -> dict[str, Any]:
    """Decompress `src` (.znn.safetensors) into `dst` (.safetensors)."""
    from safetensors import safe_open
    from safetensors.torch import save_file
    from zipnn import ZipNN
    from zipnn.util_safetensors import (
        COMPRESSION_METHOD,
        COMPRESSED_DTYPE,
        get_compressed_tensors_metadata,
    )

    tensors: dict[str, Any] = {}
    with safe_open(src, "pt", "cpu") as f:
        metadata = f.metadata()
        compressed_infos = get_compressed_tensors_metadata(metadata or {})
        znn = ZipNN(
            input_format="torch",
            bytearray_dtype=COMPRESSED_DTYPE,
            method=COMPRESSION_METHOD,
        )
        keys = list(f.keys())
        total = max(1, len(keys))
        for index, name in enumerate(keys):
            tensor = f.get_tensor(name)
            if name not in compressed_infos:
                tensors[name] = tensor
            else:
                tensors[name] = znn.decompress(tensor.contiguous().numpy())
            progress(index + 1, total, "tensors")
        if metadata:
            metadata.pop("znn_compressed_vectors", None)

    tmp_dst = f"{dst}.tmp"
    save_file(tensors, tmp_dst, metadata)
    os.replace(tmp_dst, dst)
    return {"tensors": len(keys), "decompressedTensors": len(compressed_infos)}


class ZipNNRoutes:
    def add_routes(self, routes):
        @routes.get("/model-manager/zipnn/available")
        async def zipnn_status(request):
            return web.json_response(
                {"success": True, "data": {"available": zipnn_available()}}
            )

        @routes.post("/model-manager/zipnn/compress")
        async def zipnn_compress(request):
            return await self._run(request, "compress")

        @routes.post("/model-manager/zipnn/decompress")
        async def zipnn_decompress(request):
            return await self._run(request, "decompress")

    async def _run(self, request, mode: str):
        data = await utils.get_request_body(request)
        model_type = data.get("type")
        path_index = int(data.get("pathIndex") or 0)
        fullname = data.get("fullname")
        if not model_type or not fullname:
            return web.json_response(
                {"success": False, "error": "type and fullname are required"}
            )
        if not is_safetensors(fullname):
            return web.json_response(
                {
                    "success": False,
                    "error": "ZipNN compression supports .safetensors files only",
                }
            )
        try:
            src = utils.get_valid_full_path(model_type, path_index, fullname)
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)})
        if src is None:
            return web.json_response({"success": False, "error": "model not found"})

        if mode == "compress":
            if is_compressed_name(fullname):
                return web.json_response(
                    {"success": False, "error": "model is already compressed"}
                )
            base = src[: -len(SAFE_SUFFIX)]
            dst = f"{base}{ZNN_SUFFIX}"
        else:
            if not is_compressed_name(fullname):
                return web.json_response(
                    {"success": False, "error": "model is not ZipNN compressed"}
                )
            base = src[: -len(ZNN_SUFFIX)]
            dst = f"{base}{SAFE_SUFFIX}"
        if os.path.exists(dst):
            return web.json_response(
                {"success": False, "error": f"target already exists: {os.path.basename(dst)}"}
            )

        force = bool(data.get("force"))
        task_id = uuid.uuid4().hex
        ZIPNN_TASKS[task_id] = {"mode": mode, "status": "running", "src": src, "dst": dst}
        await utils.send_json(
            "update_zipnn_progress",
            {"taskId": task_id, "progress": 0.0, "phase": "prepare", "mode": mode},
        )

        loop = asyncio.get_running_loop()

        async def worker():
            try:
                await loop.run_in_executor(utils.cpu_executor(), ensure_zipnn, force)
            except Exception as e:
                await self._fail(
                    task_id,
                    src,
                    str(e),
                    install_failed=isinstance(e, ZipNNInstallError),
                )
                return

            def progress(done: int, total: int, phase: str):
                asyncio.run_coroutine_threadsafe(
                    utils.send_json(
                        "update_zipnn_progress",
                        {
                            "taskId": task_id,
                            "progress": (done / total * 100) if total else 0.0,
                            "phase": phase,
                            "mode": mode,
                        },
                    ),
                    loop,
                )

            fn = compress_safetensors if mode == "compress" else decompress_safetensors
            try:
                stats = await loop.run_in_executor(
                    utils.cpu_executor(), fn, src, dst, progress
                )
            except Exception as e:
                # never leave a half-written target behind
                for candidate in (dst, f"{dst}.tmp"):
                    if os.path.exists(candidate):
                        try:
                            os.remove(candidate)
                        except OSError:
                            pass
                await self._fail(task_id, src, str(e))
                return

            # The model entry moves to the new file: previews and notes follow.
            try:
                _sidecar_move(src, dst)
                os.remove(src)
            except Exception as e:
                await self._fail(task_id, src, str(e))
                return

            ZIPNN_TASKS[task_id]["status"] = "complete"
            await utils.send_json(
                "update_zipnn_progress",
                {"taskId": task_id, "progress": 100.0, "phase": "done", "mode": mode},
            )
            await utils.send_json(
                "zipnn_complete",
                {
                    "taskId": task_id,
                    "mode": mode,
                    "ok": True,
                    "stats": stats,
                    "fullname": os.path.basename(dst),
                },
            )

        loop.create_task(self._schedule(worker()))
        return web.json_response({"success": True, "data": {"taskId": task_id}})

    async def _schedule(self, coro):
        try:
            await coro
        except Exception as e:  # pragma: no cover - defensive
            utils.print_error(f"zipnn worker crashed: {e}")

    async def _fail(
        self, task_id: str, src: str, error: str, install_failed: bool = False
    ):
        ZIPNN_TASKS[task_id]["status"] = "error"
        utils.print_error(f"zipnn failed for {src}: {error}")
        await utils.send_json(
            "zipnn_complete",
            {
                "taskId": task_id,
                "ok": False,
                "error": error,
                # The UI turns this into a "retry install" action, because the
                # backend caches a failed install for a few minutes.
                "installFailed": install_failed,
            },
        )
