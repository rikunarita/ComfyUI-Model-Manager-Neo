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


def zipnn_available() -> bool:
    try:
        import zipnn  # noqa: F401
        import zipnn_core  # noqa: F401

        return True
    except Exception:
        return False


def ensure_zipnn() -> None:
    """Install ZipNN on first use (opt-in: it compiles from source on Linux)."""
    if zipnn_available():
        return
    utils.print_info("Installing zipnn (first use of the ZipNN feature)...")
    utils.pip_install("zipnn")
    if not zipnn_available():
        raise RuntimeError(
            "zipnn could not be installed on this machine (it needs a C++ toolchain "
            "to build from source). See https://github.com/zipnn/zipnn"
        )


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

        task_id = uuid.uuid4().hex
        ZIPNN_TASKS[task_id] = {"mode": mode, "status": "running", "src": src, "dst": dst}
        await utils.send_json(
            "update_zipnn_progress",
            {"taskId": task_id, "progress": 0.0, "phase": "prepare", "mode": mode},
        )

        loop = asyncio.get_running_loop()

        async def worker():
            try:
                await loop.run_in_executor(utils.cpu_executor(), ensure_zipnn)
            except Exception as e:
                await self._fail(task_id, src, str(e))
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

    async def _fail(self, task_id: str, src: str, error: str):
        ZIPNN_TASKS[task_id]["status"] = "error"
        utils.print_error(f"zipnn failed for {src}: {error}")
        await utils.send_json(
            "zipnn_complete",
            {"taskId": task_id, "ok": False, "error": error},
        )
