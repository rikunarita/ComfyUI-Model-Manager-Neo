import asyncio
import base64
import functools
import hashlib
import os
import pathlib
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Literal, Optional, Union
from urllib.parse import urlparse

import aiohttp
import folder_paths
import requests
from aiohttp import web

from . import auth
from . import config
from . import thread
from . import utils

@dataclass
class TaskStatus:
    taskId: str
    type: str
    fullname: str
    preview: Optional[str]
    status: Literal["pause", "waiting", "doing"] = "pause"
    platform: Union[str, None] = None
    downloadedSize: float = 0
    totalSize: float = 0
    progress: float = 0
    bps: float = 0
    error: Optional[str] = None
    source: str = "remote"

    def __init__(self, **kwargs: Any):
        self.taskId = kwargs.get("taskId") or ""
        self.type = kwargs.get("type") or ""
        self.fullname = kwargs.get("fullname") or ""
        self.preview = kwargs.get("preview", None)
        self.status = kwargs.get("status", "pause")
        self.platform = kwargs.get("platform", None)
        self.downloadedSize = kwargs.get("downloadedSize", 0)
        self.totalSize = kwargs.get("totalSize", 0)
        self.progress = kwargs.get("progress", 0)
        self.bps = kwargs.get("bps", 0)
        self.error = kwargs.get("error", None)
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
    downloadUrl: Optional[str]
    sizeBytes: float
    hashes: Optional[dict[str, str]] = None
    revision: Optional[str] = None
    source: str = "remote"
    subFolder: Optional[str] = None
    msRepoId: Optional[str] = None
    msFilePath: Optional[str] = None

    def __init__(self, **kwargs: Any):
        self.type = kwargs.get("type") or ""
        self.pathIndex = int(kwargs.get("pathIndex", 0))
        self.fullname = kwargs.get("fullname") or ""
        self.description = kwargs.get("description") or ""
        self.downloadPlatform = kwargs.get("downloadPlatform") or ""
        self.downloadUrl = kwargs.get("downloadUrl", None)
        self.sizeBytes = float(kwargs.get("sizeBytes", 0))
        self.hashes = kwargs.get("hashes", None)
        self.revision = kwargs.get("revision", None)
        self.source = kwargs.get("source", "remote")
        self.subFolder = kwargs.get("subFolder", None)
        self.msRepoId = kwargs.get("msRepoId", None)
        self.msFilePath = kwargs.get("msFilePath", None)
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

def _sha256_of(path: str) -> str | None:
    """Lower-case hex SHA256 of a file (None when it vanished)."""
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ModelDownload:
    def __init__(self):
        self.api_key = auth.get_api_key()

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
            try:
                task_id = request.match_info.get("task_id", None)
                if task_id is None:
                    raise web.HTTPBadRequest(reason="Invalid task id")

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
                error_msg = f"Resume download task failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.delete("/model-manager/download/{task_id}")
        async def delete_model_download_task(request):
            task_id = request.match_info.get("task_id", None)
            try:
                await self.delete_model_download_task(task_id)
                return web.json_response({"success": True})
            except Exception as e:
                error_msg = f"Delete download task failed: {str(e)}"
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
                error_msg = f"Create model download task failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

    download_model_task_status: dict[str, TaskStatus] = {}

    download_thread_pool = thread.DownloadThreadPool()

    def set_task_content(self, task_id: str, task_content: Union[TaskContent, dict]):
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
        model_type = task_data.get("type", None)
        # `int(None)` raised TypeError instead of the intended validation
        # error when a client omitted pathIndex. Defaulting to 0 would silently
        # file such a download into the wrong folder, so reject it explicitly.
        raw_index = task_data.get("pathIndex")
        if raw_index is None:
            raise RuntimeError("pathIndex is required")
        path_index = int(raw_index)
        fullname = task_data.get("fullname", None)
        sub_folder = task_data.get("subFolder", None)
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
                    f"{needed / 2 ** 30:.2f} GiB but only {free / 2 ** 30:.2f} GiB "
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
        download_platform = task_data.get("downloadPlatform", None)

        try:
            # The gallery arrives as previewFile / previewFile2 / ... in order.
            preview_items = []
            for key in list(task_data):
                if key == "previewFile" or (
                    key.startswith("previewFile") and key[len("previewFile"):].isdigit()
                ):
                    preview_items.append((0 if key == "previewFile" else int(key[len("previewFile"):]), task_data.pop(key)))
            preview_items = [v for _, v in sorted(preview_items)]
            preview_items = [
                v for v in preview_items if not (type(v) is str and v in ("", "undefined"))
            ]
            if preview_items:
                utils.save_model_previews(task_path, preview_items, download_platform)
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

        await utils.send_json("delete_download_task", task_id)

    async def download_model(self, task_id: str, request):
        async def download_task(task_id: str):
            async def report_progress(task_status: TaskStatus):
                await utils.send_json("update_download_task", task_status.to_dict())

            try:
                task_status = self.get_task_status(task_id)
            except:
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
            status = self.download_thread_pool.submit(download_task(task_id), task_id)
            if status == "Waiting":
                task_status = self.get_task_status(task_id)
                task_status.status = "waiting"
                await utils.send_json("update_download_task", task_status.to_dict())
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
            loop = asyncio.get_running_loop()
            actual_sha = await loop.run_in_executor(
                utils.cpu_executor(), _sha256_of, download_tmp_file
            )
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
        await utils.send_json("complete_download_task", task_id)

    async def download_model_file_http(
        self,
        task_id: str,
        headers: dict,
        progress_callback: Callable[[TaskStatus], Coroutine[Any, Any, Any]],
        interval: float = 1.0,
    ) -> None:
        """Stream a download to `<task>.download` with aiohttp.

        Optimization A-5, implemented conservatively: the transfer used to run
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

        model_url = task_content.downloadUrl
        if not model_url:
            raise RuntimeError("No downloadUrl found")

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
            async with session.get(
                model_url, headers=headers, allow_redirects=True
            ) as response:
                if response.status not in (200, 206):
                    if (
                        response.status == 401
                        and task_content.downloadPlatform == "civitai"
                    ):
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
                else:
                    if total_size == 0 or total_size != response_total_size:
                        total_size = response_total_size
                        task_content.sizeBytes = total_size
                        task_status.totalSize = total_size
                        self.set_task_content(task_id, task_content)
                        await utils.send_json("update_download_task", task_status.to_dict())

                with open(download_tmp_file, "ab") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        # Cooperative pause, checked exactly as before.
                        if task_status.status == "pause":
                            break

                        f.write(chunk)
                        downloaded_size += len(chunk)

                        if time.time() - last_update_time >= interval:
                            await push_progress(downloaded_size - last_downloaded_size)
                            last_update_time = time.time()
                            last_downloaded_size = downloaded_size

                await push_progress(downloaded_size - last_downloaded_size)

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
        except ImportError:
            raise RuntimeError(
                "huggingface_hub is not installed. Please install it with: pip install huggingface_hub hf_xet"
            )

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
            await self.download_model_file_http(
                task_id, fallback_headers, progress_callback, interval
            )
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
                    filename = "/".join(path_parts[resolve_idx + 2:])
        except (ValueError, IndexError):
            if len(path_parts) > 2:
                filename = "/".join(path_parts[2:])
            if not filename:
                utils.print_warning(f"Could not parse HF filename, falling back to HTTP: {model_url}")
                await self.download_model_file_http(
                    task_id, fallback_headers, progress_callback, interval
                )
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

            poller = threading.Thread(
                target=_poll, daemon=True, name=f"mm-hf-progress-{task_id[:8]}"
            )
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
