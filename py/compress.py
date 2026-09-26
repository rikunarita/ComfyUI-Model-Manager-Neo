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
import json
import os
import platform
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from aiohttp import web

from . import config, native, utils

ZNN_SUFFIX = ".znn.safetensors"
SAFE_SUFFIX = ".safetensors"

# Neo extension to the official ZipNN metadata layout: the pre-compression
# on-disk size of the source file, recorded at compress time so the UI can
# show the original size / compressed size / ratio breakdown for a compressed
# model (the original file itself is gone by then). Other ZipNN tools ignore
# unknown metadata keys, and decompression removes it again, so the restored
# file carries exactly the metadata the original had.
ZNN_ORIGINAL_SIZE_KEY = "znn_neo_original_bytes"

# Phase 2 (native pipeline) integrity records — written by the Rust core
# (Plan §4.4.3), and stripped by BOTH decompressors so a restored file never
# leaks Neo bookkeeping:
#   znn_neo_src_sha256        SHA-256 of the whole source file (verified on
#                             restore — default ON; mismatch on a byte-exact
#                             capable file keeps the compressed source and
#                             retreats the restore to `.corrupt`)
#   znn_neo_exact             "1" when the source header was canonical, i.e.
#                             the restore is byte-exact and the sha is
#                             ENFORCED; "0" downgrades to the structural
#                             guarantee (Plan §4.7.4)
#   znn_neo_src_meta_absent   "1" when the source had no __metadata__ at all
#   znn_neo_extended          "1" when Neo-extension dtypes are present
#                             (Phase 4 — stripped here already so future
#                             files round-trip through both paths)
ZNN_SRC_SHA_KEY = "znn_neo_src_sha256"
ZNN_EXACT_KEY = "znn_neo_exact"
ZNN_SRC_META_ABSENT_KEY = "znn_neo_src_meta_absent"
ZNN_EXTENDED_KEY = "znn_neo_extended"

# Every Neo/ZipNN metadata key the RESTORE must strip (both paths).
ZNN_NEO_METADATA_KEYS = (
    ZNN_ORIGINAL_SIZE_KEY,
    ZNN_SRC_SHA_KEY,
    ZNN_EXACT_KEY,
    ZNN_SRC_META_ABSENT_KEY,
    ZNN_EXTENDED_KEY,
)

# task_id -> bookkeeping, same shape as the HF upload tasks
ZIPNN_TASKS: dict[str, dict] = {}

# Strong references to the in-flight background workers. asyncio keeps only
# WEAK references to tasks, so a `create_task` result nobody stores can be
# garbage-collected mid-run - a multi-gigabyte compression could silently
# vanish. Each task discards itself from the set when it finishes.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn_background(loop: asyncio.AbstractEventLoop, coro) -> None:
    task = loop.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


ProgressCb = Callable[[int, int, str], None]

# ---------------------------------------------------------------------------
# Native (Rust `mm_core`) job path — the Phase 2 switchover (Plan §4.2.3).
#
# The Rust core runs the whole pipeline (mmap → per-tensor codec → integrity
# sha → atomic rename) on its own thread; this side only POLLS the atomic
# progress at 10 Hz (Plan §4.3 — no GIL-reacquiring callbacks) and keeps the
# ws event / stats contract byte-identical to the legacy path.
# ---------------------------------------------------------------------------

# Native phases → the legacy ws `phase` vocabulary the UI understands
# (`prepare`/`tensors`/`done`); `write`/`verify` are short assembly steps
# that read as "tensors" to the frontend, `failed` never surfaces as a phase
# (it becomes a `zipnn_complete` error).
_WS_PHASE_FOR_NATIVE = {
    "prepare": "prepare",
    "tensors": "tensors",
    "write": "tensors",
    "verify": "tensors",
    "delta": "delta",
    "done": "done",
    "failed": "tensors",
}

# Delta routes report their whole in-flight vocabulary as the legacy
# "delta" phase (the legacy delta worker only ever sent prepare/delta/done).
_WS_PHASE_FOR_DELTA = {
    "prepare": "delta",
    "tensors": "delta",
    "write": "delta",
    "verify": "delta",
    "delta": "delta",
    "done": "done",
    "failed": "delta",
}

# 10 Hz polling (Plan §4.3: "AtomicU64 を Python 側 10 Hz ポーリング").
_NATIVE_POLL_INTERVAL = 0.1


def native_core():
    """The loaded ``mm_core`` when the native path should run, else None.

    Honours ``MM_NATIVE`` (Plan §5.4): ``0`` forces the legacy path, ``1``
    REQUIRES the native core (``native.load()`` raises when unavailable — an
    installation that demands the Rust core must never silently fall back to
    the C one), ``auto`` (default) uses the native core when the prebuilt
    binary loads and passes the API handshake.
    """
    if native.native_mode() == "0":
        return None
    if native.load():
        return native.core()
    return None


def paranoid_enabled(request=None) -> bool:
    """Compress-then-immediately-decompress-and-verify (Plan §4.4.3-4).

    Default OFF. Switches, in precedence order: the ``MM_ZNN_PARANOID``
    environment variable (QA/automation), then the persisted user setting
    ``ModelManager.ZipNN.Paranoid`` (a frontend toggle can be added without
    backend changes; until then the default applies).
    """
    env = os.environ.get("MM_ZNN_PARANOID", "").strip().lower()
    if env in ("1", "on", "true", "yes"):
        return True
    if env in ("0", "off", "false", "no"):
        return False
    if request is not None:
        return bool(utils.get_setting_value(request, "zipnn.paranoid", False))
    return False


def _cleanup_targets(dst: str) -> None:
    """Remove every PARTIAL-output name a failed run can leave.

    Deliberately does NOT delete ``dst`` itself: both pipelines create the
    destination only through a final atomic rename (native: commit after
    verification; legacy: ``os.replace`` after ``save_file``), so on any
    failure path ``dst`` either never existed — or was created by somebody
    else between the route's existence check and the failure (a rare but
    real data-loss race the earlier dst-deleting cleanup had).
    NEVER touches `.corrupt` files either — those are deliberate diagnostics
    of a failed verification (Plan §4.4.3) whose compressed source was kept.
    """
    for candidate in (f"{dst}.tmp", f"{dst}.verify.tmp", f"{dst}.tmp.fix"):
        try:
            if os.path.exists(candidate):
                os.remove(candidate)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Startup cleanup of crash/kill leftovers (Plan §4.4.4)
# ---------------------------------------------------------------------------

# Only delete `.tmp` leftovers OLDER than this: both pipelines commit via
# rename and a live run's `.tmp` is continuously written, so a 15-minute-old
# partial in a model folder is dead by definition — while a foreign tool's
# in-flight `*.safetensors.tmp` download (they exist) is never touched.
_STRAY_TMP_MIN_AGE_S = 900.0


def _cleanup_delta_failure(dst: str, mode: str, native: bool) -> None:
    """Delta-route failure cleanup.

    Partials: legacy writes `<dst>.tmp` itself, so the legacy path sweeps
    it (``_cleanup_targets``); the NATIVE path must NOT (the Rust Drop
    guard owns its partials and a blind sweep could destroy a concurrent
    job's tmp — the Phase-2 lesson).

    Committed-delta exception (compress only): when the job died AFTER the
    delta file was renamed into place but BEFORE its sidecar landed (an
    ENOSPC on the tiny JSON), the artifact would be unrestorable whenever
    padding was involved — remove it to keep the "a failed run leaves no
    artifact" invariant. ``dst`` can only be ours here: the route checked
    its absence when the task was created, and delta names live inside the
    base model's own ``*_DeltaZNN`` folder.
    """
    if not native:
        _cleanup_targets(dst)
    if mode == "compress" and os.path.exists(dst) and not os.path.exists(_delta_meta_path(dst)):
        try:
            os.remove(dst)
        except OSError:
            pass


def _is_stray_tmp_name(name: str) -> bool:
    """A ZipNN pipeline partial: `<model>.tmp` / `<delta>.znn.tmp` / the
    native pipeline's `.verify.tmp` / `.tmp.fix` siblings."""
    if not name.endswith((".tmp", ".tmp.fix")):
        return False
    return SAFE_SUFFIX in name or ".znn" in name


def _is_corrupt_name(name: str) -> bool:
    """A failed-verification restore diagnostic (`<model>.corrupt`)."""
    return name.endswith(".corrupt") and (SAFE_SUFFIX in name or ".znn" in name)


def cleanup_stray_files() -> dict[str, Any]:
    """Sweep dead `.tmp` partials from the model roots; list `.corrupt` files.

    Runs in the background at extension start-up (see `__init__.py`) so a
    slow/network library never delays the boot. `.tmp` files are removed
    (they are uncommitted partials of a crashed or killed run — a committed
    model never ends in `.tmp`); `.corrupt` files are only REPORTED: they are
    deliberate diagnostics whose compressed source was kept intact, so
    deleting them automatically could destroy the only copy of a failed
    restore (Plan §4.4.3 — manual QA item "強制終了復旧").
    """
    removed: list[str] = []
    corrupt: list[str] = []
    errors: list[str] = []
    now = time.time()
    roots: set[str] = set()
    try:
        for paths in utils.resolve_model_base_paths().values():
            roots.update(paths)
    except Exception as e:  # a broken folder_paths must not kill the sweep
        return {"removed": removed, "corrupt": corrupt, "errors": [str(e)]}
    for root in sorted(roots):
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                # utils.join_path keeps the slash-normalized form the rest of
                # the backend reports (model roots arrive normalized — raw
                # os.path.join would mix separators on Windows)
                full = utils.join_path(dirpath, name)
                try:
                    if _is_stray_tmp_name(name):
                        if now - os.path.getmtime(full) >= _STRAY_TMP_MIN_AGE_S:
                            os.remove(full)
                            removed.append(full)
                    elif _is_corrupt_name(name):
                        corrupt.append(full)
                except OSError as e:
                    errors.append(f"{full}: {e}")
    if removed:
        shown = ", ".join(os.path.basename(p) for p in removed[:5])
        utils.print_warning(f"startup cleanup: removed {len(removed)} stale ZipNN .tmp file(s): {shown}")
    if corrupt:
        shown = ", ".join(os.path.basename(p) for p in corrupt[:5])
        utils.print_warning(
            f"found {len(corrupt)} .corrupt diagnostic file(s) from failed ZipNN restores "
            f"(the compressed models were kept; inspect and remove manually): {shown}"
        )
    return {"removed": removed, "corrupt": corrupt, "errors": errors}


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
        return importlib.util.find_spec("zipnn") is not None and importlib.util.find_spec("zipnn_core") is not None
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
_CC_NAME_RE = re.compile(r"^(?:cc|clang(?:-\d+)?|gcc(?:-\d+(?:\.\d+)*)?|(?:[A-Za-z0-9_.]+-)+gcc(?:-\d+)?)$")

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
        env["LDSHARED"] = alt + ldshared[len(recorded) :]
    note = f"the compiler this Python expects (`{recorded}`) was not found; building with CC={alt} instead"
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
    return not any(c and os.path.exists(os.path.join(c, "Python.h")) for c in candidates)


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
        missing.append(f"no Python headers (Python.h not found for {sysconfig.get_paths().get('include')})")
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
        conda_cmd = "conda install -y -c conda-forge cxx-compiler"
        fix = f"{fix}  |  conda: {conda_cmd}" if fix else f"conda: {conda_cmd}"
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
            f"`pip {' '.join(args)}` failed (exit {proc.returncode}):\n" + "\n".join(output.strip().splitlines()[-25:])
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

    Matches the exact file names the import machinery binds to
    ``import zipnn_core``: ``zipnn_core`` + one of this interpreter's
    ``EXTENSION_SUFFIXES`` (e.g. ``.cpython-315-x86_64-linux-gnu.so``,
    ``.abi3.so``, ``.pyd`` on Windows). A directory of cores for *other*
    Python versions correctly counts as "no prebuilt here" - those files end
    in ``.so`` too, but FileFinder only binds whole ``zipnn_core<suffix>``
    names, so a loose ``endswith`` test used to promise a core this
    interpreter could never import.
    """
    import importlib.machinery

    if not os.path.isdir(bin_dir):
        return False
    names = set(os.listdir(bin_dir))
    return any(f"zipnn_core{suffix}" in names for suffix in importlib.machinery.EXTENSION_SUFFIXES)


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


def _compose_failure_message(had_prebuilt: bool, prebuilt_error: str | None, build_error: str | None) -> str:
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
        "Fix the toolchain (or run on a platform that has a prebuilt core), then use the toast's retry action.",
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
        ext = preview[len(old_base) :]
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
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file
    from zipnn import ZipNN
    from zipnn.util_header import EnumFormat
    from zipnn.util_safetensors import (
        COMPRESSED_DTYPE,
        COMPRESSION_METHOD,
        build_compressed_tensor_info,
        set_compressed_tensors_metadata,
    )
    from zipnn.util_torch import zipnn_is_floating_point

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
                tensors[name] = torch.frombuffer(bytearray(compressed_buf), dtype=COMPRESSED_DTYPE)
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
        COMPRESSED_DTYPE,
        COMPRESSION_METHOD,
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
        # The native pipeline records that the ORIGINAL file carried no
        # __metadata__ at all — honour it so a legacy decompression of a
        # native-compressed file restores byte-identically (without the
        # record, an empty dict would be written back as `"__metadata__":{}`).
        meta_absent = bool(metadata) and metadata.get(ZNN_SRC_META_ABSENT_KEY) == "1"
        if metadata:
            # Strip the ZipNN infos record and EVERY Neo bookkeeping key so
            # the restored file carries exactly the metadata the original had
            # (including files compressed by the native path).
            metadata.pop(METADATA_KEY, None)
            for key in ZNN_NEO_METADATA_KEYS:
                metadata.pop(key, None)
        if meta_absent and not metadata:
            metadata = None

    tmp_dst = f"{dst}.tmp"
    save_file(tensors, tmp_dst, metadata)
    os.replace(tmp_dst, dst)
    return {"tensors": len(keys), "decompressedTensors": len(compressed_infos)}


# ---------------------------------------------------------------------------
# Folder batch processing (official `scripts/zipnn_compress_path.py` semantics:
# every compressible file in the folder tree, in place) and file-level delta
# compression (official `scripts/zipnn_compress_file_delta.py` /
# `zipnn_decompress_file_delta.py` semantics).
# ---------------------------------------------------------------------------


def _is_bundle_dir_name(name: str) -> bool:
    """True for ZipNN bundle folders (`*_DeltaZNN`, legacy `*_ZNN`)."""
    return utils.is_bundle_folder_name(name)


def _walk_model_files(folder: str, mode: str, skip_bundles: bool = False) -> list[str]:
    """Files a batch run will process, in a stable order.

    ``compress``: every plain ``.safetensors`` (already-``.znn.`` files are
    skipped). ``decompress``: every ``.znn.safetensors``.

    ``skip_bundles`` prunes bundle sub-trees (`*_ZNN` / `*_DeltaZNN`) from the
    walk: their content is already ZipNN-compressed (`.znn` delta files would
    otherwise trip the "folder holds models ZipNN cannot convert" guard of a
    type-root compress).
    """
    found: list[str] = []
    for root, dirs, names in os.walk(folder):
        if skip_bundles:
            dirs[:] = [d for d in dirs if not _is_bundle_dir_name(d)]
        for name in names:
            if mode == "compress":
                if name.endswith(SAFE_SUFFIX) and not name.endswith(ZNN_SUFFIX):
                    found.append(os.path.join(root, name))
            elif name.endswith(ZNN_SUFFIX):
                found.append(os.path.join(root, name))
    return sorted(found)


def _walk_decompress_files(folder: str) -> list[str]:
    """Everything a batch decompress restores, in a stable order.

    * `*.znn.safetensors` anywhere under `folder` (bundle folders AND legacy
      in-place compressed type roots);
    * `*_delta_*.znn` delta files inside `*_DeltaZNN` folders (their padding
      sidecar `*.neo-delta.json` travels implicitly and is removed with the
      delta file).
    """
    found: list[str] = []
    for root, _dirs, names in os.walk(folder):
        in_delta_folder = os.path.basename(root).endswith(utils.DELTA_FOLDER_SUFFIX)
        for name in names:
            if name.endswith(ZNN_SUFFIX) or (in_delta_folder and name.endswith(".znn") and "_delta_" in name):
                found.append(os.path.join(root, name))
    return sorted(found)


def _batch_invariants_blockers(folder: str) -> list[str]:
    """Model files that would break the bundle content rule after a batch.

    A bundle folder may only hold ZipNN content (plus sidecars). Plain
    `.safetensors` become `.znn.safetensors` during the batch, so the blockers
    are the *other* supported model extensions (`.gguf`, `.ckpt`, delta
    `.znn`, ...) that the batch cannot convert. Bundle sub-trees are skipped:
    their `.znn` content already satisfies the rule.
    """
    import folder_paths

    blockers: list[str] = []
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if not _is_bundle_dir_name(d)]
        for name in names:
            extension = os.path.splitext(name)[1]
            if (
                extension in folder_paths.supported_pt_extensions
                and ".znn." not in name
                and not name.endswith(SAFE_SUFFIX)
                and not name.endswith(".znn")
            ):
                blockers.append(os.path.join(root, name))
    return sorted(blockers)


def _bundle_dst_root(folder: str, is_type_root: bool) -> str:
    """`<parent>/<name>_DeltaZNN` - where a batch compress moves its output.

    Model-type roots get the bundle *inside* themselves
    (`T/<T-name>_DeltaZNN`): a sibling of a type root would live outside every
    ComfyUI-mapped path and disappear from both the loader and the manager.
    """
    folder = folder.rstrip(os.sep) or folder
    parent = folder if is_type_root else os.path.dirname(folder)
    name = os.path.basename(folder)
    return utils.join_path(parent, f"{name}{utils.DELTA_FOLDER_SUFFIX}")


def _plain_name(name: str) -> str:
    """`x.znn.safetensors` -> `x.safetensors`."""
    return name[: -len(ZNN_SUFFIX)] + SAFE_SUFFIX


def _locate_bundle(path: str, walk_root: str) -> tuple[str, list[str]] | None:
    """Nearest bundle-named ancestor dir of `path` under `walk_root`.

    Returns (bundle_dir, dir parts between the bundle and the file), or None
    when the file does not live inside a bundle sub-tree.
    """
    rel = os.path.relpath(path, walk_root)
    parts = rel.split(os.sep)
    dir_parts = parts[:-1]
    for index in range(len(dir_parts) - 1, -1, -1):
        if _is_bundle_dir_name(dir_parts[index]):
            bundle = os.path.join(walk_root, *dir_parts[: index + 1])
            return bundle, dir_parts[index + 1 :]
    return None


def _batch_restore_root(bundle: str) -> str:
    """The folder a batch bundle empties back into.

    * sibling bundle `P/X_DeltaZNN` (or legacy `P/X_ZNN`): back into `P/X`;
    * inner bundle `T/T_DeltaZNN` (a model-type root keeps its bundle inside
      itself): back into `T` - recognised by the parent dir carrying exactly
      the name the bundle was derived from.
    """
    bundle = bundle.rstrip(os.sep)
    parent = os.path.dirname(bundle)
    source = os.path.basename(bundle)
    for suffix in (utils.DELTA_FOLDER_SUFFIX, utils.ZNN_FOLDER_SUFFIX):
        if source.endswith(suffix):
            source = source[: -len(suffix)]
            break
    if os.path.basename(parent.rstrip(os.sep)) == source:
        return parent
    return utils.join_path(parent, source)


def _decompress_target(path: str, walk_root: str, out_name: str, is_delta: bool) -> str:
    """Where a decompressed file lands.

    * batch content (`*.znn.safetensors`) inside a bundle sub-tree `B`: back
      into the folder `B` was named after (`_batch_restore_root`), keeping the
      path relative to the bundle;
    * delta content (`*_delta_*.znn` inside `B=<base>_DeltaZNN`): beside the
      base model, i.e. `parent(B)` - the fine-tune lived next to its base;
    * the walked root itself is a bundle: same rules one level up;
    * anywhere else (legacy in-place compressed type root): in place.
    """
    located = _locate_bundle(path, walk_root)
    rel = os.path.relpath(path, walk_root)
    dir_parts = rel.split(os.sep)[:-1]
    if located is not None:
        bundle, inner = located
        root = os.path.dirname(bundle.rstrip(os.sep)) if is_delta else _batch_restore_root(bundle)
        return os.path.join(root, *inner, out_name)
    if _is_bundle_dir_name(os.path.basename(walk_root.rstrip(os.sep))):
        root = os.path.dirname(walk_root.rstrip(os.sep)) if is_delta else _batch_restore_root(walk_root)
        return os.path.join(root, *dir_parts, out_name)
    return os.path.join(os.path.dirname(path), out_name)


def _compress_target(path: str, walk_root: str, bundle_root: str) -> str:
    """Mirror of `_decompress_target`: the file's place inside the bundle."""
    rel = os.path.relpath(path, walk_root)
    return os.path.join(bundle_root, rel[: -len(SAFE_SUFFIX)] + ZNN_SUFFIX)


def _prune_empty_dirs(folder: str, remove_root: bool) -> None:
    """Delete directories the batch emptied, bottom-up (best effort)."""
    for root, dirs, _names in os.walk(folder, topdown=False):
        for name in dirs:
            path = os.path.join(root, name)
            try:
                if not os.listdir(path):
                    os.rmdir(path)
            except OSError:
                pass
    if remove_root:
        try:
            if not os.listdir(folder):
                os.rmdir(folder)
        except OSError:
            pass


def _run_native_job_sync(mm: Any, task_id: str | None, submit: Callable[..., Any], label: str) -> dict[str, Any]:
    """Submit one native job and block-poll it (batch/executor side).

    The batch flow runs inside ``cpu_executor`` (a sync context), so it
    polls the same 10 Hz contract the async routes use (``time.sleep``
    releases the GIL — the ComfyUI loop keeps breathing). Registering the
    handle in ``ZIPNN_TASKS`` makes the running file cancellable through
    ``POST /model-manager/zipnn/cancel`` (a cancelled job fails with
    "cancelled by user" like any other failure, failing the batch).

    Returns the job's stats dict; raises RuntimeError with the job error.
    """
    handle = submit()
    if task_id is not None and task_id in ZIPNN_TASKS:
        ZIPNN_TASKS[task_id]["handle"] = handle
    try:
        while True:
            time.sleep(_NATIVE_POLL_INTERVAL)
            _done, _total, phase = mm.job_progress(handle)
            if phase == "failed":
                err = None
                try:
                    err = mm.job_error(handle)
                except Exception:
                    err = None
                raise RuntimeError(err or "native job failed")
            if phase == "done":
                break
        result = json.loads(mm.job_result(handle))
    finally:
        if task_id is not None and task_id in ZIPNN_TASKS:
            ZIPNN_TASKS[task_id].pop("handle", None)
    for warning in result.get("warnings") or []:
        utils.print_warning(f"zipnn[{label}]: {warning}")
    stats = result.get("stats")
    if not isinstance(stats, dict):
        raise RuntimeError("native job returned no stats")
    return stats


def _walk_files(folder: str, mode: str, mm: Any) -> list[str]:
    """The batch file set for `mode`, in the stable legacy order.

    Native path: the Rust parallel walk (``mm.walk_models`` — Plan §6.2
    Phase 3 batch primitive). Legacy path: the Python ``os.walk`` walkers.
    Both return sorted absolute paths; the bundle-semantics constants come
    from ``py/utils`` so the Python side stays the single source of truth.
    """
    if mm is not None:
        import folder_paths

        opts: dict[str, Any] = {
            "mode": mode,
            "bundleSuffixes": [utils.DELTA_FOLDER_SUFFIX, utils.ZNN_FOLDER_SUFFIX],
            "deltaFolderSuffix": utils.DELTA_FOLDER_SUFFIX,
        }
        if mode == "compress":
            opts["skipBundles"] = True
        elif mode == "blockers":
            opts["extensions"] = sorted(folder_paths.supported_pt_extensions)
        return [str(p) for p in json.loads(mm.walk_models(folder, opts))]
    if mode == "compress":
        return _walk_model_files(folder, "compress", skip_bundles=True)
    if mode == "decompress":
        return _walk_decompress_files(folder)
    return _batch_invariants_blockers(folder)


def _move_sidecars(mm: Any, src: str, dst: str) -> None:
    """Sidecar move through the native primitive when available (the Rust
    port is golden-tested against ``_delta_sidecar_move``), else the Python
    mover."""
    if mm is not None:
        mm.move_with_sidecars(src, dst)
    else:
        _delta_sidecar_move(src, dst)


def batch_process_folder(
    folder: str,
    mode: str,
    is_type_root: bool,
    progress: ProgressCb,
    mm: Any = None,
    task_id: str | None = None,
    paranoid: bool = False,
) -> dict[str, Any]:
    """Batch-compress / batch-decompress every eligible file under `folder`.

    compress: every plain `.safetensors` becomes `.znn.safetensors` and MOVES
    into the bundle folder `<parent>/<name>_DeltaZNN` (previews/notes follow;
    directories the batch emptied are removed, so `X` is replaced by
    `X_DeltaZNN`). Model-type roots keep themselves and get the bundle inside
    (`T/T_DeltaZNN`).

    decompress: the exact mirror - bundle content moves back to the folder the
    bundle was named after, delta files (`*_delta_*.znn` inside
    `*_DeltaZNN`) are restored to their fine-tuned models beside the base, and
    the emptied bundle folder disappears. Legacy in-place compressed files
    (type roots of older versions) decompress where they are.

    A failed run leaves already-processed files moved (each file is committed
    atomically via its `.tmp` + rename); unprocessed files are untouched.
    """
    folder = folder.rstrip(os.sep) or folder
    if mode == "compress":
        bundle = _bundle_dst_root(folder, is_type_root)
        if os.path.exists(bundle):
            raise RuntimeError(f"target already exists: {os.path.basename(bundle)}")
        files = _walk_files(folder, "compress", mm)
        total = max(1, len(files))
        for index, path in enumerate(files):
            target = _compress_target(path, folder, bundle)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if mm is not None:
                opts = {"threads": 0, "paranoid": bool(paranoid)}
                _run_native_job_sync(
                    mm,
                    task_id,
                    lambda p=path, t=target, o=opts: mm.zipnn_compress(p, t, o),
                    f"batch-compress {os.path.basename(path)}",
                )
            else:
                compress_safetensors(path, target, lambda *_args: None)
            _move_sidecars(mm, path, target)
            os.remove(path)
            progress(index + 1, total, "files")
        _prune_empty_dirs(folder, remove_root=not is_type_root)
        return {"files": len(files), "folder": bundle}

    files = _walk_files(folder, "decompress", mm)
    total = max(1, len(files))
    restored = 0
    skipped = 0
    for index, path in enumerate(files):
        name = os.path.basename(path)
        if name.endswith(ZNN_SUFFIX):
            target = _decompress_target(path, folder, _plain_name(name), False)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if mm is not None:
                _run_native_job_sync(
                    mm,
                    task_id,
                    lambda p=path, t=target: mm.zipnn_decompress(p, t, {"threads": 0}),
                    f"batch-decompress {name}",
                )
            else:
                decompress_safetensors(path, target, lambda *_args: None)
            _move_sidecars(mm, path, target)
            os.remove(path)
            restored += 1
        else:
            # A delta file: restore the fine-tuned model beside its base.
            delta_dir = os.path.dirname(path)
            base_base = os.path.basename(delta_dir)[: -len(utils.DELTA_FOLDER_SUFFIX)]
            suffix = f"_delta_{base_base}.znn"
            if not name.endswith(suffix):
                utils.print_warning(f"batch decompress: skipping {name} (not a delta file)")
                skipped += 1
                progress(index + 1, total, "files")
                continue
            ft_base = name[: -len(suffix)]
            located = _locate_bundle(path, folder)
            base_dir = os.path.dirname(located[0].rstrip(os.sep)) if located is not None else os.path.dirname(delta_dir)
            base_path = os.path.join(base_dir, f"{base_base}{SAFE_SUFFIX}")
            if not os.path.isfile(base_path):
                raise RuntimeError(f"base model not found for {name}: {base_base}")
            target = _decompress_target(path, folder, f"{ft_base}{SAFE_SUFFIX}", True)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if mm is not None:
                meta = _read_delta_meta(path)
                _run_native_job_sync(
                    mm,
                    task_id,
                    lambda b=base_path, p=path, t=target, m=meta: mm.zipnn_delta_decompress(b, p, t, m, {"threads": 0}),
                    f"batch-delta {name}",
                )
            else:
                delta_decompress_file(base_path, path, target, lambda *_args: None)
            _move_sidecars(mm, path, target)
            os.remove(path)
            sidecar = _delta_meta_path(path)
            if os.path.exists(sidecar):
                try:
                    os.remove(sidecar)
                except OSError:
                    pass
            restored += 1
        progress(index + 1, total, "files")
    _prune_empty_dirs(folder, remove_root=_is_bundle_dir_name(os.path.basename(folder)))
    return {"files": restored, "skipped": skipped, "folder": folder}


def _safetensors_split(path: str) -> tuple[int, bytes, bytes]:
    """(header_len, header_bytes, data_bytes) of a safetensors file."""
    import struct

    with open(path, "rb") as f:
        (header_len,) = struct.unpack("<Q", f.read(8))
        header = f.read(header_len)
        data = f.read()
    return header_len, header, data


def _delta_aligned_bytes(base_path: str, ft_path: str) -> tuple[bytes, bytes, dict]:
    """Byte-equal-length renderings of both files for ZipNN's file-level delta.

    ZipNN's delta mode XOR-compares raw bytes, so both files must have the
    *same total length*. Fine-tunes of the same architecture always have an
    identical data section, but their JSON headers routinely differ (extra /
    renamed metadata keys), which shifts the total length and made ZipNN die
    with "Length of delta file has to match the length of the original file."
    A safetensors header is JSON, and trailing spaces inside the header region
    are valid JSON whitespace - so the shorter header is space-padded (and the
    8-byte length prefix adjusted) until both renderings match. The padding is
    recorded in a sidecar so decompression can restore the *exact* original
    bytes. If the DATA sections themselves differ, the models are not the same
    architecture and delta compression is genuinely impossible.
    """
    import struct

    base_len, base_header, base_data = _safetensors_split(base_path)
    ft_len, ft_header, ft_data = _safetensors_split(ft_path)
    if len(base_data) != len(ft_data):
        raise RuntimeError(
            "the two models have different tensor data sizes "
            f"({len(base_data)} vs {len(ft_data)} bytes): delta compression "
            "only works between a base and a fine-tune with the exact same "
            "architecture and tensor layout"
        )
    pad_base = max(0, ft_len - base_len)
    pad_ft = max(0, base_len - ft_len)
    base_bytes = struct.pack("<Q", base_len + pad_base) + base_header + b" " * pad_base + base_data
    ft_bytes = struct.pack("<Q", ft_len + pad_ft) + ft_header + b" " * pad_ft + ft_data
    return base_bytes, ft_bytes, {"basePad": pad_base, "ftPad": pad_ft}


def _delta_unpad(restored: bytes, pad: int) -> bytes:
    """Undo `_delta_aligned_bytes` padding (byte-exact original file)."""
    import struct

    if not pad:
        return restored
    (padded_len,) = struct.unpack("<Q", restored[:8])
    original_len = padded_len - pad
    header = restored[8 : 8 + original_len]
    data = restored[8 + padded_len :]
    return struct.pack("<Q", original_len) + header + data


def _delta_meta_path(delta_path: str) -> str:
    return f"{delta_path}.neo-delta.json"


def _read_delta_meta(delta_path: str) -> dict[str, Any]:
    """The parsed ``.neo-delta.json`` sidecar ({} when missing/corrupt).

    Same degradation as the legacy ``delta_decompress_file`` reader — the
    length checks of the delta codec then fail with the legacy wording
    unless the pads genuinely were zero.
    """
    try:
        with open(_delta_meta_path(delta_path), encoding="utf-8") as f:
            meta = json.load(f)
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}


def _delta_sidecar_move(src_model: str, dst_model: str) -> None:
    """Move previews/notes between *different* directories.

    `_sidecar_move` renames sidecars inside one directory, but delta files live
    in the base model's `<base>_DeltaZNN/` folder while the fine-tune's
    previews/notes live beside the fine-tune - so the delta flow needs a
    cross-directory move (fine-tune dir -> delta dir on compress, and back on
    decompress). Without it the sidecars kept their `_delta_` names forever
    (reported bug: "previews/notes disappear after delta decompress").
    """
    src_dir = os.path.dirname(src_model)
    dst_dir = os.path.dirname(dst_model)
    src_base = os.path.splitext(os.path.basename(src_model))[0]
    dst_base = os.path.splitext(os.path.basename(dst_model))[0]
    names = utils.get_dir_names(src_dir)
    for preview in utils.previews_in_names(names, src_base):
        ext = preview[len(src_base) :]
        src = utils.join_path(src_dir, preview)
        dst = utils.join_path(dst_dir, f"{dst_base}{ext}")
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(dst_dir, exist_ok=True)
            os.rename(src, dst)
    for desc in utils.get_model_all_descriptions(src_model):
        src = utils.join_path(src_dir, desc)
        dst = utils.join_path(dst_dir, f"{dst_base}{os.path.splitext(desc)[1]}")
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(dst_dir, exist_ok=True)
            os.rename(src, dst)


def delta_compress_files(base_path: str, ft_path: str, out_path: str, progress: ProgressCb) -> dict[str, Any]:
    """Delta-compress `ft_path` against `base_path` (official file-level API).

    `ZipNN(delta_compressed_type="byte").compress(ft_bytes, delta_second_data=
    base_bytes)` stores only the difference; both sides are header-padded to
    equal length first (see `_delta_aligned_bytes`). The padding sidecar travels
    with the delta file so decompression restores the fine-tune byte-exactly.
    """
    import json

    from zipnn import ZipNN
    from zipnn.util_safetensors import COMPRESSION_METHOD

    base_bytes, ft_bytes, meta = _delta_aligned_bytes(base_path, ft_path)
    # `delta_compressed_type="byte"` (not "file"): the "file" mode re-reads the
    # base from disk by path, which would bypass the header padding above.
    zpn = ZipNN(
        bytearray_dtype="float32",
        delta_compressed_type="byte",
        method=COMPRESSION_METHOD,
    )
    progress(1, 3, "delta")
    compressed = zpn.compress(ft_bytes, delta_second_data=base_bytes)
    progress(2, 3, "delta")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = f"{out_path}.tmp"
    with open(tmp, "wb") as f:
        f.write(compressed)
    os.replace(tmp, out_path)
    with open(_delta_meta_path(out_path), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    progress(3, 3, "delta")
    return {"originalBytes": len(ft_bytes), "compressedBytes": len(compressed)}


def delta_decompress_file(base_path: str, delta_path: str, out_path: str, progress: ProgressCb) -> dict[str, Any]:
    """Restore the exact fine-tuned bytes from a delta file + its base model."""
    import json

    from zipnn import ZipNN

    meta: dict[str, int] = {}
    try:
        with open(_delta_meta_path(delta_path), encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        meta = {}
    # Rebuild the padded base rendering exactly as compress saw it.
    import struct

    base_len, base_header, base_data = _safetensors_split(base_path)
    pad_base = int(meta.get("basePad", 0))
    base_bytes = struct.pack("<Q", base_len + pad_base) + base_header + b" " * pad_base + base_data
    zpn = ZipNN(is_streaming=True, delta_compressed_type="byte")
    with open(delta_path, "rb") as f:
        delta_bytes = f.read()
    progress(1, 3, "delta")
    restored_padded = zpn.decompress(delta_bytes, delta_second_data=base_bytes)
    progress(2, 3, "delta")
    restored = _delta_unpad(restored_padded, int(meta.get("ftPad", 0)))
    tmp = f"{out_path}.tmp"
    with open(tmp, "wb") as f:
        f.write(restored)
    os.replace(tmp, out_path)
    progress(3, 3, "delta")
    return {"originalBytes": len(restored), "compressedBytes": len(delta_bytes)}


class ZipNNRoutes:
    def add_routes(self, routes):
        @routes.get("/model-manager/zipnn/available")
        async def zipnn_status(request):
            # Phase 2: capability = native core OR the legacy vendored path.
            # The native probe is cheap and cached; when it answers, the
            # legacy probe (which imports torch on first call) is skipped —
            # that also keeps this diagnostic route from ever blocking the
            # event loop on the native path. `engine`/`reason` are additive
            # diagnostics; `available` keeps its legacy meaning for any
            # external caller.
            engine = None
            reason = None
            try:
                if native_core() is not None:
                    engine = "native"
                else:
                    reason = native.reason()
                    if zipnn_available():
                        engine = "legacy"
            except Exception as e:  # diagnostics must never explode
                reason = str(e)
            return web.json_response(
                {
                    "success": True,
                    "data": {
                        "available": engine is not None,
                        "engine": engine,
                        "reason": reason,
                    },
                }
            )

        @routes.post("/model-manager/zipnn/compress")
        async def zipnn_compress(request):
            return await self._run(request, "compress")

        @routes.post("/model-manager/zipnn/decompress")
        async def zipnn_decompress(request):
            return await self._run(request, "decompress")

        @routes.post("/model-manager/zipnn/batch-folder")
        async def zipnn_batch_folder(request):
            return await self._run_batch(request)

        @routes.post("/model-manager/zipnn/delta-compress")
        async def zipnn_delta_compress(request):
            return await self._run_delta(request, "compress")

        @routes.post("/model-manager/zipnn/delta-decompress")
        async def zipnn_delta_decompress(request):
            return await self._run_delta(request, "decompress")

        @routes.post("/model-manager/zipnn/cancel")
        async def zipnn_cancel(request):
            """Cooperative cancellation of a running NATIVE job (Plan §4.2.2).

            The worker observes the flag at tensor/chunk boundaries, removes
            its partial output and reports ``zipnn_complete {ok: false,
            error: "cancelled by user"}`` like any other failure. Legacy-path
            tasks (vendored C core, ``MM_NATIVE=0``) run inside one blocking
            C call per tensor and cannot be cancelled mid-flight — the
            response says so explicitly.
            """
            data = await utils.get_request_body(request)
            task_id = str(data.get("taskId") or "")
            entry = ZIPNN_TASKS.get(task_id)
            if entry is None:
                return web.json_response({"success": False, "error": "unknown task"})
            handle = entry.get("handle")
            if handle is None:
                return web.json_response(
                    {
                        "success": False,
                        "error": "this task runs on the legacy (C core) path and cannot be cancelled mid-run",
                    }
                )
            mm = native.core()
            if mm is None:
                return web.json_response({"success": False, "error": "the native core is no longer loaded"})
            try:
                was_running = bool(mm.job_cancel(handle))
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})
            return web.json_response({"success": True, "data": {"wasRunning": was_running}})

    async def _run_native_job(self, mm, task_id: str, mode: str, src: str, dst: str, paranoid: bool):
        """Drive one compress/decompress job on the Rust core (Phase 2 path).

        Submits the job, then hands over to [`_poll_native_job`]. Returns
        the stats dict on success, or None after reporting the failure
        through `_fail`.

        NO python-side `.tmp` cleanup here (unlike the legacy path): the Rust
        pipeline removes its own partials on EVERY failure route (AtomicWriter
        Drop guard, cancellation, panic unwind), and a blind sweep could
        delete the tmp of a CONCURRENT job for the same target (the writer's
        create-new guard rejects the second job — its failure handler must
        not then destroy the first job's file). `.corrupt` diagnostics of a
        failed verification are deliberately kept.
        """
        opts = {"threads": 0, "paranoid": bool(paranoid)}
        try:
            handle = mm.zipnn_compress(src, dst, opts) if mode == "compress" else mm.zipnn_decompress(src, dst, opts)
        except Exception as e:
            await self._fail(task_id, src, f"native job could not start: {e}")
            return None
        return await self._poll_native_job(mm, task_id, mode, src, handle, _WS_PHASE_FOR_NATIVE)

    async def _run_native_delta_job(self, mm, task_id: str, mode: str, src: str, second: str, dst: str, paranoid: bool):
        """Drive one delta job on the Rust core (Phase 3 path).

        compress: `src` = base model, `second` = fine-tune → `dst` delta
        file (+ `.neo-delta.json` sidecar, written by the job itself with
        the new `ftSha256` integrity key). decompress: `src` = base model,
        `second` = delta file → `dst` restored fine-tune; the sidecar is
        parsed HERE (same missing/corrupt degradation as the legacy reader)
        and passed across the boundary.
        """
        try:
            if mode == "compress":
                opts = {"threads": 0, "paranoid": bool(paranoid)}
                handle = mm.zipnn_delta_compress(src, second, dst, opts)
            else:
                meta = _read_delta_meta(second)
                handle = mm.zipnn_delta_decompress(src, second, dst, meta, {"threads": 0})
        except Exception as e:
            await self._fail(task_id, second, f"native job could not start: {e}")
            return None
        return await self._poll_native_job(mm, task_id, mode, second, handle, _WS_PHASE_FOR_DELTA)

    async def _poll_native_job(self, mm, task_id: str, mode: str, src: str, handle, phase_map: dict[str, str]):
        """Poll a submitted native job at 10 Hz and re-emit the legacy ws
        contract (`update_zipnn_progress` with the same payload shape;
        phases mapped through `phase_map`). Returns the stats dict on
        success, or None after reporting the failure through `_fail`."""
        ZIPNN_TASKS[task_id]["handle"] = handle

        last_sent: tuple[float, str] | None = None
        while True:
            await asyncio.sleep(_NATIVE_POLL_INTERVAL)
            try:
                done, total, phase = mm.job_progress(handle)
            except Exception as e:
                await self._fail(task_id, src, f"native job vanished: {e}")
                return None
            if phase not in ("done", "failed"):
                pct = (done / total * 100) if total else 0.0
                ws_phase = phase_map.get(phase, "tensors")
                event = (round(pct, 3), ws_phase)
                if event != last_sent:
                    last_sent = event
                    await utils.send_json(
                        "update_zipnn_progress",
                        {"taskId": task_id, "progress": pct, "phase": ws_phase, "mode": mode},
                    )
            if phase == "failed":
                try:
                    err = mm.job_error(handle)
                except Exception:
                    err = None
                await self._fail(task_id, src, err or "native job failed")
                return None
            if phase == "done":
                break

        try:
            result = json.loads(mm.job_result(handle))
        except Exception as e:
            await self._fail(task_id, src, f"native job result unreadable: {e}")
            return None
        for warning in result.get("warnings") or []:
            utils.print_warning(f"zipnn[{mode}]: {warning}")
        stats = result.get("stats")
        if not isinstance(stats, dict):
            await self._fail(task_id, src, "native job returned no stats")
            return None
        return stats

    async def _run(self, request, mode: str):
        data = await utils.get_request_body(request)
        model_type = data.get("type")
        path_index = int(data.get("pathIndex") or 0)
        fullname = data.get("fullname")
        if not model_type or not fullname:
            return web.json_response({"success": False, "error": "type and fullname are required"})
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
                return web.json_response({"success": False, "error": "model is already compressed"})
            base = src[: -len(SAFE_SUFFIX)]
            dst = f"{base}{ZNN_SUFFIX}"
        else:
            if not is_compressed_name(fullname):
                return web.json_response({"success": False, "error": "model is not ZipNN compressed"})
            base = src[: -len(ZNN_SUFFIX)]
            dst = f"{base}{SAFE_SUFFIX}"
        if os.path.exists(dst):
            return web.json_response({"success": False, "error": f"target already exists: {os.path.basename(dst)}"})

        force = bool(data.get("force"))
        paranoid = paranoid_enabled(request)
        task_id = uuid.uuid4().hex
        ZIPNN_TASKS[task_id] = {"mode": mode, "status": "running", "src": src, "dst": dst}
        await utils.send_json(
            "update_zipnn_progress",
            {"taskId": task_id, "progress": 0.0, "phase": "prepare", "mode": mode},
        )

        loop = asyncio.get_running_loop()

        async def worker():
            # ANY escaping exception must flip the task to "error" and emit
            # zipnn_complete — a worker that dies silently would leave the UI
            # spinner running forever (`_schedule` only logs).
            try:
                await worker_body()
            except Exception as e:
                try:
                    await self._fail(task_id, src, f"zipnn worker crashed: {e}")
                except Exception:
                    utils.print_error(f"zipnn worker crash could not be reported: {e}")

        async def worker_body():
            try:
                mm = native_core()
            except RuntimeError as e:
                # MM_NATIVE=1 with an unavailable core: the reason() text is
                # actionable (missing binary / failed handshake) — surface it.
                await self._fail(task_id, src, str(e))
                return

            if mm is not None:
                stats = await self._run_native_job(mm, task_id, mode, src, dst, paranoid)
                if stats is None:
                    return  # failure/cancellation already reported
            else:
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
                    stats = await loop.run_in_executor(utils.cpu_executor(), fn, src, dst, progress)
                except Exception as e:
                    # never leave a half-written target behind
                    _cleanup_targets(dst)
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

        _spawn_background(loop, self._schedule(worker()))
        return web.json_response({"success": True, "data": {"taskId": task_id}})

    async def _run_batch(self, request):
        """Batch-compress / batch-decompress a whole folder (selection bar).

        compress: every plain `.safetensors` under `X` is compressed and moved
        into the bundle folder `X_DeltaZNN` (a model-type root `T` gets the
        bundle inside itself: `T/T_DeltaZNN`, because a sibling of a type root
        would fall outside every ComfyUI-mapped path). decompress: the exact
        mirror - bundle content moves back to the folder the bundle was named
        after, `*_delta_*.znn` files are restored to their fine-tuned models,
        and the emptied bundle folder is removed. `mode="auto"` lets the
        server pick the direction from the folder content (plain models
        present -> compress, only compressed ones -> decompress).
        """
        data = await utils.get_request_body(request)
        if not isinstance(data, dict) or not data:
            # Defensive: some proxies/middlewares re-encode JSON bodies; fall
            # back to form parsing so a legit click can never die here.
            try:
                data = dict(await request.post())
            except Exception:
                data = {}
        mode = data.get("mode")
        model_type = data.get("type")
        path_index = int(data.get("pathIndex") or 0)
        rel_folder = str(data.get("folder") or data.get("fullname") or "").strip("/")
        if mode not in ("compress", "decompress", "auto") or not model_type or not rel_folder:
            utils.print_warning(
                f"batch-folder request rejected; received keys: {sorted(data.keys()) if data else '<empty body>'}"
            )
            return web.json_response(
                {
                    "success": False,
                    "error": (
                        "mode, type and folder are required (received: "
                        f"{', '.join(sorted(data.keys())) if data else 'empty body'})"
                    ),
                }
            )
        try:
            folder = utils.get_full_path(model_type, path_index, rel_folder)
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)})
        # '.' is the relative path of a model-type root folder; normpath folds
        # it into the base path so the type-root detection below works.
        folder = os.path.normpath(folder)
        if not os.path.isdir(folder):
            return web.json_response({"success": False, "error": "folder not found"})
        bases = utils.resolve_model_base_paths().get(model_type, [])
        is_type_root = path_index < len(bases) and utils.normalize_path(folder) == utils.normalize_path(
            bases[path_index]
        )

        folder_name = os.path.basename(folder.rstrip("/"))
        # Native probe for the validation walks AND the worker. A hard
        # MM_NATIVE=1 failure surfaces inside the worker through _fail (the
        # probe here must not turn request validation into a 500).
        mm = None
        try:
            mm = native_core()
        except RuntimeError:
            mm = None
        paranoid = paranoid_enabled(request)
        if mode == "auto":
            if _walk_files(folder, "compress", mm):
                mode = "compress"
            elif _walk_files(folder, "decompress", mm):
                mode = "decompress"
            else:
                return web.json_response(
                    {
                        "success": False,
                        "error": "folder holds no compressible or compressed models",
                    }
                )
        if mode == "compress":
            if _is_bundle_dir_name(folder_name):
                return web.json_response(
                    {
                        "success": False,
                        "error": (
                            "folder is already a ZipNN bundle "
                            f"(*{utils.DELTA_FOLDER_SUFFIX}): batch-decompress it instead"
                        ),
                    }
                )
            blockers = _walk_files(folder, "blockers", mm)
            if blockers:
                names = ", ".join(os.path.basename(b) for b in blockers[:5])
                return web.json_response(
                    {
                        "success": False,
                        "error": (
                            "folder holds models ZipNN cannot convert "
                            f"({names}); a *{utils.DELTA_FOLDER_SUFFIX} folder "
                            "may only contain *.znn.* / *.znn models"
                        ),
                    }
                )
            files = _walk_files(folder, "compress", mm)
            if not files:
                return web.json_response({"success": False, "error": "no .safetensors files to compress"})
            # Every compressed file MOVES into `<name>_DeltaZNN`; model-type
            # roots get the bundle inside themselves (a sibling of a type root
            # would fall outside every ComfyUI-mapped path).
            dst_folder = _bundle_dst_root(folder, is_type_root)
        else:
            # Bundles empty back into the folder they were named after;
            # legacy in-place compressed folders decompress where they are.
            dst_folder = folder
            files = _walk_files(folder, "decompress", mm)
            if not files:
                return web.json_response(
                    {
                        "success": False,
                        "error": "no .znn.safetensors / delta files to decompress",
                    }
                )
        if dst_folder != folder and os.path.exists(dst_folder):
            return web.json_response(
                {
                    "success": False,
                    "error": f"target already exists: {os.path.basename(dst_folder)}",
                }
            )

        task_id = uuid.uuid4().hex
        ZIPNN_TASKS[task_id] = {
            "mode": f"batch-{mode}",
            "status": "running",
            "src": folder,
            "dst": dst_folder,
        }
        await utils.send_json(
            "update_zipnn_progress",
            {"taskId": task_id, "progress": 0.0, "phase": "prepare", "mode": mode},
        )
        loop = asyncio.get_running_loop()

        async def worker():
            # ANY escaping exception must flip the task to "error" and emit
            # zipnn_complete — a worker that dies silently would leave the UI
            # spinner running forever (`_schedule` only logs).
            try:
                await worker_body()
            except Exception as e:
                try:
                    await self._fail(task_id, folder, f"zipnn worker crashed: {e}")
                except Exception:
                    utils.print_error(f"zipnn worker crash could not be reported: {e}")

        async def worker_body():
            try:
                mm_run = native_core()
            except RuntimeError as e:
                # MM_NATIVE=1 with an unavailable core: actionable reason()
                await self._fail(task_id, folder, str(e))
                return

            if mm_run is None:
                try:
                    await loop.run_in_executor(utils.cpu_executor(), ensure_zipnn, False)
                except Exception as e:
                    await self._fail(
                        task_id,
                        folder,
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

            try:
                stats = await loop.run_in_executor(
                    utils.cpu_executor(),
                    batch_process_folder,
                    folder,
                    mode,
                    is_type_root,
                    progress,
                    mm_run,
                    task_id,
                    paranoid,
                )
            except Exception as e:
                await self._fail(task_id, folder, str(e))
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
                    "kind": "folder",
                    "ok": True,
                    "stats": stats,
                    "fullname": os.path.basename(dst_folder),
                },
            )

        _spawn_background(loop, self._schedule(worker()))
        return web.json_response({"success": True, "data": {"taskId": task_id}})

    async def _run_delta(self, request, mode: str):
        """Delta (de)compression of a fine-tuned model against its base.

        compress: base + FT -> `<base>_DeltaZNN/<ft>_delta_<base>.znn`, then the
        FT original is removed (its bytes are recoverable from base + delta).
        decompress: base + delta -> the exact FT file back beside the base.
        """
        data = await utils.get_request_body(request)
        model_type = data.get("type")
        path_index = int(data.get("pathIndex") or 0)
        if not model_type:
            return web.json_response({"success": False, "error": "type is required"})

        if mode == "compress":
            base_full = data.get("baseFullname")
            ft_full = data.get("fullname")
            if not base_full or not ft_full:
                return web.json_response({"success": False, "error": "baseFullname and fullname are required"})
            try:
                base_path = utils.get_valid_full_path(model_type, path_index, base_full)
                ft_path = utils.get_valid_full_path(model_type, path_index, ft_full)
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})
            if not base_path or not ft_path:
                return web.json_response({"success": False, "error": "base or fine-tuned model not found"})
            if base_path == ft_path:
                return web.json_response({"success": False, "error": "base and fine-tuned model must differ"})
            for candidate in (base_path, ft_path):
                if not is_safetensors(candidate) or is_compressed_name(candidate):
                    return web.json_response(
                        {
                            "success": False,
                            "error": "delta compression needs plain .safetensors inputs",
                        }
                    )
            base_base = os.path.basename(base_path)[: -len(SAFE_SUFFIX)]
            ft_base = os.path.basename(ft_path)[: -len(SAFE_SUFFIX)]
            delta_dir = utils.join_path(os.path.dirname(base_path), f"{base_base}{utils.DELTA_FOLDER_SUFFIX}")
            out_path = utils.join_path(delta_dir, f"{ft_base}_delta_{base_base}.znn")
            if os.path.exists(out_path):
                return web.json_response(
                    {
                        "success": False,
                        "error": f"target already exists: {os.path.basename(out_path)}",
                    }
                )
            src, second, dst = base_path, ft_path, out_path
        else:
            delta_full = data.get("fullname")
            if not delta_full:
                return web.json_response({"success": False, "error": "fullname is required"})
            try:
                delta_path = utils.get_valid_full_path(model_type, path_index, delta_full)
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})
            if not delta_path:
                return web.json_response({"success": False, "error": "delta file not found"})
            delta_dir = os.path.dirname(delta_path)
            delta_folder = os.path.basename(delta_dir)
            if not delta_folder.endswith(utils.DELTA_FOLDER_SUFFIX):
                return web.json_response({"success": False, "error": "not inside a *_DeltaZNN folder"})
            base_base = delta_folder[: -len(utils.DELTA_FOLDER_SUFFIX)]
            delta_name = os.path.basename(delta_path)
            suffix = f"_delta_{base_base}.znn"
            if not delta_name.endswith(suffix):
                return web.json_response({"success": False, "error": "unexpected delta file name"})
            ft_base = delta_name[: -len(suffix)]
            base_path = utils.join_path(os.path.dirname(delta_dir), f"{base_base}{SAFE_SUFFIX}")
            if not os.path.isfile(base_path):
                return web.json_response({"success": False, "error": f"base model not found: {base_base}"})
            out_path = utils.join_path(os.path.dirname(delta_dir), f"{ft_base}{SAFE_SUFFIX}")
            if os.path.exists(out_path):
                return web.json_response(
                    {
                        "success": False,
                        "error": f"target already exists: {os.path.basename(out_path)}",
                    }
                )
            src, second, dst = base_path, delta_path, out_path

        task_id = uuid.uuid4().hex
        ZIPNN_TASKS[task_id] = {
            "mode": f"delta-{mode}",
            "status": "running",
            "src": second,
            "dst": dst,
        }
        await utils.send_json(
            "update_zipnn_progress",
            {"taskId": task_id, "progress": 0.0, "phase": "prepare", "mode": mode},
        )
        loop = asyncio.get_running_loop()
        paranoid = paranoid_enabled(request)

        async def worker():
            # ANY escaping exception must flip the task to "error" and emit
            # zipnn_complete — a worker that dies silently would leave the UI
            # spinner running forever (`_schedule` only logs).
            try:
                await worker_body()
            except Exception as e:
                try:
                    await self._fail(task_id, second, f"zipnn worker crashed: {e}")
                except Exception:
                    utils.print_error(f"zipnn worker crash could not be reported: {e}")

        async def worker_body():
            try:
                mm = native_core()
            except RuntimeError as e:
                # MM_NATIVE=1 with an unavailable core: the reason() text is
                # actionable (missing binary / failed handshake) — surface it.
                await self._fail(task_id, second, str(e))
                return

            if mm is not None:
                stats = await self._run_native_delta_job(mm, task_id, mode, src, second, dst, paranoid)
                if stats is None:
                    # failure already reported; the Rust Drop guard removed
                    # its own partials — only the committed-delta-without-
                    # sidecar case needs Python's help
                    _cleanup_delta_failure(dst, mode, native=True)
                    return
            else:
                try:
                    await loop.run_in_executor(utils.cpu_executor(), ensure_zipnn, False)
                except Exception as e:
                    await self._fail(
                        task_id,
                        second,
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

                fn = delta_compress_files if mode == "compress" else delta_decompress_file
                try:
                    stats = await loop.run_in_executor(utils.cpu_executor(), fn, src, second, dst, progress)
                except Exception as e:
                    _cleanup_delta_failure(dst, mode, native=False)
                    await self._fail(task_id, second, str(e))
                    return

            try:
                if mode == "compress":
                    # previews/notes of the fine-tuned model travel with the
                    # delta file, then the (now redundant) original goes away.
                    _delta_sidecar_move(second, dst)
                    os.remove(second)
                else:
                    _delta_sidecar_move(second, dst)
                    os.remove(second)
                    sidecar_meta = _delta_meta_path(second)
                    if os.path.exists(sidecar_meta):
                        try:
                            os.remove(sidecar_meta)
                        except OSError:
                            pass
                    try:
                        if not os.listdir(delta_dir):
                            os.rmdir(delta_dir)
                    except OSError:
                        pass
            except Exception as e:
                await self._fail(task_id, second, str(e))
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
                    "kind": "delta",
                    "ok": True,
                    "stats": stats,
                    "fullname": os.path.basename(dst),
                },
            )

        _spawn_background(loop, self._schedule(worker()))
        return web.json_response({"success": True, "data": {"taskId": task_id}})

    async def _schedule(self, coro):
        try:
            await coro
        except Exception as e:  # pragma: no cover - defensive
            utils.print_error(f"zipnn worker crashed: {e}")

    async def _fail(self, task_id: str, src: str, error: str, install_failed: bool = False):
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
