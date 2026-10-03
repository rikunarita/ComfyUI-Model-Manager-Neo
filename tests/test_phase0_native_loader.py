"""Plan Phase 0 (Phase 8 single-path): py/native.py loader — platform tags,
handshake, diagnostics.

Written against the loader's public surface: ``platform_tag`` / ``load`` /
``available`` / ``core`` / ``core_if_enabled`` / ``reason`` / ``core_version``
/ ``diagnostics`` — plus, since NEO-PLAN-2026-003, the interpreter-flavour
surface ``is_free_threaded`` / ``tag_rejection_reason`` (abi3t ``<tag>t``
routing and the GIL-3.12 / free-threaded-3.15 floor guards). Phase 8 removed
the ``MM_NATIVE`` switch: ``load()`` never raises, it reports
``available() is False`` + ``reason()``, and the ZipNN routes turn that into
their actionable error (covered in test_phase2_routes).
The loader caches its attempt in module state, so every test reloads
``mmneo_py.native``; an autouse fixture restores ``sys.path`` and
``sys.modules["mm_core"]`` because ``load()`` appends the binary directory to
the import path, and a second autouse fixture pins a SUPPORTED interpreter
baseline (GIL 3.12) so the floor guards cannot make these assertions depend
on the interpreter that happens to run pytest.
"""

from __future__ import annotations

import importlib
import sys
import sysconfig
from pathlib import Path

import pytest
from harness import REPO_ROOT, import_ext


@pytest.fixture(autouse=True)
def _isolate_loader_state(monkeypatch):
    """Undo the loader's global side effects between tests.

    Also scrub any real ``native-bin`` directory another test file left on
    ``sys.path`` (e.g. a route test whose ``get_model_metadata`` /
    ``scan_models`` called ``native.load()`` on the built artifact): the loader
    APPENDS its bin_dir, so a pre-existing real entry would shadow the per-test
    fake these loader tests install and the origin guard would fire before the
    version check they are asserting. Removing it at setup is safe — the tests
    that need the real prebuilt re-add it through ``native.load()``.
    """
    sys.path[:] = [p for p in sys.path if "native-bin" not in p]
    sys.modules.pop("mm_core", None)
    path_snapshot = list(sys.path)
    yield
    sys.path[:] = path_snapshot
    sys.modules.pop("mm_core", None)


def _fresh_native():
    """(Re-)import py.native with pristine attempt state; returns the module."""
    native = import_ext("native")
    return importlib.reload(native)


def _point_extension_at(tmp_path: Path) -> None:
    config = import_ext("config")
    config.extension_uri = str(tmp_path)


class _VersionInfo(tuple):
    """A constructible stand-in for ``sys.version_info``.

    CPython's real object is a structseq whose type refuses instantiation
    ("cannot create 'sys.version_info' instances"), so the loader tests fake
    the interpreter version with a plain tuple subclass that also carries the
    ``major``/``minor``/``micro`` attributes.
    """

    def __new__(cls, major: int, minor: int, micro: int, releaselevel: str = "final", serial: int = 0):
        self = super().__new__(cls, (major, minor, micro, releaselevel, serial))
        self.major, self.minor, self.micro = major, minor, micro
        self.releaselevel, self.serial = releaselevel, serial
        return self


def _force_interpreter(monkeypatch, *, version=(3, 12, 7), free_threaded=False, abiflags=None):
    """Monkeypatch the three interpreter signals the loader reads.

    ``version`` is ``(major, minor, micro)``; ``free_threaded`` drives the
    ``Py_GIL_DISABLED`` sysconfig value (1/0); ``abiflags`` overrides
    ``sys.abiflags`` (default: ``"t"`` when free_threaded, ``""`` otherwise).
    Passing the two flavour signals independently exercises BOTH OR-paths of
    ``is_free_threaded()`` (Plan-3 §3.3)."""
    major, minor, micro = version
    monkeypatch.setattr(sys, "version_info", _VersionInfo(major, minor, micro))
    flags = ("t" if free_threaded else "") if abiflags is None else abiflags
    monkeypatch.setattr(sys, "abiflags", flags, raising=False)
    gil_disabled = 1 if free_threaded else 0
    real_get_config_var = sysconfig.get_config_var
    monkeypatch.setattr(
        sysconfig,
        "get_config_var",
        lambda name: gil_disabled if name == "Py_GIL_DISABLED" else real_get_config_var(name),
    )


# The REAL host interpreter, captured at import time: the autouse baseline
# below monkeypatches exactly these three signals, so a test that has to
# consult the truth cannot read them back from `sys` / `sysconfig` afterwards.
_REAL_VERSION = tuple(sys.version_info[:3])
_REAL_ABIFLAGS = getattr(sys, "abiflags", "")
_REAL_GIL_DISABLED = sysconfig.get_config_var("Py_GIL_DISABLED") == 1
_REAL_FREE_THREADED = _REAL_GIL_DISABLED or "t" in _REAL_ABIFLAGS


def _use_real_interpreter(monkeypatch) -> None:
    """Re-assert the REAL host interpreter over the autouse GIL-3.12 baseline.

    The baseline is a Python-level fiction: it changes what ``py.native``
    BELIEVES the interpreter is, not what the import machinery ACCEPTS. A test
    that performs a real ``import mm_core`` (or reads the real
    ``EXTENSION_SUFFIXES``) therefore has to run against the truth — see
    ``test_load_finds_prebuilt_and_handshakes`` for the incident that made
    this explicit (native run #134: on a free-threaded host the pinned tag
    ``<tag>`` pointed at ``mm_core.abi3.so``, a name such an interpreter
    cannot resolve at all, so the loader correctly reported "No module named
    'mm_core'" and the assertion — not the loader — was wrong).
    """
    _force_interpreter(
        monkeypatch,
        version=_REAL_VERSION,
        free_threaded=_REAL_GIL_DISABLED,
        abiflags=_REAL_ABIFLAGS,
    )


@pytest.fixture(autouse=True)
def _supported_interpreter_baseline(monkeypatch):
    """Pin every test here to a SUPPORTED GIL-3.12 interpreter.

    The floor guards (NEO-PLAN-2026-003) make ``platform_tag()`` / ``load()``
    depend on the RUNNING interpreter — without this pin the assertions below
    would flip on a 3.11 host (floor rejection instead of a tag) or on a
    free-threaded host (``<tag>t``). Tests that exercise other interpreter
    states override the signals again through ``_force_interpreter``; tests
    that touch the REAL import machinery undo the pin entirely through
    ``_use_real_interpreter``.
    """
    _force_interpreter(monkeypatch, version=(3, 12, 7))


def test_platform_tag_mapping(monkeypatch):
    native = _fresh_native()
    import platform

    cases = [
        (("Linux", "x86_64"), "linux-x86_64"),
        (("Linux", "amd64"), "linux-x86_64"),
        (("Linux", "aarch64"), "linux-aarch64"),
        (("Linux", "arm64"), "linux-aarch64"),
        (("Windows", "AMD64"), "windows-x86_64"),
        (("Windows", "x86_64"), "windows-x86_64"),
        (("Darwin", "arm64"), "macos-universal2"),
        (("Darwin", "x86_64"), "macos-universal2"),
        (("Plan9", "mips"), None),
        (("Linux", "riscv64"), None),
    ]
    for (system, machine), expected in cases:
        monkeypatch.setattr(platform, "system", lambda s=system: s)
        monkeypatch.setattr(platform, "machine", lambda m=machine: m)
        assert native.platform_tag() == expected, (system, machine)


def test_load_finds_prebuilt_and_handshakes(monkeypatch):
    """With native-bin/<tag>/ populated, load() succeeds and reports versions.

    Runs against the REAL host interpreter (``_use_real_interpreter``): this
    is the only test here that performs a real import of a real extension
    binary, and the autouse GIL-3.12 baseline is a fiction the import
    machinery does not honour. On a free-threaded host the PINNED tag
    (``<tag>``) points at the abi3 family, whose files such an interpreter
    cannot even RESOLVE — CPython compiles the ``.abi3*`` entries of
    ``_PyImport_DynLoadFiletab`` out under ``Py_GIL_DISABLED``
    (``Python/dynload_shlib.c``), so ``.abi3.so`` is absent from
    ``importlib.machinery.EXTENSION_SUFFIXES`` and ``mm_core.abi3.so`` can
    never answer to the module name ``mm_core``. The staged linux artifact
    carries ALL FOUR tag directories, so the file is present and the old
    skip guard did not fire: ``load()`` returned False with "import mm_core
    failed: No module named 'mm_core'" and this assertion — not the loader —
    was wrong (native run #134, integration ubuntu 3.15.0-rc.2t).
    """
    _use_real_interpreter(monkeypatch)
    native = _fresh_native()
    config = import_ext("config")
    config.extension_uri = str(REPO_ROOT)
    tag = native.platform_tag()
    # The stable-ABI file name follows the FLAVOUR: abi3t (PEP 803) for
    # free-threaded builds, abi3 for GIL builds. Windows keeps skipping — its
    # artifact is mm_core.pyd, the platform has no ABI-tagged suffix at all
    # (``Python/dynload_win.c``), and this probe has always been POSIX-shaped.
    family = "mm_core.abi3t.so" if native.is_free_threaded() else "mm_core.abi3.so"
    binary = REPO_ROOT / "native" / "native-bin" / (tag or "") / family
    if tag is None:
        # Reachable on a real host now that the pin is gone: free-threaded
        # 3.13/3.14 (no abi3t family) and GIL < 3.12 (below the abi3-py312
        # floor) have no tag at all — say why instead of "not present for None".
        why = native.tag_rejection_reason() or "unsupported platform"
        pytest.skip(f"no native-bin tag for this interpreter: {why}")
    if not binary.exists():
        pytest.skip(f"prebuilt {family} not present for {tag} (build it: scripts/build-native.sh --target {tag})")
    assert native.load() is True
    assert native.available() is True
    assert native.reason() is None
    core = native.core()
    assert core is not None
    assert core.api_version() == native.MIN_API_VERSION
    version = native.core_version()
    assert version and "+" in version  # "x.y.z+commit"
    diag = native.diagnostics()
    assert diag["available"] is True
    assert diag["platformTag"] == tag and diag["apiVersion"] == native.MIN_API_VERSION
    # The artifact really is the flavour this interpreter needs: a GIL build
    # loaded <tag>/mm_core.abi3.so, a free-threaded one <tag>t/mm_core.abi3t.so.
    assert (core.__file__ or "").endswith(family), core.__file__
    assert diag["freeThreaded"] is native.is_free_threaded()
    # Idempotence: a second load() must not re-import or flip state.
    assert native.load() is True


def test_extension_suffixes_enforce_the_flavour_split(monkeypatch):
    """The ``<tag>`` / ``<tag>t`` split is not a preference — it is the only
    thing the import machinery accepts (the mechanism behind the run #134
    failure above, pinned as a permanent guard).

    ``FileFinder._find_spec`` matches nothing but ``name + suffix`` over
    ``importlib.machinery.EXTENSION_SUFFIXES`` (``Lib/importlib/
    _bootstrap_external.py``), and that list IS ``_PyImport_DynLoadFiletab``
    (``_imp.extension_suffixes``). Measured across the flavours this project
    ships for:

    * GIL 3.12 — ``.abi3.so`` (the abi3-py312 family),
    * GIL 3.15.0rc2 — ``.abi3.so`` AND ``.abi3t.so`` (the ``.abi3t*`` entries
      are unconditional in ``Python/dynload_shlib.c``, which is what makes the
      abi3-import matrix's "3.15 GIL x abi3t artifact" cell meaningful),
    * free-threaded 3.15.0rc2t — ``.abi3t.so`` ONLY: the ``.abi3*`` entries sit
      inside ``#ifndef Py_GIL_DISABLED``, so a free-threaded build cannot even
      RESOLVE ``mm_core.abi3.so`` as the module ``mm_core``,
    * free-threaded 3.13.16t / 3.14.8t — still ``.abi3.so`` and no ``.abi3t``
      (the guard landed in 3.15), which is exactly why the loader refuses those
      EARLY with "abi3t requires 3.15+" instead of letting a GIL-only
      extension reach ``dlopen()`` in a no-GIL interpreter,
    * Windows (any flavour) — ``.pyd`` only: ``Python/dynload_win.c`` lists
      just ``PYD_TAGGED_SUFFIX`` / ``PYD_UNTAGGED_SUFFIX``
      (``.cp315[t]-win_amd64.pyd`` / ``.pyd``, ``Include/internal/
      pycore_importdl.h``), so there the flavour split rides on the DIRECTORY
      name, never on the file name.

    Read against the REAL host: the autouse baseline patches the very signals
    this asserts on.
    """
    import importlib.machinery
    import os

    _use_real_interpreter(monkeypatch)
    suffixes = importlib.machinery.EXTENSION_SUFFIXES
    if os.name != "posix":
        assert ".pyd" in suffixes, suffixes
        assert not any(s.startswith(".abi3") for s in suffixes), suffixes
    elif _REAL_FREE_THREADED and _REAL_VERSION[:2] >= (3, 15):
        assert ".abi3.so" not in suffixes, suffixes
        assert ".abi3t.so" in suffixes, suffixes
    else:
        assert ".abi3.so" in suffixes, suffixes


def test_core_if_enabled_never_raises_and_reports_none(tmp_path):
    """Phase 8 contract: ``core_if_enabled`` is the single entry point — it
    loads when the binary is there and returns None (never raises) when it is
    not; ``reason()`` carries the explanation for the ZipNN routes' error."""
    native = _fresh_native()
    _point_extension_at(tmp_path)  # no native/native-bin under tmp_path
    assert native.core_if_enabled() is None
    assert native.available() is False
    assert "native-bin directory missing" in (native.reason() or "")


def test_missing_binary_reports_reason_without_raising(tmp_path):
    """No prebuilt => load() False (never raises) + a human-readable reason."""
    native = _fresh_native()
    _point_extension_at(tmp_path)
    assert native.load() is False
    assert native.available() is False
    assert "native-bin directory missing" in (native.reason() or "")
    assert native.core() is None and native.core_version() is None


def test_unknown_platform_reports_reason(monkeypatch):
    native = _fresh_native()
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Plan9")
    monkeypatch.setattr(platform, "machine", lambda: "mips")
    assert native.platform_tag() is None
    assert native.load() is False
    assert "no prebuilt native core" in (native.reason() or "")


def test_api_version_mismatch_is_reported_and_not_leaked(tmp_path):
    """A binary with a foreign API version must be refused — with a reason,
    and without leaving the rejected module behind in sys.modules."""
    native = _fresh_native()
    tag = native.platform_tag()
    if tag is None:
        pytest.skip("unsupported platform")
    fake_bin = tmp_path / "native" / "native-bin" / tag
    fake_bin.mkdir(parents=True)
    (fake_bin / "mm_core.py").write_text(
        "def api_version():\n    return 999\n\ndef core_version():\n    return 'fake'\n",
        encoding="utf-8",
    )
    _point_extension_at(tmp_path)
    sys.modules.pop("mm_core", None)

    assert native.load() is False
    reason = native.reason() or ""
    assert "outside supported range" in reason
    # The rejected module must not be importable by accident elsewhere.
    assert "mm_core" not in sys.modules


def test_foreign_sys_modules_mm_core_is_rejected(tmp_path):
    """An ALREADY-IMPORTED foreign ``mm_core`` must not pass as ours.

    ``importlib.import_module`` short-circuits on ``sys.modules`` and never
    consults the appended native-bin directory in that case — without the
    origin guard, a same-named module from anywhere (another extension, a
    stray pip package) whose ``api_version()`` happens to match would be
    adopted as the native core.
    """
    import types

    native = _fresh_native()
    tag = native.platform_tag()
    if tag is None:
        pytest.skip("unsupported platform")
    bin_dir = tmp_path / "native" / "native-bin" / tag
    bin_dir.mkdir(parents=True)  # exists, but holds no binary
    foreign = types.ModuleType("mm_core")
    foreign.api_version = lambda: native.MIN_API_VERSION  # would PASS the handshake
    foreign.core_version = lambda: "foreign-not-ours"
    foreign.__file__ = str(tmp_path / "elsewhere" / "mm_core.abi3.so")
    sys.modules["mm_core"] = foreign
    _point_extension_at(tmp_path)

    assert native.load() is False
    assert native.available() is False
    assert "does not originate" in (native.reason() or "")
    # The foreign module is not ours to evict — it must stay untouched.
    assert sys.modules.get("mm_core") is foreign


def test_free_threaded_detection_and_t_tags(monkeypatch):
    """NEO-PLAN-2026-003: free-threaded 3.15+ is served by ``<tag>t`` (abi3t,
    PEP 803) on every platform — via BOTH detection signals — while the GIL
    build of the SAME 3.15 interpreter stays on the plain ``<tag>`` (the abi3
    artifacts load there too; double-shipping is avoided, Plan-3 §2-2)."""
    import platform

    native = _fresh_native()
    cases = [
        (("Linux", "x86_64"), "linux-x86_64t"),
        (("Linux", "aarch64"), "linux-aarch64t"),
        (("Windows", "AMD64"), "windows-x86_64t"),
        (("Darwin", "arm64"), "macos-universal2t"),
    ]
    for (system, machine), expected in cases:
        monkeypatch.setattr(platform, "system", lambda s=system: s)
        monkeypatch.setattr(platform, "machine", lambda m=machine: m)
        # Signal path 1: the Py_GIL_DISABLED build flag (abiflags empty —
        # Windows free-threaded builds have no sys.abiflags at all).
        _force_interpreter(monkeypatch, version=(3, 15, 0), free_threaded=True, abiflags="")
        assert native.is_free_threaded() is True, system
        assert native.platform_tag() == expected, system
        # Signal path 2: sys.abiflags "t" with Py_GIL_DISABLED reporting 0.
        _force_interpreter(monkeypatch, version=(3, 15, 0), free_threaded=False, abiflags="t")
        assert native.is_free_threaded() is True, system
        assert native.platform_tag() == expected, system
    # The GIL build of 3.15 keeps the abi3 family.
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    _force_interpreter(monkeypatch, version=(3, 15, 0))
    assert native.is_free_threaded() is False
    assert native.platform_tag() == "linux-x86_64"
    assert native.tag_rejection_reason() is None


def test_free_threaded_below_315_degrades_with_reason(monkeypatch, tmp_path):
    """abi3t exists only from 3.15 (PEP 803): free-threaded 3.13/3.14 have NO
    artifact family — the plain abi3 binaries must not be served to them (a
    free-threaded build cannot load them; CPython raises on the attempt). The
    loader converts that into the degrade contract: None tag + reason()."""
    import platform

    for version in ((3, 13, 2), (3, 14, 0)):
        native = _fresh_native()
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(platform, "machine", lambda: "x86_64")
        _force_interpreter(monkeypatch, version=version, free_threaded=True)
        assert native.platform_tag() is None, version
        assert "abi3t requires 3.15+" in (native.tag_rejection_reason() or "")
        _point_extension_at(tmp_path)
        assert native.load() is False
        reason = native.reason() or ""
        assert "abi3t requires 3.15+" in reason, reason
        assert "free-threaded" in reason, reason
        assert native.available() is False and native.core() is None


def test_gil_floor_guard_degrades_with_reason(monkeypatch, tmp_path):
    """GIL < 3.12 (the abi3-py312 floor): refuse BEFORE the import attempt —
    on an older interpreter the 3.12 stable-ABI binary fails with unreadable
    undefined-symbol errors, so the loader reports the floor instead
    (Plan-3 §3.3/R8). 3.12 itself is served."""
    import platform

    native = _fresh_native()
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    _force_interpreter(monkeypatch, version=(3, 11, 9))
    assert native.platform_tag() is None
    assert "abi3-py312 floor" in (native.tag_rejection_reason() or "")
    _point_extension_at(tmp_path)
    assert native.load() is False
    reason = native.reason() or ""
    assert "3.12+" in reason and "abi3-py312" in reason, reason

    # The floor version itself is supported (boundary: 3.12.0).
    native = _fresh_native()
    _force_interpreter(monkeypatch, version=(3, 12, 0))
    assert native.platform_tag() == "linux-x86_64"
    assert native.tag_rejection_reason() is None

    # 3.10 (the former floor, EOL 2026-10-01) is rejected too.
    native = _fresh_native()
    _force_interpreter(monkeypatch, version=(3, 10, 11))
    assert native.platform_tag() is None
    assert "abi3-py312 floor" in (native.tag_rejection_reason() or "")


def test_diagnostics_reports_free_threaded(monkeypatch):
    """diagnostics() grows the ``freeThreaded`` key (Plan-3 §3.3) so bug
    reports can tell the flavour the loader routed on."""
    import platform

    native = _fresh_native()
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    _force_interpreter(monkeypatch, version=(3, 15, 0), free_threaded=True)
    diag = native.diagnostics()
    assert diag["freeThreaded"] is True
    assert diag["platformTag"] == "linux-x86_64t"
    _force_interpreter(monkeypatch, version=(3, 12, 7))
    diag = native.diagnostics()
    assert diag["freeThreaded"] is False
    assert diag["platformTag"] == "linux-x86_64"
