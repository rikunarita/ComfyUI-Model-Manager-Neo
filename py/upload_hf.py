import asyncio
import hashlib
import io
import os
import time
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


class _ProgressFile(io.BufferedIOBase):
    """Binary file wrapper reporting the bytes read by the consumer.

    Phase 1 (local hashing) is silenced: progress events only start after the
    consumer rewound the stream (the beginning of the real transfer), so the
    percentage shown in the UI is the transfer percentage, not the hash pass.

    BUG FIX: the wrapper must subclass `io.BufferedIOBase`. huggingface_hub
    validates `path_or_fileobj` with
    `isinstance(..., (str, bytes, io.BufferedIOBase))` and rejects any other
    file-like with "path_or_fileobj must be either an instance of str, bytes
    or io.BufferedIOBase" - a plain duck-typed object never reached the
    transfer at all (the upload died with a ValueError before any HTTP call).
    """

    def __init__(self, path: str, on_progress) -> None:
        super().__init__()
        self._file = open(path, "rb")
        self._size = os.path.getsize(path)
        self._on_progress = on_progress
        self._phase = 1
        self._saw_eof = False

    # -- io.BufferedIOBase surface used by huggingface_hub ------------------
    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        position = self._file.tell()
        if self._saw_eof and position == 0 and self._phase == 1:
            # Rewind after a full pass: the hashing pass is over, the
            # transfer is starting.
            self._phase = 2
            self._on_progress(0, self._size)
        data = self._file.read(size)
        if self._phase == 2:
            self._on_progress(self._file.tell(), self._size)
        if not data or self._file.tell() >= self._size:
            self._saw_eof = True
        return data

    def seek(self, *args) -> int:
        return self._file.seek(*args)

    def tell(self) -> int:
        return self._file.tell()

    def close(self) -> None:
        self._file.close()
        super().close()


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

        progress_state = {"last": 0.0}

        def report_progress(sent_bytes: int, total_bytes: int) -> None:
            """Marshal an accurate progress push back onto the main loop."""
            now = time.time()
            if now - progress_state["last"] < 0.4 and sent_bytes not in (0, total_bytes):
                return
            progress_state["last"] = now
            progress = (sent_bytes / total_bytes * 100) if total_bytes > 0 else 0.0
            asyncio.run_coroutine_threadsafe(
                utils.send_json(
                    "update_hf_upload_progress",
                    {
                        "taskId": task_id,
                        "uploadedSize": float(sent_bytes),
                        "totalSize": float(total_bytes),
                        "progress": progress,
                    },
                ),
                loop,
            )

        # HEAD sha before the transfer: huggingface_hub "succeeds" on an
        # unchanged file (it skips the empty commit and returns a CommitInfo
        # built from the EXISTING head), which used to be reported to the UI
        # as a plain successful upload - a silent no-op that looked exactly
        # like a broken upload. Comparing the oids makes the no-op visible.
        head_before = {"sha": None}

        def blob_url() -> str:
            from urllib.parse import quote

            return (
                f"https://huggingface.co/{repo_id}/blob/main/"
                f"{quote(path_in_repo)}"
            )

        def preflight():
            """Detect an identical file at the destination BEFORE paying for
            a transfer attempt.

            The Hub rejects re-uploads of unchanged content with an empty-commit
            skip ("Upload 0 LFS files" + "No files have been modified since last
            commit"), which from the outside is indistinguishable from a broken
            upload. Comparing the local sha256 with the sha256 of the remote
            tree entry turns that silent no-op into an explicit, linkable
            answer. Any failure here degrades to "go" so a real upload is
            never blocked by the check itself.
            """
            try:
                digest = hashlib.sha256()
                with open(local_path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                local_sha = digest.hexdigest()
                local_size = os.path.getsize(local_path)

                api = HfApi(token=token, library_name="ComfyUI-Model-Manager-Neo")
                info = api.model_info(
                    repo_id=repo_id, revision="main", files_metadata=True
                )
                for sibling in getattr(info, "siblings", None) or []:
                    if getattr(sibling, "rfilename", None) != path_in_repo:
                        continue
                    lfs = getattr(sibling, "lfs", None)
                    remote_sha = getattr(lfs, "sha256", None) if lfs else None
                    remote_size = (
                        getattr(lfs, "size", None)
                        if lfs
                        else getattr(sibling, "size", None)
                    )
                    if (
                        remote_sha
                        and remote_sha == local_sha
                        and remote_size in (None, local_size)
                    ):
                        return "duplicate", blob_url()
                return "go", None
            except Exception:
                return "go", None

        def do_upload():
            api = HfApi(token=token, library_name="ComfyUI-Model-Manager-Neo")

            # Create the repository when it does not exist.
            # The private flag only applies on creation.
            if not api.repo_exists(repo_id=repo_id):
                api.create_repo(repo_id=repo_id, private=private, exist_ok=True)
            try:
                head_before["sha"] = api.repo_info(
                    repo_id=repo_id, repo_type="model"
                ).sha
            except Exception:
                head_before["sha"] = None

            # BUG FIX: accurate upload progress.
            #
            # huggingface_hub exposes no per-chunk upload callback, so the UI
            # could only ever show 0% -> 100% (an indeterminate sweep in
            # between): "the exact progress is never displayed".
            #
            # The transfer is therefore fed through `_ProgressFile`, a thin
            # file-like wrapper whose read() reports the bytes actually
            # handed to the uploader. Two read passes happen per upload:
            #   1. huggingface_hub hashes the payload locally
            #      (UploadInfo.from_fileobj - fast, disk bound);
            #   2. the network transfer reads the payload again.
            # The wrapper detects the rewind between them and only reports
            # progress for pass 2, so the percentage tracks the real transfer
            # (sequential for regular/basic uploads, range-wise for LFS
            # multipart - `tell()` stays monotonic in both).
            #
            # Trade-off, taken deliberately on user request: passing a
            # file-like object makes huggingface_hub use the classic
            # basic/multipart transfer instead of the path-only hf_xet
            # protocol, which is the price of per-chunk accuracy here.
            with _ProgressFile(local_path, report_progress) as payload:
                return api.upload_file(
                    path_or_fileobj=payload,
                    path_in_repo=path_in_repo,
                    repo_id=repo_id,
                    repo_type="model",
                    token=token,
                )

        # Short-circuit re-uploads of identical content: no transfer attempt,
        # no confusing "0 LFS files" round-trips - just the explicit answer
        # with a link to the file that already lives in the repository.
        duplicate, duplicate_url = await loop.run_in_executor(None, preflight)
        if duplicate == "duplicate":
            HF_UPLOAD_TASKS[task_id]["status"] = "skipped"
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
                {
                    "taskId": task_id,
                    "repoId": repo_id,
                    "pathInRepo": path_in_repo,
                    "skipped": True,
                    "url": duplicate_url,
                },
            )
            return

        try:
            result = await loop.run_in_executor(None, do_upload)
        except Exception as e:
            HF_UPLOAD_TASKS[task_id]["status"] = "error"
            await utils.send_json(
                "hf_upload_error",
                {"taskId": task_id, "error": str(e)},
            )
            raise

        # An unchanged file (same content at the same path) makes
        # huggingface_hub skip the empty commit and return the EXISTING head
        # sha - surface that as an explicit "skipped" completion instead of a
        # silent success.
        result_oid = getattr(result, "oid", None)
        skipped = (
            head_before["sha"] is not None
            and result_oid is not None
            and str(result_oid) == str(head_before["sha"])
        )
        HF_UPLOAD_TASKS[task_id]["status"] = "skipped" if skipped else "complete"
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
            {
                "taskId": task_id,
                "repoId": repo_id,
                "pathInRepo": path_in_repo,
                "skipped": skipped,
                "url": blob_url() if skipped else None,
            },
        )
