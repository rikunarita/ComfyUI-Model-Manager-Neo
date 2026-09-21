"""Identify a local model file against the Civitai catalog.

Routes
------
GET /model-manager/identify-by-hash?type=&index=&filename=
    Hashes one local model file and looks the hashes up on the public
    ``GET /api/v1/model-versions/by-hash/{hash}`` endpoint (the route the
    official CLI relies on). The hashes recorded in the sidecar front matter
    (``<basename>.md``) are tried first, so models downloaded from Civitai
    identify without touching the file; otherwise the file is hashed in a
    single streaming pass: SHA256 (whole file), AutoV2 (``SHA256[:10]``),
    AutoV1 (``SHA256(file[1 MiB : 1 MiB + 64 KiB])[:8]``), CRC32 (Civitai's
    byte-swapped notation) and BLAKE3 when the optional ``blake3`` module is
    importable - every published definition was verified against the live
    values of a real model file. The first lookup hit wins; the hashing runs
    on the CPU pool and the lookups on the IO pool, so neither blocks the
    event loop.
"""

import asyncio
import binascii
import hashlib
import os
import struct

import requests
import yaml
from aiohttp import web

from . import auth, utils

_AUTOV1_OFFSET = 0x100000  # 1 MiB
_AUTOV1_WINDOW = 0x10000  # 64 KiB
_CHUNK = 1024 * 1024
_LOOKUP_ORDER = ("SHA256", "AutoV2", "BLAKE3", "CRC32", "AutoV1")
_LOOKUP_TIMEOUT = 12.0


def _crc32_hex(value: int) -> str:
    """Civitai's CRC32 notation is the file's CRC32 with its four bytes
    reversed (verified against the published hashes of a live model file)."""
    swapped = struct.unpack(">I", struct.pack("<I", value & 0xFFFFFFFF))[0]
    return f"{swapped:08X}"


def compute_hashes(path: str) -> dict[str, str]:
    """Single streaming pass over the file: every hash notation at once."""
    sha = hashlib.sha256()
    autov1 = hashlib.sha256()
    crc = 0
    try:
        import blake3 as _blake3

        blake = _blake3.blake3()
    except Exception:
        blake = None
    pos = 0
    win_start, win_end = _AUTOV1_OFFSET, _AUTOV1_OFFSET + _AUTOV1_WINDOW
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            sha.update(chunk)
            crc = binascii.crc32(chunk, crc)
            if blake is not None:
                blake.update(chunk)
            lo = max(win_start, pos)
            hi = min(win_end, pos + len(chunk))
            if hi > lo:
                autov1.update(chunk[lo - pos : hi - pos])
            pos += len(chunk)
    sha_hex = sha.hexdigest().upper()
    hashes = {
        "SHA256": sha_hex,
        "AutoV2": sha_hex[:10],
        "AutoV1": autov1.hexdigest()[:8].upper(),
        "CRC32": _crc32_hex(crc),
    }
    if blake is not None:
        hashes["BLAKE3"] = blake.hexdigest().upper()
    return hashes


def recorded_hashes(model_path: str) -> dict[str, str]:
    """The hashes recorded in the sidecar front matter, if any."""
    desc = utils.get_model_description_name(model_path)
    path = utils.join_path(os.path.dirname(model_path), desc)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if not text.startswith("---"):
            return {}
        end = text.find("---", 3)
        if end < 0:
            return {}
        front = yaml.safe_load(text[3:end]) or {}
        hashes = front.get("hashes") if isinstance(front, dict) else None
        if not isinstance(hashes, dict):
            return {}
        return {str(key): str(value).strip().upper() for key, value in hashes.items() if str(value).strip()}
    except Exception:
        return {}


def _shape_match(version: dict, kind: str, value: str) -> dict:
    model = version.get("model") or {}
    model_id = model.get("id") or version.get("modelId")
    version_id = version.get("id")
    files = version.get("files") or []
    return {
        "hash": value,
        "hashType": kind,
        "versionId": version_id,
        "modelId": model_id,
        "modelName": model.get("name"),
        "modelType": model.get("type"),
        "versionName": version.get("name"),
        "baseModel": version.get("baseModel"),
        "trainedWords": version.get("trainedWords") or [],
        "images": [
            image.get("url") for image in version.get("images") or [] if isinstance(image, dict) and image.get("url")
        ],
        "files": [
            {
                "name": f.get("name"),
                "sizeKB": f.get("sizeKB"),
                "downloadUrl": f.get("downloadUrl"),
                "hashes": f.get("hashes"),
            }
            for f in files
            if isinstance(f, dict)
        ],
        "modelPage": (
            f"https://civitai.com/models/{model_id}?modelVersionId={version_id}" if model_id and version_id else None
        ),
        "downloadCommand": (f"civitai download --version {version_id} --layout comfyui" if version_id else None),
        "createdAt": version.get("createdAt"),
        "updatedAt": version.get("updatedAt"),
    }


def lookup_by_hashes(hashes: dict[str, str]) -> dict | None:
    """First catalog hit across the hash notations (None when no entry)."""
    headers = auth.get_civitai_headers()
    for kind in _LOOKUP_ORDER:
        value = (hashes.get(kind) or "").strip()
        if not value:
            continue
        try:
            r = requests.get(
                f"https://civitai.com/api/v1/model-versions/by-hash/{value}",
                headers=headers,
                timeout=_LOOKUP_TIMEOUT,
            )
        except Exception as e:
            utils.print_warning(f"civitai by-hash lookup ({kind}) failed: {e}")
            continue
        if r.status_code != 200:
            continue
        try:
            payload = r.json() or {}
        except Exception:
            continue
        if not payload.get("id"):
            continue
        return _shape_match(payload, kind, value)
    return None


class IdentifyRoutes:
    def add_routes(self, routes):
        @routes.get("/model-manager/identify-by-hash")
        async def identify_by_hash(request):
            model_type = (request.query.get("type") or "").strip()
            index = (request.query.get("index") or "").strip()
            filename = (request.query.get("filename") or "").strip()
            if not model_type or not index or not filename:
                return web.json_response({"success": False, "error": "type, index and filename are required."})
            try:
                full_path = utils.get_full_path(model_type, int(index), filename)
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})
            if not os.path.isfile(full_path):
                return web.json_response({"success": False, "error": f"File not found: {filename}"})

            loop = asyncio.get_running_loop()

            def run():
                hashes = recorded_hashes(full_path)
                match = lookup_by_hashes(hashes)
                hashed_file = False
                if match is None:
                    computed = utils.cpu_executor().submit(compute_hashes, full_path).result()
                    hashed_file = True
                    # Recorded values win where both exist; the computed set
                    # fills every notation the sidecar did not carry.
                    hashes = {**computed, **hashes}
                    match = lookup_by_hashes(hashes)
                return {"matched": match, "hashes": hashes, "hashedFile": hashed_file}

            try:
                data = await loop.run_in_executor(utils.io_executor(), run)
                return web.json_response({"success": True, "data": data})
            except Exception as e:
                error_msg = f"Identify model failed: {e}"
                utils.print_error(error_msg)
                return web.json_response({"success": False, "error": error_msg})
