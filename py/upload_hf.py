import asyncio
import os

from aiohttp import web

from . import auth
from . import utils

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

        total_size = os.path.getsize(local_path)

        # Send initial progress (0%) so the UI can show an indeterminate progress bar
        await utils.send_json(
            "update_hf_upload_progress",
            {
                "uploadedSize": 0.0,
                "totalSize": float(total_size),
                "progress": 0.0,
            },
        )

        def do_upload():
            api = HfApi(token=token, library_name="ComfyUI-Model-Manager-Neo")

            # Create the repository when it does not exist.
            # The private flag only applies on creation.
            if not api.repo_exists(repo_id=repo_id):
                api.create_repo(repo_id=repo_id, private=private, exist_ok=True)

            # Pass the local_path (string) directly to upload_file.
            # This allows huggingface_hub to use the highly optimized hf_xet transfer
            # protocol (chunk-based deduplication) instead of falling back to legacy HTTP.
            # We intentionally do NOT use a file-like wrapper here, because passing a 
            # BinaryIO object bypasses xet and forces a slower legacy HTTP upload.
            api.upload_file(
                path_or_fileobj=local_path,
                path_in_repo=path_in_repo,
                repo_id=repo_id,
                repo_type="model",
                token=token,
            )

        # Run the blocking upload in a thread executor
        await loop.run_in_executor(None, do_upload)

        # Send final progress (100%)
        await utils.send_json(
            "update_hf_upload_progress",
            {
                "uploadedSize": float(total_size),
                "totalSize": float(total_size),
                "progress": 100.0,
            },
        )

        await utils.send_json(
            "hf_upload_complete",
            {"repoId": repo_id, "pathInRepo": path_in_repo},
        )
