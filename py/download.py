import os
import uuid
import time
import asyncio
import shutil
import requests
import base64

import folder_paths

from typing import Callable, Awaitable, Any, Literal, Union, Optional
from dataclasses import dataclass
from aiohttp import web

from . import config
from . import utils
from . import thread
from . import auth


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
        }


class ModelDownload:
    def __init__(self):
        self.api_key = auth.get_api_key()

    def add_routes(self, routes):
        @routes.post("/model-manager/download/init")
        async def init_download(request):
            """
            Init download setting.
            """
            result = self.api_key.init(request)
            return web.json_response({"success": True, "data": result})

        @routes.post("/model-manager/download/setting")
        async def set_download_setting(request):
            """
            Set download setting.
            """
            json_data = await request.json()
            key = json_data.get("key", None)
            value = json_data.get("value", None)
            value = base64.b64decode(value).decode("utf-8") if value is not None else None
            self.api_key.set_value(key, value)
            return web.json_response({"success": True})

        @routes.get("/model-manager/download/task")
        async def scan_download_tasks(request):
            """
            Read download task list.
            """
            try:
                result = await self.scan_model_download_task_list()
                return web.json_response({"success": True, "data": result})
            except Exception as e:
                error_msg = f"Read download task list failed: {e}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.put("/model-manager/download/{task_id}")
        async def resume_download_task(request):
            """
            Toggle download task status.
            """
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
            """
            Delete download task.
            """
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
            """
            Create a new model.

            request body: x-www-form-urlencoded
            - type: model type.
            - pathIndex: index of the model folders.
            - fullname: filename that relative to the model folder.
            - previewFile: preview file.
            - description: description.
            - downloadPlatform: download platform.
            - downloadUrl: download url.
            - hash: a JSON string containing the hash value of the downloaded model.
            """
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
            )

            self.download_model_task_status[task_id] = task_status

        return task_status

    def delete_task_status(self, task_id: str):
        self.download_model_task_status.pop(task_id, None)

    async def scan_model_download_task_list(self):
        """
        Scan the download directory and send the task list to the client.
        """
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
        """
        Creates a download task for the given data.
        """
        model_type = task_data.get("type", None)
        path_index = int(task_data.get("pathIndex", None))
        fullname = task_data.get("fullname", None)

        model_path = utils.get_full_path(model_type, path_index, fullname)
        # Check if the model path is valid
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

    async def delete_model_download_task(self, task_id: str):
        task_status = self.get_task_status(task_id)
        is_running = task_status.status == "doing"
        task_status.status = "waiting"
        await utils.send_json("delete_download_task", task_id)

        # Pause the task
        if is_running:
            task_status.status = "pause"
            time.sleep(1)

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
                # When starting a task from the queue, the task may not exist
                task_status = self.get_task_status(task_id)
            except:
                return

            # Update task status
            task_status.status = "doing"
            await utils.send_json("update_download_task", task_status.to_dict())

            try:
                # Set download request headers
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

                # Branch by platform: HuggingFace uses huggingface_hub,
                # others use direct HTTP download
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
                task_status.status = "pause"
                task_status.error = str(e)
                await utils.send_json("update_download_task", task_status.to_dict())
                task_status.error = None
                utils.print_error(str(e))

        try:
            status = self.download_thread_pool.submit(download_task, task_id)
            if status == "Waiting":
                task_status = self.get_task_status(task_id)
                task_status.status = "waiting"
                await utils.send_json("update_download_task", task_status.to_dict())
        except Exception as e:
            task_status.status = "pause"
            task_status.error = str(e)
            await utils.send_json("update_download_task", task_status.to_dict())
            task_status.error = None
            utils.print_error(str(e))

    async def _download_complete(self, task_id: str):
        """
        Complete download: write description, move file to target directory,
        remove task file, and notify frontend.
        """
        task_content = self.get_task_content(task_id)
        download_path = utils.get_download_path()

        model_type = task_content.type
        path_index = task_content.pathIndex
        fullname = task_content.fullname

        # Write description file
        description = task_content.description
        description_file = utils.join_path(download_path, f"{task_id}.md")
        with open(description_file, "w", encoding="utf-8", newline="") as f:
            f.write(description)

        download_tmp_file = utils.join_path(download_path, f"{task_id}.download")
        model_path = utils.get_full_path(model_type, path_index, fullname)

        utils.rename_model(download_tmp_file, model_path)

        time.sleep(1)
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
        """
        Download model file using direct HTTP requests (for Civitai and fallback).
        """

        async def update_progress():
            nonlocal last_update_time
            nonlocal last_downloaded_size
            progress = (downloaded_size / total_size) * 100 if total_size > 0 else 0
            task_status.downloadedSize = downloaded_size
            task_status.progress = progress
            task_status.bps = downloaded_size - last_downloaded_size
            await progress_callback(task_status)
            last_update_time = time.time()
            last_downloaded_size = downloaded_size

        task_status = self.get_task_status(task_id)
        task_content = self.get_task_content(task_id)

        # Check download uri
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

        response = requests.get(
            url=model_url,
            headers=headers,
            stream=True,
            allow_redirects=True,
        )

        if response.status_code not in (200, 206):
            raise RuntimeError(f"Failed to download {task_content.fullname}, status code: {response.status_code}")

        # Some models require logging in before they can be downloaded.
        # If no token is carried, it will be redirected to the login page.
        content_type = response.headers.get("content-type")
        if content_type and content_type.startswith("text/html"):
            raise RuntimeError(f"{task_content.fullname} needs to be logged in to download. Please set the API-Key first.")

        # When parsing model information from HuggingFace API,
        # the file size was not found and needs to be obtained from the response header.
        # Fixed issue #169. Some model information from Civitai, providing the wrong file size
        response_total_size = float(response.headers.get("content-length", 0))

        # For 206 Partial Content, content-length is the REMAINING bytes, not total.
        # So we must add downloaded_size to get the actual total.
        if response.status_code == 206:
            actual_total = response_total_size + downloaded_size
            if total_size == 0 or total_size != actual_total:
                total_size = actual_total
                task_content.sizeBytes = total_size
                task_status.totalSize = total_size
                self.set_task_content(task_id, task_content)
                await utils.send_json("update_download_task", task_content.to_dict())
        else:
            if total_size == 0 or total_size != response_total_size:
                total_size = response_total_size
                task_content.sizeBytes = total_size
                task_status.totalSize = total_size
                self.set_task_content(task_id, task_content)
                await utils.send_json("update_download_task", task_content.to_dict())

        with open(download_tmp_file, "ab") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if task_status.status == "pause":
                    break

                f.write(chunk)
                downloaded_size += len(chunk)

                if time.time() - last_update_time >= interval:
                    await update_progress()

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
        """
        Download model file from HuggingFace using huggingface_hub.
        Supports private/gated repositories, Xet Storage, chunked transfer,
        and HF cache integration.
        """
        from urllib.parse import urlparse

        try:
            from huggingface_hub import hf_hub_download
            from huggingface_hub.utils import HfHubHTTPError, EntryNotFoundError, RepositoryNotFoundError, GatedRepoError
        except ImportError as e:
            raise RuntimeError(
                f"huggingface_hub is not installed. Please install it with: pip install huggingface_hub hf_xet"
            )

        # Import tqdm for progress tracking
        try:
            from tqdm.auto import tqdm as base_tqdm
        except ImportError:
            base_tqdm = None

        task_status = self.get_task_status(task_id)
        task_content = self.get_task_content(task_id)

        model_url = task_content.downloadUrl
        if not model_url:
            raise RuntimeError("No downloadUrl found")

        # Parse HuggingFace URL: https://huggingface.co/{space}/{name}/resolve/{revision}/{filepath}
        parsed = urlparse(model_url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]

        if len(path_parts) < 3:
            # Fallback to HTTP download if URL format is unexpected
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

        # Determine revision and filepath
        revision = getattr(task_content, "revision", None) or "main"
        filename = ""

        try:
            resolve_idx = path_parts.index("resolve")
            if resolve_idx + 1 < len(path_parts):
                revision = path_parts[resolve_idx + 1]
            if resolve_idx + 2 < len(path_parts):
                filename = "/".join(path_parts[resolve_idx + 2:])
        except (ValueError, IndexError):
            # Fallback: try parts after repo name
            if len(path_parts) > 2:
                filename = "/".join(path_parts[2:])

        if not filename:
            # Cannot parse, fall back to HTTP
            utils.print_warning(f"Could not parse HF filename, falling back to HTTP: {model_url}")
            headers = {"User-Agent": config.user_agent}
            token = auth.get_hf_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            await self.download_model_file_http(task_id, headers, progress_callback, interval)
            return

        download_path = utils.get_download_path()

        # Create a custom tqdm class that reports progress to the task status
        # The workaround for tqdm's non-TTY auto-disable bug:
        # force disable=False so update() works in web server environments
        loop = asyncio.get_event_loop()
        last_progress_time = [time.time()]

        class ModelManagerTqdm(base_tqdm if base_tqdm else object):
            def __init__(self, *args, **kwargs):
                # Strip HF-specific kwargs that may cause issues
                kwargs.pop("name", None)
                # Force enable in non-TTY environments to ensure progress tracking
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
                    # Schedule the async progress callback on the event loop
                    asyncio.run_coroutine_threadsafe(
                        progress_callback(task_status),
                        loop
                    )
                except Exception:
                    pass

        token = auth.get_hf_token()

        # hf_hub_download is blocking, run in thread executor
        result_path = None
        try:
            result_path = await loop.run_in_executor(
                None,
                lambda: hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    token=token,
                    local_dir=download_path,
                    force_download=False,
                    resume_download=True,
                    tqdm_class=ModelManagerTqdm,
                    user_agent=config.user_agent,
                )
            )
        except (EntryNotFoundError, RepositoryNotFoundError, GatedRepoError) as e:
            raise RuntimeError(f"HuggingFace access denied for {repo_id}: {e}. Please check your HF API token and repository access.")
        except HfHubHTTPError as e:
            raise RuntimeError(f"HuggingFace download failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to download from HuggingFace: {e}")

        if not result_path or not os.path.exists(result_path):
            raise RuntimeError(f"Downloaded file not found at {result_path}")

        # hf_hub_download places the file at local_dir/{filename}
        # and creates .cache/huggingface/ inside local_dir for metadata.
        # Move the downloaded file to the task's temp file for compatibility
        # with the existing _download_complete() logic.
        download_tmp_file = utils.join_path(download_path, f"{task_id}.download")

        # Remove existing tmp file if any (from a previous interrupted download)
        if os.path.exists(download_tmp_file):
            os.remove(download_tmp_file)

        # Move the downloaded file to the temp file location
        try:
            shutil.move(result_path, download_tmp_file)
        except Exception as e:
            # If move fails (e.g., cross-device), try copy
            shutil.copy2(result_path, download_tmp_file)
            os.remove(result_path)

        # Clean up the .cache/huggingface directory created by hf_hub_download
        # inside local_dir. This is metadata cache and not needed after download.
        hf_cache_dir = utils.join_path(download_path, ".cache")
        if os.path.isdir(hf_cache_dir):
            try:
                shutil.rmtree(hf_cache_dir)
            except Exception as e:
                utils.print_warning(f"Failed to clean up HF cache dir {hf_cache_dir}: {e}")

        # Update task status to 100%
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

        # Trigger completion
        await self._download_complete(task_id)
