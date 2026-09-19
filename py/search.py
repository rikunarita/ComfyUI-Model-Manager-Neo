"""Cross-platform model search and Civitai helpers (discovery routes).

Routes
------
GET /model-manager/search?query=&limit=&platform=&cursor=
    Parallel model-name search across Hugging Face (huggingface_hub
    ``HfApi.list_models``), ModelScope (``modelscope_hub`` ``list_repos``) and
    Civitai (public REST ``/api/v1/models``). Every item carries the owner
    avatar (best effort) and deep links to the model page and the owner page.
    Results page per platform through an opaque ``nextCursor`` (HF: item
    offset, ModelScope: page number, Civitai: the API's own cursor - with a
    ``query`` the API refuses ``page``); re-requesting with ``platform`` +
    ``cursor`` appends the next page ("show more").
GET /model-manager/auth-status
    Which hub API keys are currently configured (no network round-trip).
GET /model-manager/civitai/whoami
    The authenticated Civitai account (``GET https://civitai.com/api/v1/me``).
GET /model-manager/civitai/image-meta?model-version-id=&url=
    Generation metadata (prompt / sampler / steps / seed / resources, …) of one
    preview image of a Civitai model version (``withMeta=true&flatMeta=true``).

All network calls run in the IO executor; a failing provider degrades to an
``error`` entry instead of failing the whole search.
"""

import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse

import requests
from aiohttp import web

from . import auth
from . import utils
from .information import MODELSCOPE_INTL_ENDPOINT

SEARCH_TIMEOUT = 12.0
_UA = {"User-Agent": "ComfyUI-Model-Manager-Neo/0.1"}

# owner -> avatar url (or None when the hub has none); bounded, best effort.
_AVATAR_CACHE: dict[str, str | None] = {}
_AVATAR_CACHE_LIMIT = 256


def _cache_avatar(key: str, value: str | None) -> str | None:
    _AVATAR_CACHE[key] = value
    while len(_AVATAR_CACHE) > _AVATAR_CACHE_LIMIT:
        _AVATAR_CACHE.pop(next(iter(_AVATAR_CACHE)))
    return value


# ---------------------------------------------------------------------------
# Avatar proxy. ModelScope's resource CDN serves uploaded avatar objects with
# ``Content-Type: application/octet-stream`` (verified live on both
# resources.modelscope.ai and resources.modelscope.cn), which browsers may
# refuse to paint inside ``<img>``; hot-link- and geo-unstable CDNs are another
# failure source the user's browser should not have to fight. The extension
# therefore re-serves hub avatars from its own route with a sniffed, correct
# content type, cached in memory with an ETag like the SVG artwork.
# ---------------------------------------------------------------------------
_AVATAR_PROXY_HOSTS = ("modelscope.ai", "modelscope.cn", "huggingface.co", "civitai.com")
_AVATAR_PROXY_CACHE: dict[str, tuple[str, str, bytes]] = {}
_AVATAR_PROXY_LIMIT = 96


def _sniff_image_content_type(body: bytes) -> str:
    if body[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if body[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if body[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    if body[:2] == b"BM":
        return "image/bmp"
    if b"<svg" in body[:64]:
        return "image/svg+xml"
    return "application/octet-stream"


def _fetch_avatar_bytes(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=_UA, timeout=10)
    except Exception:
        return None
    if r.status_code != 200 or not r.content:
        return None
    return r.content


def avatar_proxy_url(url: str | None) -> str | None:
    """Route a hub avatar through the extension's proxy (None stays None)."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.scheme != "https":
        return None
    host = parsed.hostname or ""
    if not host.endswith(_AVATAR_PROXY_HOSTS):
        return None
    return f"/model-manager/avatar?url={quote(url, safe='')}"


def _hf_avatar(owner: str) -> str | None:
    """Hugging Face owner avatar.

    Personal accounts answer ``{"avatarUrl": …}`` on
    ``GET /api/users/{name}/avatar``; organisations live under
    ``GET /api/organizations/{name}/avatar`` instead - the users endpoint
    answers 404 ("This user does not exist") for them, which is why org-owned
    repositories (Qwen, unsloth, …) used to fall back to an initials badge.
    Both shapes were verified against the live API. Accounts without any
    avatar fall back to the initials badge in the UI.
    """
    if owner in _AVATAR_CACHE:
        return _AVATAR_CACHE[owner]
    for kind in ("users", "organizations"):
        try:
            r = requests.get(
                f"https://huggingface.co/api/{kind}/{owner}/avatar",
                headers=_UA,
                timeout=8,
            )
            if r.status_code != 200:
                continue
            url = (r.json() or {}).get("avatarUrl")
            if isinstance(url, str) and url:
                return _cache_avatar(owner, url)
        except Exception:
            continue
    return _cache_avatar(owner, None)


def _search_huggingface(query: str, limit: int, cursor: str | None) -> tuple[list[dict], str | None]:
    from huggingface_hub import HfApi

    items: list[dict] = []
    offset = max(0, int(cursor or 0))
    # `expand=["author"]` is required: without it list_models leaves
    # `author` empty on search results (verified against huggingface_hub).
    # One extra item is fetched to learn whether a further page exists.
    models = HfApi().list_models(
        search=query, sort="downloads", limit=offset + limit + 1, expand=["author"]
    )
    seen = 0
    for m in models:
        mid = getattr(m, "id", None) or getattr(m, "modelId", None)
        if not mid or "/" not in mid:
            continue
        if seen < offset:
            seen += 1
            continue
        if len(items) > limit:
            break
        owner, repo = mid.split("/", 1)
        owner = getattr(m, "author", None) or owner
        items.append(
            {
                "platform": "hf",
                "key": mid,
                "owner": owner,
                "repo": repo,
                "title": mid,
                "downloads": getattr(m, "downloads", 0) or 0,
                "likes": getattr(m, "likes", 0) or 0,
                "avatar": _hf_avatar(owner),
                "pageUrl": f"https://huggingface.co/{mid}",
                "ownerUrl": f"https://huggingface.co/{owner}",
            }
        )
        seen += 1
    next_cursor = str(offset + limit) if len(items) > limit else None
    return items[:limit], next_cursor


_MS_OWNER_CACHE: dict[str, tuple[str | None, str | None, str | None]] = {}
_MS_OWNER_CACHE_LIMIT = 256


def _cache_ms_owner(key: str, value: tuple[str | None, str | None, str | None]):
    _MS_OWNER_CACHE[key] = value
    while len(_MS_OWNER_CACHE) > _MS_OWNER_CACHE_LIMIT:
        _MS_OWNER_CACHE.pop(next(iter(_MS_OWNER_CACHE)))
    return value


def _ms_plain_description(desc: str | None) -> str | None:
    """Plain-text form of a ModelScope profile description.

    ModelScope answers either plain text or a rich-text JSON tree
    (``["root",{},["p",{},["span",{"data-type":"text"},["span",
    {"data-type":"leaf"},"…"]]]]``); the JSON form is flattened to its leaf
    strings so a tooltip never shows raw JSON. Empty leaves yield None.
    """
    text = (desc or "").strip()
    if not text:
        return None
    if not text.startswith("["):
        return text
    try:
        leaves: list[str] = []

        def walk(node):
            if isinstance(node, list):
                if len(node) >= 2 and node[-2] == "leaf" and isinstance(node[-1], str):
                    leaves.append(node[-1])
                for child in node:
                    walk(child)
            elif isinstance(node, dict):
                for child in node.values():
                    walk(child)

        walk(json.loads(text))
        plain = "".join(leaves).strip()
        return plain or None
    except Exception:
        return None


def _ms_owner_info(owner: str, name: str) -> tuple[str | None, str | None, str | None]:
    """(avatar, display, description) of a ModelScope owner, via the payload.

    ``GET /api/v1/models/{owner}/{name}`` answers ``{"Data": {"Name": ...,
    "Organization": {"Name": ..., "Description": ..., "Avatar": ...}}}``.
    ``Data.Organization.Name`` is the organization's display name (the block
    is absent for personal accounts), ``Data.Organization.Description`` the
    profile description (may be an empty string), and
    ``Data.Organization.Avatar`` the organization's avatar URL. Rich-text
    JSON descriptions are flattened to plain text (see
    ``_ms_plain_description``). The legacy ``/openapi/v1/`` surface the SDK's
    ``openapi.get_model`` hits carries none of them (verified against the
    live endpoint), which is why owners used to fall back to an initials
    badge. Personal accounts keep the raw account name and the initials badge
    in the UI. Verified against the live international endpoint.
    """
    if owner in _MS_OWNER_CACHE:
        return _MS_OWNER_CACHE[owner]
    try:
        r = requests.get(
            f"{MODELSCOPE_INTL_ENDPOINT}/api/v1/models/{owner}/{name}",
            headers=_UA,
            timeout=8,
        )
        if r.status_code != 200:
            return _cache_ms_owner(owner, (None, None, None))
        data = (r.json() or {}).get("Data") or {}
        org = data.get("Organization") or {}
        display = org.get("Name")
        desc = org.get("Description")
        avatar = org.get("Avatar")
        if not isinstance(display, str) or not display.strip():
            return _cache_ms_owner(owner, (None, None, None))
        return _cache_ms_owner(
            owner,
            (
                avatar.strip() if isinstance(avatar, str) and avatar.strip() else None,
                display.strip(),
                _ms_plain_description(desc if isinstance(desc, str) else None),
            ),
        )
    except Exception:
        return _cache_ms_owner(owner, (None, None, None))


def _search_modelscope(query: str, limit: int, cursor: str | None) -> tuple[list[dict], str | None]:
    from modelscope_hub import HubApi

    api = HubApi(endpoint=MODELSCOPE_INTL_ENDPOINT)
    page_number = max(1, int(cursor or 1))
    page = api.list_repos(
        "model", search=query, sort="downloads", page_number=page_number, page_size=limit
    )
    items: list[dict] = []
    for r in page.items:
        owner = getattr(r, "owner", None)
        name = getattr(r, "name", None)
        if not owner or not name:
            continue
        avatar, display, description = _ms_owner_info(owner, name)
        items.append(
            {
                "platform": "modelscope",
                "key": f"{owner}/{name}",
                "owner": owner,
                "ownerDisplay": display,
                "ownerDescription": description,
                "repo": name,
                "title": f"{owner}/{name}",
                "downloads": getattr(r, "downloads", 0) or 0,
                "likes": getattr(r, "likes", 0) or 0,
                "avatar": avatar_proxy_url(avatar),
                "pageUrl": f"{MODELSCOPE_INTL_ENDPOINT}/models/{owner}/{name}",
                "ownerUrl": f"{MODELSCOPE_INTL_ENDPOINT}/organization/{owner}",
            }
        )
    next_cursor = str(page_number + 1) if getattr(page, "has_next", False) else None
    return items, next_cursor


def _search_civitai(query: str, limit: int, cursor: str | None) -> tuple[list[dict], str | None]:
    token = auth.get_civitai_token()
    headers = dict(_UA)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params: dict[str, str] = {"query": query, "limit": str(limit)}
    # With a `query` the API refuses `page` and asks for cursor pagination
    # (verified live: "Cannot use page param with query search").
    if cursor:
        params["cursor"] = cursor
    r = requests.get(
        "https://civitai.com/api/v1/models",
        params=params,
        headers=headers,
        timeout=SEARCH_TIMEOUT,
    )
    r.raise_for_status()
    payload = r.json() or {}
    items: list[dict] = []
    for it in payload.get("items", []):
        mid = it.get("id")
        if not mid:
            continue
        creator = it.get("creator") or {}
        owner = creator.get("username") or f"user{it.get('userId', '')}"
        stats = it.get("stats") or {}
        items.append(
            {
                "platform": "civitai",
                "key": str(mid),
                "owner": owner,
                "repo": it.get("name") or str(mid),
                "title": it.get("name") or str(mid),
                "downloads": stats.get("downloadCount", 0) or 0,
                "likes": stats.get("likeCount", 0) or 0,
                "avatar": creator.get("image") or None,
                "pageUrl": f"https://civitai.com/models/{mid}",
                "ownerUrl": f"https://civitai.com/user/{owner}",
            }
        )
    next_cursor = (payload.get("metadata") or {}).get("nextCursor") or None
    return items, (str(next_cursor) if next_cursor is not None else None)


_PROVIDERS = {
    "hf": _search_huggingface,
    "modelscope": _search_modelscope,
    "civitai": _search_civitai,
}


class SearchRoutes:
    def add_routes(self, routes):
        @routes.get("/model-manager/search")
        async def search_models(request):
            query = (request.query.get("query") or "").strip()
            try:
                limit = max(1, min(20, int(request.query.get("limit") or 8)))
            except ValueError:
                limit = 8
            if not query:
                return web.json_response({"success": True, "data": {}})
            # "Show more" paging: a single platform can be re-requested with
            # its own cursor; a fresh search runs every provider cursor-less.
            platform = (request.query.get("platform") or "").strip()
            cursor = (request.query.get("cursor") or "").strip() or None
            loop = asyncio.get_running_loop()

            def run(provider: str, page_cursor: str | None):
                try:
                    items, next_cursor = _PROVIDERS[provider](query, limit, page_cursor)
                    return provider, {"items": items, "nextCursor": next_cursor}
                except Exception as e:  # provider outage must not kill the rest
                    utils.print_warning(f"search provider {provider} failed: {e}")
                    return provider, {"items": [], "error": str(e), "nextCursor": None}

            if platform in _PROVIDERS:
                name, res = await loop.run_in_executor(
                    utils.io_executor(), run, platform, cursor
                )
                return web.json_response({"success": True, "data": {name: res}})

            with ThreadPoolExecutor(max_workers=3) as pool:
                futs = [pool.submit(run, name, None) for name in _PROVIDERS]
                data = {}
                for fut in as_completed(futs, timeout=SEARCH_TIMEOUT + 5):
                    name, res = fut.result()
                    data[name] = res
            return web.json_response({"success": True, "data": data})

        @routes.get("/model-manager/avatar")
        async def avatar_proxy(request):
            """Re-serve a hub avatar with a correct, sniffed content type.

            See ``avatar_proxy_url``: ModelScope's CDN answers avatar objects
            as ``application/octet-stream``, which browsers may refuse to
            paint; the proxy also keeps hot-link- and geo-unstable CDNs out of
            the user's browser. Cached in memory with an ETag and a day-long
            max-age, like the SVG artwork.
            """
            url = (request.query.get("url") or "").strip()
            try:
                parsed = urlparse(url)
            except Exception:
                raise web.HTTPNotFound()
            host = parsed.hostname or ""
            if parsed.scheme != "https" or not host.endswith(_AVATAR_PROXY_HOSTS):
                raise web.HTTPNotFound()

            hit = _AVATAR_PROXY_CACHE.get(url)
            if hit is None:
                loop = asyncio.get_running_loop()
                body = await loop.run_in_executor(utils.io_executor(), _fetch_avatar_bytes, url)
                if body is None:
                    raise web.HTTPNotFound()
                etag = f'"avatar-{hashlib.sha256(body).hexdigest()[:16]}"'
                hit = (etag, _sniff_image_content_type(body), body)
                _AVATAR_PROXY_CACHE[url] = hit
                while len(_AVATAR_PROXY_CACHE) > _AVATAR_PROXY_LIMIT:
                    _AVATAR_PROXY_CACHE.pop(next(iter(_AVATAR_PROXY_CACHE)))
            etag, content_type, body = hit
            headers = {
                "ETag": etag,
                "Cache-Control": "public, max-age=86400, must-revalidate",
            }
            if request.headers.get("If-None-Match") == etag:
                return web.Response(status=304, headers=headers)
            return web.Response(body=body, content_type=content_type, headers=headers)

        @routes.get("/model-manager/auth-status")
        async def auth_status(request):
            return web.json_response(
                {
                    "success": True,
                    "data": {
                        "civitai": bool(auth.get_civitai_token()),
                        "hf": bool(auth.get_hf_token()),
                        "modelscope": bool(auth.get_modelscope_token()),
                    },
                }
            )

        @routes.get("/model-manager/civitai/whoami")
        async def civitai_whoami(request):
            """Verified against the Civitai CLI: identity lives at /api/v1/me."""
            token = auth.get_civitai_token()
            if not token:
                return web.json_response(
                    {
                        "success": False,
                        "error": (
                            "Civitai API key not set. Create one at "
                            "https://civitai.com/user/account and store it in "
                            "Settings > Model Manager Neo > API Key."
                        ),
                    }
                )
            loop = asyncio.get_running_loop()

            def fetch():
                r = requests.get(
                    "https://civitai.com/api/v1/me",
                    headers={**_UA, "Authorization": f"Bearer {token}"},
                    timeout=SEARCH_TIMEOUT,
                )
                r.raise_for_status()
                return r.json() or {}

            try:
                me = await loop.run_in_executor(utils.io_executor(), fetch)
                return web.json_response(
                    {
                        "success": True,
                        "data": {
                            "name": me.get("username"),
                            "id": me.get("id"),
                        },
                    }
                )
            except Exception as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                hint = (
                    " The key was rejected (401): check its scopes/validity at "
                    "https://civitai.com/user/account."
                    if status == 401
                    else ""
                )
                return web.json_response(
                    {"success": False, "error": f"Civitai whoami failed: {e}.{hint}"}
                )

        @routes.get("/model-manager/civitai/image-meta")
        async def civitai_image_meta(request):
            """Generation metadata of one preview image of a model version.

            ``GET /api/v1/images?modelVersionId=…&withMeta=true&flatMeta=true``
            (the parameter pair the official CLI relies on - without it the
            API answers ``meta: null``). The stored preview URL is matched by
            the image id encoded in its file name, falling back to a full URL
            compare.
            """
            version_id = (request.query.get("model-version-id") or "").strip()
            url = (request.query.get("url") or "").strip()
            if not version_id or not url:
                return web.json_response({"success": True, "data": None})
            loop = asyncio.get_running_loop()

            def fetch():
                r = requests.get(
                    "https://civitai.com/api/v1/images",
                    params={
                        "modelVersionId": version_id,
                        "withMeta": "true",
                        "flatMeta": "true",
                        "limit": "100",
                    },
                    headers=_UA,
                    timeout=SEARCH_TIMEOUT,
                )
                r.raise_for_status()
                return r.json() or {}

            try:
                payload = await loop.run_in_executor(utils.io_executor(), fetch)
            except Exception as e:
                utils.print_warning(f"civitai image meta fetch failed: {e}")
                return web.json_response({"success": True, "data": None})

            want_id = url.rstrip("/").split("/")[-1].split(".")[0]
            want_url = url.split("?")[0]
            for it in payload.get("items", []):
                item_url = (it.get("url") or "").split("?")[0]
                if str(it.get("id")) == want_id or item_url == want_url:
                    meta = it.get("meta")
                    return web.json_response(
                        {"success": True, "data": meta if isinstance(meta, dict) else None}
                    )
            return web.json_response({"success": True, "data": None})
