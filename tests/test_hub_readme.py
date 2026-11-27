"""Hub README fetching / sanitizing / notes merging.

The Hugging Face and ModelScope searchers used to write
"No description about this model" into the notes, so the model card's
Description tab rendered nothing for hub models (Civitai was unaffected).
These tests pin the fix without touching the live hubs:

* the front-matter split / merge policy (scalars and short scalar lists
  only, ours win, depth 1, bounded key count);
* the HTML sanitizer's security contract (no <script>, no on* handlers, no
  javascript: URLs, relative URLs resolved against the repo's raw base);
* the markdown-relative URL absolutizer;
* both searchers against a LOCAL aiohttp mock hub (HF API + raw resolve) and
  a monkeypatched ModelScope SDK file list (no network).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestServer
from harness import import_ext

pytest.importorskip("markdownify", reason="py/information.py needs markdownify (pip install -r requirements.txt)")

from aiohttp import web


# ---------------------------------------------------------------------------
# local mock hub (same shape as test_phase6_http.py's, kept self-contained)
# ---------------------------------------------------------------------------
class MockHub:
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
    yield
    http_client = import_ext("http_client")
    await http_client.close_session()


# ---------------------------------------------------------------------------
# split_front_matter
# ---------------------------------------------------------------------------
def test_split_front_matter_roundtrip():
    readme = import_ext("readme")
    card, body = readme.split_front_matter("---\nlicense: apache-2.0\ntags:\n- a\n- b\n---\n# Title\n\nbody\n")
    assert card == {"license": "apache-2.0", "tags": ["a", "b"]}
    assert body == "# Title\n\nbody\n"


def test_split_front_matter_degrades_without_losing_the_body():
    readme = import_ext("readme")
    # no block at all
    assert readme.split_front_matter("# No front matter") == ({}, "# No front matter")
    # unparseable YAML: body survives, card is empty
    card, body = readme.split_front_matter("---\n: : : not yaml [\n---\nbody text\n")
    assert card == {}
    assert "body text" in body
    # non-mapping YAML: body survives, card is empty
    card, body = readme.split_front_matter("---\n- just\n- a\n- list\n---\nbody text\n")
    assert card == {}
    assert "body text" in body


# ---------------------------------------------------------------------------
# merge_card_metadata
# ---------------------------------------------------------------------------
def test_merge_card_metadata_ours_win_and_values_are_capped():
    readme = import_ext("readme")
    ours = {"website": "Hugging Face", "author": "someone"}
    card = {
        "license": "mit",
        "author": "card-author",  # ours wins
        "widget": list(range(100)),  # shortened to the cap
        "config": {"nested": "dropped"},
        "long": "x" * 1000,  # truncated
    }
    merged = readme.merge_card_metadata(ours, card)
    assert merged["website"] == "Hugging Face"
    assert merged["author"] == "someone"
    assert merged["license"] == "mit"
    assert merged["widget"] == list(range(8))
    assert "config" not in merged
    assert merged["long"] == "x" * 500


def test_merge_card_metadata_limits_key_count_and_key_shape():
    readme = import_ext("readme")
    card = {f"key{i}": i for i in range(50)}
    merged = readme.merge_card_metadata({}, card)
    assert len(merged) == 20
    # keys that would break YAML/renderer expectations are skipped
    merged = readme.merge_card_metadata({}, {"bad key!": "x", "../evil": "y", "ok_key": "z"})
    assert merged == {"ok_key": "z"}


# ---------------------------------------------------------------------------
# sanitize_readme_html
# ---------------------------------------------------------------------------
def test_sanitizer_drops_script_and_event_handlers():
    readme = import_ext("readme")
    out = readme.sanitize_readme_html(
        '<p onclick="steal()">safe</p><script>alert(1)</script><style>body{display:none}</style>',
        None,
    )
    assert "safe" in out
    assert "onclick" not in out
    assert "alert" not in out
    assert "display:none" not in out


def test_sanitizer_img_src_relative_becomes_absolute_and_onerror_dropped():
    readme = import_ext("readme")
    out = readme.sanitize_readme_html(
        '<img src="assets/pic.png" onerror="steal()" alt="pic">',
        "https://hub/o/r/resolve/main/",
    )
    assert 'src="https://hub/o/r/resolve/main/assets/pic.png"' in out
    assert "onerror" not in out
    assert 'alt="pic"' in out


def test_sanitizer_url_schemes():
    readme = import_ext("readme")
    out = readme.sanitize_readme_html(
        '<a href="javascript:alert(1)">js</a>'
        '<a href="https://ok.example/x">https</a>'
        '<a href="data:text/html,<script>alert(1)</script>">data</a>'
        '<a href="#frag">frag</a>'
        '<a href="mailto:a@b.c">mail</a>',
        None,
    )
    assert "javascript:" not in out
    assert 'href="https://ok.example/x"' in out
    assert "data:text/html" not in out
    assert 'href="#frag"' in out
    assert 'href="mailto:a@b.c"' in out
    # every anchor gets a safe target
    assert out.count('target="_blank"') >= 3


def test_sanitizer_unwraps_unknown_tags_and_keeps_text():
    readme = import_ext("readme")
    out = readme.sanitize_readme_html("<marquee><b>bold</b> keeps text</marquee>", None)
    assert "bold" in out
    assert "keeps text" in out
    assert "marquee" not in out


def test_sanitizer_iframes_and_svg_are_dropped_with_contents():
    readme = import_ext("readme")
    dirty = '<div>before<iframe src="https://evil">inner</iframe><svg><script>s()</script></svg>after</div>'
    out = readme.sanitize_readme_html(dirty, None)
    assert "before" in out
    assert "after" in out
    assert "iframe" not in out
    assert "evil" not in out
    assert "s()" not in out


# ---------------------------------------------------------------------------
# absolutize_markdown_urls
# ---------------------------------------------------------------------------
def test_absolutize_markdown_urls():
    readme = import_ext("readme")
    base = "https://hub/o/r/resolve/main/"
    out = readme.absolutize_markdown_urls(
        "![img](assets/a.png) [file](<./b c.txt>) [abs](https://other/x) [frag](#sec) [scheme](mailto:a@b.c)",
        base,
    )
    assert "![img](https://hub/o/r/resolve/main/assets/a.png)" in out
    assert "[file](<https://hub/o/r/resolve/main/b c.txt>)" in out
    assert "[abs](https://other/x)" in out
    assert "[frag](#sec)" in out
    assert "[scheme](mailto:a@b.c)" in out


# ---------------------------------------------------------------------------
# process_readme
# ---------------------------------------------------------------------------
def test_process_readme_end_to_end():
    readme = import_ext("readme")
    card, body = readme.process_readme(
        "---\nlicense: mit\n---\n# Card Title\n\n![diagram](./diagram.png)\n\n<script>alert(1)</script>safe text\n",
        "https://hub/o/r/resolve/main/",
    )
    assert card == {"license": "mit"}
    assert "# Card Title" in body
    assert "https://hub/o/r/resolve/main/diagram.png" in body
    assert "safe text" in body
    assert "alert" not in body


# ---------------------------------------------------------------------------
# HF searcher: README lands in the notes
# ---------------------------------------------------------------------------
HF_MODEL_PAYLOAD = {
    "id": "owner/repo",
    "author": "owner",
    "name": "repo",
    "siblings": [
        {"rfilename": "model.safetensors"},
        {"rfilename": "README.md"},
        {"rfilename": "assets/teaser.png"},
    ],
}
HF_README = b"""---
license: apache-2.0
language:
- en
---
# Repo Card

The **best** model. <script>steal()</script>

![teaser](./assets/teaser.png)
"""


@pytest.mark.asyncio
async def test_hf_search_embeds_the_readme_in_the_notes(hub_factory, monkeypatch):
    information = import_ext("information")
    hub = await hub_factory(
        {
            "GET /api/models/owner/repo": HF_MODEL_PAYLOAD,
            "GET /api/models/owner/repo/tree/main": [{"type": "file", "path": "model.safetensors", "size": 1234}],
            "GET /owner/repo/resolve/main/README.md": (200, HF_README, {"Content-Type": "text/markdown"}),
        }
    )
    monkeypatch.setattr(information, "HF_API_BASE", f"{hub.base}/api")
    monkeypatch.setattr(information, "HF_WEB_BASE", hub.base)

    searcher = information.HuggingfaceModelSearcher()
    models = await searcher.search_by_url("https://huggingface.co/owner/repo")

    assert len(models) == 1
    description = models[0]["description"]
    _front_matter, _, body = description.partition("---\n")
    # the card's license made it into the notes' front-matter rows
    assert "license: apache-2.0" in description
    assert "website: Hugging Face" in description
    # the README body is embedded, sanitized, with absolutized URLs
    assert "# Repo Card" in body
    assert "steal()" not in body
    assert f"{hub.base}/owner/repo/resolve/main/assets/teaser.png" in body


@pytest.mark.asyncio
async def test_hf_search_without_readme_keeps_the_fallback(hub_factory, monkeypatch):
    information = import_ext("information")
    hub = await hub_factory(
        {
            "GET /api/models/owner/repo": HF_MODEL_PAYLOAD,
            "GET /api/models/owner/repo/tree/main": [],
            "GET /owner/repo/resolve/main/README.md": (404, b"not found"),
        }
    )
    monkeypatch.setattr(information, "HF_API_BASE", f"{hub.base}/api")
    monkeypatch.setattr(information, "HF_WEB_BASE", hub.base)

    searcher = information.HuggingfaceModelSearcher()
    models = await searcher.search_by_url("https://huggingface.co/owner/repo")
    assert len(models) == 1
    assert "No description about this model" in models[0]["description"]


# ---------------------------------------------------------------------------
# ModelScope searcher: README lands in the notes
# ---------------------------------------------------------------------------
class _FakeFileInfo:
    def __init__(self, path: str, size: int = 100):
        self.is_dir = False
        self.path = path
        self.size = size
        self.sha256 = "ab" * 32
        self.lfs = None


@pytest.mark.asyncio
async def test_modelscope_search_embeds_the_readme_in_the_notes(hub_factory, monkeypatch):
    information = import_ext("information")
    hub = await hub_factory(
        {
            "GET /models/owner/repo/resolve/master/README.md": (200, HF_README, {"Content-Type": "text/markdown"}),
        }
    )
    monkeypatch.setattr(information, "MODELSCOPE_INTL_ENDPOINT", hub.base)
    monkeypatch.setattr(
        information.ModelScopeModelSearcher,
        "_list_repo_files",
        lambda self, repo_id: [_FakeFileInfo("model.safetensors", 1234)],
    )

    searcher = information.ModelScopeModelSearcher()
    models = await searcher.search_by_url(f"{hub.base}/models/owner/repo")

    assert len(models) == 1
    description = models[0]["description"]
    assert "license: apache-2.0" in description
    assert "website: ModelScope" in description
    assert "# Repo Card" in description
    assert "steal()" not in description


@pytest.mark.asyncio
async def test_modelscope_readme_falls_back_to_main(hub_factory, monkeypatch):
    information = import_ext("information")
    hub = await hub_factory(
        {
            # master 404s, main serves the README
            "GET /models/owner/repo/resolve/master/README.md": (404, b"not found"),
            "GET /models/owner/repo/resolve/main/README.md": (
                200,
                b"# Main Branch Card\n",
                {"Content-Type": "text/markdown"},
            ),
        }
    )
    monkeypatch.setattr(information, "MODELSCOPE_INTL_ENDPOINT", hub.base)
    monkeypatch.setattr(
        information.ModelScopeModelSearcher,
        "_list_repo_files",
        lambda self, repo_id: [_FakeFileInfo("model.safetensors", 1234)],
    )

    searcher = information.ModelScopeModelSearcher()
    models = await searcher.search_by_url(f"{hub.base}/models/owner/repo")
    assert len(models) == 1
    assert "# Main Branch Card" in models[0]["description"]
    # both branches were tried, in order
    assert [path for _, path in hub.calls] == [
        "/models/owner/repo/resolve/master/README.md",
        "/models/owner/repo/resolve/main/README.md",
    ]
