import asyncio
import base64
import hashlib
import json
import os
import pathlib
import shutil
import threading
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, ClassVar, Literal
from urllib.parse import urlparse

import aiohttp
import folder_paths
from aiohttp import web

from . import auth, config, native, thread, utils

# Quick Win A2 (Plan §4.8-A2): the download write loop used to pull 8 KiB
# chunks (1.3 M Python-loop iterations for a 10 GB file). 1 MiB cuts that to
# ~10 K, freeing the event loop and feeding the inline hasher (B1) efficiently.
_DOWNLOAD_CHUNK = 1024 * 1024


@dataclass
class TaskStatus:
    taskId: str
    type: str
    fullname: str
    preview: str | None
    status: Literal["pause", "waiting", "doing"] = "pause"
    platform: str | None = None
    downloadedSize: float = 0
    totalSize: float = 0
    progress: float = 0
    bps: float = 0
    error: str | None = None
    source: str = "remote"

    def __init__(self, **kwargs: Any):
        self.taskId = kwargs.get("taskId") or ""
        self.type = kwargs.get("type") or ""
        self.fullname = kwargs.get("fullname") or ""
        self.preview = kwargs.get("preview")
        self.status = kwargs.get("status", "pause")
        self.platform = kwargs.get("platform")
        self.downloadedSize = kwargs.get("downloadedSize", 0)
        self.totalSize = kwargs.get("totalSize", 0)
        self.progress = kwargs.get("progress", 0)
        self.bps = kwargs.get("bps", 0)
        self.error = kwargs.get("error")
        self.source = kwargs.get("source", "remote")

    def to_dict(self):
        return {
            "taskId": self.taskId,
            "type": self.type,
            "fullname": self.fullname,
            "preview": self.preview,
            "status": self.status,
            "platform": self.platform,
            "downloadedSize": self.downloadedSize,
            "totalSize": self.totalSize,
            "progress": self.progress,
            "bps": self.bps,
            "error": self.error,
            "source": self.source,
        }


@dataclass
class TaskContent:
    type: str
    pathIndex: int
    fullname: str
    description: str
    downloadPlatform: str
    downloadUrl: str | None
    sizeBytes: float
    hashes: dict[str, str] | None = None
    revision: str | None = None
    source: str = "remote"
    subFolder: str | None = None
    msRepoId: str | None = None
    msFilePath: str | None = None

    def __init__(self, **kwargs: Any):
        self.type = kwargs.get("type") or ""
        self.pathIndex = int(kwargs.get("pathIndex", 0))
        self.fullname = kwargs.get("fullname") or ""
        self.description = kwargs.get("description") or ""
        self.downloadPlatform = kwargs.get("downloadPlatform") or ""
        self.downloadUrl = kwargs.get("downloadUrl")
        self.sizeBytes = float(kwargs.get("sizeBytes", 0))
        self.hashes = kwargs.get("hashes")
        self.revision = kwargs.get("revision")
        self.source = kwargs.get("source", "remote")
        self.subFolder = kwargs.get("subFolder")
        self.msRepoId = kwargs.get("msRepoId")
        self.msFilePath = kwargs.get("msFilePath")
        # The client submits multipart FormData, so nested objects arrive as
        # JSON *strings*; normalise `hashes` back to a dict once, here, so
        # every consumer (ModelScope sha verification, ...) can rely on it.
        hashes = self.hashes
        if isinstance(hashes, str):
            import json as _json

            try:
                hashes = _json.loads(hashes)
            except Exception:
                hashes = None
        self.hashes = hashes if isinstance(hashes, dict) else None

    def to_dict(self):
        return {
            "type": self.type,
            "pathIndex": self.pathIndex,
            "fullname": self.fullname,
            "description": self.description,
            "downloadPlatform": self.downloadPlatform,
            "downloadUrl": self.downloadUrl,
            "sizeBytes": self.sizeBytes,
            "hashes": self.hashes,
            "revision": self.revision,
            "source": self.source,
            "subFolder": self.subFolder,
            "msRepoId": self.msRepoId,
            "msFilePath": self.msFilePath,
        }


def _seed_hasher_from_file(mm, handle: int, path: str) -> bool:
    """Feed an already-downloaded partial file to an incremental hasher.

    BUG FIX (Phase 5 audit): this read used to run directly ON the event loop
    inside `download_model_file_http`. A resumed download can be tens of
    gigabytes and the "it is page-cached anyway" assumption only holds while
    the same process wrote it moments ago - after a ComfyUI restart the cache is
    cold, so resuming a 10 GB task froze every websocket and request for the
    whole disk read. It now runs in the io executor like every other blocking
    step of the download path.

    Returns False when the file cannot be read; the caller then drops the
    hasher and `_download_complete` verifies by re-reading (correctness is
    unchanged, only the extra I/O returns for that one task).
    """
    try:
        with open(path, "rb") as pf:
            for block in iter(lambda: pf.read(_DOWNLOAD_CHUNK), b""):
                mm.hasher_update(handle, block)
        return True
    except Exception as e:
        utils.print_warning(f"inline hasher seeding failed ({e}); will re-read to verify")
        return False


def _drop_hasher(mm, handle: int) -> None:
    """Release a hasher handle that will not be finalised (best effort).

    Keeps the native registry tidy when inline hashing is abandoned mid-task
    (a failed seed, a lost handle); `hasher_finalize` removes the entry.
    """
    try:
        mm.hasher_finalize(handle)
    except Exception:
        pass


def _sha256_of(path: str) -> str | None:
    """Lower-case hex SHA256 of a file (None when it vanished)."""
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_task_id(task_id: str) -> bool:
    """Reject route parameters that are not plain task ids.

    ``{task_id}`` is a single URL segment, but percent-encoding lets a client
    smuggle separators (``%2F``, ``%2E%2E``) through the router; the value is
    joined onto the downloads directory (``<id>.task`` / ``<id>.download``), so
    anything but a separator-free name would escape it. Legitimate ids are
    ``uuid4().hex``; the check is a whitelist, not a blacklist.
    """
    return bool(task_id) and all(ch.isalnum() for ch in task_id)


class ModelDownload:
    def __init__(self):
        self.api_key = auth.get_api_key()
        # Inline Civitai verification (Plan §4.8-B1 / K7): the download write
        # loop feeds a native hasher as bytes land, so a finished download's
        # SHA256 is known WITHOUT the extra full re-read `_sha256_of` did. The
        # digest is staged here (keyed by task) for `_download_complete` to
        # consume; absent (legacy path, paused, or a resumed-complete file) it
        # falls back to the re-read.
        self._inline_sha256: dict[str, str] = {}

    def add_routes(self, routes):
        @routes.post("/model-manager/download/init")
        async def init_download(request):
            result = self.api_key.init(request)
            return web.json_response({"success": True, "data": result})

        @routes.post("/model-manager/download/setting")
        async def set_download_setting(request):
            json_data = await request.json()
            key = json_data.get("key", None)
            value = json_data.get("value", None)
            value = base64.b64decode(value).decode("utf-8") if value is not None else None
            self.api_key.set_value(key, value)
            return web.json_response({"success": True})

        @routes.get("/model-manager/download/task")
        async def scan_download_tasks(request):
            try:
                result = await self.scan_model_download_task_list()
                return web.json_response({"success": True, "data": result})
            except Exception as e:
                error_msg = f"Read download task list failed: {e}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.put("/model-manager/download/{task_id}")
        async def resume_download_task(request):
            task_id = request.match_info.get("task_id", None)
            if task_id is None or not _is_task_id(task_id):
                raise web.HTTPBadRequest(reason="Invalid task id")
            try:
                json_data = await request.json()
                status = json_data.get("status", None)

                if status == "pause":
                    await self.pause_model_download_task(task_id)
                elif status == "resume":
                    await self.download_model(task_id, request)
                else:
                    raise web.HTTPBadRequest(reason="Invalid status")

                return web.json_response({"success": True})
            except Exception as e:
                error_msg = f"Resume download task failed: {e!s}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.delete("/model-manager/download/{task_id}")
        async def delete_model_download_task(request):
            task_id = request.match_info.get("task_id", None)
            if task_id is None or not _is_task_id(task_id):
                raise web.HTTPBadRequest(reason="Invalid task id")
            try:
                await self.delete_model_download_task(task_id)
                return web.json_response({"success": True})
            except Exception as e:
                error_msg = f"Delete download task failed: {e!s}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.post("/model-manager/model")
        async def create_model(request):
            task_data = await request.post()
            task_data = dict(task_data)
            try:
                task_id = await self.create_model_download_task(task_data, request)
                return web.json_response({"success": True, "data": {"taskId": task_id}})
            except Exception as e:
                error_msg = f"Create model download task failed: {e!s}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

    # Deliberately class-level: py/upload.py registers local upload tasks
    # into the SAME status table and thread pool through the singleton.
    download_model_task_status: ClassVar[dict[str, TaskStatus]] = {}

    download_thread_pool: ClassVar[thread.DownloadThreadPool] = thread.DownloadThreadPool()

    def set_task_content(self, task_id: str, task_content: TaskContent | dict):
        download_path = utils.get_download_path()
        task_file_path = utils.join_path(download_path, f"{task_id}.task")
        utils.save_dict_pickle_file(task_file_path, task_content)

    def get_task_content(self, task_id: str):
        download_path = utils.get_download_path()
        task_file = utils.join_path(download_path, f"{task_id}.task")
        if not os.path.isfile(task_file):
            raise RuntimeError(f"Task {task_id} not found")
        task_content = utils.load_dict_pickle_file(task_file)
        if isinstance(task_content, TaskContent):
            return task_content
        return TaskContent(**task_content)

    def get_task_status(self, task_id: str):
        task_status = self.download_model_task_status.get(task_id, None)

        if task_status is None:
            download_path = utils.get_download_path()
            task_content = self.get_task_content(task_id)
            download_file = utils.join_path(download_path, f"{task_id}.download")
            download_size = 0
            if os.path.exists(download_file):
                download_size = os.path.getsize(download_file)

            total_size = task_content.sizeBytes
            task_status = TaskStatus(
                taskId=task_id,
                type=task_content.type,
                fullname=task_content.fullname,
                preview=utils.get_model_preview_name(download_file),
                platform=task_content.downloadPlatform,
                downloadedSize=download_size,
                totalSize=task_content.sizeBytes,
                progress=download_size / total_size * 100 if total_size > 0 else 0,
                source=task_content.source,
            )

            self.download_model_task_status[task_id] = task_status

        return task_status

    def delete_task_status(self, task_id: str):
        self.download_model_task_status.pop(task_id, None)

    async def scan_model_download_task_list(self):
        download_dir = utils.get_download_path()
        task_files = utils.search_files(download_dir)
        task_files = folder_paths.filter_files_extensions(task_files, [".task"])
        task_files = sorted(
            task_files,
            key=lambda x: os.stat(utils.join_path(download_dir, x)).st_ctime,
            reverse=True,
        )
        task_list: list[dict] = []
        for task_file in task_files:
            task_id = task_file.replace(".task", "")
            task_status = self.get_task_status(task_id)
            task_list.append(task_status.to_dict())

        return task_list

    async def create_model_download_task(self, task_data: dict, request):
        model_type = task_data.get("type")
        # `int(None)` raised TypeError instead of the intended validation
        # error when a client omitted pathIndex. Defaulting to 0 would silently
        # file such a download into the wrong folder, so reject it explicitly.
        raw_index = task_data.get("pathIndex")
        if raw_index is None:
            raise RuntimeError("pathIndex is required")
        path_index = int(raw_index)
        fullname = task_data.get("fullname")
        sub_folder = task_data.get("subFolder")
        if model_type is None or fullname is None:
            raise RuntimeError("type and fullname are required")

        # The chosen sub-folder becomes part of the task's fullname.
        if sub_folder:
            fullname = utils.join_path(sub_folder, fullname)
            # BUG FIX: the joined fullname must be written back into task_data
            # before it is persisted. Otherwise TaskContent.fullname stayed the
            # bare file name and `_download_complete` moved the finished file to
            # the model-type ROOT instead of the chosen sub-folder.
            task_data["fullname"] = fullname

        model_path = utils.get_full_path(model_type, path_index, fullname)
        if os.path.exists(model_path):
            raise RuntimeError(f"File already exists: {model_path}")
        # Pre-download free-space guard: refuse a task whose announced size
        # cannot possibly fit on the target volume (the frontend also warns,
        # but the backend is the ground truth).
        import shutil

        needed = float(task_data.get("sizeBytes", 0) or 0)
        if needed > 0:
            # The target sub-folder may not exist yet (it is created on
            # completion), so measure the nearest existing ancestor volume.
            check_dir = os.path.dirname(model_path)
            while not os.path.isdir(check_dir):
                parent = os.path.dirname(check_dir)
                if parent == check_dir:
                    break
                check_dir = parent
            free = shutil.disk_usage(check_dir).free
            if needed > free:
                raise RuntimeError(
                    f"Not enough free disk space: the file needs "
                    f"{needed / 2**30:.2f} GiB but only {free / 2**30:.2f} GiB "
                    f"are free on the target volume"
                )
        # ZipNN bundle folders (*_ZNN) must never receive a non-compressed
        # model file (checked at task creation so the task never even starts).
        utils.enforce_znn_folder_rule(model_path)

        download_path = utils.get_download_path()

        task_id = uuid.uuid4().hex
        task_path = utils.join_path(download_path, f"{task_id}.task")
        if os.path.exists(task_path):
            raise RuntimeError(f"Task {task_id} already exists")
        download_platform = task_data.get("downloadPlatform")

        try:
            # The gallery arrives as previewFile / previewFile2 / ... in order.
            preview_items = []
            for key in list(task_data):
                if key == "previewFile" or (key.startswith("previewFile") and key[len("previewFile") :].isdigit()):
                    order = 0 if key == "previewFile" else int(key[len("previewFile") :])
                    preview_items.append((order, task_data.pop(key)))
            preview_items = [v for _, v in sorted(preview_items)]
            preview_items = [v for v in preview_items if not (type(v) is str and v in ("", "undefined"))]
            if preview_items:
                await utils.save_model_previews(task_path, preview_items, download_platform)
            self.set_task_content(task_id, task_data)
            task_status = TaskStatus(
                taskId=task_id,
                type=model_type,
                fullname=fullname,
                preview=utils.get_model_preview_name(task_path),
                platform=download_platform,
                totalSize=float(task_data.get("sizeBytes", 0)),
            )
            self.download_model_task_status[task_id] = task_status
            await utils.send_json("create_download_task", task_status.to_dict())
        except Exception as e:
            await self.delete_model_download_task(task_id)
            raise RuntimeError(str(e)) from e

        await self.download_model(task_id, request)
        return task_id

    async def pause_model_download_task(self, task_id: str):
        task_status = self.get_task_status(task_id=task_id)
        task_status.status = "pause"
        self.download_thread_pool.cancel(task_id)
        # BUG FIX: cancelling the task raises CancelledError at the download
        # coroutine's next await, so it never reaches its own "paused" push at
        # the end of the read loop. The Download List therefore kept showing the
        # pause button and a live speed read-out for a task that had already
        # stopped - the resume button only appeared after a manual refresh (or
        # a websocket reconnect, which re-fetches the task list). Report the new
        # state here; the push is idempotent if the coroutine ever does send its
        # own.
        await utils.send_json("update_download_task", task_status.to_dict())

    async def delete_model_download_task(self, task_id: str):
        task_status = self.get_task_status(task_id)
        is_running = task_status.status == "doing"
        task_status.status = "waiting"
        await utils.send_json("delete_download_task", task_id)

        self.download_thread_pool.cancel(task_id)
        if is_running:
            task_status.status = "pause"
            await asyncio.sleep(1)

        download_dir = utils.get_download_path()
        task_file_list = os.listdir(download_dir)
        for task_file in task_file_list:
            task_file_target = os.path.splitext(task_file)[0]
            if task_file_target == task_id:
                self.delete_task_status(task_id)
                os.remove(utils.join_path(download_dir, task_file))

        # The hub working directories (`<task_id>_hf` / `<task_id>_ms`) carry
        # no dotted extension, so the scan above never matches them. Remove
        # them explicitly: an already-abandoned hub transfer thread (cancelling
        # a task cannot kill its executor thread) then fails fast on its next
        # write instead of quietly leaving orphaned partial files behind.
        for hub_suffix in ("_hf", "_ms"):
            hub_dir = utils.join_path(download_dir, f"{task_id}{hub_suffix}")
            if os.path.isdir(hub_dir):
                shutil.rmtree(hub_dir, ignore_errors=True)

        await utils.send_json("delete_download_task", task_id)

    async def download_model(self, task_id: str, request):
        async def download_task(task_id: str):
            async def report_progress(task_status: TaskStatus):
                await utils.send_json("update_download_task", task_status.to_dict())

            try:
                task_status = self.get_task_status(task_id)
            except Exception:
                return

            task_status.status = "doing"
            await utils.send_json("update_download_task", task_status.to_dict())

            try:
                headers = {"User-Agent": config.user_agent}

                download_platform = task_status.platform
                if download_platform == "civitai":
                    api_key = auth.get_civitai_token()
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"

                elif download_platform == "huggingface":
                    api_key = auth.get_hf_token()
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"

                progress_interval = 1.0

                if download_platform == "modelscope":
                    await self.download_model_file_modelscope(
                        task_id=task_id,
                        progress_callback=report_progress,
                        interval=progress_interval,
                    )
                elif download_platform == "huggingface":
                    await self.download_model_file_hf(
                        task_id=task_id,
                        progress_callback=report_progress,
                        interval=progress_interval,
                    )
                else:
                    await self.download_model_file_http(
                        task_id=task_id,
                        headers=headers,
                        progress_callback=report_progress,
                        interval=progress_interval,
                    )
            except Exception as e:
                task_status = self.get_task_status(task_id)
                task_status.status = "pause"
                task_status.error = str(e)
                await utils.send_json("update_download_task", task_status.to_dict())
                task_status.error = None
                utils.print_error(str(e))

        try:
            # submit() starts the transfer as a task on the running loop and
            # dedupes by task id ("Existing" while one is already alive).
            self.download_thread_pool.submit(download_task(task_id), task_id)
        except Exception as e:
            task_status = self.get_task_status(task_id)
            task_status.status = "pause"
            task_status.error = str(e)
            await utils.send_json("update_download_task", task_status.to_dict())
            task_status.error = None
            utils.print_error(str(e))

    async def _download_complete(self, task_id: str):
        task_content = self.get_task_content(task_id)
        download_path = utils.get_download_path()

        model_type = task_content.type
        path_index = task_content.pathIndex
        fullname = task_content.fullname

        # BUG FIX: TaskContent.description defaults to None when the client
        # omits the field, and `f.write(None)` raised TypeError inside the
        # completion step - after the model had already been downloaded, so the
        # file stayed in downloads/ as `<task>.download` and the task never
        # completed. An absent description is simply an empty notes file.
        description = task_content.description or ""
        description_file = utils.join_path(download_path, f"{task_id}.md")
        with open(description_file, "w", encoding="utf-8", newline="") as f:
            f.write(description)

        download_tmp_file = utils.join_path(download_path, f"{task_id}.download")
        model_path = utils.get_full_path(model_type, path_index, fullname)

        # Civitai integrity gate: verify the downloaded bytes against the
        # SHA256 the model page published (recorded in the task hashes at
        # resolve time) BEFORE the file enters the library - the same default
        # the official civitai CLI applies. A mismatch deletes the partial
        # file and fails the task, so a corrupted or tampered transfer can
        # never masquerade as a finished download.
        expected_sha = (task_content.hashes or {}).get("SHA256")
        if task_content.downloadPlatform == "civitai" and expected_sha:
            # B1 (Plan §4.8 / K7): prefer the INLINE digest the write loop fed
            # the native hasher — verifying costs ZERO extra I/O. Fall back to
            # the full re-read only when no inline digest was staged (no
            # native core on this machine, a file that was already complete on
            # resume, or a task whose hasher was dropped on pause).
            actual_sha = self._inline_sha256.pop(task_id, None)
            if actual_sha is None:
                loop = asyncio.get_running_loop()
                actual_sha = await loop.run_in_executor(utils.cpu_executor(), _sha256_of, download_tmp_file)
            if actual_sha and actual_sha.casefold() != str(expected_sha).casefold():
                if os.path.isfile(download_tmp_file):
                    os.remove(download_tmp_file)
                raise RuntimeError(
                    f"SHA256 mismatch for {fullname}: the page published "
                    f"{expected_sha} but the downloaded bytes hash to "
                    f"{actual_sha}. The file was deleted - re-download or "
                    "check the source."
                )

        utils.rename_model(download_tmp_file, model_path)

        await asyncio.sleep(1)
        task_file = utils.join_path(download_path, f"{task_id}.task")
        if os.path.exists(task_file):
            os.remove(task_file)
        # `complete_download_task` is itself a ws BROADCAST and the client
        # handler already re-scans the landing type on every client (Plan
        # §4.7.2-1's "download complete" trigger is satisfied by it), so no
        # separate `models_changed` is needed here — that would double-scan.
        await utils.send_json("complete_download_task", task_id)

    async def download_model_file_http(
        self,
        task_id: str,
        headers: dict,
        progress_callback: Callable[[TaskStatus], Coroutine[Any, Any, Any]],
        interval: float = 1.0,
    ) -> None:
        """Stream a download to `<task>.download` with aiohttp.

        The transfer used to run
        a *blocking* `requests` stream inside a worker thread, which is why the
        code needed pause-polling, thread-marshalled progress pushes and the
        "close the response inside the thread" workaround. On the event loop
        all of that becomes ordinary `await` points:

        - pause is observed between chunks and simply stops the iterator;
        - cancellation (task delete) closes the session through `async with`;
        - progress is pushed directly, throttled to `interval` seconds;
        - resume still works through the `Range` header and the partial file.

        Behaviour, error strings and the completion rules are unchanged;
        resume, pause, delete and the sub-folder landing all keep working
        through the same `await` points.
        """

        async def push_progress(bps: float) -> None:
            task_status.downloadedSize = downloaded_size
            task_status.progress = (downloaded_size / total_size) * 100 if total_size > 0 else 0
            task_status.bps = bps
            await progress_callback(task_status)

        task_status = self.get_task_status(task_id)
        task_content = self.get_task_content(task_id)

        # Inline Civitai verification (Plan §4.8-B1 / K7): when the native core
        # is available and this is a Civitai download with a published SHA256, a
        # streaming hasher consumes each written chunk, so the finished file's
        # digest is known WITHOUT the extra full re-read `_sha256_of` did. The
        # hasher is (re)created per attempt below, once the resume/reset state
        # is settled (a 206 resume seeds it from the partial file — page-cached,
        # cheap; a 200 reset starts it fresh).
        mm = native.core_if_enabled()
        expected_sha = (task_content.hashes or {}).get("SHA256")
        use_inline_hash = bool(mm is not None and task_content.downloadPlatform == "civitai" and expected_sha)
        # Drop any digest staged by a previous attempt of this task so the
        # early-complete path below can never verify against a stale value (it
        # falls back to the re-read instead).
        self._inline_sha256.pop(task_id, None)

        model_url = task_content.downloadUrl
        if not model_url:
            raise RuntimeError("No downloadUrl found")

        loop = asyncio.get_running_loop()

        download_path = utils.get_download_path()
        download_tmp_file = utils.join_path(download_path, f"{task_id}.download")

        downloaded_size = 0
        if os.path.isfile(download_tmp_file):
            downloaded_size = os.path.getsize(download_tmp_file)
            headers = {**headers, "Range": f"bytes={downloaded_size}-"}

        total_size = task_content.sizeBytes

        if total_size > 0 and downloaded_size == total_size:
            await self._download_complete(task_id)
            return

        # A host that accepts the connection but never answers must not hang
        # the task forever; the read timeout only applies between chunks.
        timeout = aiohttp.ClientTimeout(connect=30, sock_read=600, total=None)

        last_update_time = time.time()
        last_downloaded_size = downloaded_size

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # One extra attempt when resuming: a 416 (the partial file no
            # longer matches the remote object, e.g. it was replaced upstream)
            # discards the partial and re-requests the full body instead of
            # failing the task outright.
            attempts = 2 if downloaded_size > 0 else 1
            for attempt in range(attempts):
                async with session.get(model_url, headers=headers, allow_redirects=True) as response:
                    if response.status == 416 and attempt + 1 < attempts:
                        utils.print_warning(
                            f"Resume range rejected (416) for {task_content.fullname}; "
                            "discarding the partial file and restarting from zero"
                        )
                        downloaded_size = 0
                        last_downloaded_size = 0
                        headers = {k: v for k, v in headers.items() if k.lower() != "range"}
                        try:
                            os.remove(download_tmp_file)
                        except OSError:
                            pass
                        continue

                    if response.status not in (200, 206):
                        if response.status == 401 and task_content.downloadPlatform == "civitai":
                            # Scope-aware guidance: gated Civitai files answer 401
                            # without a token - say exactly where to get one and
                            # how to retry instead of a bare status code.
                            raise RuntimeError(
                                f"Civitai rejected the download of {task_content.fullname} "
                                "(401 Unauthorized): this file requires authentication. "
                                "Create an API key at https://civitai.com/user/account, "
                                "store it in Settings > Model Manager Neo > API Key > "
                                "Civitai, then resume this task."
                            )
                        raise RuntimeError(
                            f"Failed to download {task_content.fullname}, status code: {response.status}"
                        )

                    content_type = response.headers.get("content-type")
                    if content_type and content_type.startswith("text/html"):
                        raise RuntimeError(
                            f"{task_content.fullname} needs to be logged in to download. Please set the API-Key first."
                        )

                    response_total_size = float(response.headers.get("content-length", 0) or 0)

                    if response.status == 206:
                        actual_total = response_total_size + downloaded_size
                        if total_size == 0 or total_size != actual_total:
                            total_size = actual_total
                            task_content.sizeBytes = total_size
                            task_status.totalSize = total_size
                            self.set_task_content(task_id, task_content)
                            await utils.send_json("update_download_task", task_status.to_dict())
                        open_mode = "ab"
                    else:
                        # A 200 answer carries the WHOLE file: the server did
                        # not honour the Range request (or there was nothing
                        # to resume). Appending the full body after an old
                        # partial would corrupt the model beyond repair, so
                        # any stale partial is discarded and the file is
                        # written from zero.
                        downloaded_size = 0
                        last_downloaded_size = 0
                        open_mode = "wb"
                        if total_size == 0 or total_size != response_total_size:
                            total_size = response_total_size
                            task_content.sizeBytes = total_size
                            task_status.totalSize = total_size
                            self.set_task_content(task_id, task_content)
                            await utils.send_json("update_download_task", task_status.to_dict())

                    # (Re)create the inline hasher now that downloaded_size and
                    # open_mode are settled. A 206 resume seeds it with the
                    # existing partial file (just written → page-cached, so the
                    # re-read is memory-speed, not disk); a 200 reset starts it
                    # fresh (downloaded_size == 0).
                    hasher = None
                    if use_inline_hash and mm is not None:
                        hasher = mm.hasher_new(["SHA256"])
                        if downloaded_size > 0 and os.path.isfile(download_tmp_file):
                            seeded = await loop.run_in_executor(
                                utils.io_executor(),
                                _seed_hasher_from_file,
                                mm,
                                hasher,
                                download_tmp_file,
                            )
                            if not seeded:
                                _drop_hasher(mm, hasher)
                                hasher = None

                    with open(download_tmp_file, open_mode) as f:
                        async for chunk in response.content.iter_chunked(_DOWNLOAD_CHUNK):
                            # Cooperative pause, checked exactly as before.
                            if task_status.status == "pause":
                                break

                            f.write(chunk)
                            if hasher is not None and mm is not None:
                                # Zero-copy: the chunk is borrowed at the PyO3
                                # boundary, never copied into Rust. A lost
                                # handle (the native registry evicts past its
                                # cap) must NOT fail a download whose bytes are
                                # perfectly fine - drop inline verification and
                                # let `_download_complete` re-read instead.
                                try:
                                    mm.hasher_update(hasher, chunk)
                                except Exception as e:
                                    utils.print_warning(f"inline hasher update failed ({e}); will re-read to verify")
                                    hasher = None
                            downloaded_size += len(chunk)

                            if time.time() - last_update_time >= interval:
                                await push_progress(downloaded_size - last_downloaded_size)
                                last_update_time = time.time()
                                last_downloaded_size = downloaded_size

                    await push_progress(downloaded_size - last_downloaded_size)

                    # Settle the inline hasher: a COMPLETE download stages its
                    # digest for `_download_complete` (verifying then costs zero
                    # extra I/O — K7); a paused/incomplete one drops it (the
                    # resume re-seeds from the partial file). A finalize failure
                    # degrades to the re-read fallback in `_download_complete`.
                    if hasher is not None and mm is not None:
                        if total_size > 0 and downloaded_size == total_size:
                            try:
                                digest = json.loads(mm.hasher_finalize(hasher)).get("SHA256")
                                if digest:
                                    self._inline_sha256[task_id] = digest
                            except Exception as e:  # fall back to the re-read
                                utils.print_warning(f"inline hasher finalize failed ({e}); will re-read to verify")
                        else:
                            try:
                                mm.hasher_finalize(hasher)  # drop it from the registry
                            except Exception:  # best-effort cleanup
                                pass
                break

        if total_size > 0 and downloaded_size == total_size:
            await self._download_complete(task_id)
        else:
            task_status.status = "pause"
            await utils.send_json("update_download_task", task_status.to_dict())

    async def _hub_transfer(
        self,
        task_id: str,
        progress_callback: Callable[[TaskStatus], Coroutine[Any, Any, Any]],
        interval: float,
        fetch: Callable[[Callable[..., None]], tuple],
    ) -> None:
        """Shared transfer plumbing for the hub backends (HF / ModelScope).

        ``fetch(report)`` runs on the io executor and returns
        ``(downloaded_path, cleanup_or_None)``; ``report(sent, total, bps)``
        marshals throttled progress pushes onto the main loop. Completion
        (move onto ``<task>.download`` + the shared completion path) is
        identical for every backend - the hubs only differ in *how* they
        fetch, which stays inside their ``fetch`` closure.
        """
        loop = asyncio.get_running_loop()
        task_status = self.get_task_status(task_id)
        task_content = self.get_task_content(task_id)
        total_size = task_content.sizeBytes
        state = {"last": 0.0, "peak": 0.0}

        async def _push(sent: float, total: float, bps: float) -> None:
            task_status.downloadedSize = sent
            if total:
                task_status.totalSize = total
                # Transfers can legitimately move a few bytes more than the
                # announced size (retries, xet re-fetches): cap the bar at
                # 100% instead of letting it overshoot.
                task_status.progress = min(100.0, sent / total * 100)
            task_status.bps = bps
            await progress_callback(task_status)

        def report(sent: float, total: float, bps: float = 0.0) -> None:
            # Progress must never go backwards. A hub transfer can be fed by
            # several interleaved sources at once - xet-backed Hugging Face
            # downloads drive TWO tqdm bars (network transfer + on-disk
            # reconstruction) through the same callback, and the disk poller
            # observes buffered flushes - and a lagging source would otherwise
            # yank the bar back down (the "progress jumps around / one task
            # sits at 0" defect when downloads run in parallel). A sample
            # below the running peak is a stale reading: drop it whole, its
            # speed estimate included.
            if sent < state["peak"]:
                return
            state["peak"] = sent
            # The size resolved at task creation is the authoritative total;
            # bar-reported totals can be dynamically inflated display values
            # (the xet transfer bar grows its own total past the file size)
            # and must not rewrite the task's real size.
            effective_total = total_size if total_size > 0 else total
            now = time.time()
            if now - state["last"] < interval:
                return
            state["last"] = now
            asyncio.run_coroutine_threadsafe(_push(sent, effective_total, bps), loop)

        path, cleanup = await loop.run_in_executor(utils.io_executor(), fetch, report)
        try:
            download_path = utils.get_download_path()
            tmp = utils.join_path(download_path, f"{task_id}.download")
            if os.path.exists(tmp):
                os.remove(tmp)
            shutil.move(str(path), tmp)
        finally:
            if cleanup:
                cleanup()
        task_status.progress = 100.0
        task_status.bps = 0.0
        if task_status.totalSize:
            # The transfer is over: report the full size instead of leaving
            # the last reconstruction-lagged sample next to a 100% bar.
            task_status.downloadedSize = task_status.totalSize
        await progress_callback(task_status)
        await self._download_complete(task_id)

    async def download_model_file_hf(
        self,
        task_id: str,
        progress_callback: Callable[[TaskStatus], Coroutine[Any, Any, Any]],
        interval: float = 1.0,
    ):
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise RuntimeError(
                "huggingface_hub is not installed. Please install it with: pip install huggingface_hub hf_xet"
            ) from exc

        try:
            from tqdm.auto import tqdm as base_tqdm
        except ImportError:
            base_tqdm = None

        task_content = self.get_task_content(task_id)

        model_url = task_content.downloadUrl
        if not model_url:
            raise RuntimeError("No downloadUrl found")

        parsed = urlparse(model_url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]

        fallback_headers = {"User-Agent": config.user_agent}
        token = auth.get_hf_token()
        if token:
            fallback_headers["Authorization"] = f"Bearer {token}"

        if len(path_parts) < 3:
            utils.print_warning(f"HF URL format unexpected, falling back to HTTP: {model_url}")
            await self.download_model_file_http(task_id, fallback_headers, progress_callback, interval)
            return

        space = path_parts[0]
        name = path_parts[1]
        repo_id = f"{space}/{name}"

        revision = getattr(task_content, "revision", None) or "main"
        filename = ""

        try:
            resolve_idx = path_parts.index("resolve")
            if resolve_idx + 1 < len(path_parts):
                revision = path_parts[resolve_idx + 1]
                if resolve_idx + 2 < len(path_parts):
                    filename = "/".join(path_parts[resolve_idx + 2 :])
        except (ValueError, IndexError):
            if len(path_parts) > 2:
                filename = "/".join(path_parts[2:])
            if not filename:
                utils.print_warning(f"Could not parse HF filename, falling back to HTTP: {model_url}")
                await self.download_model_file_http(task_id, fallback_headers, progress_callback, interval)
                return

        download_path = utils.get_download_path()
        task_hf_dir = utils.join_path(download_path, f"{task_id}_hf")
        os.makedirs(task_hf_dir, exist_ok=True)

        def fetch(report):
            expected_total = float(task_content.sizeBytes or 0)

            class ModelManagerTqdm(base_tqdm if base_tqdm else object):  # type: ignore[misc]
                """Counting tqdm shim: feeds the task reporter, prints nothing.

                huggingface_hub instantiates ``tqdm_class`` for its console
                bars. The bars are suppressed (the UI has its own progress
                row) but the accounting stays enabled - a disabled tqdm skips
                ``update()`` entirely, which is why ``disable`` is forced off
                while ``display``/``refresh`` render nothing.
                """

                def __init__(self, *args, **kwargs):
                    kwargs.pop("name", None)
                    kwargs["disable"] = False
                    if base_tqdm:
                        super().__init__(*args, **kwargs)

                def display(self, *args, **kwargs):
                    pass

                def refresh(self, *args, **kwargs):
                    pass

                def update(self, n=1):
                    if base_tqdm:
                        super().update(n)
                    try:
                        rate = self.format_dict.get("rate") if base_tqdm else None
                        report(
                            float(self.n),
                            float(self.total or 0),
                            float(rate) if rate else 0.0,
                        )
                    except Exception:
                        pass

            # Version-independent progress source. The tqdm hook above only
            # works when huggingface_hub routes the transfer through its own
            # bars: on xet-backed files (hf_xet, the default transport) older
            # releases bypass `tqdm_class` entirely - the task then sat at 0%
            # until it jumped to 100% - and current ones create TWO bars
            # (network transfer + on-disk reconstruction) whose interleaved
            # readings made progress bounce. Whatever the internal transport
            # is, the partial file always lands as `*.incomplete` under the
            # task-local `local_dir`, so polling its size reports honest,
            # monotonic progress on every release. The shared reporter in
            # _hub_transfer merges this with any tqdm readings, keeping the
            # highest watermark.
            stop = threading.Event()

            def _incomplete_bytes() -> float:
                total = 0.0
                for root, _dirs, files in os.walk(task_hf_dir):
                    for name in files:
                        if name.endswith(".incomplete"):
                            try:
                                total += os.path.getsize(os.path.join(root, name))
                            except OSError:
                                pass
                return total

            def _poll() -> None:
                last = _incomplete_bytes()
                last_at = time.time()
                while not stop.wait(0.5):
                    size = _incomplete_bytes()
                    now = time.time()
                    dt = now - last_at
                    bps = (size - last) / dt if dt > 0 and size >= last else 0.0
                    last, last_at = size, now
                    if size > 0:
                        report(size, expected_total, bps)

            poller = threading.Thread(target=_poll, daemon=True, name=f"mm-hf-progress-{task_id[:8]}")
            poller.start()
            try:
                result_path = hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    token=token,
                    local_dir=task_hf_dir,
                    force_download=False,
                    tqdm_class=ModelManagerTqdm if base_tqdm else None,
                    user_agent=config.user_agent,
                )
                return result_path, lambda: shutil.rmtree(task_hf_dir, ignore_errors=True)
            finally:
                stop.set()
                poller.join(timeout=2.0)

        await self._hub_transfer(task_id, progress_callback, interval, fetch)

    async def download_model_file_modelscope(
        self,
        task_id: str,
        progress_callback: Callable[[TaskStatus], Coroutine[Any, Any, Any]],
        interval: float = 1.0,
    ) -> None:
        """Download through modelscope_hub (international endpoint).

        Only the fetch differs from the Hugging Face path: a ProgressCallback
        subclass feeds the shared reporter, and the finished file is handed
        to the shared completion plumbing unchanged.
        """
        from modelscope_hub import HubApi, ProgressCallback

        from .information import MODELSCOPE_INTL_ENDPOINT

        task_content = self.get_task_content(task_id)
        repo_id = task_content.msRepoId
        file_path = task_content.msFilePath
        if not repo_id or not file_path:
            raise RuntimeError("Missing ModelScope repository/file information")
        sha = (task_content.hashes or {}).get("SHA256") or None
        if not isinstance(sha, str):
            sha = None
        file_size = float(task_content.sizeBytes or 0)

        download_path = utils.get_download_path()
        tmp_dir = utils.join_path(download_path, f"{task_id}_ms")
        os.makedirs(tmp_dir, exist_ok=True)
        token = auth.get_modelscope_token()

        def fetch(report):
            acc = {"done": 0.0, "last_done": 0.0, "last_at": time.time(), "bps": 0.0}

            class _Cb(ProgressCallback):
                def update(self, size: int) -> None:
                    acc["done"] += size
                    # modelscope_hub reports chunk sizes only; derive the
                    # transfer speed here (smoothed) so the task row can show
                    # a live speed read-out like the other backends do.
                    now = time.time()
                    dt = now - acc["last_at"]
                    if dt >= 0.25:
                        instant = (acc["done"] - acc["last_done"]) / dt
                        acc["bps"] = 0.7 * acc["bps"] + 0.3 * instant if acc["bps"] else instant
                        acc["last_done"] = acc["done"]
                        acc["last_at"] = now
                    report(acc["done"], file_size, acc["bps"])

                def end(self) -> None:
                    report(acc["done"], file_size, acc["bps"])

            api = HubApi(endpoint=MODELSCOPE_INTL_ENDPOINT, token=token)
            path = api.downloader.download_file(
                repo_id,
                "model",
                file_path,
                local_dir=pathlib.Path(tmp_dir),
                expected_sha256=sha,
                progress_callbacks=[_Cb],
            )
            return path, lambda: shutil.rmtree(tmp_dir, ignore_errors=True)

        await self._hub_transfer(task_id, progress_callback, interval, fetch)


_model_download_instance = None


def get_model_download():
    """Get the global ModelDownload singleton instance."""
    global _model_download_instance
    if _model_download_instance is None:
        _model_download_instance = ModelDownload()
    return _model_download_instance
