import asyncio
import os
import uuid

from aiohttp import web

from . import auth
from . import download
from . import utils

# In-flight HuggingFace uploads, keyed by task id.
#
# BUG FIX: the upload used to run *inside* the HTTP handler
# (`await self.upload_to_hf(...)`), so the request stayed open for the whole
# transfer. ComfyUI's `api.fetchApi` aborts any request whose response headers
# have not arrived within 60 s, and aiohttp cancels a handler whose client
# goes away - closing the dialog, navigating away or simply exceeding the
# timeout therefore killed the coroutine that reported progress/completion
# (and, for uploads that were still in their setup phase, the transfer
# itself). The upload now runs as a background task on the shared download
# pool; the handler only validates and returns a task id, so nothing the
# user does in the browser can cancel a running upload any more.
HF_UPLOAD_TASKS: dict[str, dict] = {}


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
            Start uploading a local model file to a HuggingFace repository.

            Returns immediately with a task id; progress and completion are
            reported through the `update_hf_upload_progress` /
            `hf_upload_complete` / `hf_upload_error` websocket events so the
            UI can follow (and re-attach to) the transfer.
            """
            try:
                json_data = await request.json()
                task_id = await self.start_upload(json_data)
                return web.json_response({"success": True, "data": {"taskId": task_id}})
            except Exception as e:
                error_msg = f"HuggingFace upload failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

    async def start_upload(self, data: dict) -> str:
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

        total_size = os.path.getsize(local_path)
        task_id = uuid.uuid4().hex
        HF_UPLOAD_TASKS[task_id] = {
            "repoId": repo_id,
            "pathInRepo": path_in_repo,
            "status": "running",
        }

        # Initial progress (0%) so the UI can show its bar right away.
        await utils.send_json(
            "update_hf_upload_progress",
            {
                "taskId": task_id,
                "uploadedSize": 0.0,
                "totalSize": float(total_size),
                "progress": 0.0,
            },
        )

        # Shared pool with the download tasks: runs on the main loop, survives
        # any client disconnect, and keeps its duplicate-submit guard.
        pool = download.get_model_download().download_thread_pool
        pool.submit(
            self.run_upload(
                task_id=task_id,
                token=token,
                local_path=local_path,
                repo_id=repo_id,
                path_in_repo=path_in_repo,
                private=private,
                total_size=total_size,
            ),
            task_id,
        )
        return task_id

    async def run_upload(
        self,
        task_id: str,
        token: str,
        local_path: str,
        repo_id: str,
        path_in_repo: str,
        private: bool,
        total_size: int,
    ) -> None:
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

        def do_upload():
            api = HfApi(token=token, library_name="ComfyUI-Model-Manager-Neo")

            # Create the repository when it does not exist.
            # The private flag only applies on creation.
            if not api.repo_exists(repo_id=repo_id):
                api.create_repo(repo_id=repo_id, private=private, exist_ok=True)

            # Pass the local_path (string) directly to upload_file.
            # This allows huggingface_hub to use the highly optimized hf_xet
            # transfer protocol (chunk-based deduplication) instead of
            # falling back to legacy HTTP. We intentionally do NOT use a
            # file-like wrapper here, because passing a BinaryIO object
            # bypasses xet and forces a slower legacy HTTP upload.
            api.upload_file(
                path_or_fileobj=local_path,
                path_in_repo=path_in_repo,
                repo_id=repo_id,
                repo_type="model",
                token=token,
            )

        try:
            await loop.run_in_executor(None, do_upload)
        except Exception as e:
            HF_UPLOAD_TASKS[task_id]["status"] = "error"
            await utils.send_json(
                "hf_upload_error",
                {"taskId": task_id, "error": str(e)},
            )
            raise

        HF_UPLOAD_TASKS[task_id]["status"] = "complete"
        # Final progress (100%) + completion; the UI settles on these events
        # instead of the HTTP round-trip.
        await utils.send_json(
            "update_hf_upload_progress",
            {
                "taskId": task_id,
                "uploadedSize": float(total_size),
                "totalSize": float(total_size),
                "progress": 100.0,
            },
        )
        await utils.send_json(
            "hf_upload_complete",
            {"taskId": task_id, "repoId": repo_id, "pathInRepo": path_in_repo},
        )
