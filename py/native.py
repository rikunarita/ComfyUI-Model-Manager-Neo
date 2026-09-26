"""Loader for the Rust native core (``mm_core``).

Phase 0 scaffold of the native-core refresh (``Agent/Plan.md`` §4.2.3): the
heavy ZipNN/scan/hash work moves into a Rust extension module that ships as
**prebuilt binaries** under ``native/native-bin/<platform tag>/``. Loading is
deliberately dumb and side-effect free — platform detection, one ``sys.path``
entry, one ``import``, one version check. **No compilation, no pip, no
network** (Plan §2.1-5); when anything does not line up, the module simply
reports ``available() is False`` plus a human-readable ``reason()``, and the
caller keeps using the vendored ``third_party`` path (until Phase 7 removes it).

The ``MM_NATIVE`` environment variable switches the code path (Plan §5.4):

* ``0`` — never load the native core (legacy path forced);
* ``1`` — the native core is *required*: ``load()`` raises when unavailable;
* anything else / unset — ``auto``: use the native core when it loads.

Nothing imports this module at extension start-up yet; ``py/compress.py`` and
friends wire into it in Phase 2+ (``MM_NATIVE=0/1/auto`` transition period).
"""

import importlib
import os
import platform
import sys
from types import ModuleType

from . import config, utils

# The Python-facing API surface this backend understands (Plan §4.2.2
# `api_version()`); bump together with the Rust constant in
# native/crates/mm-core/src/lib.rs.
#
# * 1 — Phase 0: version handshake only,
# * 2 — Phase 2: the ZipNN safetensors job API (zipnn_compress/decompress +
#   job_progress/cancel/result/error) that py/compress.py calls directly,
# * 3 — Phase 3: the delta jobs (zipnn_delta_compress/decompress) and the
#   batch primitives (walk_models/move_with_sidecars) that the delta and
#   batch-folder routes call directly.
# The range is EXACT (min == max): an older binary would pass a `>=` handshake
# and then fail with an AttributeError deep inside a compression task — an
# incompatible binary must be rejected at load time with a clear reason().
MIN_API_VERSION = 3
MAX_API_VERSION = 3

_NATIVE_DIR = "native"
_NATIVE_BIN_DIR = "native-bin"
_MODULE_NAME = "mm_core"

# Loaded module (None until a successful load()).
_module: ModuleType | None = None
# Why the native core is unavailable (None when it is available).
_reason: str | None = None
# load() is idempotent; the guard keeps repeated calls cheap.
_attempted = False


def platform_tag() -> str | None:
    """The ``native-bin/`` subdirectory for this machine, or None.

    Tags follow Plan §4.2.1: ``linux-x86_64``, ``linux-aarch64``,
    ``windows-x86_64``, ``macos-universal2`` (one fat binary serves both
    Intel and Apple Silicon). Anything else (32-bit, exotic architectures)
    has no prebuilt support.
    """
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Linux":
        if machine in ("x86_64", "amd64"):
            return "linux-x86_64"
        if machine in ("aarch64", "arm64"):
            return "linux-aarch64"
    elif system == "Windows":
        # Windows reports AMD64 for x86_64 (and ARM64 for aarch64, which has
        # no prebuilt binary — Plan §4.2.1).
        if machine in ("amd64", "x86_64"):
            return "windows-x86_64"
    elif system == "Darwin":
        if machine in ("x86_64", "arm64"):
            return "macos-universal2"
    return None


def native_mode() -> str:
    """Normalized ``MM_NATIVE`` value: ``"0"``, ``"1"`` or ``"auto"``."""
    raw = os.environ.get("MM_NATIVE", "auto").strip().lower()
    if raw in ("0", "off", "false", "no"):
        return "0"
    if raw in ("1", "on", "true", "yes"):
        return "1"
    return "auto"


def load() -> bool:
    """Try to make ``mm_core`` importable (idempotent).

    Returns True when the native core is loaded and its API version is in the
    supported range. With ``MM_NATIVE=1`` a failure raises instead — an
    installation that *requires* the native core must not silently fall back
    to the legacy path (Plan §5.4).
    """
    global _module, _reason, _attempted
    if _attempted:
        return _module is not None
    _attempted = True

    mode = native_mode()
    if mode == "0":
        _reason = "disabled via MM_NATIVE=0"
        return False

    tag = platform_tag()
    if tag is None:
        _reason = f"no prebuilt native core for {platform.system()}/{platform.machine()}"
        return _fail(mode)

    bin_dir = utils.join_path(config.extension_uri, _NATIVE_DIR, _NATIVE_BIN_DIR, tag)
    if not os.path.isdir(bin_dir):
        _reason = f"native-bin directory missing for {tag}: {bin_dir}"
        return _fail(mode)

    if bin_dir not in sys.path:
        # Appended, not prepended (unlike ensure_zipnn's insert(0) for the
        # vendored core): `mm_core` is a unique name, and appending keeps a
        # user-installed mm_core of higher precedence impossible to shadow by
        # accident in the other direction.
        sys.path.append(bin_dir)
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(_MODULE_NAME)
    except Exception as exc:  # reported via reason(), never fatal in auto mode
        _reason = f"import {_MODULE_NAME} failed: {exc}"
        return _fail(mode)

    # Origin guard: `import_module` short-circuits on `sys.modules` — an
    # already-imported same-named module (another extension's bundle, a stray
    # pip package) would be handed back WITHOUT ever consulting `bin_dir`,
    # and a cooperative `api_version()` on it would pass the handshake below
    # while the real native core was never loaded. Accept the module only
    # when its file really lives inside the probed native-bin directory.
    # (A foreign module is NOT evicted from sys.modules — it belongs to
    # whoever imported it; we only refuse to adopt it.)
    origin = getattr(module, "__file__", None)
    bin_prefix = os.path.normcase(os.path.realpath(bin_dir)) + os.sep
    if not origin or not os.path.normcase(os.path.realpath(origin)).startswith(bin_prefix):
        _reason = f"imported {_MODULE_NAME} does not originate from {bin_dir} (got {origin!r})"
        return _fail(mode)

    api_version = getattr(module, "api_version", None)
    version = api_version() if callable(api_version) else None
    if not isinstance(version, int) or not MIN_API_VERSION <= version <= MAX_API_VERSION:
        _reason = (
            f"{_MODULE_NAME}.api_version()={version!r} outside supported range [{MIN_API_VERSION}, {MAX_API_VERSION}]"
        )
        # A module that imported fine but FAILED the handshake must not linger
        # in sys.modules: anything else doing `import mm_core` (or a retry
        # against a fixed native-bin) would silently pick the rejected module
        # back up instead of failing/reporting cleanly.
        sys.modules.pop(_MODULE_NAME, None)
        return _fail(mode)

    _module = module
    _reason = None
    utils.print_info(
        f"native core ready: {_MODULE_NAME} api_version={version} core_version={core_version() or '?'} ({tag})"
    )
    return True


def _fail(mode: str) -> bool:
    """Record unavailability; raise only in MM_NATIVE=1 mode."""
    if mode == "1":
        raise RuntimeError(f"MM_NATIVE=1 but the native core is unavailable: {_reason}")
    return False


def available() -> bool:
    """True once load() succeeded (does not trigger a load itself)."""
    return _module is not None


def core() -> ModuleType | None:
    """The loaded ``mm_core`` module, or None when unavailable."""
    return _module


def reason() -> str | None:
    """Why the native core is unavailable (None when available)."""
    return _reason


def core_version() -> str | None:
    """``mm_core.core_version()`` ("x.y.z+commit"), or None when unavailable."""
    if _module is None:
        return None
    getter = getattr(_module, "core_version", None)
    if not callable(getter):
        return None
    try:
        return str(getter())
    except Exception:  # diagnostics must never explode
        return None


def diagnostics() -> dict[str, object]:
    """JSON-safe snapshot for the settings/about surface and bug reports."""
    return {
        "mode": native_mode(),
        "platformTag": platform_tag(),
        "available": available(),
        "reason": reason(),
        "apiVersion": getattr(_module, "api_version", lambda: None)() if _module else None,
        "coreVersion": core_version(),
    }
