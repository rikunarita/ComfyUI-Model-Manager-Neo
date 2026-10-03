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
    import sysconfig

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


@pytest.fixture(autouse=True)
def _supported_interpreter_baseline(monkeypatch):
    """Pin every test here to a SUPPORTED GIL-3.12 interpreter.

    The floor guards (NEO-PLAN-2026-003) make ``platform_tag()`` / ``load()``
    depend on the RUNNING interpreter — without this pin the assertions below
    would flip on a 3.11 host (floor rejection instead of a tag) or on a
    free-threaded host (``<tag>t``). Tests that exercise other interpreter
    states override the signals again through ``_force_interpreter``.
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


def test_load_finds_prebuilt_and_handshakes():
    """With native-bin/<tag>/ populated, load() succeeds and reports versions."""
    native = _fresh_native()
    config = import_ext("config")
    config.extension_uri = str(REPO_ROOT)
    tag = native.platform_tag()
    binary = REPO_ROOT / "native" / "native-bin" / (tag or "") / "mm_core.abi3.so"
    if tag is None or not binary.exists():
        pytest.skip(f"prebuilt binary not present for {tag} (build it: scripts/build-native.sh --target {tag})")
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
    # Idempotence: a second load() must not re-import or flip state.
    assert native.load() is True


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
