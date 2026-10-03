"""Loader for the Rust native core (``mm_core``).

Phase 0 scaffold of the native-core refresh (refresh-plan §4.2.3 — the plan
documents were retired from the tree after completion and live in the git
history): the heavy ZipNN/scan/hash work moves into a Rust extension module
that ships as **prebuilt binaries** under ``native/native-bin/<platform tag>/``.
Loading is
deliberately dumb and side-effect free — platform detection, one ``sys.path``
entry, one ``import``, one version check. **No compilation, no pip, no
network** (Plan §2.1-5); when anything does not line up, the module simply
reports ``available() is False`` plus a human-readable ``reason()``.

Phase 8 removed the ``MM_NATIVE`` transition switch: the prebuilt core under
``native-bin/`` is the SINGLE native path (the vendored C core and its Python
frontends are gone). ``load()`` never raises — when the binary is missing or
the handshake fails it reports ``available() is False`` plus a human-readable
``reason()``, and each feature decides its own degradation: the ZipNN routes
fail with that reason (there is no other engine), while resilient read paths
(scan / header / hashes) keep their pure-Python fallbacks.

NEO-PLAN-2026-003 added the interpreter-FLAVOUR routing on top of that
contract: free-threaded CPython 3.15+ is served by the ``<tag>t`` abi3t
artifacts (PEP 803 — a free-threaded build cannot load the plain abi3
binaries), GIL builds stay on ``<tag>`` (abi3-py312 floor), and interpreters
below either floor degrade with an explicit reason instead of attempting an
import that could only fail with unreadable undefined-symbol errors.
"""

import importlib
import os
import platform
import sys
import sysconfig
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
# * 4 — Phase 5: the scan / hygiene / safetensors-header / hash surface
#   (scan_models/scan_hygiene/safetensors_header/hash_file/hasher_*) that
#   py/manager.py, py/utils.py, py/identify.py and py/download.py call
#   directly, plus the persistent front-matter index.
# * 5 — Phase 6: the display tensor tree (safetensors_tensor_tree, the Rust
#   pre-grouping of Plan §4.7.3) that py/utils.py serves to the model-detail
#   route, plus the optional library watcher (watch_start/watch_poll/
#   watch_stop/watch_diagnostics, Plan §4.7.2-2) that py/watcher.py drives.
# * 6 — Phase 7 (T7): the preview WebP codec (webp_decode / webp_encode /
#   webp_encode_animation, the zenwebp-backed pure-Rust encode/decode/animation
#   of Plan §3.8 追記) that py/utils.py's preview pipeline calls with a PIL
#   fallback.
# The range is EXACT (min == max): an older binary would pass a `>=` handshake
# and then fail with an AttributeError deep inside a compression task — an
# incompatible binary must be rejected at load time with a clear reason().
MIN_API_VERSION = 6
MAX_API_VERSION = 6

# Interpreter floors (NEO-PLAN-2026-003). The GIL-build artifacts are built
# against the `abi3-py312` Stable ABI floor; importing them on an older
# interpreter dies with unreadable undefined-symbol errors, so the loader
# refuses EARLY and converts that into the degrade contract's reason().
# Free-threaded builds get their own artifact family (`<tag>t`, the PEP 803
# `abi3t` stable ABI): abi3t exists only from CPython 3.15 onward, and a
# free-threaded build cannot load the plain abi3 binaries — so free-threaded
# 3.13/3.14 degrade with an explicit reason as well (Plan-3 §3.3/R8).
MIN_GIL_VERSION = (3, 12)
MIN_FT_VERSION = (3, 15)

_NATIVE_DIR = "native"
_NATIVE_BIN_DIR = "native-bin"
_MODULE_NAME = "mm_core"

# Loaded module (None until a successful load()).
_module: ModuleType | None = None
# Why the native core is unavailable (None when it is available).
_reason: str | None = None
# load() is idempotent; the guard keeps repeated calls cheap.
_attempted = False


def is_free_threaded() -> bool:
    """True on a free-threaded (GIL-disabled BUILD) CPython.

    The single flavour-detection point of the loader (Plan-3 §3.3):
    ``Py_GIL_DISABLED`` is the documented build-time flag (defined from
    CPython 3.13 onward; absent or 0 on GIL builds) and ``sys.abiflags``
    carrying ``t`` is the same fact from the interpreter's own ABI flags —
    either signal counts (``abiflags`` only exists on POSIX builds, hence
    the getattr guard: load() must never raise on any platform). The
    RUNTIME GIL state (``sys._is_gil_enabled()``) is deliberately not
    consulted: re-enabling the GIL at runtime does not make the plain-abi3
    artifacts loadable on a free-threaded build.
    """
    return sysconfig.get_config_var("Py_GIL_DISABLED") == 1 or "t" in getattr(sys, "abiflags", "")


def _base_platform_tag() -> str | None:
    """The OS/architecture tag WITHOUT the flavour suffix, or None.

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


def platform_tag() -> str | None:
    """The ``native-bin/`` subdirectory for this machine, or None.

    NEO-PLAN-2026-003 routes each interpreter flavour to its own artifact
    family on top of the Plan §4.2.1 base tags:

    * GIL build >= 3.12 → ``<tag>`` (the abi3-py312 binaries),
    * free-threaded build >= 3.15 → ``<tag>t`` (the abi3t binaries, PEP 803;
      GIL 3.15+ deliberately stays on ``<tag>`` — the abi3 artifacts load
      there too and double-shipping is avoided),
    * below either floor, or an unsupported OS/architecture → None, with the
      interpreter-side cases explained by ``tag_rejection_reason()``.
    """
    base = _base_platform_tag()
    if base is None:
        return None
    if is_free_threaded():
        return base + "t" if sys.version_info[:2] >= MIN_FT_VERSION else None
    if sys.version_info[:2] < MIN_GIL_VERSION:
        return None
    return base


def tag_rejection_reason() -> str | None:
    """Why ``platform_tag()`` is None for INTERPRETER reasons (else None).

    None here does NOT mean "supported": an unsupported OS/architecture also
    yields a None tag, but ``load()`` reports that case itself ("no prebuilt
    native core for ..."). Keeping the two families separate is what lets the
    degrade contract name the actual blocker (floor vs. platform) in the ZipNN
    routes' error toast and in diagnostics.
    """
    if _base_platform_tag() is None:
        return None
    version = f"{sys.version_info[0]}.{sys.version_info[1]}"
    if is_free_threaded():
        if sys.version_info[:2] < MIN_FT_VERSION:
            return (
                f"free-threaded CPython {version} has no stable-ABI artifact "
                "(abi3t requires 3.15+, PEP 803), and a free-threaded build "
                "cannot load the plain abi3 binaries"
            )
        return None
    if sys.version_info[:2] < MIN_GIL_VERSION:
        return (
            f"native core requires CPython {MIN_GIL_VERSION[0]}.{MIN_GIL_VERSION[1]}+ "
            f"(abi3-py{MIN_GIL_VERSION[0]}{MIN_GIL_VERSION[1]} floor), running on {version}"
        )
    return None


def load() -> bool:
    """Try to make ``mm_core`` importable (idempotent).

    Returns True when the native core is loaded and its API version is in the
    supported range; False (with ``reason()`` set) when it is not. Never
    raises — callers decide what an unavailable core means for them.
    """
    global _module, _reason, _attempted
    if _attempted:
        return _module is not None
    _attempted = True

    tag = platform_tag()
    if tag is None:
        # Interpreter-floor rejections (GIL < 3.12 / free-threaded < 3.15)
        # carry their own actionable reason; anything else is the classic
        # unsupported-OS/architecture case (NEO-PLAN-2026-003 §3.3).
        _reason = tag_rejection_reason() or (f"no prebuilt native core for {platform.system()}/{platform.machine()}")
        return False

    bin_dir = utils.join_path(config.extension_uri, _NATIVE_DIR, _NATIVE_BIN_DIR, tag)
    if not os.path.isdir(bin_dir):
        _reason = f"native-bin directory missing for {tag}: {bin_dir}"
        return False

    if bin_dir not in sys.path:
        # Appended, not prepended (the legacy vendored-core loader used to
        # insert(0)): `mm_core` is a unique name, and appending keeps a
        # user-installed mm_core of higher precedence impossible to shadow by
        # accident in the other direction.
        sys.path.append(bin_dir)
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(_MODULE_NAME)
    except Exception as exc:  # reported via reason(), never fatal
        _reason = f"import {_MODULE_NAME} failed: {exc}"
        return False

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
        return False

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
        return False

    _module = module
    _reason = None
    utils.print_info(
        f"native core ready: {_MODULE_NAME} api_version={version} core_version={core_version() or '?'} ({tag})"
    )
    return True


def available() -> bool:
    """True once load() succeeded (does not trigger a load itself)."""
    return _module is not None


def core() -> ModuleType | None:
    """The loaded ``mm_core`` module, or None when unavailable."""
    return _module


def core_if_enabled() -> ModuleType | None:
    """The loaded ``mm_core``, or None when this machine cannot run it.

    The shared entry point of every native consumer (``py/compress.py`` jobs,
    ``py/manager.py`` scan, ``py/utils.py`` header/preview, ``py/identify.py``
    hashing, ``py/download.py`` inline verification, ``py/watcher.py``).
    Phase 8 removed the ``MM_NATIVE`` switch: this simply returns the core
    when the prebuilt binary loads and passes the handshake, else None (with
    ``reason()`` explaining why).
    """
    if load():
        return _module
    return None


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
        "platformTag": platform_tag(),
        "freeThreaded": is_free_threaded(),
        "available": available(),
        "reason": reason(),
        "apiVersion": getattr(_module, "api_version", lambda: None)() if _module else None,
        "coreVersion": core_version(),
    }
