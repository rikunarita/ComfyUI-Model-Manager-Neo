"""Shared aiohttp client for the extension's hub round-trips (Quick Win A3).

Plan §4.8-A3 / §3.8 / §6.2 Phase 6: `search.py`, `information.py` and
`identify.py` used to issue their hub API calls with **blocking `requests.get`
inside io-executor workers**. Every call therefore cost a thread hop and pinned
one of the eight IO-pool slots for the whole round trip (DNS + TLS + body),
timeouts were per-call-site literals, and a slow provider could exhaust the
pool the scan / preview / hygiene routes share. This module gives all of them
ONE lazily created `aiohttp.ClientSession` on the server's event loop.

Deliberately NOT Rust (Plan §3.8, user decision 2026-09-27): `reqwest` would
pull a C/asm TLS backend (aws-lc-sys / ring) into the "no compiler needed"
distribution, measured 4.9 MB for a minimal probe, and `huggingface_hub` 2.x is
httpx2-based anyway - so a Rust HTTP stack would be a *third* stack, not a
unification.

Behaviour parity with the `requests` call sites it replaces (Plan §6.2 Phase 6
A3 "挙動 parity"):

* **timeouts** stay the historical pairs. A `requests` timeout is
  ``(connect, read-between-bytes)``, NOT a total deadline, so it maps to
  ``aiohttp.ClientTimeout(connect=…, sock_read=…, total=None)`` - a slow-but-
  steady download is not aborted by either library.
* **HTTP status failures keep the exact `requests` wording**
  (``"403 Client Error: Forbidden for url: …"``) and the ``.response.
  status_code`` attribute the call sites inspect for the 401 guidance, via
  [HttpStatusError].
* **JSON is decoded regardless of `Content-Type`** (``requests``' ``.json()``
  does not check it; aiohttp's does - so ``content_type=None`` is passed).
  ModelScope's CDN is a live example of a hub answering JSON-ish bodies with an
  unexpected content type.
* **environment proxies are honoured** (``trust_env=True``): `requests` reads
  ``HTTPS_PROXY`` by default, aiohttp only opt-in.
* Transport-level exception *text* differs between the two libraries (there is
  no shared wording to preserve); the code paths, prefixes and user-visible
  meaning do not.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from . import config, utils

# `(connect seconds, read-between-bytes seconds)` - the pairs the replaced call
# sites passed to `requests.get(timeout=…)`.
SearchTimeout = tuple[float, float]

#: The search/lookup budget (`search.py SEARCH_TIMEOUT`, `identify.py
#: _LOOKUP_TIMEOUT`): a single float in `requests` = both connect and read.
SEARCH_TIMEOUT: SearchTimeout = (12.0, 12.0)
#: `information.py`'s hub lookups: `timeout=(10, 60)`.
HUB_TIMEOUT: SearchTimeout = (10.0, 60.0)
#: The avatar/owner probes: `timeout=8`.
AVATAR_TIMEOUT: SearchTimeout = (8.0, 8.0)
#: `utils.py`'s preview fetch: `timeout=(15, 120)` (kept for reference - the
#: preview pipeline still runs in the executor, Plan §3.8).
PREVIEW_TIMEOUT: SearchTimeout = (15.0, 120.0)

#: Connector bound: generous for a fan-out of three providers plus avatars,
#: bounded so a runaway retry loop cannot open unbounded sockets.
_CONNECTION_LIMIT = 24

_session: aiohttp.ClientSession | None = None
_session_loop: asyncio.AbstractEventLoop | None = None


class _ResponseShim:
    """The `response` attribute `requests` exceptions carry.

    The call sites read exactly one thing from it -
    ``getattr(getattr(e, "response", None), "status_code", None)`` for the
    Civitai 401 guidance - so that is all this provides.
    """

    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url
        self.headers: dict[str, str] = {}


class HttpStatusError(Exception):
    """`requests.exceptions.HTTPError`-shaped non-2xx failure.

    ``str(exc)`` reproduces `requests`' `raise_for_status` message verbatim so
    the user-visible error text of every route that surfaces it is unchanged.
    """

    def __init__(self, status_code: int, reason: str, url: str):
        kind = "Client" if 400 <= status_code < 500 else "Server"
        super().__init__(f"{status_code} {kind} Error: {reason} for url: {url}")
        self.response = _ResponseShim(status_code, url)
        self.status_code = status_code


class HttpJsonError(ValueError):
    """A body that is not valid JSON (`requests` raises `JSONDecodeError`,
    itself a `ValueError` - the call sites catch `Exception`)."""


def client_timeout(timeout: SearchTimeout | float) -> aiohttp.ClientTimeout:
    """Map a `requests`-style timeout onto aiohttp's.

    A bare float means "the same value for connect and read-between-bytes"
    (exactly what `requests` does); `total` stays `None` in both libraries'
    semantics for these call sites (no overall deadline).
    """
    if isinstance(timeout, tuple):
        connect, sock_read = timeout
    else:
        connect = sock_read = float(timeout)
    return aiohttp.ClientTimeout(total=None, connect=connect, sock_read=sock_read)


async def get_session() -> aiohttp.ClientSession:
    """The process-wide session, created on first use inside the running loop.

    A session belongs to the loop that created it: if the loop changed (tests,
    or a ComfyUI restart inside one process) the old one is closed best-effort
    and a fresh session is built.
    """
    global _session, _session_loop
    loop = asyncio.get_running_loop()
    if _session is not None and not _session.closed and _session_loop is loop:
        return _session
    if _session is not None and not _session.closed:
        await close_session()
    connector = aiohttp.TCPConnector(
        limit=_CONNECTION_LIMIT,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )
    # `trust_env`: honour HTTP(S)_PROXY / NO_PROXY exactly like `requests` does
    # by default. No default User-Agent header is set - every call site passes
    # its own (`_UA`), and a session-level default would silently change the
    # header order/value the hubs see.
    _session = aiohttp.ClientSession(connector=connector, trust_env=True)
    _session_loop = loop
    return _session


async def close_session() -> None:
    """Close the shared session (app shutdown / test teardown). Idempotent."""
    global _session, _session_loop
    session, _session, _session_loop = _session, None, None
    if session is None or session.closed:
        return
    try:
        await session.close()
    except Exception as e:  # a dead loop must not break shutdown
        utils.print_debug(f"http_client: session close failed: {e}")


def install_cleanup_hook() -> None:
    """Close the shared session when ComfyUI shuts down (best effort).

    Registered from the extension entry point next to the watcher hooks. An
    aiohttp session that outlives its loop logs "Unclosed client session" and
    leaks the connector's sockets, so the cleanup is worth the two lines - but
    it must never break startup on an unexpected server object.
    """
    try:
        app = getattr(config.serverInstance, "app", None)
        if app is None or not hasattr(app, "on_cleanup"):
            return

        async def _on_cleanup(_app):
            await close_session()

        app.on_cleanup.append(_on_cleanup)
    except Exception as e:
        utils.print_debug(f"http_client: cleanup hook not installed ({e})")


def raise_for_status(status: int, reason: str | None, url: str) -> None:
    """`requests`' `Response.raise_for_status()` for an aiohttp response."""
    if status < 400:
        return
    raise HttpStatusError(status, reason or "", str(url))


def decode_json(body: bytes) -> Any:
    """Decode a response body the way `requests`' `.json()` does (no
    content-type gate)."""
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except ValueError as e:
        raise HttpJsonError(f"response body is not valid JSON: {e}") from e


async def fetch_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: SearchTimeout | float = HUB_TIMEOUT,
) -> Any:
    """GET `url`, raise on a non-2xx status, return the decoded JSON body.

    The direct replacement of the ``r = requests.get(...); r.raise_for_status();
    payload = r.json()`` triple the hub call sites used.
    """
    session = await get_session()
    async with session.get(url, params=params, headers=headers, timeout=client_timeout(timeout)) as response:
        body = await response.read()
        raise_for_status(response.status, response.reason, str(response.url))
        return decode_json(body)


async def fetch_status_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: SearchTimeout | float = HUB_TIMEOUT,
) -> tuple[int, Any]:
    """GET `url` and return `(status, decoded-json-or-None)` WITHOUT raising on
    a non-2xx status - the shape of the call sites that branched on
    ``r.status_code != 200`` (avatar / owner / by-hash probes)."""
    session = await get_session()
    async with session.get(url, params=params, headers=headers, timeout=client_timeout(timeout)) as response:
        body = await response.read()
        if response.status != 200:
            return response.status, None
        return response.status, decode_json(body)


async def fetch_bytes_capped(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: SearchTimeout | float = AVATAR_TIMEOUT,
    max_bytes: int,
    chunk: int = 64 * 1024,
) -> bytes | None:
    """Stream GET `url`, refusing more than `max_bytes` (None on any failure).

    The replacement of `search.py _fetch_avatar_bytes`' `stream=True` +
    `iter_content` loop: the cap is enforced while reading, so a hostile or
    misbehaving CDN object cannot balloon the in-memory avatar cache.
    """
    try:
        session = await get_session()
        async with session.get(url, headers=headers, timeout=client_timeout(timeout)) as response:
            if response.status != 200:
                return None
            chunks: list[bytes] = []
            received = 0
            async for block in response.content.iter_chunked(chunk):
                if not block:
                    continue
                received += len(block)
                if received > max_bytes:
                    return None
                chunks.append(block)
            body = b"".join(chunks)
            return body or None
    except Exception:
        return None
