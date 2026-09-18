import asyncio
import os
import time
import uuid
from typing import Any

from aiohttp import web

from . import auth
from . import download
from . import utils
from .information import MODELSCOPE_INTL_ENDPOINT
from .upload_hf import (
    HF_UPLOAD_TASKS,
    LIBRARY_NAME,
    PHASE_PREPARE,
    PHASE_UPLOAD,
    _forget_task,
    _ProgressFile,
    _set_task_field,
)

# ModelScope uploads reuse the HuggingFace upload task bookkeeping and the
# same websocket event names (the completion detail carries
# `provider: "modelscope"` so the UI can word its toasts correctly).


class MsUploader:
    def add_routes(self, routes):

        @routes.get("/model-manager/modelscope/whoami")
        async def ms_whoami(request):
            """The authenticated ModelScope user (token check for the UI)."""
            try:
                token = auth.get_modelscope_token()
                if not token:
                    return web.json_response(
                        {
                            "success": False,
                            "error": "ModelScope token not set. Please set it in Settings > API Key.",
                        }
                    )
                from modelscope_hub import HubApi

                loop = asyncio.get_running_loop()
                info = await loop.run_in_executor(
                    utils.io_executor(),
                    lambda: HubApi(endpoint=MODELSCOPE_INTL_ENDPOINT, token=token).whoami(),
                )
                return web.json_response(
                    {
                        "success": True,
                        "data": {
                            "name": getattr(info, "name", None),
                            "fullname": getattr(info, "name", None),
                        },
                    }
                )
            except Exception as e:
                error_msg = f"ModelScope whoami failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.post("/model-manager/modelscope/upload")
        async def ms_upload(request):
            """Start a ModelScope upload; answers with a task id immediately."""
            try:
                json_data = await request.json()
                task_id = await self.start_upload(json_data)
                return web.json_response({"success": True, "data": {"taskId": task_id}})
            except Exception as e:
                error_msg = f"ModelScope upload failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

    async def start_upload(self, data: dict) -> str:
        token = auth.get_modelscope_token()
        if not token:
            raise RuntimeError(
                "ModelScope token not set. Please set it in Settings > API Key."
            )

        repo_id = (data.get("repoId") or "").strip()
        path_in_repo = (data.get("pathInRepo") or "").strip()
        private = bool(data.get("private", False))

        if not repo_id:
            raise RuntimeError("Repository id is required")
        if not path_in_repo:
            raise RuntimeError("Destination path in repository is required")

        files: list[dict] = []
        raw_files = data.get("files")
        if raw_files:
            import json as _json

            try:
                parsed = _json.loads(raw_files) if isinstance(raw_files, str) else raw_files
            except Exception as e:
                raise RuntimeError(f"Invalid files payload: {e}")
            if not isinstance(parsed, list) or not parsed:
                raise RuntimeError("files must be a non-empty list")
            base = path_in_repo.rstrip("/")
            for entry in parsed:
                ftype = entry.get("type")
                findex = int(entry.get("pathIndex", 0))
                fname = entry.get("fullname")
                if not ftype or not fname:
                    raise RuntimeError("every file needs type and fullname")
                local = utils.get_valid_full_path(ftype, findex, fname)
                if local is None:
                    raise RuntimeError(f"Model file not found: {fname}")
                files.append({"local_path": local, "path_in_repo": f"{base}/{fname}"})
        else:
            model_type = data.get("type", None)
            path_index = int(data.get("pathIndex", 0))
            fullname = data.get("fullname", None)
            if model_type is None or fullname is None:
                raise RuntimeError("type and fullname are required")
            local_path = utils.get_valid_full_path(model_type, path_index, fullname)
            if local_path is None:
                raise RuntimeError(f"Model file not found: {fullname}")
            files.append({"local_path": local_path, "path_in_repo": path_in_repo})

        total_size = sum(os.path.getsize(f["local_path"]) for f in files)
        task_id = uuid.uuid4().hex
        HF_UPLOAD_TASKS[task_id] = {
            "repoId": repo_id,
            "pathInRepo": path_in_repo,
            "status": "running",
            "fileCount": len(files),
        }

        await utils.send_json(
            "update_hf_upload_progress",
            {
                "taskId": task_id,
                "uploadedSize": 0.0,
                "totalSize": float(total_size),
                "progress": 0.0,
                "phase": PHASE_PREPARE,
                "provider": "modelscope",
            },
        )

        pool = download.get_model_download().download_thread_pool
        pool.submit(
            self.run_upload(
                task_id=task_id,
                token=token,
                files=files,
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
        files: list[dict],
        repo_id: str,
        path_in_repo: str,
        private: bool,
        total_size: int,
    ) -> None:
        try:
            from modelscope_hub import HubApi
        except ImportError:
            raise RuntimeError(
                "modelscope_hub is not installed. Please install it with: pip install modelscope_hub"
            )

        loop = asyncio.get_running_loop()
        progress_state: dict[str, Any] = {"last": 0.0, "phase": None}
        completed_bytes = 0

        def report_progress(sent_bytes: int, file_total: int, phase: str = PHASE_UPLOAD) -> None:
            now = time.time()
            phase_changed = phase != progress_state["phase"]
            boundary = sent_bytes in (0, file_total)
            if not phase_changed and not boundary and now - progress_state["last"] < 0.4:
                return
            progress_state["last"] = now
            progress_state["phase"] = phase
            cumulative = completed_bytes + sent_bytes
            progress = (cumulative / total_size * 100) if total_size > 0 else 0.0
            asyncio.run_coroutine_threadsafe(
                utils.send_json(
                    "update_hf_upload_progress",
                    {
                        "taskId": task_id,
                        "uploadedSize": float(cumulative),
                        "totalSize": float(total_size),
                        "progress": progress,
                        "phase": phase,
                        "provider": "modelscope",
                    },
                ),
                loop,
            )

        repo_state = {"ensured": False, "created": False}

        def ensure_repo():
            api = HubApi(endpoint=MODELSCOPE_INTL_ENDPOINT, token=token)
            if not repo_state["ensured"]:
                if not api.repo_exists(repo_id, "model"):
                    api.create_repo(
                        repo_id,
                        "model",
                        visibility="private" if private else "public",
                    )
                    repo_state["created"] = True
                repo_state["ensured"] = True
            return api

        transferred_total = 0
        first_url: str | None = None

        for item in files:
            local_path = item["local_path"]
            in_repo = item["path_in_repo"]
            file_size = os.path.getsize(local_path)

            def do_upload():
                api = ensure_repo()
                with _ProgressFile(local_path, report_progress) as payload:
                    api.upload_file(
                        repo_id,
                        "model",
                        payload,
                        in_repo,
                        commit_message=f"Upload {os.path.basename(in_repo)}",
                        disable_tqdm=True,
                    )
                return payload.transferred_bytes

            try:
                transferred = await loop.run_in_executor(utils.io_executor(), do_upload)
            except Exception as e:
                _set_task_field(task_id, status="error")
                await utils.send_json(
                    "hf_upload_error",
                    {"taskId": task_id, "error": str(e), "provider": "modelscope"},
                )
                _forget_task(task_id)
                raise
            if transferred:
                transferred_total += int(transferred)
            first_url = first_url or f"{MODELSCOPE_INTL_ENDPOINT}/models/{repo_id}/files/{in_repo}"
            completed_bytes += file_size

        from urllib.parse import quote as _quote

        deduplicated = transferred_total == 0 and completed_bytes > 0
        _set_task_field(
            task_id,
            status="complete",
            transferredBytes=float(transferred_total),
            created=repo_state["created"],
        )
        await utils.send_json(
            "update_hf_upload_progress",
            {
                "taskId": task_id,
                "uploadedSize": float(total_size),
                "totalSize": float(total_size),
                "progress": 100.0,
                "phase": PHASE_UPLOAD,
                "provider": "modelscope",
            },
        )
        await utils.send_json(
            "hf_upload_complete",
            {
                "taskId": task_id,
                "repoId": repo_id,
                "pathInRepo": path_in_repo,
                "skipped": False,
                "deduplicated": deduplicated,
                "transferredBytes": float(transferred_total),
                "created": repo_state["created"],
                "private": private,
                "url": first_url
                or f"{MODELSCOPE_INTL_ENDPOINT}/models/{repo_id}/files/{_quote(path_in_repo)}",
                "fileCount": len(files),
                "skippedCount": 0,
                "provider": "modelscope",
            },
        )
        _forget_task(task_id)
