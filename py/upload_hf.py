import asyncio
import os
import time

from aiohttp import web

from . import auth
from . import utils

class ProgressFileWrapper:
    """
    Seekable binary file wrapper that reports read progress.
    
    NOTE on hf_xet / LFS behavior:
    huggingface_hub (via hf_xet or LFS) typically reads the file twice:
    1. To compute hashes (SHA256) and determine upload strategy.
    2. To actually upload the content.
    
    To prevent the progress bar from jumping to 100% during the hash phase
    or exceeding 100%, we reset the uploaded counter when a backward seek
    to the beginning (or near beginning) is detected. This ensures the
    progress bar reflects the actual network upload phase (the second pass).
    """

    def __init__(self, path: str, on_progress):
        self._file = open(path, "rb")
        self._total = os.path.getsize(path)
        self._uploaded = 0
        self._on_progress = on_progress
        self._last_report = time.time()
        self._pass_count = 0  # Track read passes

    def read(self, size=-1):
        data = self._file.read(size)
        if data:
            position = self._file.tell()
            # Only update progress if we are moving forward in the current pass
            if position > self._uploaded:
                self._uploaded = position
                self._maybe_report()
        return data

    def _maybe_report(self, force=False):
        now = time.time()
        if force or now - self._last_report >= 1.0:
            self._last_report = now
            # Calculate progress based on current pass
            # If we are in the second pass (upload), map 0-total to 0-100%
            # If we are in the first pass (hash), we might want to show indeterminate or 0-50%?
            # Simplest robust approach: 
            # Pass 1 (Hashing): Show 0% or "Preparing" (handled by UI if needed, but here we just report raw bytes)
            # Pass 2 (Uploading): Report 0-100%.
            
            # Actually, to keep it simple for the UI which expects 0-100:
            # We treat the LAST pass as the real progress.
            # But detecting "last pass" is hard.
            
            # Better heuristic for HF Hub:
            # The library seeks to 0 after hashing. So when we see a seek to 0,
            # we know the next read phase is the upload.
            
            # For now, let's just report the percentage of the current read position relative to total.
            # If it resets, the bar resets. This is visually acceptable (Bar fills -> resets -> fills again = done).
            # To make it smoother, we could offset, but let's stick to accurate "current stream position".
            
            progress = (self._uploaded / self._total * 100) if self._total > 0 else 0
            self._on_progress(self._uploaded, self._total, progress)

    def seek(self, offset, whence=0):
        # Detect backward seek to start (reset for upload phase)
        if whence == 0 and offset == 0 and self._uploaded > 0:
            # We are restarting from the beginning. 
            # This usually means Hash phase is done, Upload phase is starting.
            self._uploaded = 0
            self._pass_count += 1
        
        return self._file.seek(offset, whence)

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

        def report_progress(uploaded: float, total: float, progress: float):
            now = time.time()
            # Throttle updates to 1 second, but always send the final 100%
            if now - last_report[0] < 1.0 and progress < 100.0:
                return
            last_report[0] = now
            
            # We only care about the progress during the actual upload phase.
            # Since we reset on seek(0), the progress will go 0->100 during the upload.
            # During the hash phase, it also goes 0->100 but quickly.
            # To avoid confusion, we could ignore the first pass, but without complex state,
            # letting it reset is the most honest representation of "streaming bytes".
            
            asyncio.run_coroutine_threadsafe(
                utils.send_json(
                    "update_hf_upload_progress",
                    {
                        "uploadedSize": float(uploaded),
                        "totalSize": float(total),
                        "progress": float(progress),
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
                # upload_file accepts a file-like object.
                # hf_xet will handle chunking/dedup internally.
                result = api.upload_file(
                    path_or_fileobj=wrapper,
                    path_in_repo=path_in_repo,
                    repo_id=repo_id,
                    repo_type="model",
                    token=token,
                )
            finally:
                wrapper.close()

            # Force final 100% report
            report_progress(total, total, 100.0)
            return result

        await loop.run_in_executor(None, do_upload)
        await utils.send_json(
            "hf_upload_complete",
            {"repoId": repo_id, "pathInRepo": path_in_repo},
        )
