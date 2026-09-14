import asyncio
import hashlib
import io
import os
import time
import uuid
from typing import Any

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

# Bookkeeping only; bounded so a long-running ComfyUI session cannot grow it
# without limit.
HF_UPLOAD_TASKS_LIMIT = 64

LIBRARY_NAME = "ComfyUI-Model-Manager-Neo"

# Upload phases, reported to the UI so the progress read-out can say what the
# extension is actually doing instead of sitting on a motionless 0%.
PHASE_PREPARE = "prepare"
PHASE_HASH = "hash"
PHASE_UPLOAD = "upload"


def _set_task_field(task_id: str, **fields) -> None:
    """Update the bookkeeping entry of a task, tolerating a missing one.

    BUG FIX: `HF_UPLOAD_TASKS[task_id]["status"] = ...` raised `KeyError`
    whenever the entry was gone (or never created), which turned a perfectly
    finished upload into an `hf_upload_error` push. Bookkeeping must never be
    able to fail the transfer it describes.
    """
    entry = HF_UPLOAD_TASKS.get(task_id)
    if entry is None:
        return
    entry.update(fields)


def _forget_task(task_id: str) -> None:
    """Drop finished tasks once the bookkeeping table grows too large."""
    HF_UPLOAD_TASKS.pop(task_id, None)
    while len(HF_UPLOAD_TASKS) > HF_UPLOAD_TASKS_LIMIT:
        oldest = next(iter(HF_UPLOAD_TASKS))
        HF_UPLOAD_TASKS.pop(oldest, None)


class _ProgressFile(io.BufferedIOBase):
    """Binary file wrapper reporting the bytes read by the consumer.

    huggingface_hub reads the payload twice per upload:
      1. `UploadInfo.from_fileobj()` hashes it locally (disk bound, no bytes
         leave the machine);
      2. the network transfer reads it again.
    Only pass 2 counts as "uploaded", so the percentage shown in the UI is the
    transfer percentage and not the hash pass. Pass 1 is reported separately
    through the `hash` phase, which is what makes the read-out move during the
    (often minutes-long) hashing of a multi-gigabyte model instead of sitting
    on 0%.

    BUG FIX: the wrapper must subclass `io.BufferedIOBase`. huggingface_hub
    validates `path_or_fileobj` with
    `isinstance(..., (str, bytes, io.BufferedIOBase))` and rejects any other
    file-like with "path_or_fileobj must be either an instance of str, bytes
    or io.BufferedIOBase" - a plain duck-typed object never reached the
    transfer at all (the upload died with a ValueError before any HTTP call).

    BUG FIX: the hash pass used to be detected as "the stream was rewound to
    position 0 after EOF". `UploadInfo.from_fileobj()` starts with
    `fileobj.read(512)`, so for any file of 512 bytes or less that very first
    sample read already reached EOF and the *hashing* pass was mistaken for
    the transfer. The phase now flips on the first true EOF (a `read()` that
    returned no data), which `sha_fileobj()` always produces and the 512-byte
    sample never does.
    """

    def __init__(self, path: str, on_progress) -> None:
        super().__init__()
        self._file = open(path, "rb")
        self._size = os.path.getsize(path)
        self._on_progress = on_progress
        self._saw_eof = False
        self._in_transfer = False
        # Bytes the consumer actually took during the transfer pass. Zero after
        # a completed upload means HuggingFace deduplicated the blob (the
        # identical content was already in the repository's LFS storage), which
        # is exactly the "Upload 0 LFS files" case: the commit still happens,
        # but not one byte travels. The UI reports that honestly instead of
        # claiming a transfer that never ran.
        self.transferred_bytes = 0

    # -- io.BufferedIOBase surface used by huggingface_hub ------------------
    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def read(self, size: int | None = -1) -> bytes:
        if self._saw_eof and not self._in_transfer:
            # A full pass finished and the consumer rewound: the hashing pass
            # is over, the transfer is starting.
            self._in_transfer = True
            self._on_progress(0, self._size, PHASE_UPLOAD)
        data = self._file.read(size)
        if self._in_transfer:
            position = self._file.tell()
            self.transferred_bytes = max(self.transferred_bytes, position)
            self._on_progress(position, self._size, PHASE_UPLOAD)
        if not data:
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
                    utils.io_executor(), lambda: HfApi(token=token).whoami()
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
        if model_type is None or fullname is None:
            raise RuntimeError("type and fullname are required")
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
                "phase": PHASE_PREPARE,
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

        loop = asyncio.get_running_loop()

        progress_state: dict[str, Any] = {"last": 0.0, "phase": None}

        def report_progress(sent_bytes: int, total_bytes: int, phase: str = PHASE_UPLOAD) -> None:
            """Marshal an accurate progress push back onto the main loop."""
            now = time.time()
            phase_changed = phase != progress_state["phase"]
            boundary = sent_bytes in (0, total_bytes)
            if not phase_changed and not boundary and now - progress_state["last"] < 0.4:
                return
            progress_state["last"] = now
            progress_state["phase"] = phase
            progress = (sent_bytes / total_bytes * 100) if total_bytes > 0 else 0.0
            asyncio.run_coroutine_threadsafe(
                utils.send_json(
                    "update_hf_upload_progress",
                    {
                        "taskId": task_id,
                        "uploadedSize": float(sent_bytes),
                        "totalSize": float(total_bytes),
                        "progress": progress,
                        "phase": phase,
                    },
                ),
                loop,
            )

        def blob_url() -> str:
            from urllib.parse import quote

            return f"https://huggingface.co/{repo_id}/blob/main/{quote(path_in_repo)}"

        def hash_local_file() -> str:
            """sha256 of the local file, with the hashing pass reported.

            BUG FIX: this pass used to run in complete silence. Hashing a
            multi-gigabyte checkpoint takes minutes, during which the UI showed
            a motionless 0% bar - the single most common reason an upload looks
            like it "never started".
            """
            digest = hashlib.sha256()
            read_bytes = 0
            with open(local_path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                    read_bytes += len(chunk)
                    report_progress(read_bytes, total_size, PHASE_HASH)
            return digest.hexdigest()

        def fetch_remote_entry():
            """The tree entry at the destination, if the repo answers at all."""
            api = HfApi(token=token, library_name=LIBRARY_NAME)
            info = api.model_info(
                repo_id=repo_id, revision="main", files_metadata=True
            )
            for sibling in getattr(info, "siblings", None) or []:
                if getattr(sibling, "rfilename", None) == path_in_repo:
                    return sibling
            return None

        async def preflight():
            """Detect an identical file at the destination BEFORE paying for
            a transfer attempt.

            The Hub rejects re-uploads of unchanged content with an empty-commit
            skip ("Upload 0 LFS files" + "No files have been modified since last
            commit"), which from the outside is indistinguishable from a broken
            upload. Comparing the local sha256 with the sha256 of the remote
            tree entry turns that silent no-op into an explicit, linkable
            answer. Any failure here degrades to "go" so a real upload is
            never blocked by the check itself.

            The comparison is ordered cheap-first: the remote size is already in
            the tree listing, and a size mismatch can never be the same content,
            so the (expensive) local hash pass only runs when the sizes agree -
            and that pass runs on the cpu pool while the Hub round-trip runs on
            the io pool (optimizations A-4 / A-8).
            """
            try:
                target = await loop.run_in_executor(utils.io_executor(), fetch_remote_entry)
                if target is None:
                    return {"status": "go"}

                lfs = getattr(target, "lfs", None)
                remote_sha = getattr(lfs, "sha256", None) if lfs else None
                remote_size = (
                    getattr(lfs, "size", None) if lfs else getattr(target, "size", None)
                )
                if not remote_sha:
                    return {"status": "go"}
                if remote_size is not None and int(remote_size) != int(total_size):
                    return {"status": "go"}

                local_sha = await loop.run_in_executor(utils.cpu_executor(), hash_local_file)
                if remote_sha == local_sha:
                    return {"status": "duplicate", "url": blob_url()}
                return {"status": "go"}
            except Exception:
                return {"status": "go"}

        def do_upload():
            api = HfApi(token=token, library_name=LIBRARY_NAME)

            # Create the repository when it does not exist.
            # The private flag only applies on creation.
            created = False
            if not api.repo_exists(repo_id=repo_id):
                api.create_repo(repo_id=repo_id, private=private, exist_ok=True)
                created = True
            head_sha = None
            try:
                head_sha = api.repo_info(repo_id=repo_id, repo_type="model").sha
            except Exception:
                head_sha = None

            # BUG FIX: accurate upload progress.
            #
            # huggingface_hub exposes no per-chunk upload callback, so the UI
            # could only ever show 0% -> 100% (an indeterminate sweep in
            # between): "the exact progress is never displayed".
            #
            # The transfer is therefore fed through `_ProgressFile`, a thin
            # file-like wrapper whose read() reports the bytes actually
            # handed to the uploader (sequential for regular/basic uploads,
            # range-wise for LFS multipart - `tell()` stays monotonic in both).
            #
            # Trade-off, taken deliberately on user request: passing a
            # file-like object makes huggingface_hub use the classic
            # basic/multipart transfer instead of the path-only hf_xet
            # protocol, which is the price of per-chunk accuracy here.
            with _ProgressFile(local_path, report_progress) as payload:
                try:
                    # `_ProgressFile` is a BufferedIOBase: huggingface_hub's
                    # stubs only advertise BinaryIO, but the runtime validation
                    # accepts exactly this class, so the `type: ignore` below
                    # silences the overload mismatch without hiding a real bug.
                    result = api.upload_file(  # type: ignore[call-overload]
                        path_or_fileobj=payload,
                        path_in_repo=path_in_repo,
                        repo_id=repo_id,
                        repo_type="model",
                        token=token,
                    )
                except AttributeError as exc:
                    # huggingface_hub's LFS batch validation reads
                    # `response.get("actions", {}).get("upload")`, which raises
                    # `'NoneType' object has no attribute 'get'` when the Hub
                    # answers the git-lfs batch request with an explicit
                    # `"actions": null` - the protocol's way of saying "this
                    # object is already in storage". Nothing was transferred at
                    # that point, so retry once from the plain file path: that
                    # takes the hf_xet code path (no LFS batch round-trip) and
                    # completes the upload. Per-chunk progress is not available
                    # on that route, which the UI shows as an indeterminate bar.
                    if "NoneType" not in str(exc) or "has no attribute" not in str(exc):
                        raise
                    utils.print_warning(
                        "LFS batch answered with a null action set; retrying through the file path."
                    )
                    result = api.upload_file(
                        path_or_fileobj=local_path,
                        path_in_repo=path_in_repo,
                        repo_id=repo_id,
                        repo_type="model",
                        token=token,
                    )
                    # `None` = "not measurable", which must never be read as
                    # "zero bytes moved": the xet route really did transfer the
                    # file, it just exposes no per-chunk callback.
                    return result, created, head_sha, None
                return result, created, head_sha, payload.transferred_bytes

        # Short-circuit re-uploads of identical content: no transfer attempt,
        # no confusing "0 LFS files" round-trips - just the explicit answer
        # with a link to the file that already lives in the repository.
        preflight_result = await preflight()
        if preflight_result.get("status") == "duplicate":
            _set_task_field(task_id, status="skipped")
            await utils.send_json(
                "update_hf_upload_progress",
                {
                    "taskId": task_id,
                    "uploadedSize": float(total_size),
                    "totalSize": float(total_size),
                    "progress": 100.0,
                    "phase": PHASE_UPLOAD,
                },
            )
            await utils.send_json(
                "hf_upload_complete",
                {
                    "taskId": task_id,
                    "repoId": repo_id,
                    "pathInRepo": path_in_repo,
                    "skipped": True,
                    "deduplicated": True,
                    "transferredBytes": 0.0,
                    "created": False,
                    "private": private,
                    "url": preflight_result.get("url") or blob_url(),
                },
            )
            _forget_task(task_id)
            return

        try:
            result, created, head_sha, transferred = await loop.run_in_executor(
                utils.io_executor(), do_upload
            )
        except Exception as e:
            _set_task_field(task_id, status="error")
            await utils.send_json(
                "hf_upload_error",
                {"taskId": task_id, "error": str(e)},
            )
            _forget_task(task_id)
            raise

        # An unchanged file (same content at the same path) makes
        # huggingface_hub skip the empty commit and return the EXISTING head
        # sha - surface that as an explicit "skipped" completion instead of a
        # silent success.
        result_oid = getattr(result, "oid", None)
        skipped = (
            head_sha is not None
            and result_oid is not None
            and str(result_oid) == str(head_sha)
        )
        # A commit that moved no bytes means the Hub already held the blob and
        # deduplicated it ("Upload 0 LFS files"). The file is in the repository,
        # but reporting a plain "Success" next to a bar that never moved is what
        # made this look like a failed upload.
        deduplicated = not skipped and transferred is not None and int(transferred) == 0
        status = "skipped" if skipped else "complete"
        _set_task_field(
            task_id,
            status=status,
            transferredBytes=None if transferred is None else float(transferred),
            created=created,
        )
        # Final progress (100%) + completion; the UI settles on these events
        # instead of the HTTP round-trip.
        await utils.send_json(
            "update_hf_upload_progress",
            {
                "taskId": task_id,
                "uploadedSize": float(total_size),
                "totalSize": float(total_size),
                "progress": 100.0,
                "phase": PHASE_UPLOAD,
            },
        )
        await utils.send_json(
            "hf_upload_complete",
            {
                "taskId": task_id,
                "repoId": repo_id,
                "pathInRepo": path_in_repo,
                "skipped": skipped,
                "deduplicated": deduplicated,
                "transferredBytes": None if transferred is None else float(transferred),
                "created": created,
                "private": private,
                "url": blob_url() if (skipped or deduplicated) else None,
            },
        )
        _forget_task(task_id)
