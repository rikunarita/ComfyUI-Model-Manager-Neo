import asyncio
import os
import time

from aiohttp import web

from . import auth
from . import utils

class ProgressFileWrapper:
    """
    Seekable binary file wrapper that reports read progress.
    Used to provide progress events for huggingface_hub uploads without
    bypassing the library's own (LFS/xet) transfer handling.
    """

    def __init__(self, path: str, on_progress):
        self._file = open(path, "rb")
        self._total = os.path.getsize(path)
        self._uploaded = 0
        self._on_progress = on_progress
        self._last_report = time.time()

    def read(self, size=-1):
        data = self._file.read(size)
        if data:
            position = self._file.tell()
            if position > self._uploaded:
                self._uploaded = position
                self._maybe_report()
        return data

    def _maybe_report(self, force=False):
        now = time.time()
        if force or now - self._last_report >= 1.0:
            self._last_report = now
            self._on_progress(self._uploaded, self._total)

    def seek(self, *args):
        return self._file.seek(*args)

    def tell(self):
        return self._file.tell()

    def seekable(self):
        return True

    def readable(self):
        return True

    def writable(self):
        return False

    @property
    def name(self):
        return self._file.name

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

class HfUploader:
    def add_routes(self, routes):

        @routes.get("/model-manager/hf/whoami")
        async def hf_whoami(request):
            """
            Get the currently authenticated HuggingFace user.
            """
            try:
                token = auth.get_hf_token()
                if not token:
                    return web.json_response(
                        {
                            "success": False,
                            "error": "HuggingFace token not set. Please set it in Settings > API Key.",
                        }
                    )

                from huggingface_hub import HfApi

                loop = asyncio.get_running_loop()
                info = await loop.run_in_executor(
                    None, lambda: HfApi(token=token).whoami()
                )
                return web.json_response(
                    {
                        "success": True,
                        "data": {
                            "name": info.get("name"),
                            "fullname": info.get("fullname"),
                        },
                    }
                )
            except Exception as e:
                error_msg = f"HuggingFace whoami failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.post("/model-manager/hf/upload")
        async def hf_upload(request):
            """
            Upload a local model file to a HuggingFace repository.
            """
            try:
                json_data = await request.json()
                await self.upload_to_hf(json_data)
                utils.print_info(f"HuggingFace upload success")
                return web.json_response({"success": True, "data": None})
            except Exception as e:
                error_msg = f"HuggingFace upload failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

    async def upload_to_hf(self, data: dict):
        token = auth.get_hf_token()
        if not token:
            raise RuntimeError(
                "HuggingFace token not set. Please set it in Settings > API Key."
            )

        model_type = data.get("type", None)
        path_index = int(data.get("pathIndex", 0))
        fullname = data.get("fullname", None)
        repo_id = (data.get("repoId") or "").strip()
        path_in_repo = (data.get("pathInRepo") or "").strip()
        private = bool(data.get("private", False))

        if not repo_id:
            raise RuntimeError("Repository id is required")
        if not path_in_repo:
            raise RuntimeError("Destination path in repository is required")

        local_path = utils.get_valid_full_path(model_type, path_index, fullname)
        if local_path is None:
            raise RuntimeError(f"Model file not found: {fullname}")

        try:
            from huggingface_hub import HfApi
        except ImportError:
            raise RuntimeError(
                "huggingface_hub is not installed. Please install it with: pip install huggingface_hub hf_xet"
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        last_report = [time.time()]

        def report_progress(uploaded: float, total: float):
            now = time.time()
            if now - last_report[0] < 1.0 and uploaded != total:
                return
            last_report[0] = now
            asyncio.run_coroutine_threadsafe(
                utils.send_json(
                    "update_hf_upload_progress",
                    {
                        "uploadedSize": float(uploaded),
                        "totalSize": float(total),
                        "progress": (uploaded / total * 100) if total > 0 else 0,
                    },
                ),
                loop,
            )

        def do_upload():
            api = HfApi(token=token, library_name="ComfyUI-Model-Manager-Neo")

            # Create the repository when it does not exist.
            # The private flag only applies on creation.
            if not api.repo_exists(repo_id=repo_id):
                api.create_repo(repo_id=repo_id, private=private, exist_ok=True)

            total = os.path.getsize(local_path)
            wrapper = ProgressFileWrapper(local_path, report_progress)
            try:
                result = api.upload_file(
                    path_or_fileobj=wrapper,
                    path_in_repo=path_in_repo,
                    repo_id=repo_id,
                    repo_type="model",
                    token=token,
                )
            finally:
                wrapper.close()

            report_progress(total, total)
            return result

        await loop.run_in_executor(None, do_upload)
        await utils.send_json(
            "hf_upload_complete",
            {"repoId": repo_id, "pathInRepo": path_in_repo},
        )
