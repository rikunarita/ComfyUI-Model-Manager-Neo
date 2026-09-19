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

# In-flight hub uploads (Hugging Face AND ModelScope), keyed by task id.
#
# BUG FIX heritage: the upload used to run inside the HTTP handler, so
# ComfyUI's 60 s fetch abort / aiohttp handler cancellation killed multi-GB
# transfers. Uploads now return a task id immediately and run as background
# tasks; progress / completion / errors are websocket events handled
# module-wide in `hooks/hfUpload`, and the shared state survives closing and
# re-opening the dialog.
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
    """Update the bookkeeping entry of a task, tolerating a missing one."""
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

    huggingface_hub / modelscope_hub expose no per-chunk upload callback, so
    the transfer is fed through this wrapper whose read() reports the bytes
    actually handed to the uploader (sequential for regular/basic uploads,
    range-wise for LFS multipart - `tell()` stays monotonic in both).

    Trade-off, taken deliberately on user request: passing a file-like object
    makes the hubs use the classic basic/multipart transfer instead of the
    path-only xet protocol, which is the price of per-chunk accuracy here.
    """

    def __init__(self, path: str, on_progress) -> None:
        super().__init__()
        self._file = open(path, "rb")
        self._size = os.path.getsize(path)
        self._on_progress = on_progress
        self._saw_eof = False
        self._in_transfer = False
        # Bytes the consumer actually took during the transfer pass. Zero after
        # a completed upload means the hub deduplicated the blob (the identical
        # content was already in storage), which is exactly the "Upload 0 LFS
        # files" case: the commit still happens, but not one byte travels.
        self.transferred_bytes = 0

    # -- io.BufferedIOBase surface used by the hubs -------------------------
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

    @property
    def size(self) -> int:
        """Total bytes of the wrapped file."""
        return self._size

    def notify(self, sent: int, total: int, phase: str) -> None:
        """Emit a progress boundary by hand.

        Used by providers whose hub library exposes no per-chunk upload
        callback (modelscope_hub reads file-like objects into bytes before
        transferring, so the wrapper's read() never sees the transfer pass).
        """
        self._on_progress(sent, total, phase)

    def close(self) -> None:
        self._file.close()
        super().close()


def parse_upload_payload(data: dict) -> tuple[list[dict], str, str, bool]:
    """Validate an upload request into (files, repo_id, path_in_repo, private).

    One file (the classic single-model flow) or a whole list (folder batch
    upload from the selection bar); each entry keeps its folder-relative name
    so a batch preserves sub-folders inside the repository.
    """
    repo_id = (data.get("repoId") or "").strip()
    path_in_repo = (data.get("pathInRepo") or "").strip()
    private = bool(data.get("private", False))
    include_assets = bool(data.get("includeAssets", False))
    rename_notes = bool(data.get("renameNotesToReadme", False))

    if not repo_id:
        raise RuntimeError("Repository id is required")
    if not path_in_repo:
        raise RuntimeError("Destination path in repository is required")

    files: list[dict] = []

    def append_related_assets(local: str, in_repo: str) -> None:
        """Queue the model's sidecars (`<model name>.*`: previews and notes).

        They live next to the model on disk and land next to it in the
        repository (same directory as the model's destination path). With
        `renameNotesToReadme` the model's Markdown notes are committed as
        `README.md` (the hub's conventional readme name) instead of their
        local `<model name>.md` name.
        """
        repo_dir = in_repo.rsplit("/", 1)[0] if "/" in in_repo else ""
        local_dir = os.path.dirname(local)
        names: list[str] = []
        if include_assets:
            names += utils.get_model_all_previews(local)
        if include_assets or rename_notes:
            names += [n for n in utils.get_model_all_descriptions(local)]
        readme_done = False
        for name in names:
            asset_local = utils.join_path(local_dir, name)
            if not os.path.isfile(asset_local):
                continue
            repo_name = name
            if rename_notes and name.endswith(".md") and not readme_done:
                repo_name = "README.md"
                readme_done = True
            asset_repo = f"{repo_dir}/{repo_name}" if repo_dir else repo_name
            if any(entry["path_in_repo"] == asset_repo for entry in files):
                continue
            files.append({"local_path": asset_local, "path_in_repo": asset_repo})

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
            if include_assets or rename_notes:
                append_related_assets(local, f"{base}/{fname}")
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
        if include_assets or rename_notes:
            append_related_assets(local_path, path_in_repo)
    return files, repo_id, path_in_repo, private


class HubUploadBackend:
    """The provider-specific slice of a hub upload (HF / ModelScope)."""

    provider: str = "hf"

    #: True when the hub streams through `_ProgressFile.read()` so the transfer
    #: itself reports per-chunk progress (huggingface_hub). False for hubs that
    #: consume the payload opaquely (modelscope_hub reads file-like objects
    #: into bytes before transferring): the shared pipeline then runs an
    #: explicit hash pass for visible progress, and the UI renders the transfer
    #: phase as an indeterminate bar instead of a frozen percentage.
    streams_upload_progress: bool = True

    def make_api(self, token: str):
        raise NotImplementedError

    def ensure_repo(self, api, repo_id: str, private: bool) -> bool:
        """Create the repository when missing; True when it was created."""
        raise NotImplementedError

    def preflight(self, api, repo_id: str, in_repo: str, file_size: int, hash_fn):
        """Optional duplicate check before paying for a transfer; None = go."""
        return None

    def upload_one(self, api, payload: "_ProgressFile", in_repo: str):
        """Upload the payload; returns (transferred_bytes|None, oid_skipped)."""
        raise NotImplementedError

    def file_url(self, repo_id: str, in_repo: str) -> str:
        raise NotImplementedError

    def tree_url(self, repo_id: str, path_in_repo: str) -> str:
        return self.file_url(repo_id, path_in_repo)


async def run_hub_upload(
    *,
    task_id: str,
    token: str,
    files: list[dict],
    repo_id: str,
    path_in_repo: str,
    private: bool,
    total_size: int,
    backend: HubUploadBackend,
) -> None:
    """Sequential multi-file upload with cumulative progress, shared by every
    hub provider. Per file: optional duplicate preflight (no transfer attempt,
    explicit linkable answer), then the transfer through `_ProgressFile`.
    """
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
                    "provider": backend.provider,
                    "chunked": backend.streams_upload_progress,
                },
            ),
            loop,
        )

    repo_state: dict[str, Any] = {"ensured": False, "created": False}

    def ensure():
        api = backend.make_api(token)
        if not repo_state["ensured"]:
            repo_state["created"] = bool(backend.ensure_repo(api, repo_id, private))
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

        preflight = await loop.run_in_executor(
            utils.io_executor(),
            lambda: backend.preflight(ensure(), repo_id, in_repo, file_size, hash_local_file),
        )
        if preflight and preflight.get("status") == "duplicate":
            dup_count += 1
            first_url = first_url or preflight.get("url") or backend.file_url(repo_id, in_repo)
            completed_bytes += file_size
            await utils.send_json(
                "update_hf_upload_progress",
                {
                    "taskId": task_id,
                    "uploadedSize": float(completed_bytes),
                    "totalSize": float(total_size),
                    "progress": (completed_bytes / total_size * 100) if total_size else 100.0,
                    "phase": PHASE_UPLOAD,
                    "provider": backend.provider,
                    "chunked": backend.streams_upload_progress,
                },
            )
            continue

        # Hubs that consume the payload opaquely (modelscope_hub) never fire
        # per-chunk upload callbacks; run the hashing pass explicitly so the
        # bar shows real activity, and let the UI render the transfer itself
        # as indeterminate (see `streams_upload_progress`).
        if not backend.streams_upload_progress:
            await loop.run_in_executor(utils.io_executor(), hash_local_file)

        def _transfer():
            api = ensure()
            with _ProgressFile(local_path, report_progress) as payload:
                return backend.upload_one(api, payload, in_repo)

        try:
            transferred, oid_skipped = await loop.run_in_executor(
                utils.io_executor(), _transfer
            )
        except Exception as e:
            _set_task_field(task_id, status="error")
            await utils.send_json(
                "hf_upload_error",
                {"taskId": task_id, "error": str(e), "provider": backend.provider},
            )
            _forget_task(task_id)
            raise
        if transferred:
            transferred_total += int(transferred)
        if oid_skipped:
            skipped_count += 1
        first_url = first_url or backend.file_url(repo_id, in_repo)
        completed_bytes += file_size

    from urllib.parse import quote as _quote

    no_transfer = transferred_total == 0 and (dup_count + skipped_count) == len(files)
    all_skipped = no_transfer and (skipped_count > 0 or dup_count > 0)
    deduplicated = no_transfer and skipped_count == 0 and dup_count > 0
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
            "provider": backend.provider,
            "chunked": backend.streams_upload_progress,
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
            "url": first_url or backend.tree_url(repo_id, _quote(path_in_repo)),
            "fileCount": len(files),
            "skippedCount": skipped_count,
            "provider": backend.provider,
        },
    )
    _forget_task(task_id)


class HfBackend(HubUploadBackend):
    provider = "hf"

    def __init__(self, token: str, repo_id: str):
        self._token = token
        self._repo_id = repo_id

    def make_api(self, token: str):
        from huggingface_hub import HfApi

        return HfApi(token=token, library_name=LIBRARY_NAME)

    def ensure_repo(self, api, repo_id: str, private: bool) -> bool:
        created = False
        if not api.repo_exists(repo_id=repo_id):
            api.create_repo(repo_id=repo_id, private=private, exist_ok=True)
            created = True
        return created

    def preflight(self, api, repo_id: str, in_repo: str, file_size: int, hash_fn):
        """Detect an identical file at the destination BEFORE paying for a
        transfer attempt (the Hub's empty-commit skip is indistinguishable
        from a broken upload from the outside). Cheap-first: remote size, then
        the local hash only when sizes agree.
        """
        try:
            info = api.model_info(repo_id=repo_id, revision="main", files_metadata=True)
            target = None
            for sibling in getattr(info, "siblings", None) or []:
                if getattr(sibling, "rfilename", None) == in_repo:
                    target = sibling
                    break
            if target is None:
                return {"status": "go"}
            lfs = getattr(target, "lfs", None)
            remote_sha = getattr(lfs, "sha256", None) if lfs else None
            remote_size = getattr(lfs, "size", None) if lfs else getattr(target, "size", None)
            if not remote_sha:
                return {"status": "go"}
            if remote_size is not None and int(remote_size) != int(file_size):
                return {"status": "go"}
            if remote_sha == hash_fn():
                from urllib.parse import quote

                return {
                    "status": "duplicate",
                    "url": f"https://huggingface.co/{repo_id}/blob/main/{quote(in_repo)}",
                }
            return {"status": "go"}
        except Exception:
            return {"status": "go"}

    def upload_one(self, api, payload: _ProgressFile, in_repo: str):
        head_sha = None
        try:
            head_sha = api.repo_info(repo_id=self._repo_id, repo_type="model").sha
        except Exception:
            head_sha = None
        try:
            result = api.upload_file(
                path_or_fileobj=payload,
                path_in_repo=in_repo,
                repo_id=self._repo_id,
                repo_type="model",
                token=self._token,
            )
        except AttributeError as exc:
            # huggingface_hub's LFS batch validation reads
            # `response.get("actions", {}).get("upload")`, which raises
            # `'NoneType' object has no attribute 'get'` when the Hub answers
            # the git-lfs batch request with an explicit `"actions": null` -
            # the protocol's way of saying "this object is already in
            # storage". Retry once from the plain file path (xet route).
            if "NoneType" not in str(exc) or "has no attribute" not in str(exc):
                raise
            utils.print_warning(
                "LFS batch answered with a null action set; retrying through the file path."
            )
            result = api.upload_file(
                path_or_fileobj=payload._file.name,
                path_in_repo=in_repo,
                repo_id=self._repo_id,
                repo_type="model",
                token=self._token,
            )
            return None, False
        result_oid = getattr(result, "oid", None)
        oid_skipped = (
            head_sha is not None and result_oid is not None and str(result_oid) == str(head_sha)
        )
        return payload.transferred_bytes, oid_skipped

    def file_url(self, repo_id: str, in_repo: str) -> str:
        from urllib.parse import quote

        return f"https://huggingface.co/{repo_id}/blob/main/{quote(in_repo)}"

    def tree_url(self, repo_id: str, path_in_repo: str) -> str:
        from urllib.parse import quote

        return f"https://huggingface.co/{repo_id}/tree/main/{quote(path_in_repo)}"


class HfUploader:
    def add_routes(self, routes):

        @routes.get("/model-manager/hf/whoami")
        async def hf_whoami(request):
            """The authenticated Hugging Face user (token check for the UI)."""
            try:
                token = auth.get_hf_token()
                if not token:
                    return web.json_response(
                        {
                            "success": False,
                            "error": "Hugging Face token not set. Please set it in Settings > API Key.",
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
                error_msg = f"Hugging Face whoami failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.post("/model-manager/hf/upload")
        async def hf_upload(request):
            """Start a Hugging Face upload; answers with a task id immediately."""
            try:
                json_data = await request.json()
                task_id = await self.start_upload(json_data)
                return web.json_response({"success": True, "data": {"taskId": task_id}})
            except Exception as e:
                error_msg = f"Hugging Face upload failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

    async def start_upload(self, data: dict) -> str:
        token = auth.get_hf_token()
        if not token:
            raise RuntimeError(
                "Hugging Face token not set. Please set it in Settings > API Key."
            )
        files, repo_id, path_in_repo, private = parse_upload_payload(data)
        return await _start_hub_upload(
            data, token, files, repo_id, path_in_repo, private, HfBackend(token, repo_id)
        )


async def _start_hub_upload(
    data: dict,
    token: str,
    files: list[dict],
    repo_id: str,
    path_in_repo: str,
    private: bool,
    backend: HubUploadBackend,
) -> str:
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
            "provider": backend.provider,
            "chunked": backend.streams_upload_progress,
        },
    )

    # Shared pool with the download tasks: runs on the main loop, survives
    # any client disconnect, and keeps its duplicate-submit guard.
    pool = download.get_model_download().download_thread_pool
    pool.submit(
        run_hub_upload(
            task_id=task_id,
            token=token,
            files=files,
            repo_id=repo_id,
            path_in_repo=path_in_repo,
            private=private,
            total_size=total_size,
            backend=backend,
        ),
        task_id,
    )
    return task_id
