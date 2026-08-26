import os

from . import config
from . import utils

class ApiKey:
    """
    Manages API keys for Civitai and HuggingFace.
    Keys are stored in a pickle file (private.key) and can be overridden
    by environment variables.
    Priority:
    1. Model Manager settings (private.key)
    2. Environment variables (HF_TOKEN / CIVITAI_API_KEY)
    3. None
    Existing settings are never overwritten by lower-priority sources.
    """
    _store: dict[str, str] = {}
    _cache_file: str = ""

    def __init__(self):
        self._cache_file = os.path.join(config.extension_uri, "private.key")

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
                # 【修正】ComfyUI のセキュリティチェックが 401 Unauthorized を返した場合、
                # マイグレーションをスキップし、空の設定から開始する
                utils.print_warning(f"Failed to migrate API keys from user settings: {e}")
                self._store = {"civitai": None, "huggingface": None}
                self._update()

        try:
            self._store = utils.load_dict_pickle_file(self._cache_file)
        except Exception:
            self._store = {"civitai": None, "huggingface": None}

        # Desensitization returns
        result: dict[str, str] = {}
        for key in self._store:
            v = self._store[key]
            if v is not None:
                result[key] = v[:4] + "****" + v[-4:]
        return result

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
        }
        env_key = env_map.get(key)
        if env_key:
            return os.environ.get(env_key)
        return None

    def set_value(self, key: str, value):
        """Set API key value and persist to private.key"""
        self._store[key] = value
        self._update()

    def _update(self):
        """Persist API keys to disk"""
        utils.save_dict_pickle_file(self._cache_file, self._store)

# Singleton instance
_api_key_instance = None

def get_api_key():
    """Get the global ApiKey singleton instance."""
    global _api_key_instance
    if _api_key_instance is None:
        _api_key_instance = ApiKey()
    return _api_key_instance

def get_hf_token():
    """Get HuggingFace API token."""
    return get_api_key().get_value("huggingface")

def get_civitai_token():
    """Get Civitai API token."""
    return get_api_key().get_value("civitai")

def get_hf_headers():
    """
    Return HTTP headers for HuggingFace API requests.
    Includes Authorization Bearer token if available.
    """
    headers = {"User-Agent": config.user_agent}
    token = get_hf_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

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
