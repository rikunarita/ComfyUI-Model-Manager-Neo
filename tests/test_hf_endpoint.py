"""Hugging Face endpoint selection (official hub vs. hf-mirror.com).

The ``ModelManager.Network.HuggingFaceEndpoint`` ComfyUI setting points every
Hugging Face call site at the configured endpoint; these tests pin the
default (official hub, untouched module constants), the mirror rewrite and
the fallback for unknown persisted values.
"""

from __future__ import annotations

import pytest
from harness import import_ext


@pytest.fixture
def hf_endpoint():
    module = import_ext("hf_endpoint")
    module._cached = None
    yield module
    module._cached = None


def _setting(value):
    return lambda request, key, default=None: value


def test_setting_key_is_registered():
    """The setting ID the frontend registers must resolve on the backend."""
    utils = import_ext("utils")
    assert utils.resolve_setting_key("network.huggingface_endpoint") == "ModelManager.Network.HuggingFaceEndpoint"


def test_default_is_official(hf_endpoint, monkeypatch):
    utils = import_ext("utils")
    # The stub server has no user_manager, so a plain read yields the default -
    # but pin it explicitly to keep the test independent of the stub semantics.
    monkeypatch.setattr(utils, "get_setting_value", _setting(hf_endpoint.OFFICIAL_ENDPOINT))
    assert hf_endpoint.huggingface_endpoint() == "https://huggingface.co"
    assert hf_endpoint.using_mirror() is False
    # the module constants stay authoritative (the mock tests point them at a local hub)
    assert hf_endpoint.hf_api_base("https://hub.local/api") == "https://hub.local/api"
    assert hf_endpoint.hf_web_base("https://hub.local") == "https://hub.local"
    assert hf_endpoint.page_base() == "https://huggingface.co"
    assert hf_endpoint.disable_xet_if_mirror() is False


def test_mirror_endpoint_rewrites_bases(hf_endpoint, monkeypatch):
    utils = import_ext("utils")
    monkeypatch.setattr(utils, "get_setting_value", _setting("https://hf-mirror.com"))
    assert hf_endpoint.huggingface_endpoint() == "https://hf-mirror.com"
    assert hf_endpoint.using_mirror() is True
    assert hf_endpoint.hf_api_base("https://hub.local/api") == "https://hf-mirror.com/api"
    assert hf_endpoint.hf_web_base("https://hub.local") == "https://hf-mirror.com"
    assert hf_endpoint.page_base() == "https://hf-mirror.com"


def test_mirror_disables_xet_transport(hf_endpoint, monkeypatch):
    utils = import_ext("utils")
    monkeypatch.setattr(utils, "get_setting_value", _setting("https://hf-mirror.com"))
    try:
        from huggingface_hub import constants
    except ImportError:
        pytest.skip("huggingface_hub is not installed in this environment")
    previous = constants.HF_HUB_DISABLE_XET
    try:
        assert hf_endpoint.disable_xet_if_mirror() is True
        # the Xet code paths read this attribute at transfer time
        assert constants.HF_HUB_DISABLE_XET is True
    finally:
        constants.HF_HUB_DISABLE_XET = previous


def test_trailing_slash_is_tolerated(hf_endpoint, monkeypatch):
    utils = import_ext("utils")
    monkeypatch.setattr(utils, "get_setting_value", _setting("https://hf-mirror.com/"))
    assert hf_endpoint.huggingface_endpoint() == "https://hf-mirror.com"


def test_unknown_endpoint_falls_back_to_official(hf_endpoint, monkeypatch):
    utils = import_ext("utils")
    monkeypatch.setattr(utils, "get_setting_value", _setting("https://example.com"))
    assert hf_endpoint.huggingface_endpoint() == "https://huggingface.co"
    assert hf_endpoint.disable_xet_if_mirror() is False


def test_mirror_urls_resolve_to_hf_searcher():
    information = import_ext("information")
    info = information.Information()
    for url in (
        "https://hf-mirror.com/owner/repo",
        "https://hf-mirror.com/owner/repo/tree/main",
        "https://huggingface.co/owner/repo",
    ):
        assert type(info.get_model_searcher_by_url(url)).__name__ == "HuggingfaceModelSearcher"
