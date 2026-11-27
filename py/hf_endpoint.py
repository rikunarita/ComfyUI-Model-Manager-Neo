"""Hugging Face endpoint selection (official hub vs. community mirror).

Some networks cannot reach huggingface.co. The ComfyUI setting
``ModelManager.Network.HuggingFaceEndpoint`` lets every Hugging Face call
site — search, model information, pasted-URL resolution and downloads —
point at a mirror instead. Currently the only mirror offered is
`https://hf-mirror.com`, which proxies the REST API and the classic
resolve/LFS endpoints.

Two properties of hf-mirror.com shape this module:

* it does **not** proxy the Xet content-addressed store that
  ``huggingface_hub`` uses by default for large files (the client would
  reach ``cas-server.xethub.hf.co`` directly and get HTTP 401), so the Xet
  transport is force-disabled process-wide whenever a non-default endpoint
  is selected — classic HTTP/LFS semantics, which the mirror supports;
* its resolve endpoints keep the exact ``{endpoint}/{repo}/resolve/{rev}/{file}``
  shape of the official hub, so every URL built from the web base keeps
  working unchanged.

The setting is cached for a few seconds so flipping it in the UI takes
effect without restarting ComfyUI, and so the once-a-second call sites do
not re-read ComfyUI's settings file on every request.
"""

from __future__ import annotations

import time

from . import utils

OFFICIAL_ENDPOINT = "https://huggingface.co"
MIRROR_ENDPOINT = "https://hf-mirror.com"

#: Values accepted from the settings file. Anything else (a hand-edited
#: ``comfy.settings.json``, a future mirror that was removed) falls back to
#: the official endpoint rather than silently sending traffic — and the
#: user's API key — somewhere unexpected.
KNOWN_ENDPOINTS = (OFFICIAL_ENDPOINT, MIRROR_ENDPOINT)

_TTL = 5.0
_cached: tuple[float, str] | None = None


def huggingface_endpoint() -> str:
    """The configured endpoint origin (no trailing slash)."""
    global _cached
    now = time.monotonic()
    if _cached is not None and now - _cached[0] < _TTL:
        return _cached[1]
    endpoint = OFFICIAL_ENDPOINT
    try:
        raw = utils.get_setting_value(None, "network.huggingface_endpoint", OFFICIAL_ENDPOINT)
        if isinstance(raw, str):
            candidate = raw.strip().rstrip("/")
            if candidate in KNOWN_ENDPOINTS:
                endpoint = candidate
    except Exception:
        endpoint = OFFICIAL_ENDPOINT
    _cached = (now, endpoint)
    return endpoint


def using_mirror() -> bool:
    return huggingface_endpoint() != OFFICIAL_ENDPOINT


def hf_api_base(default: str) -> str:
    """API base for raw HTTP calls.

    ``default`` is the caller's module constant so the mock tests keep
    pointing the searcher/information code at their local fake hub.
    """
    endpoint = huggingface_endpoint()
    return default if endpoint == OFFICIAL_ENDPOINT else f"{endpoint}/api"


def hf_web_base(default: str) -> str:
    """Web base for resolve/README/preview URLs (see :func:`hf_api_base`)."""
    endpoint = huggingface_endpoint()
    return default if endpoint == OFFICIAL_ENDPOINT else endpoint


def page_base() -> str:
    """Base for user-facing repository page links."""
    return huggingface_endpoint()


def disable_xet_if_mirror() -> bool:
    """Force the classic HTTP/LFS transport when a mirror is selected.

    Returns True when the Xet transport was disabled by this call (i.e. a
    mirror is selected and ``huggingface_hub`` is importable). Mutating the
    ``huggingface_hub.constants`` attribute — read at transfer time — covers
    the Xet code paths without requiring ``hf_xet`` to be absent.

    Note: once disabled, Xet stays disabled for the remainder of the
    process. Restarting ComfyUI with the official endpoint selected
    re-enables it.
    """
    if not using_mirror():
        return False
    try:
        from huggingface_hub import constants

        constants.HF_HUB_DISABLE_XET = True
        return True
    except Exception:
        return False
