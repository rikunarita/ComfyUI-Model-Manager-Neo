import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import folder_paths
import yaml
from aiohttp import web

from . import utils


def _preview_field_keys(model_data: dict) -> list[str]:
    """`previewFile`, `previewFile2`, ... in gallery order."""
    keys = []
    for key in model_data:
        if key == "previewFile":
            keys.append((0, key))
        elif key.startswith("previewFile") and key[len("previewFile") :].isdigit():
            keys.append((int(key[len("previewFile") :]), key))
    return [key for _, key in sorted(keys)]


_MODEL_PAGE_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)

# Notes front-matter is re-read on every library scan; on network storage the
# 4 KB head read per model file dominates the scan time (the "it takes ~20 s
# until a download shows up" complaint). Cache the parsed triple against the
# sidecar's (mtime_ns, size) so steady-state scans only pay a stat().
_SITE_CACHE: dict[str, tuple[int, int, str | None, str | None, str | None, str | None]] = {}
_SITE_CACHE_LIMIT = 4096


def _model_site_info_of(
    names: set[str], basename: str, directory: str, sub_folder: str
) -> tuple[str | None, str | None, str | None, str | None]:
    """The model page URL, platform, SHA256 and base model of the notes.

    Civitai / Hugging Face downloads store `modelPage`, `website`, `hashes` and
    `baseModel` in the YAML front-matter of the `.md` sidecar. Reading just that
    header (a few hundred bytes) at scan time is what lets the grid offer an
    "open model page" action - wearing the platform's logo as its background -
    and the download dialog its base-model compatibility warning, without
    loading every description in full.
    """
    candidate = f"{basename}.md"
    if candidate not in names:
        return None, None, None, None
    path = utils.join_path(directory, sub_folder, candidate) if sub_folder else utils.join_path(directory, candidate)
    try:
        st = os.stat(path)
    except OSError:
        return None, None, None, None
    hit = _SITE_CACHE.get(path)
    if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2], hit[3], hit[4], hit[5]
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4096)
    except OSError:
        return None, None, None, None
    match = _MODEL_PAGE_RE.match(head)
    if not match:
        return None, None, None, None
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except Exception:
        return None, None, None, None
    if not isinstance(meta, dict):
        return None, None, None, None
    page = meta.get("modelPage")
    platform = meta.get("website")
    hashes = meta.get("hashes")
    sha = hashes.get("SHA256") if isinstance(hashes, dict) else None
    base = meta.get("baseModel")
    parsed = (
        page if isinstance(page, str) and page.startswith("http") else None,
        platform if isinstance(platform, str) and platform.strip() else None,
        sha.upper() if isinstance(sha, str) and sha.strip() else None,
        base if isinstance(base, str) and base.strip() else None,
    )
    _SITE_CACHE[path] = (st.st_mtime_ns, st.st_size, *parsed)
    while len(_SITE_CACHE) > _SITE_CACHE_LIMIT:
        _SITE_CACHE.pop(next(iter(_SITE_CACHE)))
    return parsed


class ModelManager:
    def add_routes(self, routes):

        @routes.get("/model-manager/base-folders")
        @utils.deprecated(reason="Use `/model-manager/models` instead.")
        async def get_model_paths(request):
            """
            Returns the base folders for models.
            """
            model_base_paths = utils.resolve_model_base_paths()
            return web.json_response({"success": True, "data": model_base_paths})

        @routes.get("/model-manager/models")
        async def get_folders(request):
            """
            Returns the base folders for models.
            """
            try:
                result = utils.resolve_model_base_paths()
                return web.json_response({"success": True, "data": result})
            except Exception as e:
                error_msg = f"Read models failed: {e!s}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.get("/model-manager/models/{folder}")
        async def get_folder_models(request):
            try:
                folder = request.match_info.get("folder", None)
                # BUG FIX: listing a model folder stats every file in it. Doing
                # that inside the handler blocked the server event loop, so the
                # whole UI (websocket updates included) froze on every refresh.
                # Resolve the request-scoped setting here and run the walk in
                # the executor.
                include_hidden_files = utils.get_setting_value(request, "model_list.include_hidden_files", False)
                loop = asyncio.get_running_loop()
                results = await loop.run_in_executor(
                    utils.io_executor(), self.scan_models, folder, include_hidden_files
                )
                return web.json_response({"success": True, "data": results})
            except Exception as e:
                error_msg = f"Read models failed: {e!s}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.get("/model-manager/model/{type}/{index}/{filename:.*}")
        async def get_model_info(request):
            """
            Get the information of the specified model.
            """
            model_type = request.match_info.get("type", None)
            path_index = int(request.match_info.get("index", None))
            filename = request.match_info.get("filename", None)

            try:
                model_path = utils.get_valid_full_path(model_type, path_index, filename)
                # BUG FIX: get_valid_full_path() returns None for a file that
                # no longer exists (e.g. the model was renamed by a ZipNN
                # compress/decompress while this dialog was open), and
                # get_model_info() then died with `os.path.dirname(None)` ->
                # "expected str, bytes or os.PathLike object, not NoneType".
                # The PUT/DELETE routes already had this guard; the GET did not.
                if model_path is None:
                    raise RuntimeError(f"File {filename} not found")
                # BUG FIX: get_model_info() parses the model's safetensors JSON
                # header (hundreds of milliseconds on MoE models with
                # multi-megabyte headers) and reads the notes sidecar - all
                # blocking calls. Running them inline froze the server event
                # loop for the whole parse, websocket progress updates
                # included. The scan/hygiene/update routes already had this
                # fix; the model-detail GET was the last blocking handler.
                # Same treatment: run it in the executor.
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(utils.io_executor(), self.get_model_info, model_path)
                return web.json_response({"success": True, "data": result})
            except Exception as e:
                error_msg = f"Read model info failed: {e!s}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.get("/model-manager/model-file/{type}/{index}/{filename:.*}")
        async def download_model_file(request):
            """Stream a saved model file to the browser as an attachment.

            The "download to local" action of the model detail window: the
            file is served verbatim with ``Content-Disposition: attachment``
            whose filename is the model name as-is (RFC 5987 ``filename*``
            for non-ASCII names), so the browser saves it under exactly the
            name it carries in the library. Same realpath containment guard
            as the preview route.
            """
            model_type = request.match_info.get("type", None)
            path_index = int(request.match_info.get("index", None))
            filename = request.match_info.get("filename", None)
            try:
                model_path = utils.get_valid_full_path(model_type, path_index, filename)
                if model_path is None:
                    raise web.HTTPNotFound()
            except web.HTTPNotFound:
                raise
            except Exception as exc:
                raise web.HTTPNotFound() from exc
            base = os.path.basename(model_path)
            ascii_name = base.encode("ascii", "replace").decode("ascii")
            disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(base, safe='._-')}"
            return web.FileResponse(model_path, headers={"Content-Disposition": disposition})

        @routes.get("/model-manager/hygiene")
        async def hygiene_scan(request):
            """Local hygiene report: orphaned sidecars and empty folders.

            Name-set based only (no hashing, no network): a sidecar (preview
            image/video or `.md`/`.txt` notes) is an orphan when no model in
            the same directory claims it, and a folder is empty when it holds
            neither model files nor sub-folders.
            """
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(utils.io_executor(), self.scan_hygiene)
            return web.json_response({"success": True, "data": result})

        @routes.get("/model-manager/disk-free/{type}/{index}")
        async def get_disk_free(request):
            """Free bytes of the volume holding a model folder (download guard)."""
            import shutil

            model_type = request.match_info.get("type", None)
            path_index = int(request.match_info.get("index", 0))
            try:
                folders = utils.resolve_model_base_paths().get(model_type, [])
                if path_index >= len(folders):
                    raise RuntimeError("PathIndex out of range")
                usage = shutil.disk_usage(folders[path_index])
                return web.json_response({"success": True, "data": {"free": usage.free}})
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})

        @routes.put("/model-manager/model/{type}/{index}/{filename:.*}")
        async def update_model(request):
            """
            Update model information.

            request body: x-www-form-urlencoded
            - previewFile: preview file.
            - description: description.
            - type: model type.
            - pathIndex: index of the model folders.
            - fullname: filename that relative to the model folder.
            All fields are optional, but type, pathIndex and fullname must appear together.
            """
            model_type = request.match_info.get("type", None)
            index_raw = request.match_info.get("index", None)
            filename = request.match_info.get("filename", None)
            if index_raw is None or model_type is None or filename is None:
                raise RuntimeError("Invalid model route parameters")
            path_index = int(index_raw)

            model_data = await request.post()
            model_data = dict(model_data)

            try:
                model_path = utils.get_valid_full_path(model_type, path_index, filename)
                if model_path is None:
                    raise RuntimeError(f"File {filename} not found")
                # BUG FIX: update_model() can download a preview over HTTP
                # (save_model_preview with a URL string - the new client-side
                # fetch fallback) and re-encode images with PIL, all blocking
                # calls. Running them inline froze the server event loop for
                # the whole operation (and deadlocks outright when the preview
                # URL points back at ComfyUI itself). Same treatment as the
                # other blocking handlers: run in the executor.
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(utils.io_executor(), self.update_model, model_path, model_data)
                return web.json_response({"success": True})
            except Exception as e:
                error_msg = f"Update model failed: {e!s}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.delete("/model-manager/model/{type}/{index}/{filename:.*}")
        async def delete_model(request):
            """
            Delete model (or, when the path is a directory, a whole folder -
            the selection mode offers folders as deletable items).
            """
            model_type = request.match_info.get("type", None)
            path_index = int(request.match_info.get("index", None))
            filename = request.match_info.get("filename", None)

            try:
                if not filename or filename in (".", ".."):
                    raise RuntimeError("Invalid path")
                full_path = utils.get_full_path(model_type, path_index, filename)
                if os.path.isdir(full_path):
                    # Folder delete (selection mode): recursive, and only
                    # inside the model-type root (get_full_path guarantees
                    # containment; the type root itself is refused).
                    base = utils.resolve_model_base_paths().get(model_type, [])
                    if path_index < len(base) and utils.normalize_path(full_path) == utils.normalize_path(
                        base[path_index]
                    ):
                        raise RuntimeError("The model-type root folder cannot be deleted")
                    self.remove_folder(full_path)
                    return web.json_response({"success": True})
                model_path = utils.get_valid_full_path(model_type, path_index, filename)
                if model_path is None:
                    raise RuntimeError(f"File {filename} not found")
                self.remove_model(model_path)
                return web.json_response({"success": True})
            except Exception as e:
                error_msg = f"Delete model failed: {e!s}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.post("/model-manager/create-folder")
        async def create_folder(request):
            """Create a new (sub-)folder inside a model folder (folder view)."""
            data = await utils.get_request_body(request)
            model_type = data.get("type")
            path_index = int(data.get("pathIndex") or 0)
            sub_folder = (data.get("subFolder") or "").strip("/")
            name = (data.get("name") or "").strip().strip("/")
            if not model_type or not name:
                return web.json_response({"success": False, "error": "type and name are required"})
            segments = name.split("/")
            if any(segment in ("", ".", "..") for segment in segments) or any(ch in name for ch in '\\:*?"<>|'):
                return web.json_response({"success": False, "error": f"Invalid folder name: {name}"})
            if segments[-1].endswith(utils.ZNN_FOLDER_SUFFIX) or segments[-1].endswith(utils.DELTA_FOLDER_SUFFIX):
                return web.json_response(
                    {
                        "success": False,
                        "error": (
                            f"Names ending in {utils.ZNN_FOLDER_SUFFIX} / "
                            f"{utils.DELTA_FOLDER_SUFFIX} are reserved for ZipNN"
                        ),
                    }
                )
            relative = utils.join_path(sub_folder, name) if sub_folder else name
            try:
                target = utils.get_full_path(model_type, path_index, relative)
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})
            if os.path.exists(target):
                return web.json_response({"success": False, "error": f"Already exists: {name}"})
            try:
                os.makedirs(target)
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})
            return web.json_response({"success": True})

    def scan_models(self, folder: str, include_hidden_files: bool = False):
        result = []

        folders, *_ = folder_paths.folder_names_and_paths[folder]

        def get_file_info(
            entry: os.DirEntry[str],
            base_path: str,
            path_index: int,
            dir_names: dict[str, set[str]],
        ):
            prefix_path = utils.normalize_path(base_path)
            if not prefix_path.endswith("/"):
                prefix_path = f"{prefix_path}/"

            is_file = entry.is_file()
            relative_path = utils.normalize_path(entry.path).replace(prefix_path, "")
            sub_folder = os.path.dirname(relative_path)
            filename = os.path.basename(relative_path)
            basename = os.path.splitext(filename)[0] if is_file else filename
            extension = os.path.splitext(filename)[1] if is_file else ""

            model_preview: str | list[str] | None = None
            if is_file:
                # Resolve previews against the directory's
                # name set collected during the walk - zero extra stat() calls
                # per model (the old code probed up to 16 candidate names with
                # os.path.isfile for every single file).
                names = dir_names.get(os.path.dirname(entry.path), set())
                preview_names = utils.previews_in_names(names, basename)
                if not preview_names:
                    # No preview on disk: point straight at the default
                    # NO-PREVIEW.svg artwork instead of a URL that only
                    # worked through the old server-side fallback.
                    model_preview = utils.NO_PREVIEW_URL
                else:
                    urls = []
                    for preview_name in preview_names:
                        # BUG FIX: the preview URL used to be derived by
                        # swapping the model's trailing extension, which mapped
                        # EVERY preview of a model onto the primary preview's
                        # path (a gallery collapsed into N copies of one URL).
                        # The preview file's own name, joined onto the model's
                        # directory, is the correct relative path.
                        preview_relative = f"{sub_folder}/{preview_name}" if sub_folder else preview_name
                        urls.append(f"/model-manager/preview/{folder}/{path_index}/{preview_relative}")
                    # One preview stays a plain string (the historic shape every
                    # consumer compares with ===); a gallery becomes a list so
                    # the carousel / lightbox can page through all of it.
                    model_preview = urls[0] if len(urls) == 1 else urls

            if not os.path.exists(entry.path):
                utils.print_error(f"{entry.path} is not file or directory.")
                return None

            try:
                stat = entry.stat()
            except OSError:
                # The entry vanished between the walk and this stat (files do
                # get moved/deleted while a scan runs): skip it instead of
                # failing the whole listing.
                return None
            model_page, model_platform, model_sha, model_base = (
                _model_site_info_of(names, basename, directory=base_path, sub_folder=sub_folder)
                if is_file
                else (None, None, None, None)
            )
            return {
                "type": folder,
                "subFolder": sub_folder,
                "isFolder": not is_file,
                "basename": basename,
                "extension": extension,
                "pathIndex": path_index,
                "sizeBytes": stat.st_size if is_file else 0,
                "preview": model_preview,
                "modelPage": model_page,
                # `website` of the notes front-matter: drives the platform logo
                # on the "open model page" button and the Information table.
                "modelPlatform": model_platform,
                # SHA256 recorded in the notes front-matter (Civitai downloads):
                # powers the duplicate-model warning without any hashing pass.
                "modelSha256": model_sha,
                # baseModel of the notes front-matter (download-dialog warning)
                "modelBase": model_base,
                "createdAt": round(stat.st_ctime_ns / 1000000),
                "updatedAt": round(stat.st_mtime_ns / 1000000),
            }

        def get_all_files_entry(directory: str, dir_names: dict[str, set[str]]):
            """Collect model entries and, for free, every directory's name set
            (used for zero-stat preview resolution)."""
            entries: list[os.DirEntry[str]] = []
            if not os.path.exists(directory):
                return entries
            names: set[str] = set()
            with os.scandir(directory) as it:
                for entry in it:
                    names.add(entry.name)
                    if not include_hidden_files and entry.name.startswith("."):
                        continue

                    if entry.is_file():
                        extension = os.path.splitext(entry.name)[1]
                        if extension in folder_paths.supported_pt_extensions:
                            entries.append(entry)
                    else:
                        entries.append(entry)
                        entries.extend(get_all_files_entry(entry.path, dir_names))
            dir_names[directory] = names
            return entries

        BATCH_SIZE = 200
        MAX_WORKERS = min(4, os.cpu_count() or 1)

        for path_index, base_path in enumerate(folders):
            if not os.path.exists(base_path):
                continue
            dir_names: dict[str, set[str]] = {}
            file_entries = get_all_files_entry(base_path, dir_names)

            for i in range(0, len(file_entries), BATCH_SIZE):
                batch = file_entries[i : i + BATCH_SIZE]
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = [
                        executor.submit(get_file_info, entry, base_path, path_index, dir_names) for entry in batch
                    ]
                    # Collect in SUBMISSION order (not as_completed): the walk
                    # order is stable, so the listing the client receives does
                    # not reshuffle between refreshes (the grid's "recently
                    # used" sort keeps ties in listing order).
                    for future in futures:
                        file_info = future.result()
                        if file_info is not None:
                            result.append(file_info)

        return result

    def scan_hygiene(self):
        orphans: list[dict] = []
        empty: list[dict] = []
        for model_type, bases in utils.resolve_model_base_paths().items():
            for index, base in enumerate(bases):
                if not os.path.isdir(base):
                    continue
                for dirpath, dirnames, filenames in os.walk(base):
                    rel = os.path.relpath(dirpath, base)
                    rel = "" if rel == "." else utils.normalize_path(rel)
                    model_files: set[str] = set()
                    model_bases: set[str] = set()
                    for name in filenames:
                        ext = os.path.splitext(name)[1]
                        if ext in folder_paths.supported_pt_extensions:
                            model_files.add(name)
                            model_bases.add(os.path.splitext(name)[0])
                    candidates: set[str] = set()
                    for mb in model_bases:
                        candidates.update(utils.preview_candidates(mb))
                        candidates.add(f"{mb}.md")
                        candidates.add(f"{mb}.txt")
                    for name in filenames:
                        if name.startswith("."):
                            continue
                        ext = os.path.splitext(name)[1]
                        sidecar = ext in utils.PREVIEW_EXTENSIONS or name.endswith((".md", ".txt"))
                        if sidecar and name not in candidates and name not in model_files:
                            fullname = f"{rel}/{name}" if rel else name
                            try:
                                size = os.stat(utils.join_path(dirpath, name)).st_size
                            except OSError:
                                size = 0
                            orphans.append(
                                {
                                    "type": model_type,
                                    "pathIndex": index,
                                    "fullname": fullname,
                                    "sizeBytes": size,
                                }
                            )
                    if rel and not model_files and not dirnames:
                        empty.append(
                            {
                                "type": model_type,
                                "pathIndex": index,
                                "fullname": rel,
                                "sizeBytes": 0,
                            }
                        )
        return {"orphans": orphans, "empty": empty}

    def get_model_info(self, model_path: str):
        directory = os.path.dirname(model_path)

        metadata = utils.get_model_metadata(model_path)
        tensors = utils.get_model_tensors(model_path)

        description_file = utils.get_model_description_name(model_path)
        description_file = utils.join_path(directory, description_file)
        description = None
        if os.path.isfile(description_file):
            with open(description_file, encoding="utf-8", newline="") as f:
                description = f.read()

        return {
            "metadata": metadata,
            "description": description,
            "tensors": tensors,
        }

    def update_model(self, model_path: str, model_data: dict):

        preview_keys = _preview_field_keys(model_data)
        if preview_keys:
            # The client sends the whole gallery as previewFile, previewFile2,
            # previewFile3, ... (feature: keep every preview). replace_model_
            # previews resolves every source BEFORE removing the old set, so
            # reorders never read a slot an earlier step already destroyed.
            items = [model_data[k] for k in preview_keys]
            entries = [i for i in items if not (type(i) is str and i in ("undefined", ""))]
            if entries:
                # Same mechanics as the download-completion path: resolve all
                # sources server-side, then rewrite the set in order. A partial
                # write would silently reorder the primary, so failures raise
                # and surface to the client.
                utils.replace_model_previews(model_path, entries)
            elif any(i == "undefined" for i in items if type(i) is str):
                # "undefined" is the client's sentinel for an empty gallery:
                # an editor save that removed every preview must delete the
                # stored files instead of silently keeping them.
                utils.remove_model_preview(model_path)

        if "description" in model_data:
            description = model_data["description"]
            utils.save_model_description(model_path, description)

        if "type" in model_data and "pathIndex" in model_data and "fullname" in model_data:
            model_type = model_data.get("type")
            raw_index = model_data.get("pathIndex")
            fullname = model_data.get("fullname")
            if model_type is None or raw_index is None or fullname is None:
                raise RuntimeError("Invalid type or pathIndex or fullname")
            path_index = int(raw_index)

            # get new path
            new_model_path = utils.get_full_path(model_type, path_index, fullname)

            # ZipNN bundle folders (*_ZNN) must never receive a non-compressed
            # model file through a move/rename either.
            utils.enforce_znn_folder_rule(new_model_path)

            utils.rename_model(model_path, new_model_path)

    def remove_model(self, model_path: str):
        model_dirname = os.path.dirname(model_path)
        os.remove(model_path)

        model_previews = utils.get_model_all_previews(model_path)
        for preview in model_previews:
            os.remove(utils.join_path(model_dirname, preview))

        model_descriptions = utils.get_model_all_descriptions(model_path)
        for description in model_descriptions:
            os.remove(utils.join_path(model_dirname, description))

    def remove_folder(self, folder_path: str):
        """Recursively delete a model folder (selection-mode folder delete).

        Containment inside the model-type root is validated by the route
        (`utils.get_full_path`), so this only ever touches model directories.
        """
        import shutil

        shutil.rmtree(folder_path)
