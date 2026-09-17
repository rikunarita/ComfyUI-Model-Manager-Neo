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

        repo_id = (data.get("repoId") or "").strip()
        path_in_repo = (data.get("pathInRepo") or "").strip()
        private = bool(data.get("private", False))

        if not repo_id:
            raise RuntimeError("Repository id is required")
        if not path_in_repo:
            raise RuntimeError("Destination path in repository is required")

        # One file (the classic model-detail / single-model dialog flow) or a
        # whole list (folder batch upload from the selection bar). Each entry
        # keeps its folder-relative name so a batch preserves sub-folders
        # inside the repository.
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
        """Upload one or more files sequentially with cumulative progress.

        A single-entry `files` list reproduces the classic one-file flow
        byte-for-byte (same preflight, same skip/dedup answers, same events);
        a batch (folder upload) runs the same per-file pipeline in order and
        reports one aggregated completion.
        """
        try:
            from huggingface_hub import HfApi
        except ImportError:
            raise RuntimeError(
                "huggingface_hub is not installed. Please install it with: pip install huggingface_hub hf_xet"
            )

        loop = asyncio.get_running_loop()

        progress_state: dict[str, Any] = {"last": 0.0, "phase": None}
        completed_bytes = 0

        def report_progress(
            sent_bytes: int, file_total: int, phase: str = PHASE_UPLOAD
        ) -> None:
            """Marshal accurate cumulative progress back onto the main loop."""
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
                    },
                ),
                loop,
            )

        repo_state: dict[str, Any] = {"ensured": False, "created": False}

        def ensure_repo():
            api = HfApi(token=token, library_name=LIBRARY_NAME)
            if not repo_state["ensured"]:
                # Create the repository when it does not exist; the private
                # flag only applies on creation.
                if not api.repo_exists(repo_id=repo_id):
                    api.create_repo(repo_id=repo_id, private=private, exist_ok=True)
                    repo_state["created"] = True
                repo_state["ensured"] = True
            return api

        transferred_total = 0
        skipped_count = 0
        dup_count = 0
        first_url: str | None = None

        for item in files:
            local_path = item["local_path"]
            in_repo = item["path_in_repo"]
            file_size = os.path.getsize(local_path)

            def blob_url() -> str:
                from urllib.parse import quote

                return f"https://huggingface.co/{repo_id}/blob/main/{quote(in_repo)}"

            def hash_local_file() -> str:
                """sha256 of the local file, with the hashing pass reported."""
                digest = hashlib.sha256()
                read_bytes = 0
                with open(local_path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                        read_bytes += len(chunk)
                        report_progress(read_bytes, file_size, PHASE_HASH)
                return digest.hexdigest()

            def fetch_remote_entry():
                """The tree entry at the destination, if the repo answers."""
                api = HfApi(token=token, library_name=LIBRARY_NAME)
                info = api.model_info(repo_id=repo_id, revision="main", files_metadata=True)
                for sibling in getattr(info, "siblings", None) or []:
                    if getattr(sibling, "rfilename", None) == in_repo:
                        return sibling
                return None

            async def preflight():
                """Detect an identical file at the destination BEFORE paying
                for a transfer attempt (see the single-file design notes: the
                Hub's empty-commit skip is indistinguishable from a broken
                upload from the outside). Cheap-first: remote size, then the
                local hash on the cpu pool while the Hub round-trip runs on
                the io pool.
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
                    if remote_size is not None and int(remote_size) != int(file_size):
                        return {"status": "go"}

                    local_sha = await loop.run_in_executor(utils.cpu_executor(), hash_local_file)
                    if remote_sha == local_sha:
                        return {"status": "duplicate", "url": blob_url()}
                    return {"status": "go"}
                except Exception:
                    return {"status": "go"}

            def do_upload():
                api = ensure_repo()
                head_sha = None
                try:
                    head_sha = api.repo_info(repo_id=repo_id, repo_type="model").sha
                except Exception:
                    head_sha = None

                # Accurate progress through `_ProgressFile` (per-chunk reads);
                # the deliberate trade-off vs the path-only hf_xet route is
                # documented on the class.
                with _ProgressFile(local_path, report_progress) as payload:
                    try:
                        result = api.upload_file(
                            path_or_fileobj=payload,
                            path_in_repo=in_repo,
                            repo_id=repo_id,
                            repo_type="model",
                            token=token,
                        )
                    except AttributeError as exc:
                        # LFS batch answered with `"actions": null` ("object
                        # already in storage"): retry through the plain path
                        # (hf_xet route, no per-chunk progress).
                        if "NoneType" not in str(exc) or "has no attribute" not in str(exc):
                            raise
                        utils.print_warning(
                            "LFS batch answered with a null action set; retrying through the file path."
                        )
                        result = api.upload_file(
                            path_or_fileobj=local_path,
                            path_in_repo=in_repo,
                            repo_id=repo_id,
                            repo_type="model",
                            token=token,
                        )
                        return result, head_sha, None
                return result, head_sha, payload.transferred_bytes

            preflight_result = await preflight()
            if preflight_result.get("status") == "duplicate":
                dup_count += 1
                first_url = first_url or preflight_result.get("url") or blob_url()
                completed_bytes += file_size
                await utils.send_json(
                    "update_hf_upload_progress",
                    {
                        "taskId": task_id,
                        "uploadedSize": float(completed_bytes),
                        "totalSize": float(total_size),
                        "progress": (completed_bytes / total_size * 100) if total_size else 100.0,
                        "phase": PHASE_UPLOAD,
                    },
                )
                continue

            try:
                result, head_sha, transferred = await loop.run_in_executor(
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

            # An unchanged file makes huggingface_hub skip the empty commit
            # and return the EXISTING head sha - explicit "skipped" per file.
            result_oid = getattr(result, "oid", None)
            if head_sha is not None and result_oid is not None and str(result_oid) == str(head_sha):
                skipped_count += 1
            else:
                # `None` = "not measurable" (xet retry): count the whole file
                # so cumulative progress still reaches 100%.
                transferred_total += file_size if transferred is None else int(transferred)
            first_url = first_url or blob_url()
            completed_bytes += file_size

        from urllib.parse import quote as _quote

        all_skipped = skipped_count == len(files)
        all_dup = dup_count == len(files)
        deduplicated = (not all_skipped) and (transferred_total == 0) and (
            all_dup or (dup_count + skipped_count == len(files))
        )
        status = "skipped" if all_skipped else "complete"
        _set_task_field(
            task_id,
            status=status,
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
            },
        )
        await utils.send_json(
            "hf_upload_complete",
            {
                "taskId": task_id,
                "repoId": repo_id,
                "pathInRepo": path_in_repo,
                "skipped": all_skipped,
                "deduplicated": deduplicated,
                "transferredBytes": float(transferred_total),
                "created": repo_state["created"],
                "private": private,
                "url": first_url
                or f"https://huggingface.co/{repo_id}/tree/main/{_quote(path_in_repo)}",
                "fileCount": len(files),
                "skippedCount": skipped_count,
                "dupCount": dup_count,
            },
        )
        _forget_task(task_id)
