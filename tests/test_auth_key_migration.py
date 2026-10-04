"""First-run migration of API keys out of ComfyUI user settings (py/auth.py).

Regression coverage of the historical Hugging Face setting ID: the display
name unification of 2026-09-19 renamed the PERSISTED setting ID from
``ModelManager.APIKey.HuggingFace`` to ``ModelManager.APIKey.Hugging Face``.
The ID string is the key ComfyUI stores the user's value under (the same
doctrine the ``ModelManager.Scan.*`` IDs follow), so a key entered through the
fork origin's UI - or any build before the rename - lives under the historical
ID and the migration must read it, or the README/USAGE promise ("keys migrate
out of ComfyUI user settings on first run") silently fails for exactly one
provider while its Civitai neighbour migrates fine.
"""

from __future__ import annotations

import json

from harness import import_ext

LEGACY_HF_ID = "ModelManager.APIKey.HuggingFace"
CURRENT_HF_ID = "ModelManager.APIKey.Hugging Face"
CIVITAI_ID = "ModelManager.APIKey.Civitai"


class _FakeSettings:
    """Mirror of ComfyUI's UserManager.settings (get/save by request)."""

    def __init__(self, values: dict):
        self.values = dict(values)
        self.save_calls = 0

    def get_settings(self, request):
        return dict(self.values)

    def save_settings(self, request, settings):
        self.values = dict(settings)
        self.save_calls += 1


class _FakeServer:
    def __init__(self, settings: _FakeSettings):
        self.user_manager = type("UM", (), {"settings": settings})()


def _fresh_api_key(tmp_path, monkeypatch, settings: _FakeSettings):
    """An ApiKey whose private.key lives in tmp_path, against fake settings."""
    auth = import_ext("auth")
    config = import_ext("config")
    monkeypatch.setattr(config, "serverInstance", _FakeServer(settings))
    key = auth.ApiKey()
    key._cache_file = str(tmp_path / "private.key")
    return key


def _stored(tmp_path) -> dict:
    return json.loads((tmp_path / "private.key").read_text(encoding="utf-8"))


def test_migration_reads_the_historical_huggingface_id(tmp_path, monkeypatch):
    """A key stored under the pre-rename ID migrates into private.key."""
    settings = _FakeSettings({LEGACY_HF_ID: "hf_legacy_token", CIVITAI_ID: "civitai_token"})
    key = _fresh_api_key(tmp_path, monkeypatch, settings)

    masked = key.init(None)

    store = _stored(tmp_path)
    assert store["huggingface"] == "hf_legacy_token"
    assert store["civitai"] == "civitai_token"
    # The consumed historical entry is nulled out like every migrated key...
    assert settings.values[LEGACY_HF_ID] is None
    assert settings.values[CIVITAI_ID] is None
    # ...and the init response keeps masking the migrated value.
    assert masked["huggingface"] == "hf_l****oken"


def test_migration_prefers_the_current_id_over_the_historical_one(tmp_path, monkeypatch):
    """When both IDs hold a value, the current one wins."""
    settings = _FakeSettings({CURRENT_HF_ID: "current_token", LEGACY_HF_ID: "legacy_token"})
    key = _fresh_api_key(tmp_path, monkeypatch, settings)

    key.init(None)

    assert _stored(tmp_path)["huggingface"] == "current_token"


def test_migration_leaves_an_unconsumed_historical_entry_alone(tmp_path, monkeypatch):
    """No legacy value -> the legacy setting is never written to.

    A side-by-side installed original extension may still be waiting to run
    its own migration against that key; nulling an entry we did not consume
    would destroy it.
    """
    settings = _FakeSettings({CIVITAI_ID: "civitai_token"})
    key = _fresh_api_key(tmp_path, monkeypatch, settings)

    key.init(None)

    assert _stored(tmp_path)["huggingface"] is None
    assert LEGACY_HF_ID not in settings.values


def test_second_init_is_a_noop_reread(tmp_path, monkeypatch):
    """Once private.key exists the migration never runs again.

    A historical-ID value that appears AFTER the first migration must be
    neither consumed nor nulled: private.key is the store from then on.
    """
    settings = _FakeSettings({})
    key = _fresh_api_key(tmp_path, monkeypatch, settings)
    key.init(None)
    assert _stored(tmp_path)["huggingface"] is None

    settings.values[LEGACY_HF_ID] = "late_token"  # set AFTER the migration
    key2 = _fresh_api_key(tmp_path, monkeypatch, settings)
    key2.init(None)

    assert _stored(tmp_path)["huggingface"] is None  # not re-migrated
    assert settings.values[LEGACY_HF_ID] == "late_token"  # not consumed
