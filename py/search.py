"""Cross-platform model search and Civitai helpers (discovery routes).

Routes
------
GET /model-manager/search?query=&limit=&platform=&cursor=&sort_hf=&sort_ms=&sort_civitai=
    Parallel model-name search across Hugging Face (huggingface_hub
    ``HfApi.list_models``), ModelScope (``modelscope_hub`` ``list_repos``) and
    Civitai (public REST ``/api/v1/models``). Every item carries the owner
    avatar (best effort) and deep links to the model page and the owner page.
    Per-platform sort orders arrive as ``sort_hf`` / ``sort_ms`` /
    ``sort_civitai`` (defaults: trending_score / likes / Highest Rated); values
    outside each platform's accepted set fall back to the default.
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

Network calls run on the event loop through the shared aiohttp session
(``py/http_client.py``, Quick Win A3 — Plan §4.8-A3); only the hub SDKs
(``huggingface_hub`` / ``modelscope_hub``) still use an IO-executor worker, and
a failing provider degrades to an ``error`` entry instead of failing the whole
search.
"""

import asyncio
import hashlib
import json
from typing import Any, cast
from urllib.parse import quote, urlparse

from aiohttp import web

from . import auth, http_client, utils
from .information import MODELSCOPE_INTL_ENDPOINT

# A3 (Plan §4.8-A3 / §6.2 Phase 6): every hub round trip of this module goes
# through the shared aiohttp session (`py/http_client.py`) instead of a
# blocking `requests.get` in an io-executor worker - no thread hop, one
# connector, one timeout policy. The base URLs are module constants so the mock
# tests can point them at a local server (no live API dependency).
SEARCH_TIMEOUT = http_client.SEARCH_TIMEOUT
#: Extra seconds the three-provider sweep waits past the per-call timeout
#: before it returns partial results (the historical `as_completed(...,
#: timeout=SEARCH_TIMEOUT + 5)` margin; a constant so the mock tests can
#: exercise the partial-results path without a 5 s sleep).
SWEEP_MARGIN = 5.0
CIVITAI_API_BASE = "https://civitai.com/api/v1"
HF_API_BASE = "https://huggingface.co/api"
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
# Avatars are tiny; refuse anything larger so a hostile (or misbehaving) CDN
# object cannot balloon the in-memory cache.
_AVATAR_PROXY_MAX_BYTES = 5 * 1024 * 1024


def _is_allowed_avatar_host(host: str) -> bool:
    """Exact host or subdomain of an allowed hub.

    A plain ``endswith`` suffix test also matched look-alike domains
    (``evil-civitai.com``), turning the proxy into a limited SSRF relay;
    the dot-boundary check closes that without touching legitimate avatars
    (``resources.modelscope.ai`` and friends keep matching).
    """
    return any(host == domain or host.endswith("." + domain) for domain in _AVATAR_PROXY_HOSTS)


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


async def _fetch_avatar_bytes(url: str) -> bytes | None:
    """Fetch an avatar body, capped at `_AVATAR_PROXY_MAX_BYTES`.

    Streaming with the cap enforced WHILE reading (the historical
    `stream=True` + `iter_content` behaviour), so a hostile or misbehaving CDN
    object cannot balloon the in-memory cache. Any failure - transport, non-200,
    oversize - degrades to None, exactly as before.
    """
    return await http_client.fetch_bytes_capped(url, headers=_UA, timeout=10.0, max_bytes=_AVATAR_PROXY_MAX_BYTES)


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
    if not _is_allowed_avatar_host(host):
        return None
    return f"/model-manager/avatar?url={quote(url, safe='')}"


async def _hf_avatar(owner: str) -> str | None:
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
            status, payload = await http_client.fetch_status_json(
                f"{HF_API_BASE}/{kind}/{owner}/avatar",
                headers=_UA,
                timeout=8.0,
            )
            if status != 200:
                continue
            url = (payload or {}).get("avatarUrl")
            if isinstance(url, str) and url:
                return _cache_avatar(owner, url)
        except Exception:
            continue
    return _cache_avatar(owner, None)


def _hf_list_models(query: str, limit: int, offset: int, sort: str) -> list[Any]:
    """The blocking `huggingface_hub` page fetch (httpx2 under the hood).

    Stays in an executor: A3 unifies Neo's OWN round trips on aiohttp, it does
    not replace the hub SDK (Plan §3.8 - `huggingface_hub` 2.x is httpx2-based,
    so a "unified" stack would be a third one).
    """
    from huggingface_hub import HfApi

    # `expand=["author"]` is required: without it list_models leaves
    # `author` empty on search results (verified against huggingface_hub).
    # One extra item is fetched to learn whether a further page exists.
    models = HfApi().list_models(
        search=query,
        # The settings surface exposes every sort key the HF endpoint accepts
        # (per the user's choice); huggingface_hub 2.x narrows the `sort`
        # annotation to a closed Literal even though the API itself still
        # serves the other documented keys. The cast keeps the user-selected
        # value working without pinning the hub version (zero runtime effect).
        sort=cast(Any, sort),
        limit=offset + limit + 1,
        # `expand` limits the payload to the listed fields: author (avatar /
        # owner link) plus the counters the result rows show as icons.
        expand=["author", "downloads", "likes"],
    )
    return list(models)


async def _search_huggingface(query: str, limit: int, cursor: str | None, sort: str) -> tuple[list[dict], str | None]:
    offset = max(0, int(cursor or 0))
    loop = asyncio.get_running_loop()
    models = await loop.run_in_executor(utils.io_executor(), _hf_list_models, query, limit, offset, sort)

    # Window selection is unchanged (skip `offset`, keep `limit + 1` to learn
    # whether a further page exists).
    page: list[tuple[dict, str]] = []
    seen = 0
    for m in models:
        mid = getattr(m, "id", None) or getattr(m, "modelId", None)
        if not mid or "/" not in mid:
            continue
        if seen < offset:
            seen += 1
            continue
        if len(page) > limit:
            break
        owner, repo = mid.split("/", 1)
        owner = getattr(m, "author", None) or owner
        page.append(
            (
                {
                    "platform": "hf",
                    "key": mid,
                    "owner": owner,
                    "repo": repo,
                    "title": mid,
                    "downloads": getattr(m, "downloads", 0) or 0,
                    "likes": getattr(m, "likes", 0) or 0,
                    # filled in below (the avatar probes are concurrent now);
                    # the key stays in its historical position in the dict
                    "avatar": None,
                    "pageUrl": f"https://huggingface.co/{mid}",
                    "ownerUrl": f"https://huggingface.co/{owner}",
                },
                owner,
            )
        )
        seen += 1
    has_more = len(page) > limit
    page = page[:limit]

    # A3: one avatar probe per DISTINCT owner, concurrently (the cache still
    # absorbs repeats across searches).
    owners = list(dict.fromkeys(owner for _, owner in page))
    avatars = await asyncio.gather(*[_hf_avatar(owner) for owner in owners])
    by_owner = dict(zip(owners, avatars, strict=True))
    items: list[dict] = []
    for item, owner in page:
        item["avatar"] = by_owner.get(owner)
        items.append(item)

    next_cursor = str(offset + limit) if has_more else None
    return items, next_cursor


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

        def is_leaf_marker(node) -> bool:
            """The rich-text leaf marker, in either shape the API has been seen
            to send.

            BUG FIX: only the bare ``"leaf"`` marker was recognised, but the
            documented payload (this function's own docstring, verified against
            the live endpoint) carries an ATTRIBUTE dict at that position -
            ``["span", {"data-type": "leaf"}, "…"]`` - so every rich-text
            description flattened to an empty string and the owner tooltip
            silently showed nothing.
            """
            if node == "leaf":
                return True
            return isinstance(node, dict) and node.get("data-type") == "leaf"

        def walk(node):
            if isinstance(node, list):
                if len(node) >= 2 and is_leaf_marker(node[-2]) and isinstance(node[-1], str):
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


async def _ms_owner_info(owner: str, name: str) -> tuple[str | None, str | None, str | None]:
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
        status, payload = await http_client.fetch_status_json(
            f"{MODELSCOPE_INTL_ENDPOINT}/api/v1/models/{owner}/{name}",
            headers=_UA,
            timeout=8.0,
        )
        if status != 200:
            return _cache_ms_owner(owner, (None, None, None))
        data = (payload or {}).get("Data") or {}
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


def _ms_list_repos(query: str, limit: int, page_number: int, sort: str) -> Any:
    """The blocking `modelscope_hub` page fetch (stays in an executor — A3
    unifies Neo's own round trips, not the hub SDKs; Plan §3.8)."""
    from modelscope_hub import HubApi

    api = HubApi(endpoint=MODELSCOPE_INTL_ENDPOINT)
    return api.list_repos("model", search=query, sort=sort, page_number=page_number, page_size=limit)


async def _search_modelscope(query: str, limit: int, cursor: str | None, sort: str) -> tuple[list[dict], str | None]:
    page_number = max(1, int(cursor or 1))
    loop = asyncio.get_running_loop()
    page = await loop.run_in_executor(utils.io_executor(), _ms_list_repos, query, limit, page_number, sort)

    rows: list[tuple[Any, str, str]] = []
    for r in page.items:
        owner = getattr(r, "owner", None)
        name = getattr(r, "name", None)
        if not owner or not name:
            continue
        rows.append((r, owner, name))

    # A3: the owner probes (one per result) run concurrently on the loop
    # instead of serially inside an executor worker.
    infos = await asyncio.gather(*[_ms_owner_info(owner, name) for _, owner, name in rows])

    items: list[dict] = []
    for (r, owner, name), (avatar, display, description) in zip(rows, infos, strict=True):
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


async def _search_civitai(query: str, limit: int, cursor: str | None, sort: str) -> tuple[list[dict], str | None]:
    token = auth.get_civitai_token()
    headers = dict(_UA)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params: dict[str, str] = {"query": query, "limit": str(limit), "sort": sort}
    # With a `query` the API refuses `page` and asks for cursor pagination
    # (verified live: "Cannot use page param with query search").
    if cursor:
        params["cursor"] = cursor
    # A3: fully async (no executor hop at all) - and a non-2xx still raises the
    # requests-worded HttpStatusError the provider wrapper reports verbatim.
    payload = (
        await http_client.fetch_json(
            f"{CIVITAI_API_BASE}/models",
            params=params,
            headers=headers,
            timeout=SEARCH_TIMEOUT,
        )
        or {}
    )
    items: list[dict] = []
    # Sort keys for the post-pass below (the API ignores `sort` whenever a
    # `query` is present - verified live - so the orders its payload can
    # prove are applied here, over the matched set).
    sort_keys: list[dict] = []
    for it in payload.get("items", []):
        mid = it.get("id")
        if not mid:
            continue
        creator = it.get("creator") or {}
        owner = creator.get("username") or f"user{it.get('userId', '')}"
        stats = it.get("stats") or {}
        sort_keys.append(
            {
                "downloads": stats.get("downloadCount", 0) or 0,
                "likes": stats.get("thumbsUpCount", 0) or 0,
                "comments": stats.get("commentCount", 0) or 0,
            }
        )
        items.append(
            {
                "platform": "civitai",
                "key": str(mid),
                "owner": owner,
                "repo": it.get("name") or str(mid),
                "title": it.get("name") or str(mid),
                "downloads": stats.get("downloadCount", 0) or 0,
                "likes": stats.get("thumbsUpCount", 0) or 0,
                "avatar": creator.get("image") or None,
                "pageUrl": f"https://civitai.com/models/{mid}",
                "ownerUrl": f"https://civitai.com/user/{owner}",
            }
        )
    # Keys without reliable payload data (Highest Rated - the default and the
    # API's own no-query order -, Most Collected, Most Images, Newest, Oldest
    # and Recently Added: the search payload carries neither collected /
    # image counts nor version dates) keep the API order instead of a
    # guessed one.
    paired = list(zip(items, sort_keys, strict=True))
    if sort == "Most Downloaded":
        paired.sort(key=lambda p: -p[0]["downloads"])
    elif sort == "Most Liked":
        paired.sort(key=lambda p: -p[1]["likes"])
    elif sort == "Most Discussed":
        paired.sort(key=lambda p: -p[1]["comments"])
    items = [p[0] for p in paired]
    next_cursor = (payload.get("metadata") or {}).get("nextCursor") or None
    return items, (str(next_cursor) if next_cursor is not None else None)


_PROVIDERS = {
    "hf": _search_huggingface,
    "modelscope": _search_modelscope,
    "civitai": _search_civitai,
}

# Sort values each platform accepts (verified against the live endpoints and
# the huggingface_hub docstring). Anything else - a stale setting, a hand-made
# query - falls back to the per-platform default instead of failing the search.
_SORTS = {
    "hf": ("trending_score", "downloads", "likes", "last_modified", "created_at"),
    "modelscope": ("likes", "downloads", "last_modified", "default"),
    "civitai": (
        "Highest Rated",
        "Most Downloaded",
        "Most Liked",
        "Most Discussed",
        "Most Collected",
        "Most Images",
        "Newest",
        "Oldest",
        "Recently Added",
    ),
}
_DEFAULT_SORTS = {"hf": "trending_score", "modelscope": "likes", "civitai": "Highest Rated"}
_SORT_PARAMS = {"hf": "sort_hf", "modelscope": "sort_ms", "civitai": "sort_civitai"}


def _resolve_sort(request, provider: str) -> str:
    value = (request.query.get(_SORT_PARAMS[provider]) or "").strip()
    return value if value in _SORTS[provider] else _DEFAULT_SORTS[provider]


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

            async def run(provider: str, page_cursor: str | None, sort: str) -> tuple[str, dict]:
                try:
                    items, next_cursor = await _PROVIDERS[provider](query, limit, page_cursor, sort)
                    return provider, {"items": items, "nextCursor": next_cursor}
                except Exception as e:  # provider outage must not kill the rest
                    utils.print_warning(f"search provider {provider} failed: {e}")
                    return provider, {"items": [], "error": str(e), "nextCursor": None}

            if platform in _PROVIDERS:
                # A3 (Plan §4.8-A3): the providers are coroutines now, so the
                # whole request runs on the event loop - the io-executor hop
                # (one of eight workers, pinned for the entire round trip) is
                # gone.
                name, res = await run(platform, cursor, _resolve_sort(request, platform))
                return web.json_response({"success": True, "data": {name: res}})

            # The three-provider sweep runs as three concurrent coroutines on
            # the loop (A3): the wait no longer needs an executor worker, and
            # the historical contract is kept exactly - the sweep is bounded by
            # the search timeout + 5 s and a provider that does not answer in
            # time degrades to a per-column "search timed out" entry instead of
            # failing the whole search (partial results survive).
            sort_map = {name: _resolve_sort(request, name) for name in _PROVIDERS}
            tasks = {name: asyncio.create_task(run(name, None, sort_map[name])) for name in _PROVIDERS}
            try:
                done, pending = await asyncio.wait(tasks.values(), timeout=SEARCH_TIMEOUT[1] + SWEEP_MARGIN)
            except BaseException:
                # The client went away (or the server is shutting down) while the
                # sweep was in flight: cancel the three provider coroutines
                # instead of leaving them running with nobody to read their
                # result. The old executor version got this for free from
                # `pool.shutdown(cancel_futures=True)` in its `finally`.
                for task in tasks.values():
                    task.cancel()
                raise
            if pending:
                utils.print_warning("search: provider timed out, returning partial results")
                for task in pending:
                    task.cancel()
                # Let the cancellations settle so no task is left dangling.
                await asyncio.gather(*pending, return_exceptions=True)
            data: dict[str, dict] = {}
            for task in tasks.values():
                if task in done and not task.cancelled():
                    name, res = task.result()
                    data[name] = res
            for name in _PROVIDERS:
                data.setdefault(
                    name,
                    {"items": [], "error": "search timed out", "nextCursor": None},
                )
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
            except Exception as exc:
                raise web.HTTPNotFound() from exc
            host = parsed.hostname or ""
            if parsed.scheme != "https" or not _is_allowed_avatar_host(host):
                raise web.HTTPNotFound()

            hit = _AVATAR_PROXY_CACHE.get(url)
            if hit is None:
                # A3: the fetch is async now, so the io-executor hop (and the
                # worker it pinned for the whole round trip) is gone.
                body = await _fetch_avatar_bytes(url)
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
            try:
                # A3: async on the loop (was a blocking requests.get inside an
                # io-executor worker). The exception shape is unchanged -
                # `HttpStatusError.response.status_code` is what the 401 hint
                # below reads, and `str(e)` keeps the requests wording.
                me = (
                    await http_client.fetch_json(
                        f"{CIVITAI_API_BASE}/me",
                        headers={**_UA, "Authorization": f"Bearer {token}"},
                        timeout=SEARCH_TIMEOUT,
                    )
                ) or {}
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
                    " The key was rejected (401): check its scopes/validity at https://civitai.com/user/account."
                    if status == 401
                    else ""
                )
                return web.json_response({"success": False, "error": f"Civitai whoami failed: {e}.{hint}"})

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
            try:
                # A3: async on the loop (was a blocking requests.get in a
                # worker).
                payload = (
                    await http_client.fetch_json(
                        f"{CIVITAI_API_BASE}/images",
                        params={
                            "modelVersionId": version_id,
                            "withMeta": "true",
                            "flatMeta": "true",
                            "limit": "100",
                        },
                        headers=_UA,
                        timeout=SEARCH_TIMEOUT,
                    )
                ) or {}
            except Exception as e:
                utils.print_warning(f"civitai image meta fetch failed: {e}")
                return web.json_response({"success": True, "data": None})

            want_id = url.rstrip("/").split("/")[-1].split(".")[0]
            want_url = url.split("?")[0]
            for it in payload.get("items", []):
                item_url = (it.get("url") or "").split("?")[0]
                if str(it.get("id")) == want_id or item_url == want_url:
                    meta = it.get("meta")
                    return web.json_response({"success": True, "data": meta if isinstance(meta, dict) else None})
            return web.json_response({"success": True, "data": None})
