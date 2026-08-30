import os
import time
import uuid

import folder_paths

from aiohttp import web

from . import download
from . import utils

class LocalUploadCancelled(Exception):
    """Raised when a local upload task is cancelled while streaming."""
    pass

class ModelUploader:
    def add_routes(self, routes):

        @routes.get("/model-manager/supported-extensions")
        async def fetch_model_exts(request):
            """
            Get model exts
            """
            try:
                supported_extensions = list(folder_paths.supported_pt_extensions)
                return web.json_response({"success": True, "data": supported_extensions})
            except Exception as e:
                error_msg = f"Get model supported extension failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.post("/model-manager/upload")
        async def upload_model(request):
            """
            Upload model (local file -> ComfyUI).
            The upload is also registered as a "local" task in the shared
            download task system, so it shows up in the lower half of the
            Download List dialog.
            """
            try:
                reader = await request.multipart()
                await self.upload_model(reader)
                utils.print_info(f"Upload model success")
                return web.json_response({"success": True, "data": None})
            except LocalUploadCancelled:
                utils.print_info(f"Upload model cancelled")
                return web.json_response({"success": True, "data": None})
            except Exception as e:
                error_msg = f"Upload model failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

    def resolve_model_folder(self, file_folder: str):
        """
        Resolve the model type / pathIndex / relative directory for a given
        absolute folder path by matching it against the known model folders.
        Returns (model_type, path_index, relative_dir) or None.
        """
        base_paths = utils.resolve_model_base_paths()
        norm = utils.normalize_path(file_folder)
        best = None
        for model_type, folders in base_paths.items():
            for index, base in enumerate(folders):
                base_n = utils.normalize_path(base)
                if norm == base_n or norm.startswith(base_n.rstrip("/") + "/"):
                    if best is None or len(base_n) > len(best[2]):
                        relative_dir = norm[len(base_n):].strip("/")
                        best = (model_type, index, relative_dir)
        return best

    def create_local_task(self, file_folder: str, filename: str):
        """
        Register the local upload as a task in the shared download task
        system. Returns (task_id, task_status), or (None, None) when the
        folder cannot be resolved to a known model folder.
        """
        resolved = self.resolve_model_folder(file_folder)
        if resolved is None:
            return None, None

        model_type, path_index, relative_dir = resolved
        fullname = f"{relative_dir}/{filename}" if relative_dir else filename

        model_download = download.get_model_download()
        task_id = uuid.uuid4().hex

        task_content = download.TaskContent(
            type=model_type,
            pathIndex=path_index,
            fullname=fullname,
            description="",
            downloadPlatform="local",
            downloadUrl=None,
            sizeBytes=0,
            source="local",
        )
        model_download.set_task_content(task_id, task_content)

        task_status = download.TaskStatus(
            taskId=task_id,
            type=model_type,
            fullname=fullname,
            preview="no-preview.png",
            status="doing",
            platform="local",
            source="local",
            totalSize=0,
        )
        model_download.download_model_task_status[task_id] = task_status
        return task_id, task_status

    async def cleanup_local_task(self, task_id, tmp_filepath):
        """Remove the tmp file and the task entry of a local upload."""
        if tmp_filepath and os.path.exists(tmp_filepath):
            os.remove(tmp_filepath)
        if task_id:
            model_download = download.get_model_download()
            download_path = utils.get_download_path()
            task_file = utils.join_path(download_path, f"{task_id}.task")
            if os.path.exists(task_file):
                os.remove(task_file)
            model_download.delete_task_status(task_id)
            await utils.send_json("delete_download_task", task_id)

    async def upload_model(self, reader):
        model_download = download.get_model_download()

        uploaded_size = 0
        last_update_time = time.time()
        last_task_update_time = time.time()
        last_task_size = 0
        interval = 1.0

        file_folder = None
        task_id = None
        task_status = None
        tmp_filepath = None
        filepath = None

        try:
            while True:
                part = await reader.next()
                if part is None:
                    break

                name = part.name
                if name == "folder":
                    file_folder = await part.text()

                if name == "file":
                    filename = part.filename
                    filepath = f"{file_folder}/{filename}"
                    tmp_filepath = f"{file_folder}/{filename}.tmp"

                    task_id, task_status = self.create_local_task(file_folder, filename)
                    if task_id is not None:
                        await utils.send_json("create_download_task", task_status.to_dict())

                    with open(tmp_filepath, "wb") as f:
                        while True:
                            chunk = await part.read_chunk()
                            if not chunk:
                                break
                            f.write(chunk)
                            uploaded_size += len(chunk)

                            if task_status is not None:
                                task_status.downloadedSize = uploaded_size
                                task_status.totalSize = uploaded_size

                            if time.time() - last_update_time >= interval:
                                update_upload_progress = {
                                    "uploaded_size": uploaded_size,
                                }
                                if task_id is not None:
                                    update_upload_progress["taskId"] = task_id
                                await utils.send_json("update_upload_progress", update_upload_progress)
                                last_update_time = time.time()

                            if task_status is not None and time.time() - last_task_update_time >= interval:
                                task_status.bps = uploaded_size - last_task_size
                                last_task_size = uploaded_size
                                last_task_update_time = time.time()
                                await utils.send_json("update_download_task", task_status.to_dict())

                            if task_status is not None and task_status.status == "pause":
                                # A local upload cannot be resumed; the pause
                                # flag is used as a cancellation signal.
                                raise LocalUploadCancelled()

            # Guard against a malformed multipart request without a file part.
            if tmp_filepath is None or filepath is None:
                return

            update_upload_progress = {
                "uploaded_size": uploaded_size,
            }
            if task_id is not None:
                update_upload_progress["taskId"] = task_id
            await utils.send_json("update_upload_progress", update_upload_progress)

            if task_status is not None:
                task_status.downloadedSize = uploaded_size
                task_status.totalSize = uploaded_size
                task_status.progress = 100
                task_status.bps = 0
                await utils.send_json("update_download_task", task_status.to_dict())

            os.rename(tmp_filepath, filepath)

            if task_id is not None:
                download_path = utils.get_download_path()
                task_file = utils.join_path(download_path, f"{task_id}.task")
                if os.path.exists(task_file):
                    os.remove(task_file)
                model_download.delete_task_status(task_id)
                await utils.send_json("complete_download_task", task_id)
        except LocalUploadCancelled:
            await self.cleanup_local_task(task_id, tmp_filepath)
            raise
        except Exception:
            await self.cleanup_local_task(task_id, tmp_filepath)
            raise
