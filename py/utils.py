import functools
import json
import logging
import mimetypes
import os
import shutil
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import comfy.utils
import folder_paths
import requests
from aiohttp import web

from . import config

# Media file extensions
VIDEO_EXTENSIONS = [".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".m4v", ".ogv"]
IMAGE_EXTENSIONS = [".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"]

# The default preview artwork: models without a preview point straight at
# this URL (there is no fallback chain any more - see py/information.py).
NO_PREVIEW_URL = "/model-manager/no-preview.svg"

# Sentinel returned by get_model_preview_name() when a model has no preview on
# disk. BUG FIX: the literal "no-preview.png" was repeated in four modules
# (utils, manager, information, upload) and on the client (hooks/model.ts,
# hooks/download.ts) even though that raster was deleted in the sixth pass -
# a typo in any one of them would have silently re-pointed models at a file
# that no longer exists. It is a value, not a path: nothing is ever read from
# it, callers swap it for NO_PREVIEW_URL.
NO_PREVIEW_SENTINEL = "no-preview.png"

# Preview extensions in priority order (videos first, then images)
PREVIEW_EXTENSIONS = [".webm", ".mp4", ".webp", ".png", ".jpg", ".jpeg", ".gif", ".bmp"]

# Content type mappings
VIDEO_CONTENT_TYPE_MAP = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/x-matroska": ".mkv",
    "video/x-flv": ".flv",
    "video/x-ms-wmv": ".wmv",
    "video/ogg": ".ogv",
}

# Own extension -> content-type cache: ComfyUI v0.34.0 removed
# folder_paths.extension_mimetype_cache, and guessing a MIME type per call is
# wasteful on the preview routes.
_extension_mimetypes_cache: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Dedicated executors.
#
# Everything blocking used to share asyncio's *default* executor, so a heavy
# library walk or a multi-gigabyte sha256 pass could starve an in-flight
# download of the very threads it reports progress from. Two pools now
# separate syscall-bound work from CPU-bound work; both are deliberately
# small - the point is isolation, not parallelism.
# ---------------------------------------------------------------------------
_IO_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="mm-io")
_CPU_EXECUTOR = ThreadPoolExecutor(max_workers=max(2, (os.cpu_count() or 2) // 2), thread_name_prefix="mm-cpu")


def io_executor() -> ThreadPoolExecutor:
    """Pool for blocking I/O: model walks, downloads, uploads, HF calls."""
    return _IO_EXECUTOR


def cpu_executor() -> ThreadPoolExecutor:
    """Pool for CPU-bound work: WebP encoding, sha256 passes."""
    return _CPU_EXECUTOR


def print_info(msg, *args, **kwargs):
    logging.info(f"[{config.extension_tag}] {msg}", *args, **kwargs)


def print_warning(msg, *args, **kwargs):
    logging.warning(f"[{config.extension_tag}][WARNING] {msg}", *args, **kwargs)


def print_error(msg, *args, **kwargs):
    logging.error(f"[{config.extension_tag}][ERROR] {msg}", *args, **kwargs)
    logging.debug(traceback.format_exc())


def print_debug(msg, *args, **kwargs):
    logging.debug(f"[{config.extension_tag}] {msg}", *args, **kwargs)


def deprecated(reason: str):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            print_warning(f"{func.__name__} is deprecated: {reason}")
            return func(*args, **kwargs)

        return wrapper

    return decorator


def _matches(predicate: dict):
    def _filter(obj: dict):
        return all(obj.get(key) == value for key, value in predicate.items())

    return _filter


def filter_with(list: list, predicate):
    if isinstance(predicate, dict):
        predicate = _matches(predicate)

    return [item for item in list if predicate(item)]


async def get_request_body(request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def normalize_path(path: str):
    normpath = os.path.normpath(path)
    return normpath.replace(os.path.sep, "/")


def join_path(path: str, *paths: str) -> str:
    return normalize_path(os.path.join(path, *paths))


def get_current_version():
    try:
        import tomllib

        pyproject_path = join_path(config.extension_uri, "pyproject.toml")
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def download_web_distribution(version: str):
    """
    Web distribution is now bundled directly in the repository's 'web/' folder.
    This function only verifies that the local web folder exists and contains JS files.
    The legacy GitHub Releases download logic has been removed.
    """
    web_path = join_path(config.extension_uri, "web")

    if not os.path.isdir(web_path):
        print_error(f"Web distribution folder not found at {web_path}. The Model Manager UI will not load.")
        return

    has_js = any(f.endswith(".js") for f in os.listdir(web_path))
    if not has_js:
        print_error(f"No .js files found in {web_path}. The Model Manager UI will not load.")
        return

    print_info(f"Web distribution loaded from local repository (version {version}).")


# The folder table is static for the life of the process,
# yet nearly every request rebuilt and re-normalised it. The raw structure is
# compared by reference-cheap tuple signature; only a real change re-runs the
# (string-allocating) normalisation.
_base_paths_signature: tuple | None = None
_base_paths_cache: dict[str, list[str]] = {}


def resolve_model_base_paths() -> dict[str, list[str]]:
    """
    Resolve model base paths.
    eg. { "checkpoints": ["path/to/checkpoints"] }
    """
    global _base_paths_signature, _base_paths_cache
    raw = folder_paths.folder_names_and_paths
    signature = (
        tuple(sorted(raw.keys())),
        tuple(tuple(raw[k][0]) for k in sorted(raw.keys())),
    )
    if signature == _base_paths_signature:
        return _base_paths_cache

    folder_keys = list(raw.keys())
    model_base_paths = {}
    folder_black_list = ["configs", "custom_nodes"]
    for folder in folder_keys:
        if folder in folder_black_list:
            continue
        paths = folder_paths.get_folder_paths(folder)
        model_base_paths[folder] = [normalize_path(f) for f in paths]
    _base_paths_signature = signature
    _base_paths_cache = model_base_paths
    return model_base_paths


def resolve_file_content_type(filename: str):
    extension = filename.split(".")[-1].lower()
    if extension not in _extension_mimetypes_cache:
        # NOTE: the `strict` keyword was deprecated in Python 3.11 and
        # REMOVED in 3.13 (TypeError). For every media/model extension this
        # project handles, strict and non-strict results are identical, so
        # dropping the argument is behaviour-preserving and 3.13-safe.
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            return None
        content_type = mime_type.split("/")[0]
        _extension_mimetypes_cache[extension] = content_type
    else:
        content_type = _extension_mimetypes_cache[extension]
    return content_type


def get_full_path(model_type: str, path_index: int, filename: str):
    """
    Get the absolute path in the model type through string concatenation.
    """
    folders = resolve_model_base_paths().get(model_type, [])
    if not path_index < len(folders):
        raise RuntimeError(f"PathIndex {path_index} is not in {model_type}")
    base_path = folders[path_index]
    full_path = join_path(base_path, filename)
    real_base = os.path.realpath(base_path)
    real_full = os.path.realpath(full_path)
    if not (real_full == real_base or real_full.startswith(real_base + os.sep)):
        raise RuntimeError("Path traversal detected: filename escapes model directory")
    return full_path


# ---------------------------------------------------------------------------
# ZipNN folder conventions (mirror py/compress.py).
#
# A folder whose name ends with `_DeltaZNN` is a ZipNN bundle: batch
# compression moves every compressed model of `<name>` into
# `<name>_DeltaZNN`, and delta compression stores `<ft>_delta_<base>.znn`
# files into `<base>_DeltaZNN`. Either way the folder may only hold
# ZipNN-compressed content (`*.znn.*` models and `*.znn` delta files).
# The legacy `_ZNN` suffix (bundles created by older versions) is still
# recognised as a bundle so those folders keep decompressing in place.
# Note `*_DeltaZNN` deliberately does NOT match the `_ZNN` suffix (the
# character before "ZNN" is a letter, not an underscore).
# ---------------------------------------------------------------------------
ZNN_FOLDER_SUFFIX = "_ZNN"
DELTA_FOLDER_SUFFIX = "_DeltaZNN"


def is_znn_folder_name(name: str) -> bool:
    """True for legacy `X_ZNN` bundle folders (NOT for `X_DeltaZNN`)."""
    return name.endswith(ZNN_FOLDER_SUFFIX)


def is_delta_folder_name(name: str) -> bool:
    """True for `X_DeltaZNN` bundle / delta folders."""
    return name.endswith(DELTA_FOLDER_SUFFIX)


def is_bundle_folder_name(name: str) -> bool:
    """True for any ZipNN bundle folder (`*_ZNN` legacy or `*_DeltaZNN`)."""
    return is_znn_folder_name(name) or is_delta_folder_name(name)


def enforce_znn_folder_rule(full_path: str) -> None:
    """Refuse to place a non-ZipNN *model* file inside a bundle folder.

    Bundle folders (`*_DeltaZNN`, legacy `*_ZNN`) may only hold ZipNN
    content: `*.znn.*` models and `*.znn` delta files. Sidecar files
    (previews, notes) stay allowed - they belong to the compressed model.
    Called by every code path that can put a new file into a model folder:
    local upload, download tasks and editor rename/move.
    """
    filename = os.path.basename(full_path)
    if ".znn." in filename or filename.endswith(".znn"):
        return  # ZipNN-compressed model / delta file: exactly what bundles hold
    extension = os.path.splitext(filename)[1]
    if extension not in folder_paths.supported_pt_extensions:
        return  # preview / notes / anything non-model
    parts = normalize_path(full_path).split("/")
    if any(is_bundle_folder_name(part) for part in parts[:-1]):
        raise RuntimeError(
            f"ZipNN folders (*{DELTA_FOLDER_SUFFIX}) accept ZipNN-compressed "
            f"models (*.znn.* / *.znn) only, cannot place: {filename}"
        )


def get_valid_full_path(model_type: str, path_index: int, filename: str):
    """
    Like get_full_path but it will check whether the file is valid.
    """
    full_path = get_full_path(model_type, path_index, filename)
    if os.path.isfile(full_path):
        return full_path
    if os.path.islink(full_path):
        raise RuntimeError(f"WARNING path {full_path} exists but doesn't link anywhere, skipping.")
    return None


def get_download_path():
    download_path = join_path(config.extension_uri, "downloads")
    if not os.path.exists(download_path):
        os.makedirs(download_path)
    return download_path


def search_files(directory: str):
    entries = os.listdir(directory)
    return [f for f in entries if os.path.isfile(join_path(directory, f))]


def file_list_to_name_dict(files: list[str]):
    file_dict: dict[str, str] = {}
    for file in files:
        filename = os.path.splitext(file)[0]
        file_dict[filename] = file
    return file_dict


def get_model_metadata(filename: str):
    if not filename.endswith(".safetensors"):
        return {}
    try:
        out = comfy.utils.safetensors_header(filename, max_size=1024 * 1024)
        if out is None:
            return {}
        dt = json.loads(out)
        if "__metadata__" not in dt:
            return {}
        return dt["__metadata__"]
    except Exception:
        return {}


def get_model_tensors(filename: str):
    """Exact tensor layout of a safetensors file: [{name, dtype, shape}].

    Parses the *full* safetensors JSON header (the structure the safetensors
    library writes), so the Information tab can render a faithful tensor
    table - name / dtype / shape - like Hugging Face's safetensors viewer.
    The `__metadata__` entry is skipped; it has its own section.
    """
    if not filename.endswith(".safetensors"):
        return []
    try:
        # MoE headers run into the megabytes; 32 MiB covers every real model.
        out = comfy.utils.safetensors_header(filename, max_size=1024 * 1024 * 32)
        if out is None:
            return []
        header = json.loads(out)
    except Exception:
        return []
    tensors = []
    for name, spec in header.items():
        if name == "__metadata__" or not isinstance(spec, dict):
            continue
        tensors.append(
            {
                "name": name,
                "dtype": spec.get("dtype", ""),
                "shape": spec.get("shape", []),
            }
        )
    return tensors


# Preview file naming scheme (ordered by display priority):
#   1. `<basename>.<ext>`          the primary preview
#   2. `<basename>.preview.<ext>`  the second preview (historic name)
#   3. `<basename>.preview<N>.<ext>`  N = 2..19, further previews
# The whole scheme is resolved against a *set of directory names*, so a model
# list walk costs zero extra stat() calls and every preview
# of a model can be enumerated (feature: keep all previews).
_PREVIEW_SUFFIXES = ("", ".preview", *(f".preview{n}" for n in range(2, 20)))


def preview_candidates(basename: str) -> list[str]:
    """Every file name that could hold a preview of `basename`, in slot order.

    The slot suffix MUST be the outer loop: this order is the listing order
    (manager.scan_models) and it has to agree with the positional slot writes
    of save_model_previews()/replace_model_previews() (item 0 -> `<base>.<ext>`,
    item 1 -> `<base>.preview.<ext>`, ...). The old extension-major order
    listed e.g. `m.preview2.mp4` BEFORE the primary `m.webp`, so any gallery
    holding a video kept re-sorting the primary away from slot 1 on every
    rescan - a saved primary swap never stuck for exactly those models.
    """
    return [f"{basename}{suffix}{ext}" for suffix in _PREVIEW_SUFFIXES for ext in PREVIEW_EXTENSIONS]


def get_dir_names(directory: str) -> set[str]:
    """One scandir() instead of N isfile() probes."""
    try:
        with os.scandir(directory) as it:
            return {entry.name for entry in it}
    except OSError:
        return set()


def previews_in_names(names: set[str], basename: str) -> list[str]:
    """The preview file names present in `names`, in display priority order."""
    return [c for c in preview_candidates(basename) if c in names]


def _get_preview_path(model_path: str, extension: str, suffix: str = "") -> str:
    """Generate preview file path with given extension and scheme suffix.

    `suffix` is one of `_PREVIEW_SUFFIXES`: "" for the primary preview,
    ".preview" for the second, ".preview<N>" for the rest.
    """
    basename = os.path.splitext(model_path)[0]
    return f"{basename}{suffix}{extension}"


def get_model_all_previews(model_path: str, names: set[str] | None = None) -> list[str]:
    """Get all preview files for a model (primary first, then extras)."""
    base_dirname = os.path.dirname(model_path)
    basename = os.path.splitext(os.path.basename(model_path))[0]
    if names is None:
        names = get_dir_names(base_dirname)
    return previews_in_names(names, basename)


def get_model_preview_name(model_path: str, names: set[str] | None = None) -> str:
    """Get the first available preview file, or NO_PREVIEW_SENTINEL if none."""
    all_previews = get_model_all_previews(model_path, names)
    return all_previews[0] if all_previews else NO_PREVIEW_SENTINEL


from io import BytesIO

from PIL import Image


def remove_model_preview(model_path: str):
    """Remove all preview files for a model"""
    base_dirname = os.path.dirname(model_path)

    previews = get_model_all_previews(model_path)
    for preview in previews:
        preview_path = join_path(base_dirname, preview)
        if os.path.exists(preview_path):
            os.remove(preview_path)


def _sniff_kind(head: bytes) -> str | None:
    """Magic-byte kind of preview content, when MIME labels cannot be trusted
    (multipart uploads and proxied responses routinely arrive as
    application/octet-stream or with an empty content-type)."""
    if head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff":
        return "image"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image"
    if head[:2] == b"BM":
        return "image"
    if head[4:8] == b"ftyp" or head[:4] == b"\x1aE\xdf\xa3":
        return "video"
    return None


def _resolve_local_preview(url: str) -> str | None:
    """Absolute path of one of our own preview URLs (relative by design)."""
    parts = [part for part in url.split("?")[0].split("/") if part]
    # ['model-manager', 'preview', <type>, <index>, <filename...>]
    if len(parts) < 5 or parts[0:2] != ["model-manager", "preview"]:
        return None
    try:
        folders = folder_paths.get_folder_paths(parts[2])
        local = join_path(folders[int(parts[3])], "/".join(parts[4:]))
    except Exception:
        return None
    return local if os.path.isfile(local) else None


def _write_preview_content(
    model_path: str,
    content: bytes,
    content_type: str,
    source_name: str,
    suffix: str,
) -> None:
    kind = None
    if content_type.startswith("video/"):
        kind = "video"
    elif content_type.startswith("image/"):
        kind = "image"
    else:
        kind = _sniff_kind(content[:12])
    if kind == "video":
        ext = _get_video_extension_from_url(source_name) or _get_extension_from_content_type(content_type) or ".mp4"
        preview_path = _get_preview_path(model_path, ext, suffix)
        with open(preview_path, "wb") as f:
            f.write(content)
    elif kind == "image":
        preview_path = _get_preview_path(model_path, ".webp", suffix)
        try:
            image = Image.open(BytesIO(content))
            image.save(preview_path, "WEBP")
        except Exception as e:
            # PIL cannot decode everything labelled image/* (SVG most
            # notably): say what happened instead of leaking the raw
            # "cannot identify image file" traceback at the user.
            raise RuntimeError(f"Unsupported or corrupt preview image ({content_type or 'unknown format'}): {e}") from e
    else:
        raise RuntimeError(f"FileTypeError: expected image or video, got {content_type or 'unknown'}")


def save_model_preview(
    model_path: str,
    file_or_url: Any,
    platform: str | None = None,
    headers: dict | None = None,
    suffix: str = "",
):
    """Save one preview file for a model. Images -> WebP, videos -> original format"""

    # Download file if it is a URL
    if type(file_or_url) is str:
        url = file_or_url

        # The download-completion path is tolerant: an unusable preview must
        # never fail an otherwise finished download, so bad entries are
        # skipped with a warning instead of raising.
        if not url:
            # "no preview" - the normal case, nothing to warn about
            return
        if url == "undefined":
            print_warning(f"Ignoring invalid preview URL: {url}")
            return
        if url.startswith(("blob:", "data:")):
            # Browser-local object URLs only exist inside the page that
            # created them; the server can never fetch them. The client is
            # expected to upload such files as multipart bytes instead.
            print_warning(f"Ignoring browser-local preview URL: {url[:48]}...")
            return

        content: bytes | None = None
        content_type = ""
        # Our own preview URLs are relative: read the stored file server-side
        # instead of round-tripping HTTP (the browser fetch that produced the
        # upload can fail or mislabel the MIME type).
        if url.startswith("/model-manager/preview/"):
            local = _resolve_local_preview(url)
            if local:
                with open(local, "rb") as f:
                    content = f.read()
        if content is None:
            if not url.startswith("http"):
                print_warning(f"Ignoring invalid preview URL: {url}")
                return
            # (connect, read) timeouts: a stalled CDN must not hang the
            # download-completion path (which runs in the io pool) forever.
            response = requests.get(url, headers=headers or {}, timeout=(15, 120))
            response.raise_for_status()
            content = response.content
            content_type = response.headers.get("content-type", "")
            if not content_type:
                content_type = resolve_file_content_type(url) or ""
        _write_preview_content(model_path, content, content_type, url, suffix)

    # Handle uploaded file
    else:
        file_obj = file_or_url

        if not isinstance(file_obj, web.FileField):
            raise RuntimeError("Invalid file")

        content_type = file_obj.content_type or ""
        filename: str = getattr(file_obj, "filename", "")
        file_obj.file.seek(0)
        content = file_obj.file.read()
        _write_preview_content(model_path, content, content_type, filename or content_type, suffix)


def replace_model_previews(model_path: str, items: list[Any]) -> int:
    """Rewrite the whole preview set in the supplied order (edit-save path).

    Mirrors the download-completion path: every source is resolved to bytes
    FIRST (local preview file read, HTTP download, or uploaded multipart
    bytes), then the old set is removed and the bytes are written into the
    suffix slots. Reading everything up front makes reorders collision-free
    (an earlier slot write can never destroy a later entry's source), and
    keeping the resolution server-side removes every browser-side failure
    mode (fetch errors, MIME mislabeling, cache staleness).

    Raises when any entry cannot be resolved or written: a partially written
    gallery would silently reorder the primary preview.
    """
    staged: list[tuple[str, str, bytes]] = []
    resolve_failures: list[str] = []
    for index, item in enumerate(items):
        if item is None or item == "":
            continue
        content: bytes | None = None
        content_type = ""
        name = ""
        try:
            if type(item) is str:
                url = item
                if url == "undefined":
                    continue
                if url.startswith("/model-manager/preview/"):
                    local = _resolve_local_preview(url)
                    if local:
                        with open(local, "rb") as f:
                            content = f.read()
                        name = url
                if content is None:
                    if url.startswith(("blob:", "data:")):
                        # Browser-local object URLs cannot be resolved
                        # server-side; the client must upload the bytes as a
                        # multipart file (as the editor now does).
                        raise RuntimeError(f"browser-local preview url cannot be resolved server-side: {url[:48]}...")
                    if not url.startswith("http"):
                        raise RuntimeError(f"invalid preview url: {url}")
                    response = requests.get(url, timeout=(15, 120))
                    response.raise_for_status()
                    content = response.content
                    content_type = response.headers.get("content-type", "") or ""
                    name = url
            else:
                if not isinstance(item, web.FileField):
                    raise RuntimeError("Invalid file")
                item.file.seek(0)
                content = item.file.read()
                content_type = item.content_type or ""
                name = getattr(item, "filename", "")
            staged.append((name, content_type, content))
        except Exception as e:
            resolve_failures.append(f"#{index}: {e}")
    if resolve_failures or not staged:
        raise RuntimeError("Failed to resolve preview entries: " + "; ".join(resolve_failures or ["no entries"]))
    if len(staged) > len(_PREVIEW_SUFFIXES):
        # Writing past the scheme would create files no listing ever shows
        # (and no cleanup ever removes): refuse loudly instead.
        raise RuntimeError(f"Too many preview entries: {len(staged)} (max {len(_PREVIEW_SUFFIXES)})")
    remove_model_preview(model_path)
    failures: list[str] = []
    written = 0
    for index, (name, content_type, content) in enumerate(staged):
        suffix = _PREVIEW_SUFFIXES[index]
        try:
            _write_preview_content(model_path, content, content_type, name, suffix)
            written += 1
        except Exception as e:
            failures.append(f"#{index}: {e}")
    if failures:
        raise RuntimeError("Failed to save preview entries: " + "; ".join(failures))
    return written


def save_model_previews(
    model_path: str,
    items: list[Any],
    platform: str | None = None,
    headers: dict | None = None,
    strict: bool = False,
) -> int:
    """Save every supplied preview, in order, under the naming scheme.

    Feature: the editor and the download flow used to keep a single preview
    file and silently drop the rest of a Civitai/Hugging Face gallery. Each
    entry is now stored - primary as `<basename>.<ext>`, the following ones as
    `<basename>.preview.<ext>`, `<basename>.preview2.<ext>`, ... - so the
    carousel and the lightbox can page through all of them.

    With ``strict`` a single unwritable entry fails the whole call instead of
    being dropped: a partially written gallery would otherwise reorder the
    primary behind the caller's back (the "primary swap reverted" defect).

    Returns the number of previews actually written.
    """
    written = 0
    failures: list[str] = []
    for index, item in enumerate(items):
        if item is None or item == "":
            continue
        if index >= len(_PREVIEW_SUFFIXES):
            # Past the naming scheme: such a file would never be listed (and
            # never cleaned up) again - drop it with a warning instead of
            # writing an invisible preview.
            print_warning(f"Ignoring preview #{index}: gallery exceeds {len(_PREVIEW_SUFFIXES)} slots")
            continue
        suffix = _PREVIEW_SUFFIXES[index]
        try:
            save_model_preview(model_path, item, platform, headers, suffix=suffix)
            written += 1
        except Exception as e:
            # One bad gallery entry must not lose the whole preview set.
            print_warning(f"Failed to save preview #{index}: {e}")
            failures.append(f"#{index}: {e}")
    if strict and failures:
        raise RuntimeError("Failed to save preview entries: " + "; ".join(failures))
    return written


def _get_video_extension_from_url(url: str) -> str | None:
    """Extract video extension from URL."""
    from urllib.parse import urlparse

    path = urlparse(url).path.lower()
    for ext in VIDEO_EXTENSIONS:
        if path.endswith(ext):
            return ext
    return None


def _get_extension_from_content_type(content_type: str) -> str | None:
    """Map content-type to file extension."""
    return VIDEO_CONTENT_TYPE_MAP.get(content_type.lower())


def get_model_all_descriptions(model_path: str):
    base_dirname = os.path.dirname(model_path)
    files = search_files(base_dirname)
    files = folder_paths.filter_files_extensions(files, [".txt", ".md"])

    basename = os.path.splitext(os.path.basename(model_path))[0]
    output: list[str] = []
    for file in files:
        file_basename = os.path.splitext(file)[0]
        if file_basename == basename:
            output.append(file)
    return output


def get_model_description_name(model_path: str):
    descriptions = get_model_all_descriptions(model_path)
    basename = os.path.splitext(os.path.basename(model_path))[0]
    return descriptions[0] if len(descriptions) > 0 else f"{basename}.md"


def save_model_description(model_path: str, content: Any):
    if not isinstance(content, str):
        raise RuntimeError("Invalid description")

    base_dirname = os.path.dirname(model_path)

    # save new description
    basename = os.path.splitext(os.path.basename(model_path))[0]
    extension = ".md"
    new_desc_path = join_path(base_dirname, f"{basename}{extension}")

    with open(new_desc_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)


def rename_model(model_path: str, new_model_path: str):
    if model_path == new_model_path:
        return

    if os.path.exists(new_model_path):
        raise RuntimeError(f"Model {new_model_path} already exists")

    model_name = os.path.splitext(os.path.basename(model_path))[0]
    new_model_name = os.path.splitext(os.path.basename(new_model_path))[0]

    model_dirname = os.path.dirname(model_path)
    new_model_dirname = os.path.dirname(new_model_path)

    if not os.path.exists(new_model_dirname):
        os.makedirs(new_model_dirname)

    # move model
    shutil.move(model_path, new_model_path)

    # move preview
    previews = get_model_all_previews(model_path)
    for preview in previews:
        preview_path = join_path(model_dirname, preview)
        preview_ext = os.path.splitext(preview)[1]
        preview_stem = preview[: -len(preview_ext)] if preview_ext else preview
        # BUG FIX: every non-primary preview used to be re-filed as
        # `<new>.preview<ext>`, so a gallery of three or more images collapsed
        # onto a single file during a rename / compress (the second move
        # overwrote the first, and the `.preview2…` slots were lost entirely).
        # The scheme suffix of each preview ("" / ".preview" / ".preview<N>")
        # is carried over verbatim, keeping the gallery order intact.
        suffix = preview_stem[len(model_name) :] if preview_stem.startswith(model_name) else ""
        if suffix not in _PREVIEW_SUFFIXES:
            suffix = ".preview"
        new_preview_path = join_path(new_model_dirname, f"{new_model_name}{suffix}{preview_ext}")
        shutil.move(preview_path, new_preview_path)

    # move description
    description = get_model_description_name(model_path)
    description_path = join_path(model_dirname, description)
    if os.path.isfile(description_path):
        new_description_path = join_path(new_model_dirname, f"{new_model_name}.md")
        shutil.move(description_path, new_description_path)


import pickle


def save_dict_pickle_file(filename: str, data: Any) -> None:
    with open(filename, "wb") as f:
        pickle.dump(data, f)


def load_dict_pickle_file(filename: str) -> dict:
    with open(filename, "rb") as f:
        return pickle.load(f)


def resolve_setting_key(key: str) -> str:
    key_paths = key.split(".")
    setting_id: Any = config.setting_key
    try:
        for key_path in key_paths:
            setting_id = setting_id[key_path]
    except Exception:
        pass
    if not isinstance(setting_id, str):
        raise RuntimeError(f"Invalid key: {key}")

    return setting_id


def set_setting_value(request: web.Request, key: str, value: Any):
    try:
        setting_id = resolve_setting_key(key)
        settings = config.serverInstance.user_manager.settings.get_settings(request)
        settings[setting_id] = value
        config.serverInstance.user_manager.settings.save_settings(request, settings)
    except Exception as e:
        print_debug(f"Failed to save setting {key}: {e}")


def get_setting_value(request: web.Request, key: str, default: Any = None) -> Any:
    try:
        setting_id = resolve_setting_key(key)
        settings = config.serverInstance.user_manager.settings.get_settings(request)
        return settings.get(setting_id, default)
    except Exception as e:
        print_debug(f"Failed to load setting {key}: {e}")
        return default


async def send_json(event: str, data: Any, sid: str | None = None):
    await config.serverInstance.send_json(event, data, sid)


import importlib.metadata
import importlib.util
import subprocess
import sys


def _requirement_name(requirement: str) -> str:
    """
    Extract the bare distribution/import name from a PEP 508 requirement
    string ("markdownify>=0.14.0" -> "markdownify").
    """
    name = requirement.strip()
    for sep in ("<", ">", "=", "!", "~", ";", "[", "@", " "):
        index = name.find(sep)
        if index != -1:
            name = name[:index]
    return name


def _version_tuple(version: str):
    import re as _re

    parts = _re.findall(r"\d+", version.split("+")[0].split("-")[0])
    return tuple(int(part) for part in parts[:4]) or (0,)


def _spec_satisfied(installed: str, spec: str) -> bool:
    spec = spec.strip()
    if not spec:
        return True
    for op in (">=", "<=", "==", "!=", "~=", ">", "<"):
        if spec.startswith(op):
            inst = _version_tuple(installed)
            target = _version_tuple(spec[len(op) :])
            width = max(len(inst), len(target))
            inst = inst + (0,) * (width - len(inst))
            target = target + (0,) * (width - len(target))
            return {
                ">=": inst >= target,
                "<=": inst <= target,
                "==": inst == target,
                "!=": inst != target,
                "~=": inst >= target,
                ">": inst > target,
                "<": inst < target,
            }[op]
    return True


def requirement_satisfied(requirement: str) -> bool:
    # True when the installed distribution meets every version specifier.
    name = _requirement_name(requirement)
    try:
        installed = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    specs = requirement.strip()[len(name) :]
    return all(_spec_satisfied(installed, spec) for spec in specs.split(","))


def is_installed(package_name: str):
    # BUG FIX: requirements.txt entries carry version specifiers
    # ("hf_xet>=1.1.0"). Probing importlib with the full specifier never
    # matches, so every requirement looked "missing" and pip re-ran on EVERY
    # ComfyUI startup. Check the bare package name instead; pip_install still
    # receives the full specifier so version constraints are honoured.
    name = _requirement_name(package_name)
    if not name:
        return False

    try:
        importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        try:
            spec = importlib.util.find_spec(name)
        except (ModuleNotFoundError, ValueError):
            return False

        return spec is not None

    # RANGE ENFORCEMENT: an installed but out-of-range distribution (e.g. a
    # huggingface_hub older than the `>=1.32.0` floor in requirements.txt)
    # must count as missing so pip_install() corrects it on startup instead
    # of the pin being nominal.
    return requirement_satisfied(package_name)


def pip_install(package_name: str):
    subprocess.run([sys.executable, "-m", "pip", "install", package_name], check=True)
