import json
import os
import pickle
from typing import ClassVar

from . import config, utils


class ApiKey:
    """
    Manages API keys for Civitai and Hugging Face.
    Keys are stored in a pickle file (private.key) and can be overridden
    by environment variables.
    Priority:
    1. Model Manager settings (private.key)
    2. Environment variables (HF_TOKEN / CIVITAI_API_KEY)
    3. None
    Existing settings are never overwritten by lower-priority sources.
    """

    _store: dict[str, str]
    _cache_file: str = ""

    def __init__(self):
        self._cache_file = os.path.join(config.extension_uri, "private.key")
        # Fresh per-instance store: a mutable CLASS-level default would be
        # shared (and mutated) across instances before init() reassigns it.
        self._store = {}

    def init(self, request):
        """
        Initialize API keys. Migrates keys from ComfyUI user settings to
        the private.key pickle file on first run.
        """
        # Try to migrate api key from user setting
        if not os.path.exists(self._cache_file):
            try:
                self._store = {
                    "civitai": utils.get_setting_value(request, "api_key.civitai"),
                    "huggingface": utils.get_setting_value(request, "api_key.huggingface"),
                }
                self._update()
                # Remove api key from user setting (migration complete)
                utils.set_setting_value(request, "api_key.civitai", None)
                utils.set_setting_value(request, "api_key.huggingface", None)
            except Exception as e:
                # Reading the user settings can fail (e.g. ComfyUI's security
                # check answers 401): skip the migration and start from an
                # empty store instead of failing the whole init.
                utils.print_warning(f"Failed to migrate API keys from user settings: {e}")
                self._store = self._empty_store()
                self._update()

        self._store = self._load_store()

        # An empty store + a token in the environment => adopt it (see below).
        self.bootstrap_from_environment()

        # Desensitization returns
        result: dict[str, str] = {}
        for key in self._store:
            v = self._store[key]
            if v is not None:
                result[key] = v[:4] + "****" + v[-4:]
        return result

    # Environment variables that can seed the store, per provider.
    ENV_KEYS: ClassVar[dict[str, str]] = {
        "civitai": "CIVITAI_API_KEY",
        "huggingface": "HF_TOKEN",
        "modelscope": "MODELSCOPE_API_TOKEN",
    }

    def bootstrap_from_environment(self) -> list[str]:
        """Persist environment-provided keys when `private.key` is empty.

        BUG FIX / feature: a token exported as `HF_TOKEN` / `CIVITAI_API_KEY`
        used to work only as a read-through fallback - the Settings panel kept
        showing "None", the mask/edit UI was dead, and the first key saved from
        the UI silently shadowed the environment. When the store holds *no*
        value at all (fresh install, or an emptied `private.key`) every key that
        the environment actually provides is now written into `private.key`
        once, so it behaves exactly like a key entered through the UI. Keys not
        present in the environment are left untouched, and a store that already
        has any value is never overwritten.

        Returns the provider names that were seeded (for logging/tests).
        """
        if any(self._store.get(k) for k in self.ENV_KEYS):
            return []
        seeded = []
        for key, env_name in self.ENV_KEYS.items():
            env_value = os.environ.get(env_name)
            if env_value and not self._store.get(key):
                self._store[key] = env_value
                seeded.append(key)
        if seeded:
            self._update()
            utils.print_info("Seeded API key(s) from environment into private.key: " + ", ".join(seeded))
        return seeded

    def get_value(self, key: str):
        """
        Get API key value with priority: settings > environment variable > None
        """
        # 1. Model Manager settings (highest priority)
        value = self._store.get(key)
        if value:
            return value

        # 2. Environment variable fallback
        env_map = {
            "civitai": "CIVITAI_API_KEY",
            "huggingface": "HF_TOKEN",
            "modelscope": "MODELSCOPE_API_TOKEN",
        }
        env_key = env_map.get(key)
        if env_key:
            return os.environ.get(env_key)
        return None

    def set_value(self, key: str, value):
        """Set API key value and persist to private.key"""
        self._store[key] = value
        self._update()

    @staticmethod
    def _empty_store() -> dict:
        return {"civitai": None, "huggingface": None, "modelscope": None}

    def _sanitize(self, data) -> dict:
        """Only accept a flat str->str|None mapping (keys are secrets)."""
        store = self._empty_store()
        if isinstance(data, dict):
            for key in store:
                value = data.get(key)
                if isinstance(value, str) and value:
                    store[key] = value
        return store

    def _load_store(self) -> dict:
        """Read `private.key`, migrating the legacy pickle format once.

        Hardening: the store used to be a *pickle*, i.e.
        deserialising a file an attacker can place next to the extension could
        execute arbitrary code. It is now plain JSON written with 0600
        permissions; an existing pickle (which only this extension ever wrote)
        is converted on first read and never executed for anything but the two
        known string keys.
        """
        if not os.path.exists(self._cache_file):
            return self._empty_store()
        try:
            with open(self._cache_file, "rb") as f:
                raw = f.read()
        except OSError:
            return self._empty_store()
        if not raw.strip():
            return self._empty_store()
        try:
            return self._sanitize(json.loads(raw.decode("utf-8")))
        except Exception:
            pass
        # Legacy pickle written by older versions of this extension.
        try:
            store = self._sanitize(pickle.loads(raw))
            self._store = store
            self._update()  # rewrite as JSON immediately
            utils.print_info("Migrated private.key from pickle to JSON")
            return store
        except Exception:
            utils.print_warning("private.key is unreadable; starting empty")
            return self._empty_store()

    def _update(self):
        """Persist API keys to disk as JSON, owner-readable only."""
        with open(self._cache_file, "w", encoding="utf-8") as f:
            json.dump(self._store, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(self._cache_file, 0o600)
        except OSError:
            pass


# Singleton instance
_api_key_instance = None


def get_api_key():
    """Get the global ApiKey singleton instance."""
    global _api_key_instance
    if _api_key_instance is None:
        _api_key_instance = ApiKey()
    return _api_key_instance


def get_hf_token():
    """Get Hugging Face API token."""
    return get_api_key().get_value("huggingface")


def get_civitai_token():
    """Get Civitai API token."""
    return get_api_key().get_value("civitai")


def get_hf_headers():
    """
    Return HTTP headers for Hugging Face API requests.
    Includes Authorization Bearer token if available.
    """
    headers = {"User-Agent": config.user_agent}
    token = get_hf_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_modelscope_token():
    """Get ModelScope API token."""
    return get_api_key().get_value("modelscope")


def get_civitai_headers():
    """
    Return HTTP headers for Civitai API requests.
    Includes Authorization Bearer token if available.
    """
    headers = {"User-Agent": config.user_agent}
    token = get_civitai_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
