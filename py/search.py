"""Cross-platform model search and Civitai helpers (discovery routes).

Routes
------
GET /model-manager/search?query=&limit=
    Parallel model-name search across Hugging Face (huggingface_hub
    ``HfApi.list_models``), ModelScope (``modelscope_hub`` ``list_repos``) and
    Civitai (public REST ``/api/v1/models``). Every item carries the owner
    avatar (best effort) and deep links to the model page and the owner page.
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
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def _hf_avatar(owner: str) -> str | None:
    """Hugging Face owner avatar.

    ``GET /api/users/{name}/avatar`` answers ``{"avatarUrl": …}`` for accounts
    with a custom avatar and 404 otherwise (orgs without one) - verified
    against the live API. The UI falls back to an initials badge.
    """
    if owner in _AVATAR_CACHE:
        return _AVATAR_CACHE[owner]
    try:
        r = requests.get(
            f"https://huggingface.co/api/users/{owner}/avatar", headers=_UA, timeout=8
        )
        if r.status_code != 200:
            return _cache_avatar(owner, None)
        url = (r.json() or {}).get("avatarUrl")
        return _cache_avatar(owner, url if isinstance(url, str) and url else None)
    except Exception:
        return _cache_avatar(owner, None)


def _search_huggingface(query: str, limit: int) -> list[dict]:
    from huggingface_hub import HfApi

    items: list[dict] = []
    # `expand=["author"]` is required: without it list_models leaves
    # `author` empty on search results (verified against huggingface_hub).
    for m in HfApi().list_models(
        search=query, sort="downloads", limit=limit, expand=["author"]
    ):
        mid = getattr(m, "id", None) or getattr(m, "modelId", None)
        if not mid or "/" not in mid:
            continue
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
    return items


def _ms_owner_info(api, owner: str, name: str) -> tuple[str | None, str]:
    """(avatar, owner page url) of a ModelScope owner, via the model payload.

    ``GET /api/v1/models/{owner}/{name}`` carries ``Data.Avatar`` and the
    ``Data.Organization`` block (empty for personal accounts) - verified
    against the live international endpoint. Personal profile slugs are not
    exposed by the public API, so personal owners link to the site's owner
    page format as well.
    """
    if owner in _AVATAR_CACHE:
        return _AVATAR_CACHE[owner], f"{MODELSCOPE_INTL_ENDPOINT}/organization/{owner}"
    avatar: str | None = None
    try:
        data = (api.openapi.get_model(owner, name) or {}).get("Data") or {}
        avatar = data.get("Avatar") or None
        org = data.get("Organization") or {}
        if not avatar:
            avatar = org.get("Avatar") or None
    except Exception:
        avatar = None
    avatar = _cache_avatar(owner, avatar if isinstance(avatar, str) and avatar else None)
    return avatar, f"{MODELSCOPE_INTL_ENDPOINT}/organization/{owner}"


def _search_modelscope(query: str, limit: int) -> list[dict]:
    from modelscope_hub import HubApi

    api = HubApi(endpoint=MODELSCOPE_INTL_ENDPOINT)
    page = api.list_repos("model", search=query, sort="downloads", page_size=limit)
    items: list[dict] = []
    for r in page.items:
        owner = getattr(r, "owner", None)
        name = getattr(r, "name", None)
        if not owner or not name:
            continue
        avatar, owner_url = _ms_owner_info(api, owner, name)
        items.append(
            {
                "platform": "modelscope",
                "key": f"{owner}/{name}",
                "owner": owner,
                "repo": name,
                "title": f"{owner}/{name}",
                "downloads": getattr(r, "downloads", 0) or 0,
                "likes": getattr(r, "likes", 0) or 0,
                "avatar": avatar,
                "pageUrl": f"{MODELSCOPE_INTL_ENDPOINT}/models/{owner}/{name}",
                "ownerUrl": owner_url,
            }
        )
    return items


def _search_civitai(query: str, limit: int) -> list[dict]:
    token = auth.get_civitai_token()
    headers = dict(_UA)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(
        "https://civitai.com/api/v1/models",
        params={"query": query, "limit": str(limit)},
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
    return items


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
            loop = asyncio.get_running_loop()

            def run(provider: str):
                try:
                    return provider, {"items": _PROVIDERS[provider](query, limit)}
                except Exception as e:  # provider outage must not kill the rest
                    utils.print_warning(f"search provider {provider} failed: {e}")
                    return provider, {"items": [], "error": str(e)}

            with ThreadPoolExecutor(max_workers=3) as pool:
                futs = [pool.submit(run, name) for name in _PROVIDERS]
                data = {}
                for fut in as_completed(futs, timeout=SEARCH_TIMEOUT + 5):
                    name, res = fut.result()
                    data[name] = res
            return web.json_response({"success": True, "data": data})

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
