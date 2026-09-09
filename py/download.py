import asyncio
import base64
import functools
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional, Union
from urllib.parse import urlparse

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
    preview: str
    status: Literal["pause", "waiting", "doing"] = "pause"
    platform: Union[str, None] = None
    downloadedSize: float = 0
    totalSize: float = 0
    progress: float = 0
    bps: float = 0
    error: Optional[str] = None
    source: str = "remote"

    def __init__(self, **kwargs):
        self.taskId = kwargs.get("taskId", None)
        self.type = kwargs.get("type", None)
        self.fullname = kwargs.get("fullname", None)
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
    downloadUrl: str
    sizeBytes: float
    hashes: Optional[dict[str, str]] = None
    revision: Optional[str] = None
    source: str = "remote"
    subFolder: Optional[str] = None  # ← 追加

    def __init__(self, **kwargs):
        self.type = kwargs.get("type", None)
        self.pathIndex = int(kwargs.get("pathIndex", 0))
        self.fullname = kwargs.get("fullname", None)
        self.description = kwargs.get("description", None)
        self.downloadPlatform = kwargs.get("downloadPlatform", None)
        self.downloadUrl = kwargs.get("downloadUrl", None)
        self.sizeBytes = float(kwargs.get("sizeBytes", 0))
        self.hashes = kwargs.get("hashes", None)
        self.revision = kwargs.get("revision", None)
        self.source = kwargs.get("source", "remote")
        self.subFolder = kwargs.get("subFolder", None)  # ← 追加

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
            "subFolder": self.subFolder,  # ← 追加
        }

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
        path_index = int(task_data.get("pathIndex", None))
        fullname = task_data.get("fullname", None)
        sub_folder = task_data.get("subFolder", None)  # ← 追加

        # サブフォルダを fullname に結合
        if sub_folder:
            fullname = utils.join_path(sub_folder, fullname)  # ← 追加
            # BUG FIX: the joined fullname must be written back into task_data
            # before it is persisted. Otherwise TaskContent.fullname stayed the
            # bare file name and `_download_complete` moved the finished file to
            # the model-type ROOT instead of the chosen sub-folder.
            task_data["fullname"] = fullname

        model_path = utils.get_full_path(model_type, path_index, fullname)
        if os.path.exists(model_path):
            raise RuntimeError(f"File already exists: {model_path}")

        download_path = utils.get_download_path()

        task_id = uuid.uuid4().hex
        task_path = utils.join_path(download_path, f"{task_id}.task")
        if os.path.exists(task_path):
            raise RuntimeError(f"Task {task_id} already exists")
        download_platform = task_data.get("downloadPlatform", None)

        try:
            preview_file = task_data.pop("previewFile", None)
            utils.save_model_preview(task_path, preview_file, download_platform)
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

                if download_platform == "huggingface":
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
            # 【修正】関数オブジェクトではなく、実行したコルーチンオブジェクトを渡す
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

        description = task_content.description
        description_file = utils.join_path(download_path, f"{task_id}.md")
        with open(description_file, "w", encoding="utf-8", newline="") as f:
            f.write(description)

        download_tmp_file = utils.join_path(download_path, f"{task_id}.download")
        model_path = utils.get_full_path(model_type, path_index, fullname)

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
        progress_callback: Callable[[TaskStatus], Awaitable[Any]],
        interval: float = 1.0,
    ):
        async def update_progress():
            nonlocal last_update_time, last_downloaded_size
            progress = (downloaded_size / total_size) * 100 if total_size > 0 else 0
            task_status.downloadedSize = downloaded_size
            task_status.progress = progress
            task_status.bps = downloaded_size - last_downloaded_size
            await progress_callback(task_status)
            last_update_time = time.time()
            last_downloaded_size = downloaded_size

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
            headers["Range"] = f"bytes={downloaded_size}-"

        total_size = task_content.sizeBytes

        if total_size > 0 and downloaded_size == total_size:
            await self._download_complete(task_id)
            return

        last_update_time = time.time()
        last_downloaded_size = downloaded_size

        loop = asyncio.get_running_loop()

        # BUG FIX (regression from the thread-pool -> asyncio rewrite):
        # `requests.get(..., stream=True)` and the `iter_content()` read loop
        # below are BLOCKING calls. Upstream ran every download task in a
        # dedicated worker thread with its own event loop, so that was safe.
        # `thread.DownloadThreadPool` now schedules the coroutine on ComfyUI's
        # MAIN event loop, which meant:
        #   - the connect/TLS/response-header phase blocked the whole server
        #     with no socket timeout, so one unresponsive host froze ComfyUI
        #     entirely (no prompt callbacks, no websocket, no UI);
        #   - between chunks the loop only got control back once per `interval`,
        #     starving every websocket push - including batch-scan progress;
        #   - a download URL served by ComfyUI itself deadlocked permanently
        #     (the server could not answer a request it was blocked on).
        # The Hugging Face branch already offloads with `run_in_executor`; the
        # plain HTTP branch was missed. Same treatment here.
        response = await loop.run_in_executor(
            None,
            functools.partial(
                requests.get,
                url=model_url,
                headers=headers,
                stream=True,
                allow_redirects=True,
            ),
        )

        if response.status_code not in (200, 206):
            raise RuntimeError(f"Failed to download {task_content.fullname}, status code: {response.status_code}")

        content_type = response.headers.get("content-type")
        if content_type and content_type.startswith("text/html"):
            raise RuntimeError(f"{task_content.fullname} needs to be logged in to download. Please set the API-Key first.")

        response_total_size = float(response.headers.get("content-length", 0))

        if response.status_code == 206:
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

        # Mutable holder so the worker thread can hand the counters back.
        state = {
            "downloaded": downloaded_size,
            "last_update": last_update_time,
            "last_size": last_downloaded_size,
        }

        def pump_chunks():
            # NOTE: the response MUST be closed from inside this worker thread.
            # `pause_model_download_task` / `delete_model_download_task` cancel
            # the asyncio task, which raises CancelledError at the
            # `run_in_executor` await below; a `finally: response.close()` on
            # the loop side then ran concurrently with this thread's
            # `iter_content()` and blocked the event loop on urllib3's read
            # lock for as long as the transfer had left (measured: the whole
            # server stopped answering requests for 8s after a pause).
            try:
                with open(download_tmp_file, "ab") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        # Cooperative pause/cancel, checked exactly as before:
                        # the callers flip `task_status.status`, the loop breaks
                        # on the next chunk and the partially written
                        # `.download` file stays resumable through the `Range`
                        # header above.
                        if task_status.status == "pause":
                            break

                        f.write(chunk)
                        state["downloaded"] += len(chunk)

                        if time.time() - state["last_update"] >= interval:
                            done = state["downloaded"]
                            task_status.downloadedSize = done
                            task_status.progress = (done / total_size) * 100 if total_size > 0 else 0
                            task_status.bps = done - state["last_size"]
                            # Marshal the websocket push back onto the main
                            # loop - identical to the Hugging Face tqdm hook.
                            asyncio.run_coroutine_threadsafe(progress_callback(task_status), loop)
                            state["last_update"] = time.time()
                            state["last_size"] = done
            finally:
                response.close()

        await loop.run_in_executor(None, pump_chunks)

        downloaded_size = state["downloaded"]
        last_update_time = state["last_update"]
        last_downloaded_size = state["last_size"]

        await update_progress()

        if total_size > 0 and downloaded_size == total_size:
            await self._download_complete(task_id)
        else:
            task_status.status = "pause"
            await utils.send_json("update_download_task", task_status.to_dict())

    async def download_model_file_hf(
        self,
        task_id: str,
        progress_callback: Callable[[TaskStatus], Awaitable[Any]],
        interval: float = 1.0,
    ):
        try:
            from huggingface_hub import hf_hub_download
            from huggingface_hub.utils import HfHubHTTPError, EntryNotFoundError, RepositoryNotFoundError, GatedRepoError
        except ImportError:
            raise RuntimeError(
                "huggingface_hub is not installed. Please install it with: pip install huggingface_hub hf_xet"
            )

        try:
            from tqdm.auto import tqdm as base_tqdm
        except ImportError:
            base_tqdm = None

        task_status = self.get_task_status(task_id)
        task_content = self.get_task_content(task_id)

        model_url = task_content.downloadUrl
        if not model_url:
            raise RuntimeError("No downloadUrl found")

        parsed = urlparse(model_url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]

        if len(path_parts) < 3:
            utils.print_warning(f"HF URL format unexpected, falling back to HTTP: {model_url}")
            headers = {"User-Agent": config.user_agent}
            token = auth.get_hf_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            await self.download_model_file_http(task_id, headers, progress_callback, interval)
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
                headers = {"User-Agent": config.user_agent}
                token = auth.get_hf_token()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                await self.download_model_file_http(task_id, headers, progress_callback, interval)
                return

        download_path = utils.get_download_path()
        task_hf_dir = utils.join_path(download_path, f"{task_id}_hf")
        os.makedirs(task_hf_dir, exist_ok=True)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        last_progress_time = [time.time()]

        class ModelManagerTqdm(base_tqdm if base_tqdm else object):
            def __init__(self, *args, **kwargs):
                kwargs.pop("name", None)
                kwargs["disable"] = False
                if base_tqdm:
                    super().__init__(*args, **kwargs)

            def update(self, n=1):
                if base_tqdm:
                    super().update(n)
                try:
                    current_time = time.time()
                    if current_time - last_progress_time[0] < interval:
                        return
                    last_progress_time[0] = current_time
                    task_status.downloadedSize = float(self.n)
                    if self.total:
                        task_status.totalSize = float(self.total)
                    task_status.progress = (self.n / self.total * 100) if self.total > 0 else 0
                    
                    # bps を tqdm の組み込みレートから取得（出処から直接）
                    rate = self.format_dict.get('rate') if base_tqdm else None
                    task_status.bps = float(rate) if rate else 0.0  # ← 修正
                    
                    asyncio.run_coroutine_threadsafe(
                        progress_callback(task_status),
                        loop
                    )
                except Exception:
                    pass

        token = auth.get_hf_token()

        result_path = None
        try:
            result_path = await loop.run_in_executor(
                None,
                lambda: hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    token=token,
                    local_dir=task_hf_dir,
                    force_download=False,
                    tqdm_class=ModelManagerTqdm if base_tqdm else None,
                    user_agent=config.user_agent,
                ),
            )
        except (EntryNotFoundError, RepositoryNotFoundError, GatedRepoError) as e:
            if os.path.isdir(task_hf_dir):
                shutil.rmtree(task_hf_dir, ignore_errors=True)
            raise RuntimeError(f"HuggingFace access denied for {repo_id}: {e}. Please check your HF API token and repository access.")
        except HfHubHTTPError as e:
            if os.path.isdir(task_hf_dir):
                shutil.rmtree(task_hf_dir, ignore_errors=True)
            raise RuntimeError(f"HuggingFace download failed: {e}")
        except Exception as e:
            if os.path.isdir(task_hf_dir):
                shutil.rmtree(task_hf_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to download from HuggingFace: {e}")

        if not result_path or not os.path.exists(result_path):
            if os.path.isdir(task_hf_dir):
                shutil.rmtree(task_hf_dir, ignore_errors=True)
            raise RuntimeError(f"Downloaded file not found at {result_path}")

        download_tmp_file = utils.join_path(download_path, f"{task_id}.download")

        if os.path.exists(download_tmp_file):
            os.remove(download_tmp_file)

        try:
            shutil.move(result_path, download_tmp_file)
        except Exception:
            try:
                shutil.copy2(result_path, download_tmp_file)
            except Exception:
                pass

        if os.path.isdir(task_hf_dir):
            try:
                shutil.rmtree(task_hf_dir)
            except Exception as e:
                utils.print_warning(f"Failed to clean up HF task dir {task_hf_dir}: {e}")

        total_size = task_content.sizeBytes
        actual_size = os.path.getsize(download_tmp_file)
        if total_size == 0:
            total_size = actual_size
        task_content.sizeBytes = total_size
        self.set_task_content(task_id, task_content)

        task_status.downloadedSize = float(actual_size)
        task_status.totalSize = float(total_size)
        task_status.progress = 100.0
        task_status.bps = 0
        await progress_callback(task_status)

        await self._download_complete(task_id)

# Singleton instance
_model_download_instance = None

def get_model_download():
    """Get the global ModelDownload singleton instance."""
    global _model_download_instance
    if _model_download_instance is None:
        _model_download_instance = ModelDownload()
    return _model_download_instance
