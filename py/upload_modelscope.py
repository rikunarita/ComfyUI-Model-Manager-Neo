import asyncio

from aiohttp import web

from . import auth
from . import utils
from .information import MODELSCOPE_INTL_ENDPOINT
from .upload_hf import (
    HubUploadBackend,
    PHASE_UPLOAD,
    _ProgressFile,
    _start_hub_upload,
    parse_upload_payload,
)


class MsBackend(HubUploadBackend):
    """ModelScope slice of the shared hub upload pipeline.

    Everything else (task bookkeeping, cumulative progress, duplicate
    preflight hook, completion events) is the shared implementation in
    `upload_hf.run_hub_upload`; ModelScope always talks to the international
    `www.modelscope.ai` domain.
    """

    provider = "modelscope"

    # modelscope_hub reads file-like payloads into bytes before transferring,
    # so no per-chunk callback can fire during the transfer (see the boundary
    # notifications in upload_one); the shared pipeline compensates with an
    # explicit hash pass + an indeterminate transfer bar in the UI.
    streams_upload_progress = False

    def __init__(self, token: str, repo_id: str):
        self._token = token
        self._repo_id = repo_id

    def make_api(self, token: str):
        from modelscope_hub import HubApi

        return HubApi(endpoint=MODELSCOPE_INTL_ENDPOINT, token=token)

    def ensure_repo(self, api, repo_id: str, private: bool) -> bool:
        created = False
        if not api.repo_exists(repo_id, "model"):
            api.create_repo(
                repo_id,
                "model",
                visibility="private" if private else "public",
            )
            created = True
        return created

    def upload_one(self, api, payload: _ProgressFile, in_repo: str):
        import os as _os

        # modelscope_hub reads file-like objects fully into bytes before the
        # transfer starts, so the wrapper's per-chunk reports never fire during
        # it (unlike huggingface_hub, which streams through read()). Report the
        # two honest boundaries instead: "transfer starting" (the bar returns to
        # this file's baseline and the phase flips to Uploading) and "transfer
        # finished" (upload_file returning means the commit landed). Without
        # them the bar would keep claiming the hash pass's 100% while the
        # transfer is still running.
        payload.notify(0, payload.size, PHASE_UPLOAD)
        api.upload_file(
            self._repo_id,
            "model",
            payload,
            in_repo,
            commit_message=f"Upload {_os.path.basename(in_repo)}",
            disable_tqdm=True,
        )
        payload.notify(payload.size, payload.size, PHASE_UPLOAD)
        # The hub consumed its own bytes copy; per-chunk transferred count is
        # unavailable, so report None (the completion event carries the totals).
        return None, False

    def file_url(self, repo_id: str, in_repo: str) -> str:
        return f"{MODELSCOPE_INTL_ENDPOINT}/models/{repo_id}/files/{in_repo}"

    def tree_url(self, repo_id: str, path_in_repo: str) -> str:
        return f"{MODELSCOPE_INTL_ENDPOINT}/models/{repo_id}/files/{path_in_repo}"


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
                            # modelscope_hub's UserInfo carries `username`
                            # (there is no `name` attribute on the dataclass).
                            "name": getattr(info, "username", None),
                            "fullname": getattr(info, "username", None),
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
        files, repo_id, path_in_repo, private = parse_upload_payload(data)
        return await _start_hub_upload(
            data, token, files, repo_id, path_in_repo, private, MsBackend(token, repo_id)
        )
