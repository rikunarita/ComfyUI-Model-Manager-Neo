import asyncio
import hashlib
import os
import re
import math
import yaml
import requests
import markdownify

import folder_paths

from aiohttp import web
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse, parse_qs
from PIL import Image
from io import BytesIO

from . import utils
from . import config
from . import auth

# ---------------------------------------------------------------------------
# Browser-cacheable SVG artwork (optimization B-2).
#
# The glass folder icons and the NO-PREVIEW artwork used to be inlined into the
# bundle as data: URIs, so every folder card carried its own ~10-25 KB copy in
# the DOM and the browser could never cache any of it. They are now served over
# HTTP with an ETag and a day-long max-age: one decode per session, shared by
# every card, revalidated (304) afterwards.
# ---------------------------------------------------------------------------
SVG_CACHE_CONTROL = "public, max-age=86400, must-revalidate"

_SVG_ASSETS = {
    "folder-closed": ("assets", "Folder-Icons", "close-folder_beside-fit.svg"),
    "folder-glyph": ("assets", "Folder-Icons", "close-folder_all-fit.svg"),
    "folder-opening": ("assets", "Folder-Icons", "folder-opening-animation.svg"),
    "folder-closing": ("assets", "Folder-Icons", "folder-closing-animation.svg"),
    "no-preview": ("assets", "NOPREVIEW-Icon", "NO-PREVIEW.svg"),
    "zipnn-button": ("assets", "ZipNN-icon", "ZipNN-Button_Icon.svg"),
    # Model-hub logos, worn as the background of the "open model page" button.
    "civitai-icon": ("assets", "AIModelHub-Logos", "civitai-icon.svg"),
    "hf-icon": ("assets", "AIModelHub-Logos", "hf-icon.svg"),
    "modelscope-icon": ("assets", "AIModelHub-Logos", "modelscope-icon.svg"),
}
_SVG_CACHE: dict[str, tuple[int, str, bytes]] = {}


def _svg_payload(name: str) -> tuple[str, bytes]:
    # Keyed by mtime as well: a `git pull` that replaces the artwork must be
    # served on the next request even without a ComfyUI restart (a stale
    # in-process cache used to keep serving the old SVG - and its old
    # transparent-margin viewBox - forever).
    path = utils.join_path(config.extension_uri, *_SVG_ASSETS[name])
    mtime = os.stat(path).st_mtime_ns
    hit = _SVG_CACHE.get(name)
    if hit is not None and hit[0] == mtime:
        return hit[1], hit[2]
    body = open(path, "rb").read()
    etag = f'"svg-{hashlib.sha256(body).hexdigest()[:16]}"'
    _SVG_CACHE[name] = (mtime, etag, body)
    return etag, body


def _not_modified(request, etag: str) -> bool:
    header = request.headers.get("If-None-Match", "")
    return header == etag or etag in [h.strip() for h in header.split(",")]


def svg_response(request, name: str) -> web.Response:
    etag, body = _svg_payload(name)
    headers = {"ETag": etag, "Cache-Control": SVG_CACHE_CONTROL}
    if _not_modified(request, etag):
        return web.Response(status=304, headers=headers)
    return web.Response(body=body, content_type="image/svg+xml", headers=headers)


# ---------------------------------------------------------------------------
# Encoded-preview cache (optimization A-1).
#
# The preview route re-decoded and re-encoded every image (every frame of an
# animated one) on *each* request, so refreshing a 1000-model grid re-ran PIL a
# thousand times. The WebP bytes are now memoised against (mtime_ns, size) and
# answered with an ETag, so a warm grid costs a dict hit plus a 304.
# ---------------------------------------------------------------------------
PREVIEW_CACHE_CONTROL = "private, max-age=300, must-revalidate"
_PREVIEW_ENCODE_CACHE: dict[str, tuple[int, int, bytes]] = {}
_PREVIEW_ENCODE_LIMIT = 64


class ModelSearcher(ABC):
    """
    Abstract class for model searcher.
    """

    @abstractmethod
    def search_by_url(self, url: str) -> list[dict]:
        pass


class UnknownWebsiteSearcher(ModelSearcher):
    def search_by_url(self, url: str):
        raise RuntimeError("Unknown Website, please input a URL from huggingface.co or civitai.com.")


class CivitaiModelSearcher(ModelSearcher):
    def search_by_url(self, url: str):
        parsed_url = urlparse(url)

        pathname = parsed_url.path
        match = re.match(r"^/models/(\d*)", pathname)
        model_id = match.group(1) if match else None

        query_params = parse_qs(parsed_url.query)
        version_id = query_params.get("modelVersionId", [None])[0]

        if not model_id:
            return []

        headers = auth.get_civitai_headers()
        response = requests.get(f"https://civitai.com/api/v1/models/{model_id}", headers=headers)
        response.raise_for_status()
        res_data: dict = response.json()

        model_versions: list[dict] = res_data["modelVersions"]
        if version_id:
            model_versions = utils.filter_with(model_versions, {"id": int(version_id)})

        models: list[dict] = []

        for version in model_versions:
            version_files: list[dict] = version.get("files", [])
            model_files = utils.filter_with(version_files, {"type": "Model"})
            # issue: https://github.com/hayden-cn/ComfyUI-Model-Manager/issues/188
            # Some Embeddings do not have Model file, but Negative
            # Make sure there are at least downloadable files
            model_files = version_files if len(model_files) == 0 else model_files

            shortname = version.get("name", None) if len(model_files) > 0 else None

            for file in model_files:
                name = file.get("name", None) or ""
                extension = os.path.splitext(name)[1]
                basename = os.path.splitext(name)[0]

                metadata_info = {
                    "website": "Civitai",
                    "modelPage": f"https://civitai.com/models/{model_id}?modelVersionId={version.get('id')}",
                    "author": res_data.get("creator", {}).get("username", None),
                    "baseModel": version.get("baseModel"),
                    "hashes": file.get("hashes"),
                    "metadata": file.get("metadata"),
                    # BUG FIX: `version["images"]` raised KeyError for Civitai
                    # versions without an image list, failing the whole search.
                    "preview": [i["url"] for i in version.get("images", [])],
                }

                description_parts: list[str] = []
                description_parts.append("---")
                description_parts.append(yaml.dump(metadata_info).strip())
                description_parts.append("---")
                description_parts.append("")
                description_parts.append("# Trigger Words")
                description_parts.append("")
                description_parts.append(", ".join(version.get("trainedWords", ["No trigger words"])))
                description_parts.append("")
                description_parts.append("# About this version")
                description_parts.append("")
                # BUG FIX: `.get(key, default)` still returns None when the
                # API sends an explicit JSON null; markdownify(None) raised a
                # TypeError and aborted the entire lookup.
                version_description = version.get("description") or "<p>No description about this version</p>"
                description_parts.append(markdownify.markdownify(version_description).strip())
                description_parts.append("")
                description_parts.append(f"# {res_data.get('name')}")
                description_parts.append("")
                model_description = res_data.get("description") or "<p>No description about this model</p>"
                description_parts.append(markdownify.markdownify(model_description).strip())
                description_parts.append("")

                model = {
                    "id": version.get("id"),
                    "shortname": shortname or basename,
                    "basename": basename,
                    "extension": extension,
                    "preview": metadata_info.get("preview"),
                    "sizeBytes": file.get("sizeKB", 0) * 1024,
                    "type": self._resolve_model_type(res_data.get("type", "")),
                    "pathIndex": 0,
                    "subFolder": "",
                    "description": "\n".join(description_parts),
                    "metadata": file.get("metadata"),
                    "downloadPlatform": "civitai",
                    "downloadUrl": file.get("downloadUrl"),
                    "hashes": file.get("hashes"),
                    "files": version_files if len(version_files) > 1 else None,
                }
                models.append(model)

        return models

    # BUG FIX: `_resolve_model_type` was dropped in the fork and the Civitai
    # model type hardcoded to "". The Create Download Task dialog then had no
    # type to pre-select, so every Civitai download had to be typed by hand
    # (and was rejected with "Please select model type first" otherwise).
    # Restored from upstream, with one hardening step: the resolved type is
    # only used when ComfyUI actually has a matching model folder, so Civitai
    # categories with no local counterpart ("Wildcards", "Poses", ...) degrade
    # to "" exactly as before instead of producing an unusable type.
    CIVITAI_TYPE_MAP = {
        "TextualInversion": "embeddings",
        "LoCon": "loras",
        "DoRA": "loras",
        "Controlnet": "controlnet",
        "Upscaler": "upscale_models",
        "VAE": "vae",
        "unknown": "",
    }

    def _resolve_model_type(self, model_type: str) -> str:
        if not model_type:
            return ""
        resolved = self.CIVITAI_TYPE_MAP.get(model_type, f"{model_type.lower()}s")
        if not resolved:
            return ""
        return resolved if resolved in utils.resolve_model_base_paths() else ""


class HuggingfaceModelSearcher(ModelSearcher):
    def search_by_url(self, url: str):
        parsed_url = urlparse(url)

        pathname = parsed_url.path
        path_parts = [p for p in pathname.strip("/").split("/") if p]

        if len(path_parts) < 2:
            raise RuntimeError(f"Invalid HuggingFace URL: {url}")

        space = path_parts[0]
        name = path_parts[1]
        model_id = f"{space}/{name}"

        # Extract revision and rest_pathname from tree/blob paths
        revision = "main"
        rest_pathname = ""
        if len(path_parts) >= 4 and path_parts[2] in ("tree", "blob"):
            revision = path_parts[3]
            rest_pathname = "/".join(path_parts[4:])

        headers = auth.get_hf_headers()

        # Fetch model info from HF API
        response = requests.get(f"https://huggingface.co/api/models/{model_id}", headers=headers)
        response.raise_for_status()
        res_data: dict = response.json()

        # Fetch file tree to get actual file sizes
        file_sizes = {}
        try:
            # BUG FIX: without `recursive=true` the tree API only returns the
            # repository root, so files inside sub-directories never got a
            # size (shown as 0 B until the download corrected it).
            tree_url = f"https://huggingface.co/api/models/{model_id}/tree/{revision}?recursive=true"
            tree_response = requests.get(tree_url, headers=headers)
            if tree_response.status_code == 200:
                tree_data = tree_response.json()
                file_sizes = self._build_file_sizes(tree_data)
        except Exception as e:
            utils.print_warning(f"Failed to fetch file tree for size info: {e}")

        sibling_files: list[str] = [
            x.get("rfilename") or "" for x in res_data.get("siblings", [])
        ]

        model_files = utils.filter_with(
            utils.filter_with(sibling_files, self._match_model_files()),
            self._match_tree_files(rest_pathname),
        )

        image_files = utils.filter_with(
            utils.filter_with(sibling_files, self._match_image_files()),
            self._match_tree_files(rest_pathname),
        )
        image_files = [f"https://huggingface.co/{model_id}/resolve/{revision}/{filename}" for filename in image_files]

        models: list[dict] = []

        for filename in model_files:
            fullname = os.path.basename(filename)
            extension = os.path.splitext(fullname)[1]
            basename = os.path.splitext(fullname)[0]
            size_bytes = file_sizes.get(filename, 0)

            metadata_info = {
                "website": "HuggingFace",
                "modelPage": f"https://huggingface.co/{model_id}",
                "author": res_data.get("author", None),
                "preview": image_files,
            }

            description_parts: list[str] = []
            description_parts.append("---")
            description_parts.append(yaml.dump(metadata_info).strip())
            description_parts.append("---")
            description_parts.append("")
            description_parts.append("# Trigger Words")
            description_parts.append("")
            description_parts.append("No trigger words")
            description_parts.append("")
            description_parts.append("# About this version")
            description_parts.append("")
            description_parts.append("No description about this version")
            description_parts.append("")
            description_parts.append(f"# {res_data.get('name')}")
            description_parts.append("")
            description_parts.append("No description about this model")
            description_parts.append("")

            model = {
                "id": filename,
                "shortname": filename,
                "basename": basename,
                "extension": extension,
                "preview": image_files,
                "sizeBytes": size_bytes,
                "type": "",
                "pathIndex": 0,
                "subFolder": "",
                "description": "\n".join(description_parts),
                "metadata": {},
                "downloadPlatform": "huggingface",
                "downloadUrl": f"https://huggingface.co/{model_id}/resolve/{revision}/{filename}?download=true",
                "revision": revision,
            }
            models.append(model)

        return models

    def _build_file_sizes(self, tree_data):
        """Recursively build a dict of {filepath: size} from HF tree API response."""
        sizes = {}
        if isinstance(tree_data, list):
            for item in tree_data:
                if item.get("type") == "file":
                    sizes[item.get("path", "")] = item.get("size", 0)
                elif item.get("type") == "directory":
                    children = item.get("children", [])
                    if children:
                        sizes.update(self._build_file_sizes(children))
        return sizes

    def _match_model_files(self):
        extension = [
            ".bin",
            ".ckpt",
            ".gguf",
            ".onnx",
            ".pt",
            ".pth",
            ".safetensors",
        ]

        def _filter_model_files(file: str):
            return any(file.endswith(ext) for ext in extension)

        return _filter_model_files

    def _match_image_files(self):
        extension = [
            ".png",
            ".webp",
            ".jpeg",
            ".jpg",
            ".jfif",
            ".gif",
            ".apng",
        ]

        def _filter_image_files(file: str):
            return any(file.endswith(ext) for ext in extension)

        return _filter_image_files

    def _match_tree_files(self, pathname: str):
        # BUG FIX: `rest_pathname` (built in search_by_url) already has the
        # leading `tree|blob/<revision>` segments stripped, so the previous
        # check that required the first segment to be "tree"/"blob" never
        # matched and the filter degenerated into a no-op returning every
        # model file of the repository. The remaining pathname IS the
        # sub-path: match the exact file (blob URL) or everything inside the
        # directory (tree URL).
        prefix = pathname.strip("/")

        def _filter_tree_files(file: str):
            if not prefix:
                return True
            return file == prefix or file.startswith(prefix + "/")

        return _filter_tree_files


# ModelScope international site (per project policy: always the .ai domain).
MODELSCOPE_INTL_ENDPOINT = "https://www.modelscope.ai"

_MODEL_FILE_EXTS = (".bin", ".ckpt", ".gguf", ".onnx", ".pt", ".pth", ".safetensors")


class ModelScopeModelSearcher(ModelSearcher):
    """Model listing of a ModelScope model repository (international site).

    Mirrors the HuggingFace searcher: one entry per model file of the repo,
    with the front-matter the Information tab and the duplicate warning read
    (`website: ModelScope`), plus the repo/file pair the downloader needs.
    """

    def search_by_url(self, url: str):
        parsed_url = urlparse(url)
        parts = [p for p in parsed_url.path.strip("/").split("/") if p]
        if len(parts) < 3 or parts[0] != "models":
            return []
        owner, name = parts[1], parts[2]
        repo_id = f"{owner}/{name}"

        from modelscope_hub import HubApi

        token = auth.get_modelscope_token()
        api = HubApi(endpoint=MODELSCOPE_INTL_ENDPOINT, token=token)
        files = api.list_repo_files(repo_id, "model")

        model_page = f"{MODELSCOPE_INTL_ENDPOINT}/models/{repo_id}"
        models: list[dict] = []
        for fi in files:
            if fi.is_dir:
                continue
            ext = os.path.splitext(fi.path)[1]
            if ext not in _MODEL_FILE_EXTS:
                continue
            basename = os.path.splitext(os.path.basename(fi.path))[0]
            sha = fi.sha256 or (fi.lfs or {}).get("sha256")
            hashes = {"SHA256": sha} if sha else None

            metadata_info: dict = {
                "website": "ModelScope",
                "modelPage": model_page,
                "author": owner,
            }
            if hashes:
                metadata_info["hashes"] = hashes
            description_parts = [
                "---",
                yaml.dump(metadata_info).strip(),
                "---",
                "",
                f"# {name}",
                "",
                f"Model repository: {model_page}",
                "",
            ]

            models.append(
                {
                    "id": fi.path,
                    "shortname": name,
                    "basename": basename,
                    "extension": ext,
                    "preview": [],
                    "sizeBytes": fi.size or 0,
                    "type": "",
                    "pathIndex": 0,
                    "subFolder": "",
                    "description": "\n".join(description_parts),
                    "metadata": {},
                    "downloadPlatform": "modelscope",
                    "downloadUrl": None,
                    "hashes": hashes,
                    "files": None,
                    "msRepoId": repo_id,
                    "msFilePath": fi.path,
                }
            )
        return models


class Information:
    def add_routes(self, routes):

        @routes.get("/model-manager/model-info")
        async def fetch_model_info(request):
            """
            Fetch model information from network with model page.
            """
            try:
                model_page = request.query.get("model-page", None)
                # BUG FIX: `search_by_url` performs one or more blocking
                # `requests.get` round trips (Civitai model + version data, or
                # the Hugging Face model info AND recursive file tree). Running
                # them inline froze ComfyUI's event loop for the whole lookup -
                # no websocket traffic, no other request served - which is the
                # same defect already fixed for hashing, the Civitai hash
                # lookup, the preview download and the model-library walks.
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    utils.io_executor(), self.fetch_model_info, model_page
                )
                return web.json_response({"success": True, "data": result})
            except Exception as e:
                error_msg = f"Fetch model info failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.get("/model-manager/no-preview.svg")
        async def read_no_preview(request):
            """
            The default preview artwork (glass NO-PREVIEW.svg), served
            verbatim. Models without a preview reference this URL directly
            from the model list; it is a default, not a fallback. Cached by the
            browser like the rest of the artwork.
            """
            return svg_response(request, "no-preview")

        @routes.get("/model-manager/assets/{name}.svg")
        async def read_asset_svg(request):
            """Glass artwork (folder icons, glyphs) with browser caching."""
            name = request.match_info["name"]
            if name not in _SVG_ASSETS:
                raise web.HTTPNotFound()
            return svg_response(request, name)

        @routes.get("/model-manager/preview/{type}/{index}/{filename:.*}")
        async def read_model_preview(request):
            """
            Get the file stream of the specified preview.

            Only real preview files are served: models without a preview
            already carry the default `/model-manager/no-preview.svg` URL in
            the model list, so this route has no fallback chain any more and
            answers 404 for anything that does not exist.

            :param type: The type of the model. eg.checkpoints, loras, vae, etc.
            :param index: The index of the model folders.
            :param filename: The filename of the preview.
            """
            model_type = request.match_info.get("type", None)
            index = int(request.match_info.get("index", None))
            filename = request.match_info.get("filename", None)

            # `filename` is always a concrete preview file name produced by
            # `scan_models` (e.g. `model.webp`, `sub/model.preview2.png`), so
            # the route serves exactly that file - there is no re-resolution to
            # a "primary" preview and therefore no fallback chain. BUG FIX: the
            # old code ran `get_model_preview_name()` on the requested path,
            # which re-resolved to the highest-priority sibling and (a) collapsed
            # a gallery onto its first frame whenever a model carried two base
            # previews of different extensions, and (b) only stayed inside the
            # model folder by accident. The explicit realpath guard below makes
            # the containment deliberate.
            try:
                folders = folder_paths.get_folder_paths(model_type)
                base_path = folders[index]
                abs_path = utils.join_path(base_path, filename)
                real_base = os.path.realpath(base_path)
                real_abs = os.path.realpath(abs_path)
                if not (real_abs == real_base or real_abs.startswith(real_base + os.sep)):
                    raise web.HTTPNotFound()
            except web.HTTPNotFound:
                raise
            except Exception:
                raise web.HTTPNotFound()

            if not os.path.isfile(abs_path):
                raise web.HTTPNotFound()

            stat = os.stat(abs_path)
            etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
            cache_headers = {"ETag": etag, "Cache-Control": PREVIEW_CACHE_CONTROL}
            if _not_modified(request, etag):
                return web.Response(status=304, headers=cache_headers)

            # Determine content type from the actual file
            content_type = utils.resolve_file_content_type(abs_path)

            if content_type == "video":
                # Serve video files directly
                return web.FileResponse(abs_path, headers=cache_headers)
            else:
                # Serve image files (WebP or fallback images). The encode is
                # CPU-bound, so it lives on the cpu pool (optimization A-4)
                # and is memoised (optimization A-1).
                loop = asyncio.get_running_loop()
                encoded = await loop.run_in_executor(
                    utils.cpu_executor(), self.get_image_preview_data, abs_path
                )
                return web.Response(
                    body=encoded.getvalue(),
                    content_type="image/webp",
                    headers=cache_headers,
                )

        @routes.get("/model-manager/preview/download/{filename}")
        async def read_download_preview(request):
            """Preview of a download task; 404 when the task has none (the
            client then shows the default NO-PREVIEW.svg URL instead)."""
            filename = request.match_info.get("filename", None)

            download_path = utils.get_download_path()
            preview_path = utils.join_path(download_path, filename)

            if not os.path.isfile(preview_path):
                raise web.HTTPNotFound()

            return web.FileResponse(preview_path)

    def get_image_preview_data(self, filename: str):
        """WebP bytes for a preview, memoised against (mtime_ns, size)."""
        from io import BytesIO as _BytesIO

        stat = os.stat(filename)
        key = os.path.realpath(filename)
        hit = _PREVIEW_ENCODE_CACHE.get(key)
        if hit is not None and hit[0] == stat.st_mtime_ns and hit[1] == stat.st_size:
            return _BytesIO(hit[2])
        encoded = self._encode_preview(filename).getvalue()
        _PREVIEW_ENCODE_CACHE[key] = (stat.st_mtime_ns, stat.st_size, encoded)
        while len(_PREVIEW_ENCODE_CACHE) > _PREVIEW_ENCODE_LIMIT:
            _PREVIEW_ENCODE_CACHE.pop(next(iter(_PREVIEW_ENCODE_CACHE)))
        return _BytesIO(encoded)

    def _encode_preview(self, filename: str):
        with Image.open(filename) as img:
            max_size = 1024

            exif_data = img.info.get("exif")
            icc_profile = img.info.get("icc_profile")

            frame_count = int(getattr(img, "n_frames", 1))
            if getattr(img, "is_animated", False) and frame_count > 1:
                total_frames = frame_count
                step = max(1, math.ceil(total_frames / 30))

                frames, durations = [], []

                for frame_idx in range(0, total_frames, step):
                    img.seek(frame_idx)
                    frame = img.copy()
                    frame.thumbnail((max_size, max_size), Image.Resampling.NEAREST)

                    frames.append(frame)
                    durations.append(img.info.get("duration", 100) * step)

                save_args: dict[str, Any] = {
                    "format": "WEBP",
                    "save_all": True,
                    "append_images": frames[1:],
                    "duration": durations,
                    "loop": 0,
                    "quality": 80,
                    "method": 0,
                    "allow_mixed": False,
                }

                if exif_data:
                    save_args["exif"] = exif_data

                if icc_profile:
                    save_args["icc_profile"] = icc_profile

                img_byte_arr = BytesIO()
                frames[0].save(img_byte_arr, **save_args)
                img_byte_arr.seek(0)
                return img_byte_arr

            img.thumbnail((max_size, max_size), Image.Resampling.BICUBIC)

            img_byte_arr = BytesIO()
            save_args = {"format": "WEBP", "quality": 80}

            if exif_data:
                save_args["exif"] = exif_data
            if icc_profile:
                save_args["icc_profile"] = icc_profile

            img.save(img_byte_arr, **save_args)
            img_byte_arr.seek(0)
            return img_byte_arr

    def fetch_model_info(self, model_page: str):
        if not model_page:
            return []

        model_searcher = self.get_model_searcher_by_url(model_page)
        result = model_searcher.search_by_url(model_page)
        return result

    def get_model_searcher_by_url(self, url: str) -> ModelSearcher:
        parsed_url = urlparse(url)
        host_name = parsed_url.hostname
        if host_name == "civitai.com":
            return CivitaiModelSearcher()
        elif host_name == "huggingface.co":
            return HuggingfaceModelSearcher()
        elif host_name in ("modelscope.ai", "modelscope.cn") or (
            host_name or ""
        ).endswith(".modelscope.ai"):
            return ModelScopeModelSearcher()
        return UnknownWebsiteSearcher()
