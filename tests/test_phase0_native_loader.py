"""Plan Phase 0: py/native.py loader — platform tags, MM_NATIVE switch, handshake.

Written against the loader's public surface: ``platform_tag`` / ``native_mode``
/ ``load`` / ``available`` / ``core`` / ``reason`` / ``core_version`` /
``diagnostics``. The loader caches its attempt in module state, so every test
reloads ``mmneo_py.native``; an autouse fixture restores ``sys.path`` and
``sys.modules["mm_core"]`` because ``load()`` appends the binary directory to
the import path.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from harness import REPO_ROOT, import_ext


@pytest.fixture(autouse=True)
def _isolate_loader_state(monkeypatch):
    """Undo the loader's global side effects between tests."""
    monkeypatch.delenv("MM_NATIVE", raising=False)
    path_snapshot = list(sys.path)
    module_snapshot = sys.modules.get("mm_core")
    yield
    sys.path[:] = path_snapshot
    sys.modules.pop("mm_core", None)
    if module_snapshot is not None:
        sys.modules["mm_core"] = module_snapshot


def _fresh_native():
    """(Re-)import py.native with pristine attempt state; returns the module."""
    native = import_ext("native")
    return importlib.reload(native)


def _point_extension_at(tmp_path: Path) -> None:
    config = import_ext("config")
    config.extension_uri = str(tmp_path)


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


def test_native_mode_normalization(monkeypatch):
    native = _fresh_native()
    for raw in ("0", "off", "false", "no", " OFF ", "No"):
        monkeypatch.setenv("MM_NATIVE", raw)
        assert native.native_mode() == "0", raw
    for raw in ("1", "on", "true", "yes", " TRUE "):
        monkeypatch.setenv("MM_NATIVE", raw)
        assert native.native_mode() == "1", raw
    for raw in ("", "banana", "2", "maybe"):
        monkeypatch.setenv("MM_NATIVE", raw)
        assert native.native_mode() == "auto", raw
    monkeypatch.delenv("MM_NATIVE")
    assert native.native_mode() == "auto"


def test_auto_mode_loads_prebuilt_and_handshakes():
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
    assert diag["available"] is True and diag["mode"] == "auto"
    assert diag["platformTag"] == tag and diag["apiVersion"] == native.MIN_API_VERSION
    # Idempotence: a second load() must not re-import or flip state.
    assert native.load() is True


def test_disabled_mode_never_loads(monkeypatch):
    monkeypatch.setenv("MM_NATIVE", "0")
    native = _fresh_native()
    assert native.load() is False
    assert native.available() is False
    assert "MM_NATIVE=0" in (native.reason() or "")
    assert native.diagnostics()["mode"] == "0"


def test_required_mode_raises_when_unavailable(monkeypatch, tmp_path):
    """MM_NATIVE=1 must never silently fall back to the legacy path (§5.4)."""
    monkeypatch.setenv("MM_NATIVE", "1")
    native = _fresh_native()
    _point_extension_at(tmp_path)  # no native/native-bin under tmp_path
    with pytest.raises(RuntimeError, match="MM_NATIVE=1"):
        native.load()


def test_missing_binary_reports_reason_without_raising(tmp_path):
    """auto mode + no prebuilt => available False + a human-readable reason."""
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
