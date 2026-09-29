"""Phase 6 / Quick Win A3 - the requests -> aiohttp unification (Plan §4.8-A3).

Plan §6.2 Phase 6 states the acceptance condition for A3: behaviour parity
(timeouts / error wording / what the UI shows) plus mock tests that do not
depend on a live API. Every test here therefore runs against a LOCAL aiohttp server (no network, no
recorded fixtures to go stale) and pins the parts of the old `requests`
behaviour that reach the user:

* the HTTP-status error wording (`"403 Client Error: Forbidden for url: ..."`)
  and the `.response.status_code` attribute the Civitai 401 hint reads;
* the per-provider degradation of the search sweep (one failing provider must
  not fail the others, a hanging one becomes `"search timed out"`);
* the avatar users -> organizations fallback and its cache;
* the by-hash lookup order (first notation that hits wins, non-200 and
  non-JSON bodies are skipped, not raised);
* the capped avatar streaming (an oversized body is refused);
* the JSON bodies the two `information.py` searchers turn into download-task
  entries.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer
from harness import REPO_ROOT, FakeRequest, import_ext, json_body

# `py/search.py` imports `py/information.py`, whose MODULE-level imports are
# markdownify + PIL. Every CI cell that runs this suite installs them (ci.yml:
# `-r requirements.txt`; native.yml: the two pytest dependency steps); the guard
# keeps a minimal environment reporting a clear skip instead of a collection
# error that hides the real result.
pytest.importorskip("markdownify", reason="py/information.py needs markdownify (pip install -r requirements.txt)")
pytest.importorskip("PIL", reason="py/information.py needs pillow")


def _reset_native_loader():
    config = import_ext("config")
    config.extension_uri = str(REPO_ROOT)
    native = import_ext("native")
    native._module = None
    native._reason = None
    native._attempted = False
    return native


# ---------------------------------------------------------------------------
# local mock hub
# ---------------------------------------------------------------------------
class MockHub:
    """A tiny aiohttp server standing in for the hub APIs.

    `routes` maps ``"METHOD path"`` to a handler returning either a dict (sent
    as JSON with 200) or a `(status, payload)` / `(status, payload, headers)`
    tuple. Every request is recorded in `calls` so the tests can assert the
    order and the number of round trips.
    """

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.calls: list[tuple[str, str]] = []
        self.server: TestServer | None = None
        self.base = ""

    async def start(self) -> MockHub:
        app = web.Application()

        async def dispatch(request: web.Request) -> web.Response:
            key = f"{request.method} {request.path}"
            self.calls.append((request.method, request.path))
            handler = self.routes.get(key)
            if handler is None:
                return web.json_response({"error": f"unexpected {key}"}, status=404)
            result = handler(request) if callable(handler) else handler
            if isinstance(result, tuple):
                status, payload = result[0], result[1]
                headers = result[2] if len(result) > 2 else None
                if isinstance(payload, (bytes, bytearray)):
                    return web.Response(body=payload, status=status, headers=headers)
                return web.json_response(payload, status=status, headers=headers)
            return web.json_response(result)

        # One catch-all per method keeps the mock route table declarative.
        app.router.add_route("*", "/{tail:.*}", dispatch)
        self.server = TestServer(app)
        await self.server.start_server()
        self.base = str(self.server.make_url("")).rstrip("/")
        return self

    async def stop(self) -> None:
        if self.server is not None:
            await self.server.close()
            self.server = None


@pytest_asyncio.fixture
async def hub_factory():
    """Yields a factory of started mock hubs; all are closed after the test."""
    started: list[MockHub] = []

    async def make(routes: dict[str, object]) -> MockHub:
        hub = await MockHub(routes).start()
        started.append(hub)
        return hub

    yield make
    for hub in started:
        await hub.stop()


@pytest_asyncio.fixture(autouse=True)
async def _close_shared_session():
    """The shared aiohttp session belongs to the running loop; pytest-asyncio
    gives every test a fresh one, so close it here instead of letting the next
    test's `get_session()` close a session whose loop is already gone."""
    _reset_native_loader()
    yield
    http_client = import_ext("http_client")
    await http_client.close_session()


# ---------------------------------------------------------------------------
# http_client primitives
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_status_error_keeps_the_requests_wording(hub_factory):
    """`raise_for_status` parity: the message AND `.response.status_code`."""
    http_client = import_ext("http_client")
    hub = await hub_factory({"GET /api/thing": (403, {"detail": "no"})})

    with pytest.raises(http_client.HttpStatusError) as info:
        await http_client.fetch_json(f"{hub.base}/api/thing")
    message = str(info.value)
    assert message.startswith("403 Client Error:"), message
    assert " for url: " in message
    assert message.endswith("/api/thing"), message
    # the attribute the Civitai 401 hint reads
    assert info.value.response.status_code == 403

    # 5xx reads "Server Error", exactly like requests
    hub5 = await hub_factory({"GET /boom": (503, {})})
    with pytest.raises(http_client.HttpStatusError) as info5:
        await http_client.fetch_json(f"{hub5.base}/boom")
    assert str(info5.value).startswith("503 Server Error:"), str(info5.value)


@pytest.mark.asyncio
async def test_json_is_decoded_whatever_the_content_type(hub_factory):
    """`requests`' `.json()` ignores the content type; aiohttp's does not -
    the helper must keep the permissive behaviour (hub CDNs are sloppy)."""
    http_client = import_ext("http_client")
    hub = await hub_factory(
        {
            "GET /json-as-octet": (
                200,
                json.dumps({"ok": True}).encode(),
                {"Content-Type": "application/octet-stream"},
            ),
            "GET /not-json": (200, b"<html>nope</html>", {"Content-Type": "text/html"}),
        }
    )
    assert await http_client.fetch_json(f"{hub.base}/json-as-octet") == {"ok": True}
    with pytest.raises(http_client.HttpJsonError):
        await http_client.fetch_json(f"{hub.base}/not-json")


@pytest.mark.asyncio
async def test_fetch_status_json_never_raises_on_a_bad_status(hub_factory):
    http_client = import_ext("http_client")
    hub = await hub_factory({"GET /missing": (404, {"error": "gone"}), "GET /ok": {"a": 1}})
    status, payload = await http_client.fetch_status_json(f"{hub.base}/missing")
    assert (status, payload) == (404, None)
    status, payload = await http_client.fetch_status_json(f"{hub.base}/ok")
    assert (status, payload) == (200, {"a": 1})


@pytest.mark.asyncio
async def test_declared_charset_is_honoured_and_a_bogus_one_degrades(hub_factory):
    """`requests` decodes through `Response.text`, i.e. with the charset the
    response declares; an unusable codec name must degrade to UTF-8 instead of
    escaping as a LookupError (a 500 where requests answered a JSON error)."""
    http_client = import_ext("http_client")
    latin1_body = json.dumps({"café": "naïve"}, ensure_ascii=False).encode("iso-8859-1")
    hub = await hub_factory(
        {
            "GET /latin1": (
                200,
                latin1_body,
                {"Content-Type": "application/json; charset=iso-8859-1"},
            ),
            "GET /bogus": (200, b'{"ok": true}', {"Content-Type": "application/json; charset=not-a-codec"}),
            "GET /utf8": (
                200,
                json.dumps({"ok": "値"}, ensure_ascii=False).encode(),
                {"Content-Type": "application/json"},
            ),
        }
    )
    assert await http_client.fetch_json(f"{hub.base}/latin1") == {"café": "naïve"}
    assert await http_client.fetch_json(f"{hub.base}/bogus") == {"ok": True}
    assert await http_client.fetch_json(f"{hub.base}/utf8") == {"ok": "値"}
    # the unit-level contract (no server needed)
    assert http_client.decode_json('{"a": "値"}'.encode(), None) == {"a": "値"}
    assert http_client.decode_json(b'{"a": 1}', "not-a-codec") == {"a": 1}
    with pytest.raises(http_client.HttpJsonError):
        http_client.decode_json(b"<html>nope</html>")


@pytest.mark.asyncio
async def test_fetch_bytes_capped_refuses_an_oversized_body(hub_factory):
    """The avatar proxy's 5 MiB guard survives the aiohttp port."""
    http_client = import_ext("http_client")
    body = b"\x89PNG\r\n\x1a\n" + b"x" * 100
    hub = await hub_factory({"GET /avatar": (200, body, {"Content-Type": "image/png"})})
    assert await http_client.fetch_bytes_capped(f"{hub.base}/avatar", max_bytes=1024) == body
    assert await http_client.fetch_bytes_capped(f"{hub.base}/avatar", max_bytes=16) is None
    missing = await hub_factory({"GET /gone": (404, {})})
    assert await http_client.fetch_bytes_capped(f"{missing.base}/gone", max_bytes=1024) is None


@pytest.mark.asyncio
async def test_timeouts_map_onto_connect_and_read_not_a_total(hub_factory):
    """A `requests` timeout is (connect, read-between-bytes); the mapping must
    not turn it into an overall deadline (a slow-but-steady body would be
    aborted)."""
    http_client = import_ext("http_client")

    async def slow_then_done(_request: web.Request) -> web.Response:
        # Two chunks 120 ms apart with a 1 s read timeout and a 0.3 s total:
        # the historical behaviour completes, a `total=` mapping would not.
        response = web.StreamResponse(status=200, headers={"Content-Type": "application/json"})
        await response.prepare(_request)
        await response.write(b'{"a"')
        await asyncio.sleep(0.12)
        await response.write(b": 1}")
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_get("/slow", slow_then_done)
    server = TestServer(app)
    await server.start_server()
    try:
        base = str(server.make_url("")).rstrip("/")
        session = await http_client.get_session()
        async with session.get(f"{base}/slow", timeout=http_client.client_timeout((1.0, 1.0))) as response:
            payload = json.loads(await response.read())
        assert payload == {"a": 1}
        timeout = http_client.client_timeout((10.0, 60.0))
        assert timeout.connect == 10.0 and timeout.sock_read == 60.0 and timeout.total is None
        scalar = http_client.client_timeout(12.0)
        assert scalar.connect == 12.0 and scalar.sock_read == 12.0 and scalar.total is None
    finally:
        await server.close()


# ---------------------------------------------------------------------------
# search.py providers
# ---------------------------------------------------------------------------
CIVITAI_PAYLOAD = {
    "items": [
        {
            "id": 11,
            "name": "Small Model",
            "creator": {"username": "alice"},
            "stats": {"downloadCount": 5, "thumbsUpCount": 90, "commentCount": 1},
        },
        {
            "id": 22,
            "name": "Big Model",
            "creator": {"username": "bob"},
            "stats": {"downloadCount": 500, "thumbsUpCount": 10, "commentCount": 7},
        },
    ],
    "metadata": {"nextCursor": "cur-2"},
}


@pytest.mark.asyncio
async def test_civitai_search_shape_sort_and_cursor(hub_factory, monkeypatch):
    search = import_ext("search")
    hub = await hub_factory({"GET /api/v1/models": CIVITAI_PAYLOAD})
    monkeypatch.setattr(search, "CIVITAI_API_BASE", f"{hub.base}/api/v1")

    items, next_cursor = await search._search_civitai("sd", 8, None, "Most Downloaded")
    assert next_cursor == "cur-2"
    assert [item["title"] for item in items] == ["Big Model", "Small Model"], "downloads desc"
    assert items[0] == {
        "platform": "civitai",
        "key": "22",
        "owner": "bob",
        "repo": "Big Model",
        "title": "Big Model",
        "downloads": 500,
        "likes": 10,
        "avatar": None,
        "pageUrl": "https://civitai.com/models/22",
        "ownerUrl": "https://civitai.com/user/bob",
    }
    # the query/limit/sort parameters survived the port
    assert hub.calls == [("GET", "/api/v1/models")]

    # "Most Liked" uses the other key (the API ignores `sort` with a query)
    hub2 = await hub_factory({"GET /api/v1/models": CIVITAI_PAYLOAD})
    monkeypatch.setattr(search, "CIVITAI_API_BASE", f"{hub2.base}/api/v1")
    items2, _ = await search._search_civitai("sd", 8, None, "Most Liked")
    assert [item["title"] for item in items2] == ["Small Model", "Big Model"]


@pytest.mark.asyncio
async def test_civitai_search_reports_the_requests_worded_error(hub_factory, monkeypatch):
    """A non-2xx must reach the UI with the historical message text."""
    search = import_ext("search")
    hub = await hub_factory({"GET /api/v1/models": (403, {"error": "blocked"})})
    monkeypatch.setattr(search, "CIVITAI_API_BASE", f"{hub.base}/api/v1")
    with pytest.raises(search.http_client.HttpStatusError) as info:
        await search._search_civitai("sd", 8, None, "Highest Rated")
    assert str(info.value).startswith("403 Client Error:"), str(info.value)


@pytest.mark.asyncio
async def test_hf_avatar_falls_back_to_organizations_and_caches(hub_factory, monkeypatch):
    search = import_ext("search")
    search._AVATAR_CACHE.clear()
    hub = await hub_factory(
        {
            "GET /api/users/org-owner/avatar": (404, {"error": "This user does not exist"}),
            "GET /api/organizations/org-owner/avatar": {"avatarUrl": "https://cdn/x.png"},
            "GET /api/users/solo/avatar": {"avatarUrl": "https://cdn/solo.png"},
        }
    )
    monkeypatch.setattr(search, "HF_API_BASE", f"{hub.base}/api")
    assert await search._hf_avatar("solo") == "https://cdn/solo.png"
    assert await search._hf_avatar("org-owner") == "https://cdn/x.png"
    assert hub.calls == [
        ("GET", "/api/users/solo/avatar"),
        ("GET", "/api/users/org-owner/avatar"),
        ("GET", "/api/organizations/org-owner/avatar"),
    ]
    # the second ask is served from the cache (no new round trip)
    before = len(hub.calls)
    assert await search._hf_avatar("org-owner") == "https://cdn/x.png"
    assert len(hub.calls) == before
    # an owner without any avatar caches the negative answer
    empty = await hub_factory({})
    monkeypatch.setattr(search, "HF_API_BASE", f"{empty.base}/api")
    search._AVATAR_CACHE.clear()
    assert await search._hf_avatar("nobody") is None
    assert await search._hf_avatar("nobody") is None
    assert len(empty.calls) == 2, "users + organizations, then cached"


@pytest.mark.asyncio
async def test_modelscope_owner_info_is_parsed_and_cached(hub_factory, monkeypatch):
    search = import_ext("search")
    search._MS_OWNER_CACHE.clear()
    payload = {
        "Data": {
            "Name": "repo",
            "Organization": {
                "Name": "Qwen",
                "Description": '["root",{},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"hi"]]]]',
                "Avatar": "https://resources.modelscope.ai/a.png",
            },
        }
    }
    hub = await hub_factory({"GET /api/v1/models/Qwen/repo": payload})
    # search.py imports the endpoint constant into its own namespace
    monkeypatch.setattr(search, "MODELSCOPE_INTL_ENDPOINT", hub.base)

    avatar, display, description = await search._ms_owner_info("Qwen", "repo")
    assert display == "Qwen"
    assert description == "hi", "rich-text descriptions flatten to their leaves"
    # both leaf-marker shapes the API sends flatten (the attribute-dict form
    # used to yield nothing - see _ms_plain_description)
    plain = search._ms_plain_description
    assert plain('["root",{},["span","leaf","a b"]]') == "a b"
    assert plain('["root",{},["span",{"data-type":"leaf"},"c d"]]') == "c d"
    assert plain("just text") == "just text"
    assert plain("   ") is None
    assert plain('["root",{}]') is None
    assert avatar == "https://resources.modelscope.ai/a.png"
    assert await search._ms_owner_info("Qwen", "repo") == (avatar, display, description)
    assert len(hub.calls) == 1, "the owner cache absorbs the second ask"


@pytest.mark.asyncio
async def test_search_route_degrades_per_provider(hub_factory, monkeypatch, prompt_server):
    """The three-provider sweep: one success, one failure, one hang ->
    partial results with the historical per-column entries."""
    search = import_ext("search")
    monkeypatch.setattr(search, "SEARCH_TIMEOUT", (0.2, 0.2))
    monkeypatch.setattr(search, "SWEEP_MARGIN", 0.3)

    async def ok(query, limit, cursor, sort):
        return [{"platform": "hf", "title": "a/b"}], None

    async def boom(query, limit, cursor, sort):
        raise RuntimeError("provider down")

    async def hangs(query, limit, cursor, sort):
        await asyncio.sleep(30)
        return [], None

    monkeypatch.setattr(search, "_PROVIDERS", {"hf": ok, "civitai": boom, "modelscope": hangs})
    search.SearchRoutes().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[("GET", "/model-manager/search")]

    request = FakeRequest()
    request.query = {"query": "sd", "limit": "5"}
    body = json_body(await handler(request))
    assert body["success"] is True
    data = body["data"]
    assert set(data) == {"hf", "civitai", "modelscope"}
    assert data["hf"]["items"] == [{"platform": "hf", "title": "a/b"}]
    assert data["civitai"]["items"] == [] and data["civitai"]["error"] == "provider down"
    assert data["modelscope"]["error"] == "search timed out", "a hung provider degrades"


@pytest.mark.asyncio
async def test_search_sweep_cancels_providers_when_the_client_goes_away(prompt_server, monkeypatch):
    """A client that navigates away mid-search must not leave the provider
    coroutines running with nobody to read their result (the old executor
    version got this from `pool.shutdown(cancel_futures=True)`)."""
    search = import_ext("search")
    monkeypatch.setattr(search, "SEARCH_TIMEOUT", (5.0, 5.0))
    monkeypatch.setattr(search, "SWEEP_MARGIN", 5.0)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def hangs(query, limit, cursor, sort):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return [], None

    monkeypatch.setattr(search, "_PROVIDERS", {"civitai": hangs})
    search.SearchRoutes().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[("GET", "/model-manager/search")]

    request = FakeRequest()
    request.query = {"query": "sd"}
    task = asyncio.create_task(handler(request))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # Wait on the CONDITION (the provider's CancelledError handler setting the
    # event), not a fixed number of loop yields: `task.cancel()` only schedules
    # the inner cancellation, so a bare `sleep(0)` loop could assert before it
    # is delivered. A bounded wait is both robust and fails loudly on a real
    # orphan (the handler leaving the provider running with nobody to read it).
    await asyncio.wait_for(cancelled.wait(), timeout=5)
    assert cancelled.is_set(), "the in-flight provider coroutine was orphaned"


@pytest.mark.asyncio
async def test_search_route_single_platform_and_empty_query(prompt_server, monkeypatch):
    search = import_ext("search")
    seen: list[tuple] = []

    async def ok(query, limit, cursor, sort):
        seen.append((query, limit, cursor, sort))
        return [{"title": "x"}], "next"

    monkeypatch.setattr(search, "_PROVIDERS", {"civitai": ok})
    search.SearchRoutes().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[("GET", "/model-manager/search")]

    request = FakeRequest()
    request.query = {"query": "  pony  ", "limit": "3", "platform": "civitai", "cursor": "c1", "sort_civitai": "Newest"}
    body = json_body(await handler(request))
    assert body == {"success": True, "data": {"civitai": {"items": [{"title": "x"}], "nextCursor": "next"}}}
    assert seen == [("pony", 3, "c1", "Newest")]

    empty = FakeRequest()
    empty.query = {"query": "   "}
    assert json_body(await handler(empty)) == {"success": True, "data": {}}


@pytest.mark.asyncio
async def test_civitai_whoami_401_keeps_the_scope_hint(hub_factory, monkeypatch, prompt_server):
    """The UI's "the key was rejected (401)" guidance depends on
    `e.response.status_code` - which the aiohttp shim must still provide."""
    search = import_ext("search")
    auth = import_ext("auth")
    hub = await hub_factory({"GET /api/v1/me": (401, {"error": "unauthorized"})})
    monkeypatch.setattr(search, "CIVITAI_API_BASE", f"{hub.base}/api/v1")
    monkeypatch.setattr(auth, "get_civitai_token", lambda: "tok")
    search.SearchRoutes().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[("GET", "/model-manager/civitai/whoami")]

    body = json_body(await handler(FakeRequest()))
    assert body["success"] is False
    assert "401 Client Error" in body["error"], body["error"]
    assert "The key was rejected (401)" in body["error"], body["error"]

    ok_hub = await hub_factory({"GET /api/v1/me": {"username": "me", "id": 7}})
    monkeypatch.setattr(search, "CIVITAI_API_BASE", f"{ok_hub.base}/api/v1")
    body = json_body(await handler(FakeRequest()))
    assert body == {"success": True, "data": {"name": "me", "id": 7}}


@pytest.mark.asyncio
async def test_civitai_image_meta_matches_by_id_and_url(hub_factory, monkeypatch, prompt_server):
    search = import_ext("search")
    payload = {
        "items": [
            {"id": 1, "url": "https://image.civitai.com/a.png?width=100", "meta": {"prompt": "cat"}},
            {"id": 2, "url": "https://image.civitai.com/b.jpg", "meta": None},
        ]
    }
    hub = await hub_factory({"GET /api/v1/images": payload})
    monkeypatch.setattr(search, "CIVITAI_API_BASE", f"{hub.base}/api/v1")
    search.SearchRoutes().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[("GET", "/model-manager/civitai/image-meta")]

    request = FakeRequest()
    request.query = {"model-version-id": "9", "url": "https://image.civitai.com/a.png?x=1"}
    assert json_body(await handler(request)) == {"success": True, "data": {"prompt": "cat"}}

    request2 = FakeRequest()
    request2.query = {"model-version-id": "9", "url": "https://image.civitai.com/b.jpg"}
    assert json_body(await handler(request2)) == {"success": True, "data": None}

    # a hub outage degrades to "no data", never to a failed request
    dead = await hub_factory({"GET /api/v1/images": (500, {})})
    monkeypatch.setattr(search, "CIVITAI_API_BASE", f"{dead.base}/api/v1")
    assert json_body(await handler(request)) == {"success": True, "data": None}


# ---------------------------------------------------------------------------
# identify.py by-hash lookup
# ---------------------------------------------------------------------------
MATCH_PAYLOAD = {
    "id": 555,
    "modelId": 44,
    "name": "v1",
    "baseModel": "SD 1.5",
    "model": {"id": 44, "name": "Model", "type": "Checkpoint"},
    "files": [{"name": "m.safetensors", "sizeKB": 10, "downloadUrl": "https://x/y", "hashes": {"SHA256": "AA"}}],
    "images": [{"url": "https://x/i.png"}],
}


@pytest.mark.asyncio
async def test_lookup_by_hashes_first_hit_wins_and_skips_misses(hub_factory, monkeypatch):
    identify = import_ext("identify")
    hub = await hub_factory(
        {
            "GET /api/v1/model-versions/by-hash/SHA-MISS": (404, {}),
            "GET /api/v1/model-versions/by-hash/BAD-JSON": (200, b"<html>", {"Content-Type": "text/html"}),
            "GET /api/v1/model-versions/by-hash/NO-ID": (200, {"modelId": 1}),
            "GET /api/v1/model-versions/by-hash/HIT": MATCH_PAYLOAD,
        }
    )
    monkeypatch.setattr(identify, "CIVITAI_API_BASE", f"{hub.base}/api/v1")

    # _LOOKUP_ORDER is ("SHA256", "AutoV2", "BLAKE3", "CRC32", "AutoV1")
    match = await identify.lookup_by_hashes(
        {"SHA256": "SHA-MISS", "AutoV2": "BAD-JSON", "BLAKE3": "NO-ID", "CRC32": "HIT", "AutoV1": "never"}
    )
    assert match is not None
    assert match["hash"] == "HIT" and match["hashType"] == "CRC32"
    assert match["versionId"] == 555 and match["modelId"] == 44
    assert match["modelPage"] == "https://civitai.com/models/44?modelVersionId=555"
    assert match["images"] == ["https://x/i.png"]
    assert [path for _, path in hub.calls] == [
        "/api/v1/model-versions/by-hash/SHA-MISS",
        "/api/v1/model-versions/by-hash/BAD-JSON",
        "/api/v1/model-versions/by-hash/NO-ID",
        "/api/v1/model-versions/by-hash/HIT",
    ], "sequential, in _LOOKUP_ORDER, stopping at the first hit"

    # an empty hash set never touches the network
    hub2 = await hub_factory({})
    monkeypatch.setattr(identify, "CIVITAI_API_BASE", f"{hub2.base}/api/v1")
    assert await identify.lookup_by_hashes({"SHA256": "  "}) is None
    assert hub2.calls == []


@pytest.mark.asyncio
async def test_identify_route_hashes_only_when_the_sidecar_missed(hub_factory, monkeypatch, prompt_server, tmp_path):
    """The route's flow (recorded hashes first, then the CPU hash pass) is
    unchanged - only the transport moved."""
    identify = import_ext("identify")
    utils = import_ext("utils")
    hub = await hub_factory({"GET /api/v1/model-versions/by-hash/RECORDED": MATCH_PAYLOAD})
    monkeypatch.setattr(identify, "CIVITAI_API_BASE", f"{hub.base}/api/v1")

    model = tmp_path / "m.safetensors"
    model.write_bytes(b"x" * 16)
    monkeypatch.setattr(utils, "get_full_path", lambda *_args, **_kw: str(model))
    monkeypatch.setattr(identify, "recorded_hashes", lambda _path: {"SHA256": "RECORDED"})
    hashed: list[str] = []
    monkeypatch.setattr(identify, "compute_hashes", lambda path: hashed.append(path) or {"SHA256": "COMPUTED"})

    identify.IdentifyRoutes().add_routes(prompt_server.routes)
    handler = prompt_server.routes.handlers[("GET", "/model-manager/identify-by-hash")]
    request = FakeRequest()
    request.query = {"type": "checkpoints", "index": "0", "filename": "m.safetensors"}
    body = json_body(await handler(request))
    assert body["success"] is True
    assert body["data"]["hashedFile"] is False, "a recorded hash avoids the CPU pass"
    assert hashed == []
    assert body["data"]["matched"]["hashType"] == "SHA256"

    # no recorded hash -> the file is hashed, then looked up again
    hub2 = await hub_factory({"GET /api/v1/model-versions/by-hash/COMPUTED": MATCH_PAYLOAD})
    monkeypatch.setattr(identify, "CIVITAI_API_BASE", f"{hub2.base}/api/v1")
    monkeypatch.setattr(identify, "recorded_hashes", lambda _path: {})
    body = json_body(await handler(request))
    assert body["data"]["hashedFile"] is True
    assert hashed == [str(model)]
    assert body["data"]["hashes"] == {"SHA256": "COMPUTED"}
    assert body["data"]["matched"]["hash"] == "COMPUTED"


# ---------------------------------------------------------------------------
# information.py searchers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_civitai_searcher_builds_download_entries(hub_factory, monkeypatch):
    information = import_ext("information")
    payload = {
        "name": "Model",
        "type": "Checkpoint",
        "description": "<p>about</p>",
        "creator": {"username": "alice"},
        "modelVersions": [
            {
                "id": 7,
                "name": "v1",
                "baseModel": "SD 1.5",
                "trainedWords": ["tok"],
                "description": "<p>ver</p>",
                "images": [{"url": "https://x/i.png"}],
                "files": [
                    {
                        "name": "m.safetensors",
                        "sizeKB": 2,
                        "type": "Model",
                        "hashes": {"SHA256": "AA"},
                        "downloadUrl": "https://x/m",
                    }
                ],
            }
        ],
    }
    hub = await hub_factory({"GET /api/v1/models/44": payload})
    # the arrival host decides which API is called (mirror support), so the
    # test redirects that one function at the mock server.
    monkeypatch.setattr(information, "civitai_api_base", lambda host: f"{hub.base}/api/v1")
    searcher = information.CivitaiModelSearcher()
    monkeypatch.setattr(searcher, "_resolve_model_type", lambda kind: "checkpoints")

    models = await searcher.search_by_url("https://civitai.com/models/44?modelVersionId=7")
    assert len(models) == 1
    entry = models[0]
    assert entry["basename"] == "m" and entry["extension"] == ".safetensors"
    assert entry["sizeBytes"] == 2 * 1024
    assert entry["downloadUrl"] == "https://x/m"
    assert entry["hashes"] == {"SHA256": "AA"}
    assert entry["preview"] == ["https://x/i.png"]
    assert entry["description"].startswith("---\n")
    assert "modelPage:" in entry["description"]
    # the mirror rule is untouched: the stored page points at the arrival host
    assert "https://civitai.com/models/44?modelVersionId=7" in entry["description"]


@pytest.mark.asyncio
async def test_hf_searcher_uses_the_recursive_tree_for_sizes(hub_factory, monkeypatch):
    information = import_ext("information")
    model_payload = {
        "author": "owner",
        "siblings": [
            {"rfilename": "root.safetensors"},
            {"rfilename": "sub/nested.safetensors"},
            {"rfilename": "preview.png"},
            {"rfilename": "notes.txt"},
        ],
    }
    tree_payload = [
        {"type": "file", "path": "root.safetensors", "size": 111},
        {
            "type": "directory",
            "path": "sub",
            "children": [{"type": "file", "path": "sub/nested.safetensors", "size": 222}],
        },
    ]
    hub = await hub_factory(
        {
            "GET /api/models/owner/repo": model_payload,
            "GET /api/models/owner/repo/tree/main": tree_payload,
        }
    )
    monkeypatch.setattr(information, "HF_API_BASE", f"{hub.base}/api")
    searcher = information.HuggingfaceModelSearcher()
    models = await searcher.search_by_url("https://huggingface.co/owner/repo")
    sizes = {model["basename"]: model["sizeBytes"] for model in models}
    assert sizes == {"root": 111, "nested": 222}, "recursive tree sizes, .txt/.png excluded"
    assert all(model["downloadPlatform"] == "huggingface" for model in models)
    assert [path for _, path in hub.calls] == [
        "/api/models/owner/repo",
        "/api/models/owner/repo/tree/main",
    ]
    # a tree outage must not fail the lookup (sizes degrade to 0)
    dead = await hub_factory(
        {
            "GET /api/models/owner/repo": model_payload,
            "GET /api/models/owner/repo/tree/main": (500, {}),
        }
    )
    monkeypatch.setattr(information, "HF_API_BASE", f"{dead.base}/api")
    degraded = await searcher.search_by_url("https://huggingface.co/owner/repo")
    assert {model["basename"]: model["sizeBytes"] for model in degraded} == {"root": 0, "nested": 0}


# ---------------------------------------------------------------------------
# Phase 7 / T8 - the preview pipeline's requests -> aiohttp completion (A3).
#
# Plan §6.2 Phase 7 T8 moves the LAST two blocking `requests.get` calls
# (utils.save_model_preview's download-completion fetch and the editor-save
# fetch) onto the shared aiohttp session, so a stalled CDN no longer pins one
# of the eight io-executor workers for the 120 s read timeout. These tests pin
# the behaviour-parity contract the Plan lists: 200 / non-200 (requests wording)
# / timeout / missing content-type / the local-preview branch / blob rejection,
# plus the "no direct requests in py/" invariant.
# ---------------------------------------------------------------------------
def _webp_bytes(rgb=(200, 30, 30), size=(8, 8)) -> bytes:
    """A real (tiny) WebP so `_write_preview_content`'s PIL re-encode succeeds."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, rgb).save(buf, "WEBP")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_fetch_preview_returns_body_and_content_type(hub_factory):
    """200 with a content-type: (body, content-type) come back verbatim."""
    http_client = import_ext("http_client")
    body = _webp_bytes()
    hub = await hub_factory({"GET /p.webp": (200, body, {"Content-Type": "image/webp"})})
    got_body, got_ct = await http_client.fetch_preview(f"{hub.base}/p.webp")
    assert got_body == body
    assert got_ct == "image/webp"
    assert hub.calls == [("GET", "/p.webp")]


@pytest.mark.asyncio
async def test_fetch_preview_non_2xx_keeps_the_requests_wording(hub_factory):
    """A non-2xx raises HttpStatusError with `requests`' raise_for_status text
    and the `.response.status_code` the call sites historically inspected."""
    http_client = import_ext("http_client")
    hub = await hub_factory({"GET /forbidden": (403, {"error": "nope"})})
    with pytest.raises(http_client.HttpStatusError) as excinfo:
        await http_client.fetch_preview(f"{hub.base}/forbidden")
    message = str(excinfo.value)
    assert message.startswith("403 Client Error:")
    assert "for url:" in message
    assert excinfo.value.response.status_code == 403


@pytest.mark.asyncio
async def test_fetch_preview_passes_through_a_generic_content_type(hub_factory):
    """A generic content-type (application/octet-stream - what an unlabelled CDN
    object arrives as, and aiohttp's default for a raw body) is passed through
    unchanged; `_write_preview_content`'s magic-byte sniff handles it, exactly
    as the pre-T8 `response.headers.get("content-type", "")` path did."""
    http_client = import_ext("http_client")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    hub = await hub_factory({"GET /raw": (200, png)})
    body, content_type = await http_client.fetch_preview(f"{hub.base}/raw")
    assert body == png
    assert content_type == "application/octet-stream"


@pytest.mark.asyncio
async def test_save_model_preview_falls_back_to_url_content_type_when_missing(model_lib, monkeypatch):
    """When the fetch reports NO content-type (a real CDN can omit it; aiohttp's
    test server cannot), save_model_preview falls back to
    `resolve_file_content_type(url)` exactly as the pre-T8 requests path did."""
    import os

    utils = import_ext("utils")
    http_client = import_ext("http_client")
    checkpoints = str(model_lib / "checkpoints")
    model_path = os.path.join(checkpoints, "m.safetensors")
    with open(model_path, "wb") as f:
        f.write(b"x")
    webp = _webp_bytes()

    async def fake_fetch(url, *, headers=None, timeout=None):
        return webp, ""  # server sent no content-type

    monkeypatch.setattr(http_client, "fetch_preview", fake_fetch)
    await utils.save_model_preview(model_path, "https://cdn.example.com/img/p.webp")
    # the URL-sniff fallback (or the WebP magic bytes) still re-encode to .webp
    assert os.path.isfile(os.path.join(checkpoints, "m.webp"))


@pytest.mark.asyncio
async def test_fetch_preview_honours_the_read_timeout(hub_factory):
    """The (connect, read-between-bytes) mapping means a stalled body trips the
    sock_read budget - the network wait is on the loop, but it is still bounded
    (a hung CDN cannot wedge the fetch forever)."""
    http_client = import_ext("http_client")

    async def hang(_request: web.Request) -> web.Response:
        response = web.StreamResponse(status=200, headers={"Content-Type": "image/webp"})
        await response.prepare(_request)
        await response.write(b"partial")
        await asyncio.sleep(5)  # far beyond the 0.2 s sock_read below
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_get("/hang", hang)
    server = TestServer(app)
    await server.start_server()
    try:
        base = str(server.make_url("")).rstrip("/")
        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await http_client.fetch_preview(f"{base}/hang", timeout=(5.0, 0.2))
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_save_model_preview_writes_webp_and_skips_blob(hub_factory, model_lib):
    """Download-completion path: an HTTP image is re-encoded to `<base>.webp`;
    a browser-local `blob:` URL is skipped with no fetch and no file."""
    import os

    utils = import_ext("utils")
    model_path = os.path.join(str(model_lib / "checkpoints"), "m.safetensors")
    with open(model_path, "wb") as f:
        f.write(b"x")
    hub = await hub_factory({"GET /p.webp": (200, _webp_bytes(), {"Content-Type": "image/webp"})})

    await utils.save_model_preview(model_path, f"{hub.base}/p.webp")
    assert os.path.isfile(os.path.join(str(model_lib / "checkpoints"), "m.webp"))

    # blob: is refused server-side (never fetched) and writes nothing new.
    await utils.save_model_preview(model_path, "blob:http://localhost/xyz")
    assert hub.calls == [("GET", "/p.webp")], "the blob URL must not round-trip"


@pytest.mark.asyncio
async def test_save_model_preview_local_branch_reads_the_stored_file(model_lib):
    """Our own `/model-manager/preview/...` URL is read from disk server-side
    (no HTTP round trip), matching the pre-T8 behaviour."""
    import os

    utils = import_ext("utils")
    checkpoints = str(model_lib / "checkpoints")
    model_path = os.path.join(checkpoints, "m.safetensors")
    with open(model_path, "wb") as f:
        f.write(b"x")
    with open(os.path.join(checkpoints, "src.webp"), "wb") as f:
        f.write(_webp_bytes((0, 200, 0)))

    await utils.save_model_preview(model_path, "/model-manager/preview/checkpoints/0/src.webp")
    assert os.path.isfile(os.path.join(checkpoints, "m.webp"))


@pytest.mark.asyncio
async def test_save_model_previews_is_tolerant_of_a_bad_entry(hub_factory, model_lib):
    """The download-completion path stays tolerant: a 500 on one gallery entry
    is warned+skipped, the good one is written, and the call does NOT raise."""
    import os

    utils = import_ext("utils")
    model_path = os.path.join(str(model_lib / "checkpoints"), "m.safetensors")
    with open(model_path, "wb") as f:
        f.write(b"x")
    hub = await hub_factory(
        {
            "GET /ok.webp": (200, _webp_bytes(), {"Content-Type": "image/webp"}),
            "GET /bad.webp": (500, {}),
        }
    )
    written = await utils.save_model_previews(model_path, [f"{hub.base}/ok.webp", f"{hub.base}/bad.webp"])
    assert written == 1
    assert os.path.isfile(os.path.join(str(model_lib / "checkpoints"), "m.webp"))


@pytest.mark.asyncio
async def test_resolve_preview_sources_parity(hub_factory):
    """Editor path (resolve half): a good URL stages its bytes+content-type, and
    each failure class keeps its historical wording (404 -> requests text,
    blob -> 'browser-local', non-URL -> 'invalid preview url')."""
    utils = import_ext("utils")
    webp = _webp_bytes((10, 20, 30))
    hub = await hub_factory(
        {
            "GET /ok.webp": (200, webp, {"Content-Type": "image/webp"}),
            "GET /gone.webp": (404, {}),
        }
    )
    staged, failures = await utils.resolve_preview_sources(
        [f"{hub.base}/ok.webp", f"{hub.base}/gone.webp", "blob:xyz", "not-a-url"]
    )
    assert len(staged) == 1
    name, content_type, content = staged[0]
    assert name.endswith("/ok.webp")
    assert content_type == "image/webp"
    assert content == webp
    joined = "; ".join(failures)
    assert len(failures) == 3
    assert "404 Client Error" in joined
    assert "browser-local preview url" in joined
    assert "invalid preview url" in joined


@pytest.mark.asyncio
async def test_write_resolved_previews_rewrites_the_gallery(model_lib):
    """Editor path (write half): staged bytes are re-encoded into the suffix
    slots and the old set is replaced."""
    import os

    utils = import_ext("utils")
    checkpoints = str(model_lib / "checkpoints")
    model_path = os.path.join(checkpoints, "m.safetensors")
    with open(model_path, "wb") as f:
        f.write(b"x")
    staged = [
        ("a.webp", "image/webp", _webp_bytes((255, 0, 0))),
        ("b.webp", "image/webp", _webp_bytes((0, 255, 0))),
    ]
    written = utils.write_resolved_previews(model_path, staged)
    assert written == 2
    assert os.path.isfile(os.path.join(checkpoints, "m.webp"))
    assert os.path.isfile(os.path.join(checkpoints, "m.preview.webp"))


@pytest.mark.asyncio
async def test_update_model_junction_resolve_write_then_remove(hub_factory, model_lib):
    """Junction test (MEMO §4.5 'junction' gap): the editor route resolves the
    gallery on the loop (``_resolve_update_previews``) and hands the result to
    ``update_model``, which writes/removes in the executor. Both halves are
    pinned above; this pins the CONNECTION so a signature/plumbing regression
    between them (the classic untested-junction defect) fails here."""
    import os

    manager = import_ext("manager")
    mm = manager.ModelManager()
    checkpoints = str(model_lib / "checkpoints")
    model_path = os.path.join(checkpoints, "m.safetensors")
    with open(model_path, "wb") as f:
        f.write(b"x")
    hub = await hub_factory({"GET /p.webp": (200, _webp_bytes(), {"Content-Type": "image/webp"})})

    # ("write", staged): an http gallery entry is fetched on the loop, then written.
    model_data = {"previewFile": f"{hub.base}/p.webp"}
    resolved = await mm._resolve_update_previews(model_data)
    assert resolved is not None and resolved[0] == "write"
    mm.update_model(model_path, model_data, resolved)
    webp_path = os.path.join(checkpoints, "m.webp")
    assert os.path.isfile(webp_path)

    # ("remove",): the "undefined" sentinel deletes the stored preview.
    resolved = await mm._resolve_update_previews({"previewFile": "undefined"})
    assert resolved == ("remove",)
    mm.update_model(model_path, {}, resolved)
    assert not os.path.isfile(webp_path)

    # None: no preview keys -> no preview work (and no crash).
    resolved = await mm._resolve_update_previews({"description": "x"})
    assert resolved is None
    mm.update_model(model_path, {}, resolved)


def test_py_backend_has_no_direct_requests_usage():
    """T8 gate: `py/` must not import or call `requests` directly any more (it
    stays only as a transitive dep of modelscope_hub). AST-based so docstrings /
    comments that mention `requests.get` (http_client.py explains the parity)
    are NOT false positives."""
    import ast

    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "py").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "requests" or alias.name.startswith("requests."):
                        offenders.append(f"{path.name}: import requests")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "requests" or (node.module or "").startswith("requests."):
                    offenders.append(f"{path.name}: from requests")
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "requests":
                offenders.append(f"{path.name}: requests.{node.attr}")
    assert not offenders, f"direct requests usage remains in py/: {offenders}"
