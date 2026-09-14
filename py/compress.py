"""ZipNN compression / decompression for local safetensors models.

The tensor-by-tensor algorithm below is a faithful, non-interactive port of the
official reference scripts of the ZipNN project
(`scripts/zipnn_compress_safetensors.py` / `scripts/zipnn_decompress_safetensors.py`,
https://github.com/zipnn/zipnn, version 0.5.4):

* floating point tensors are compressed with ``ZipNN(input_format="torch",
  method=COMPRESSION_METHOD)`` and stored as ``uint8`` vectors;
* non floating point tensors are copied through untouched;
* per-tensor ``dtype``/``shape`` are recorded in the file metadata under
  ``znn_compressed_vectors`` (``zipnn.util_safetensors.METADATA_KEY``);
* a tensor whose compressed form is not smaller is left uncompressed;
* the compressed file is named ``<base>.znn.safetensors`` - the exact suffix the
  official scripts (and ``zipnn_safetensors()`` loaders) expect.

ZipNN is VENDORED, not pip-installed. PyPI ships no Linux wheels for it (only a
macOS arm64 wheel plus an sdist that compiles a C extension), so a plain
``pip install zipnn`` forces a source build that dies on any host without a C
compiler and the Python headers - which is exactly the failure this used to hit.
Instead the whole library now ships inside the extension under ``third_party/``:

* ``third_party/zipnn/`` - the ZipNN 0.5.4 Python package (MIT);
* ``third_party/zipnn-core-bin/<platform>/`` - prebuilt ``zipnn_core`` C
  extension binaries, so on the common platforms ZipNN works with **no compiler
  and no pip at all** - the module is simply put on ``sys.path``;
* ``third_party/zipnn-core/`` - the C sources (csrc + FiniteStateEntropy, BSD/
  GPLv2) used for a single clean source build on platforms that have no prebuilt
  binary (macOS / Windows / other arches). There is no cascade of pip
  strategies any more: one prebuilt lookup, else one source build.

Its only runtime dependencies are ``numpy`` / ``safetensors`` / ``torch``, all
of which ComfyUI already provides.
"""

import asyncio
import os
import platform
import re
import uuid
from typing import Any, Callable, Optional

from aiohttp import web

from . import config
from . import utils

ZNN_SUFFIX = ".znn.safetensors"
SAFE_SUFFIX = ".safetensors"

# Neo extension to the official ZipNN metadata layout: the pre-compression
# on-disk size of the source file, recorded at compress time so the UI can
# show the original size / compressed size / ratio breakdown for a compressed
# model (the original file itself is gone by then). Other ZipNN tools ignore
# unknown metadata keys, and decompression removes it again, so the restored
# file carries exactly the metadata the original had.
ZNN_ORIGINAL_SIZE_KEY = "znn_neo_original_bytes"

# task_id -> bookkeeping, same shape as the HF upload tasks
ZIPNN_TASKS: dict[str, dict] = {}

ProgressCb = Callable[[int, int, str], None]


def is_safetensors(name: str) -> bool:
    return name.endswith(SAFE_SUFFIX)


def is_compressed_name(name: str) -> bool:
    return name.endswith(ZNN_SUFFIX)


def zipnn_installed() -> bool:
    """True when both ZipNN parts are importable-by-name (without importing).

    ``importlib.invalidate_caches()`` matters here: the vendored directories are
    appended to ``sys.path`` (and a source build drops a fresh ``zipnn_core``
    into site-packages) *after* this interpreter already scanned those paths, so
    without it a successful setup can still look absent.
    """
    import importlib.util

    importlib.invalidate_caches()
    try:
        return (
            importlib.util.find_spec("zipnn") is not None
            and importlib.util.find_spec("zipnn_core") is not None
        )
    except Exception:
        return False


def zipnn_available() -> bool:
    try:
        import importlib

        importlib.invalidate_caches()
        import zipnn  # noqa: F401
        import zipnn_core  # noqa: F401

        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Vendored ZipNN layout (see third_party/README.md).
#
# `third_party/zipnn/` holds the pure-Python package; `zipnn_core` (the C
# extension) is either a prebuilt binary under
# `third_party/zipnn-core-bin/<platform-tag>/` or, on platforms with no prebuilt
# binary, compiled once from `third_party/zipnn-core/`. Nothing is downloaded.
# ---------------------------------------------------------------------------
_THIRD_PARTY_DIR = "third_party"
_ZIPNN_PKG_DIR = "zipnn"
_ZIPNN_CORE_BIN_DIR = "zipnn-core-bin"
_ZIPNN_CORE_SRC_DIR = "zipnn-core"

# The C sources are ZipNN 0.5.4's; modern toolchains (gcc >= 14, clang >= 16)
# turn a few historical C patterns into hard errors by default
# (-Werror=implicit-function-declaration, -Werror=incompatible-pointer-types),
# which would make a source build die with a bare "exit status 1". Relaxing
# exactly those diagnostics keeps every real error visible while letting the
# official sources build. (The prebuilt binaries need none of this.)
_ZIPNN_BUILD_CFLAGS = (
    "-Wno-error=implicit-function-declaration "
    "-Wno-implicit-function-declaration "
    "-Wno-error=incompatible-pointer-types "
    "-Wno-incompatible-pointer-types "
    "-Wno-error=int-conversion "
    "-Wno-int-conversion"
)


# Compiler binary names worth picking up as a substitute when the one CPython
# recorded in `sysconfig` (e.g. Gentoo's `x86_64-pc-linux-gnu-gcc`) is absent.
_CC_NAME_RE = re.compile(
    r"^(?:cc|clang(?:-\d+)?|gcc(?:-\d+(?:\.\d+)*)?|(?:[A-Za-z0-9_.]+-)+gcc(?:-\d+)?)$"
)

# Values for these keys are *appended* to whatever the environment already has
# (they are flag lists); every other key passed to `_run_pip` replaces it.
_ENV_APPEND_KEYS = frozenset({"CFLAGS", "CPPFLAGS", "CXXFLAGS", "LDFLAGS"})

# A failed install is remembered so that hammering the button does not re-run a
# doomed multi-minute build - but only for a while: the user may fix their
# toolchain, and the UI offers an explicit retry (`force`).
_ZIPNN_INSTALL_TTL = 300.0
_zipnn_install_failed: tuple[str, float] | None = None


class ZipNNInstallError(RuntimeError):
    """The optional ZipNN dependency could not be installed on this host."""


_PKG_MANAGER_HINTS = {
    "debian": "sudo apt-get install -y build-essential python3-dev",
    "ubuntu": "sudo apt-get install -y build-essential python3-dev",
    "linuxmint": "sudo apt-get install -y build-essential python3-dev",
    "pop": "sudo apt-get install -y build-essential python3-dev",
    "fedora": "sudo dnf install -y gcc gcc-c++ python3-devel",
    "rhel": "sudo dnf install -y gcc gcc-c++ python3-devel",
    "centos": "sudo dnf install -y gcc gcc-c++ python3-devel",
    "rocky": "sudo dnf install -y gcc gcc-c++ python3-devel",
    "almalinux": "sudo dnf install -y gcc gcc-c++ python3-devel",
    "arch": "sudo pacman -S --needed base-devel",
    "manjaro": "sudo pacman -S --needed base-devel",
    "opensuse": "sudo zypper install -y gcc gcc-c++ python3-devel",
    "opensuse-leap": "sudo zypper install -y gcc gcc-c++ python3-devel",
    "alpine": "sudo apk add build-base python3-dev",
    "gentoo": "sudo emerge --ask sys-devel/gcc",
}


def _distro_ids() -> list[str]:
    """IDs from /etc/os-release (``ID`` plus every ``ID_LIKE`` token).

    Derivatives often miss from a distro -> command table while their
    ``ID_LIKE`` (e.g. ``gentoo``, ``debian``) hits, so both are consulted.
    """
    ids: list[str] = []
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                key, _, value = line.partition("=")
                if key.strip() in ("ID", "ID_LIKE"):
                    ids += [tok.strip().strip('"').lower() for tok in value.split()]
    except OSError:
        pass
    return ids


def _recorded_cc() -> str:
    """The compiler binary a source build will try to exec.

    distutils/setuptools use ``$CC`` when set, otherwise the compiler CPython
    itself was built with (``sysconfig`` ``CC``). On distros such as Gentoo
    that recorded name is a triplet-prefixed binary
    (``x86_64-pc-linux-gnu-gcc``) which can be absent even when a perfectly
    usable ``gcc`` exists - the build then dies with the cryptic
    ``[Errno 2] No such file or directory: 'x86_64-pc-linux-gnu-gcc'``.
    """
    import sysconfig

    cc = os.environ.get("CC") or sysconfig.get_config_var("CC") or "cc"
    return cc.split()[0]


def _find_cc(recorded: str) -> str | None:
    """A usable substitute compiler, or ``None``.

    Only meaningful when ``recorded`` (what distutils would exec) cannot be
    found. Looks on ``PATH`` first, then scans the standard bindirs: ComfyUI is
    often started from a GUI/session/service with a stripped-down ``PATH``,
    and a perfectly good ``/usr/bin/gcc`` then "does not exist" as far as
    ``shutil.which()`` is concerned.
    """
    import shutil
    import sys

    if shutil.which(recorded):
        return None
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return found
    dirs: list[str] = []
    conda = os.environ.get("CONDA_PREFIX")
    if conda:
        dirs.append(os.path.join(conda, "bin"))
    dirs.append(os.path.join(sys.prefix, "bin"))
    dirs += ["/usr/bin", "/bin", "/usr/local/bin", "/usr/sbin", "/sbin", "/opt/homebrew/bin"]
    seen: set[str] = set()
    for directory in dirs:
        if directory in seen:
            continue
        seen.add(directory)
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        # Prefer the plainest name ("cc" < "gcc" < "gcc-13" < "x86_64-...-gcc").
        for name in sorted(entries, key=lambda e: (len(e), e)):
            if _CC_NAME_RE.match(name):
                path = os.path.join(directory, name)
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    return path
    return None


def _cc_env_patch() -> tuple[dict[str, str], str | None]:
    """Environment overrides rescuing a build whose recorded compiler is gone.

    Exporting ``CC`` makes distutils (including the copy vendored into pip's
    build isolation) exec the substitute instead, and splicing ``LDSHARED``
    keeps the link step on the same binary (older distutils do this
    themselves, but not every vendored copy does).
    """
    import sysconfig

    recorded = _recorded_cc()
    alt = _find_cc(recorded)
    if not alt:
        return {}, None
    env = {"CC": alt}
    ldshared = sysconfig.get_config_var("LDSHARED") or ""
    if ldshared.startswith(recorded):
        env["LDSHARED"] = alt + ldshared[len(recorded):]
    note = (
        f"the compiler this Python expects (`{recorded}`) was not found; "
        f"building with CC={alt} instead"
    )
    return env, note


def _python_headers_missing() -> bool:
    """True when Python.h cannot be found for the *base* interpreter."""
    import sys
    import sysconfig

    short = sysconfig.get_config_var("py_version_short") or ""
    candidates = [sysconfig.get_paths().get("include", "")]
    base = getattr(sys, "base_prefix", sys.prefix)
    candidates += [
        os.path.join(base, "include"),
        os.path.join(base, "include", f"python{short}"),
        os.path.join(base, "include", f"python{short}m"),
    ]
    return not any(
        c and os.path.exists(os.path.join(c, "Python.h")) for c in candidates
    )


def _build_prereq_hint() -> str | None:
    """Explain *why* a source build would fail, with the command that fixes it.

    PyPI ships no Linux wheel for ZipNN, so `pip install zipnn` compiles a C
    extension. The overwhelmingly common reasons that fails are a missing
    compiler and missing Python headers (`fatal error: Python.h: No such file
    or directory`) - neither is visible in a bare "exit status 1". A missing
    *recorded* compiler (the triplet-prefixed one from sysconfig) does not
    count when :func:`_find_cc` can substitute a working one via ``$CC``.
    """
    import shutil
    import sys
    import sysconfig

    missing: list[str] = []
    recorded = _recorded_cc()
    if not shutil.which(recorded) and not _find_cc(recorded):
        missing.append(
            f"no C compiler anywhere (the one this Python expects is "
            f"`{recorded}`, and no cc/gcc/clang substitute was found)"
        )
    if _python_headers_missing():
        missing.append(
            f"no Python headers (Python.h not found for {sysconfig.get_paths().get('include')})"
        )
    if not missing:
        return None

    if sys.platform == "darwin":
        fix = "xcode-select --install"
    else:
        fix = ""
        for distro in _distro_ids():
            fix = _PKG_MANAGER_HINTS.get(distro, "")
            if fix:
                break
    if os.environ.get("CONDA_PREFIX"):
        fix = (fix + "  |  conda: ").strip("  |  ") + (
            "conda install -y -c conda-forge cxx-compiler"
        )
    if not fix:
        fix = (
            "install a C compiler (gcc or clang) and the Python development "
            "headers (python3-dev / python3-devel or your distro's equivalent)"
        )
    hint = "Build prerequisites look incomplete: " + "; ".join(missing) + "."
    hint += f" Fix it with: {fix}"
    return hint


def _ensure_pip() -> None:
    """venvs created with `--without-pip` (or broken upgrades) have no pip."""
    import subprocess
    import sys

    probe = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        subprocess.run(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            capture_output=True,
            text=True,
        )


def _run_pip(args: list[str], extra_env: dict[str, str] | None = None) -> str:
    """Run a pip invocation, returning its output or raising with its tail.

    The previous implementation used ``subprocess.run(..., check=True)`` without
    capturing anything, so a failed build surfaced as a bare
    "returned non-zero exit status 1" with no way to tell *why*.

    ``extra_env`` entries for flag-list keys (:data:`_ENV_APPEND_KEYS`) are
    *appended* to whatever the environment already carries; every other key
    (``CC``, ``LDSHARED``, ...) *replaces* it - appending to a broken ``CC``
    would just produce a broken two-word command line.
    """
    import subprocess
    import sys

    env = os.environ.copy()
    for key, value in (extra_env or {}).items():
        if key in _ENV_APPEND_KEYS:
            env[key] = f"{env.get(key, '')} {value}".strip()
        else:
            env[key] = value
    proc = subprocess.run(
        [sys.executable, "-m", "pip", *args],
        capture_output=True,
        text=True,
        env=env,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(
            f"`pip {' '.join(args)}` failed (exit {proc.returncode}):\n"
            + "\n".join(output.strip().splitlines()[-25:])
        )
    return output


def _zipnn_import_error() -> str | None:
    """Why ZipNN cannot be imported, or None when it can.

    ``zipnn_core`` is probed first: ``zipnn/__init__`` imports it at module load,
    so a broken core surfaces as a ``zipnn`` import error and the real cause
    (a glibc/ABI mismatch on a prebuilt binary, a missing compiler for a source
    build) would otherwise be hidden behind ``import zipnn``.
    """
    if zipnn_available():
        return None
    try:
        import zipnn_core  # noqa: F401
    except Exception as e:  # pragma: no cover - depends on the host env
        return f"zipnn_core: {type(e).__name__}: {e}"
    try:
        import zipnn  # noqa: F401
    except Exception as e:  # pragma: no cover - depends on the host env
        return f"zipnn: {type(e).__name__}: {e}"
    return "unknown import failure"


def _third_party_dir() -> str:
    """Absolute path of the vendored-code directory (``third_party/``)."""
    return utils.join_path(config.extension_uri, _THIRD_PARTY_DIR)


def _platform_tag() -> str:
    """The ``zipnn-core-bin/`` subdirectory name for this interpreter.

    e.g. ``linux-x86_64`` / ``macos-arm64`` / ``windows-x86_64``. Python's
    import machinery then picks the ``zipnn_core.cpython-3XX-*.so`` inside it
    that matches the *running* ABI, so one directory serves every Python
    version on that platform.
    """
    system = platform.system().lower()
    if system == "darwin":
        system = "macos"
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        machine = "x86_64"
    elif machine in ("arm64", "aarch64"):
        machine = "arm64"
    return f"{system}-{machine}"


def _prebuilt_core_dir() -> str:
    """Directory holding the prebuilt ``zipnn_core`` for this platform."""
    return utils.join_path(_third_party_dir(), _ZIPNN_CORE_BIN_DIR, _platform_tag())


def _has_loadable_prebuilt(bin_dir: str) -> bool:
    """True when ``bin_dir`` holds a ``zipnn_core`` this interpreter can load.

    Matches against ``importlib.machinery.EXTENSION_SUFFIXES`` (e.g.
    ``.cpython-313-x86_64-linux-gnu.so``), so a directory of cores for *other*
    Python versions correctly counts as "no prebuilt here".
    """
    import importlib.machinery

    if not os.path.isdir(bin_dir):
        return False
    suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
    return any(
        f.startswith("zipnn_core") and f.endswith(suffixes)
        for f in os.listdir(bin_dir)
    )


def _add_sys_path(path: str) -> None:
    import sys

    if path and os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)


def _remove_sys_path(path: str) -> None:
    import sys

    while path in sys.path:
        sys.path.remove(path)


def _clear_zipnn_modules() -> None:
    """Drop cached/half-imported ``zipnn``/``zipnn_core`` and refresh finders.

    A previous attempt may have cached a failed lookup or a partially
    initialised package; clearing both (and invalidating the import caches)
    lets a fresh import see directories just added to ``sys.path`` - or a
    ``zipnn_core`` just built into site-packages.
    """
    import importlib
    import sys

    for name in list(sys.modules):
        if name == "zipnn_core" or name == "zipnn" or name.startswith("zipnn."):
            del sys.modules[name]
    importlib.invalidate_caches()


def _build_core_from_source() -> str | None:
    """One clean build of ``zipnn_core`` from the bundled C sources.

    Returns ``None`` on success or an error string on failure. This is the
    fallback for platforms with no prebuilt binary (macOS / Windows / uncommon
    arches / a brand-new CPython). Unlike the old installer it is a *single*
    command - no cascade of pip strategies and no PyPI download, because the
    sources are vendored in ``third_party/zipnn-core/``. It needs only a C
    compiler and the Python headers; when the compiler CPython recorded in
    ``sysconfig`` is absent but another usable one exists, ``CC`` is pointed at
    the substitute (see :func:`_cc_env_patch`).
    """
    src_dir = utils.join_path(_third_party_dir(), _ZIPNN_CORE_SRC_DIR)
    if not os.path.isdir(src_dir):
        return "the bundled zipnn-core source directory is missing"
    try:
        _ensure_pip()
        hint = _build_prereq_hint()
        if hint:
            utils.print_info(f"  warning: {hint}")
        cc_env, cc_note = _cc_env_patch()
        if cc_note:
            utils.print_info(f"  note: {cc_note}")
        build_env = {"CFLAGS": _ZIPNN_BUILD_CFLAGS, **cc_env}
        utils.print_info(
            "  building: pip install --no-build-isolation --no-deps "
            f"{utils.join_path(_THIRD_PARTY_DIR, _ZIPNN_CORE_SRC_DIR)}"
        )
        _run_pip(["install", "--no-build-isolation", "--no-deps", src_dir], build_env)
        return None
    except Exception as e:
        return str(e)


def _compose_failure_message(
    had_prebuilt: bool, prebuilt_error: str | None, build_error: str | None
) -> str:
    """A single, honest, actionable message when neither path produced a core."""
    lines = [
        "ZipNN could not be made available on this machine.",
        "",
        f"Platform: {_platform_tag()} (Python {platform.python_version()}).",
    ]
    if had_prebuilt:
        lines.append(
            "A prebuilt zipnn_core ships for this platform but could not be "
            f"loaded (usually a glibc/ABI mismatch): {prebuilt_error}"
        )
    else:
        lines.append(
            "No prebuilt zipnn_core ships for this platform, so it was built "
            "from the bundled C source - which needs a C compiler and the "
            "Python headers (Python.h)."
        )
    hint = _build_prereq_hint()
    if hint:
        lines.append(hint)
    if build_error:
        lines += ["", "Source build output:", build_error]
    lines += [
        "",
        "Fix the toolchain (or run on a platform that has a prebuilt core), "
        "then use the toast's retry action.",
    ]
    return "\n".join(lines)


def ensure_zipnn(force: bool = False) -> None:
    """Make the vendored ZipNN importable. Two ordered paths, no pip cascade.

    1. **Prebuilt (primary).** Put ``third_party/`` and this platform's
       ``third_party/zipnn-core-bin/<tag>/`` on ``sys.path``. On the common
       platforms the matching ``zipnn_core.cpython-3XX-*.so`` already ships, so
       ZipNN imports immediately - **no compiler, no pip, no network**. This is
       the path a normal Linux/macOS ComfyUI install takes.
    2. **Source build (fallback).** Only when no prebuilt core matches this
       platform/Python (macOS, Windows, an uncommon arch, or a brand-new CPython)
       is ``zipnn_core`` compiled from the bundled C sources with a single
       ``pip install --no-build-isolation --no-deps``.

    A prebuilt core that exists but cannot be loaded is taken off ``sys.path``
    before the build so it never shadows the freshly built one. Failures are
    cached for :data:`_ZIPNN_INSTALL_TTL` seconds so hammering the button does
    not re-run a doomed build (``force=True``, used by the UI retry, bypasses
    the cache).
    """
    global _zipnn_install_failed
    import time

    if zipnn_available():
        _zipnn_install_failed = None
        return
    if _zipnn_install_failed and not force:
        message, at = _zipnn_install_failed
        if time.time() - at < _ZIPNN_INSTALL_TTL:
            raise ZipNNInstallError(message)
        _zipnn_install_failed = None

    # 1. Prebuilt core: vendored package + the platform's binary directory.
    _add_sys_path(_third_party_dir())
    bin_dir = _prebuilt_core_dir()
    had_prebuilt = _has_loadable_prebuilt(bin_dir)
    prebuilt_error: str | None = None
    if had_prebuilt:
        _add_sys_path(bin_dir)
        _clear_zipnn_modules()
        if zipnn_available():
            _zipnn_install_failed = None
            utils.print_info("ZipNN ready (bundled package + prebuilt core).")
            return
        # It ships but will not load (e.g. glibc too old): remember why, then
        # get it off sys.path so the source build below is not shadowed by it.
        prebuilt_error = _zipnn_import_error()
        _remove_sys_path(bin_dir)
        _clear_zipnn_modules()

    # 2. Single clean source build (platforms without a usable prebuilt core).
    utils.print_info(
        "No usable prebuilt zipnn_core for this platform; building from the "
        "bundled source (needs a C compiler + Python headers)..."
    )
    build_error = _build_core_from_source()
    _clear_zipnn_modules()
    if zipnn_available():
        _zipnn_install_failed = None
        utils.print_info("ZipNN ready (built core from the bundled source).")
        return

    message = _compose_failure_message(had_prebuilt, prebuilt_error, build_error)
    _zipnn_install_failed = (message, time.time())
    utils.print_error(message)
    raise ZipNNInstallError(message)



def _sidecar_move(old_model: str, new_model: str) -> None:
    """Move previews + notes from one model file to another (same directory)."""
    directory = os.path.dirname(old_model)
    names = utils.get_dir_names(directory)
    old_base = os.path.splitext(os.path.basename(old_model))[0]
    new_base = os.path.splitext(os.path.basename(new_model))[0]
    for preview in utils.previews_in_names(names, old_base):
        ext = preview[len(old_base):]
        src = utils.join_path(directory, preview)
        dst = utils.join_path(directory, f"{new_base}{ext}")
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)
    for desc in utils.get_model_all_descriptions(old_model):
        src = utils.join_path(directory, desc)
        dst = utils.join_path(directory, f"{new_base}{os.path.splitext(desc)[1]}")
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)


def compress_safetensors(src: str, dst: str, progress: ProgressCb) -> dict[str, Any]:
    """Compress `src` (.safetensors) into `dst` (.znn.safetensors)."""
    from safetensors import safe_open
    from safetensors.torch import save_file
    from zipnn import ZipNN
    from zipnn.util_header import EnumFormat
    from zipnn.util_safetensors import (
        COMPRESSION_METHOD,
        COMPRESSED_DTYPE,
        build_compressed_tensor_info,
        set_compressed_tensors_metadata,
    )
    from zipnn.util_torch import zipnn_is_floating_point

    import torch

    tensors: dict[str, Any] = {}
    infos: dict[str, Any] = {}
    original_bytes = 0
    compressed_bytes = 0

    with safe_open(src, "pt", "cpu") as f:
        keys = list(f.keys())
        total = max(1, len(keys))
        for index, name in enumerate(keys):
            tensor = f.get_tensor(name)
            if not zipnn_is_floating_point(EnumFormat.TORCH.value, tensor, tensor.dtype):
                tensors[name] = tensor
                size = tensor.element_size() * tensor.nelement()
                original_bytes += size
                compressed_bytes += size
                progress(index + 1, total, "tensors")
                continue
            znn = ZipNN(
                input_format="torch",
                bytearray_dtype=tensor.dtype,
                method=COMPRESSION_METHOD,
            )
            uncompressed_size = tensor.element_size() * tensor.nelement()
            original_bytes += uncompressed_size
            # `ZipNN.compress()` reorders the float bits of its input IN PLACE
            # for f32/bf16 (the C core's `reorder_all_floats`), so compress a
            # throwaway clone and keep `tensor` pristine: when the compressed
            # form is not smaller we must store the ORIGINAL bytes, not the
            # bit-reordered ones.
            compressed_buf = znn.compress(tensor.clone())
            if len(compressed_buf) >= uncompressed_size:
                # Not worth it: keep the tensor as-is AND - exactly like the
                # official script - do NOT record it in `infos`. A tensor that
                # is listed in `znn_compressed_vectors` but stored in its
                # original (e.g. bfloat16) dtype cannot be Huffman-decoded, so
                # the decompressor must copy it through untouched instead.
                tensors[name] = tensor
                compressed_bytes += uncompressed_size
            else:
                # `znn.compress()` returns a read-only buffer; `torch.frombuffer`
                # on it emits a scary "The given buffer is not writable"
                # UserWarning into the ComfyUI console. The one-time copy into a
                # writable `bytearray` silences it and is cheap next to the
                # compression itself.
                tensors[name] = torch.frombuffer(
                    bytearray(compressed_buf), dtype=COMPRESSED_DTYPE
                )
                infos[name] = build_compressed_tensor_info(tensor)
                compressed_bytes += len(compressed_buf)
            progress(index + 1, total, "tensors")
        metadata = f.metadata()

    if metadata is None:
        metadata = {}
    # Neo extension: record the pre-compression on-disk size so the UI can
    # show the original / compressed / ratio breakdown for this file later
    # (the source file itself is gone by then).
    metadata[ZNN_ORIGINAL_SIZE_KEY] = str(os.path.getsize(src))
    # BUG FIX: `set_compressed_tensors_metadata` only writes into a *truthy*
    # dict, so a source file with no metadata (`f.metadata()` is None) used to
    # silently drop the `znn_compressed_vectors` record - and decompression
    # would then copy the Huffman-coded uint8 vectors through untouched,
    # corrupting the model. The dict ensured above guarantees the record
    # always survives. (Format-compatible with the official helper.)
    set_compressed_tensors_metadata(infos, metadata)
    tmp_dst = f"{dst}.tmp"
    save_file(tensors, tmp_dst, metadata)
    os.replace(tmp_dst, dst)
    return {
        "originalBytes": original_bytes,
        "compressedBytes": compressed_bytes,
        "tensors": len(keys),
        "compressedTensors": len(infos),
    }


def decompress_safetensors(src: str, dst: str, progress: ProgressCb) -> dict[str, Any]:
    """Decompress `src` (.znn.safetensors) into `dst` (.safetensors)."""
    from safetensors import safe_open
    from safetensors.torch import save_file
    from zipnn import ZipNN
    from zipnn.util_safetensors import (
        COMPRESSION_METHOD,
        COMPRESSED_DTYPE,
        METADATA_KEY,
        get_compressed_tensors_metadata,
    )

    tensors: dict[str, Any] = {}
    with safe_open(src, "pt", "cpu") as f:
        metadata = f.metadata()
        compressed_infos = get_compressed_tensors_metadata(metadata or {})
        znn = ZipNN(
            input_format="torch",
            bytearray_dtype=COMPRESSED_DTYPE,
            method=COMPRESSION_METHOD,
        )
        keys = list(f.keys())
        total = max(1, len(keys))
        for index, name in enumerate(keys):
            tensor = f.get_tensor(name)
            if name not in compressed_infos:
                tensors[name] = tensor
            else:
                tensors[name] = znn.decompress(tensor.contiguous().numpy())
            progress(index + 1, total, "tensors")
        if metadata:
            # Strip both ZipNN records so the restored file carries exactly the
            # metadata the original had (including the Neo-only size key).
            metadata.pop(METADATA_KEY, None)
            metadata.pop(ZNN_ORIGINAL_SIZE_KEY, None)

    tmp_dst = f"{dst}.tmp"
    save_file(tensors, tmp_dst, metadata)
    os.replace(tmp_dst, dst)
    return {"tensors": len(keys), "decompressedTensors": len(compressed_infos)}


class ZipNNRoutes:
    def add_routes(self, routes):
        @routes.get("/model-manager/zipnn/available")
        async def zipnn_status(request):
            return web.json_response(
                {"success": True, "data": {"available": zipnn_available()}}
            )

        @routes.post("/model-manager/zipnn/compress")
        async def zipnn_compress(request):
            return await self._run(request, "compress")

        @routes.post("/model-manager/zipnn/decompress")
        async def zipnn_decompress(request):
            return await self._run(request, "decompress")

    async def _run(self, request, mode: str):
        data = await utils.get_request_body(request)
        model_type = data.get("type")
        path_index = int(data.get("pathIndex") or 0)
        fullname = data.get("fullname")
        if not model_type or not fullname:
            return web.json_response(
                {"success": False, "error": "type and fullname are required"}
            )
        if not is_safetensors(fullname):
            return web.json_response(
                {
                    "success": False,
                    "error": "ZipNN compression supports .safetensors files only",
                }
            )
        try:
            src = utils.get_valid_full_path(model_type, path_index, fullname)
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)})
        if src is None:
            return web.json_response({"success": False, "error": "model not found"})

        if mode == "compress":
            if is_compressed_name(fullname):
                return web.json_response(
                    {"success": False, "error": "model is already compressed"}
                )
            base = src[: -len(SAFE_SUFFIX)]
            dst = f"{base}{ZNN_SUFFIX}"
        else:
            if not is_compressed_name(fullname):
                return web.json_response(
                    {"success": False, "error": "model is not ZipNN compressed"}
                )
            base = src[: -len(ZNN_SUFFIX)]
            dst = f"{base}{SAFE_SUFFIX}"
        if os.path.exists(dst):
            return web.json_response(
                {"success": False, "error": f"target already exists: {os.path.basename(dst)}"}
            )

        force = bool(data.get("force"))
        task_id = uuid.uuid4().hex
        ZIPNN_TASKS[task_id] = {"mode": mode, "status": "running", "src": src, "dst": dst}
        await utils.send_json(
            "update_zipnn_progress",
            {"taskId": task_id, "progress": 0.0, "phase": "prepare", "mode": mode},
        )

        loop = asyncio.get_running_loop()

        async def worker():
            try:
                await loop.run_in_executor(utils.cpu_executor(), ensure_zipnn, force)
            except Exception as e:
                await self._fail(
                    task_id,
                    src,
                    str(e),
                    install_failed=isinstance(e, ZipNNInstallError),
                )
                return

            def progress(done: int, total: int, phase: str):
                asyncio.run_coroutine_threadsafe(
                    utils.send_json(
                        "update_zipnn_progress",
                        {
                            "taskId": task_id,
                            "progress": (done / total * 100) if total else 0.0,
                            "phase": phase,
                            "mode": mode,
                        },
                    ),
                    loop,
                )

            fn = compress_safetensors if mode == "compress" else decompress_safetensors
            try:
                stats = await loop.run_in_executor(
                    utils.cpu_executor(), fn, src, dst, progress
                )
            except Exception as e:
                # never leave a half-written target behind
                for candidate in (dst, f"{dst}.tmp"):
                    if os.path.exists(candidate):
                        try:
                            os.remove(candidate)
                        except OSError:
                            pass
                await self._fail(task_id, src, str(e))
                return

            # The model entry moves to the new file: previews and notes follow.
            try:
                _sidecar_move(src, dst)
                os.remove(src)
            except Exception as e:
                await self._fail(task_id, src, str(e))
                return

            ZIPNN_TASKS[task_id]["status"] = "complete"
            await utils.send_json(
                "update_zipnn_progress",
                {"taskId": task_id, "progress": 100.0, "phase": "done", "mode": mode},
            )
            await utils.send_json(
                "zipnn_complete",
                {
                    "taskId": task_id,
                    "mode": mode,
                    "ok": True,
                    "stats": stats,
                    "fullname": os.path.basename(dst),
                },
            )

        loop.create_task(self._schedule(worker()))
        return web.json_response({"success": True, "data": {"taskId": task_id}})

    async def _schedule(self, coro):
        try:
            await coro
        except Exception as e:  # pragma: no cover - defensive
            utils.print_error(f"zipnn worker crashed: {e}")

    async def _fail(
        self, task_id: str, src: str, error: str, install_failed: bool = False
    ):
        ZIPNN_TASKS[task_id]["status"] = "error"
        utils.print_error(f"zipnn failed for {src}: {error}")
        await utils.send_json(
            "zipnn_complete",
            {
                "taskId": task_id,
                "ok": False,
                "error": error,
                # The UI turns this into a "retry install" action, because the
                # backend caches a failed install for a few minutes.
                "installFailed": install_failed,
            },
        )
