import asyncio
import os
import re
import math
import yaml
import requests
import markdownify

import folder_paths

from aiohttp import web
from abc import ABC, abstractmethod
from urllib.parse import urlparse, parse_qs
from PIL import Image
from io import BytesIO

from . import utils
from . import config
from . import auth


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
                name = file.get("name", None)
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

        sibling_files: list[str] = [x.get("rfilename") for x in res_data.get("siblings", [])]

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
                result = await loop.run_in_executor(None, self.fetch_model_info, model_page)
                return web.json_response({"success": True, "data": result})
            except Exception as e:
                error_msg = f"Fetch model info failed: {str(e)}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})

        @routes.get("/model-manager/preview/{type}/{index}/{filename:.*}")
        async def read_model_preview(request):
            """
            Get the file stream of the specified preview
            If the file does not exist, the glass NO-PREVIEW.svg artwork is
            returned.

            :param type: The type of the model. eg.checkpoints, loras, vae, etc.
            :param index: The index of the model folders.
            :param filename: The filename of the preview.
            """
            model_type = request.match_info.get("type", None)
            index = int(request.match_info.get("index", None))
            filename = request.match_info.get("filename", None)

            extension_uri = config.extension_uri

            try:
                folders = folder_paths.get_folder_paths(model_type)
                base_path = folders[index]
                abs_path = utils.join_path(base_path, filename)
                preview_name = utils.get_model_preview_name(abs_path)
                if preview_name:
                    dir_name = os.path.dirname(abs_path)
                    abs_path = utils.join_path(dir_name, preview_name)
            except:
                abs_path = extension_uri

            if not os.path.isfile(abs_path):
                # Glassmorphism fallback artwork (assets/no-preview.png was
                # retired together with the upstream raster icon).
                abs_path = utils.join_path(
                    extension_uri, "assets", "NOPREVIEW-Icon", "NO-PREVIEW.svg"
                )

            # The no-preview artwork is vector: serve it verbatim. PIL can
            # neither parse nor re-encode it, and rasterising would destroy
            # the gradients.
            if abs_path.lower().endswith(".svg"):
                return web.FileResponse(
                    abs_path, headers={"Content-Type": "image/svg+xml"}
                )

            # Determine content type from the actual file
            content_type = utils.resolve_file_content_type(abs_path)

            if content_type == "video":
                # Serve video files directly
                return web.FileResponse(abs_path)
            else:
                # Serve image files (WebP or fallback images)
                image_data = self.get_image_preview_data(abs_path)
                return web.Response(body=image_data.getvalue(), content_type="image/webp")

        @routes.get("/model-manager/preview/download/{filename}")
        async def read_download_preview(request):
            filename = request.match_info.get("filename", None)
            extension_uri = config.extension_uri

            download_path = utils.get_download_path()
            preview_path = utils.join_path(download_path, filename)

            if not os.path.isfile(preview_path):
                preview_path = utils.join_path(
                    extension_uri, "assets", "NOPREVIEW-Icon", "NO-PREVIEW.svg"
                )

            return web.FileResponse(preview_path)

    def get_image_preview_data(self, filename: str):
        with Image.open(filename) as img:
            max_size = 1024

            exif_data = img.info.get("exif")
            icc_profile = img.info.get("icc_profile")

            if getattr(img, "is_animated", False) and img.n_frames > 1:
                total_frames = img.n_frames
                step = max(1, math.ceil(total_frames / 30))

                frames, durations = [], []

                for frame_idx in range(0, total_frames, step):
                    img.seek(frame_idx)
                    frame = img.copy()
                    frame.thumbnail((max_size, max_size), Image.Resampling.NEAREST)

                    frames.append(frame)
                    durations.append(img.info.get("duration", 100) * step)

                save_args = {
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
        return UnknownWebsiteSearcher()
