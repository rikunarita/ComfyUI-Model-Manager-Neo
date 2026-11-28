"""Unit tests for scripts/verify_native_binary.py (container verification).

Synthetic PE binaries are generated on the fly: the verifier is a pure-stdlib
parser, so the tests exercise it end to end without needing real builds or a
Windows host.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

import pytest

from harness import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "verify_native_binary.py"
_spec = importlib.util.spec_from_file_location("verify_native_binary", _SCRIPT)
assert _spec and _spec.loader
_verify = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("verify_native_binary", _verify)
_spec.loader.exec_module(_verify)

AMD64 = 0x8664
ARM64 = 0xAA64


def _pe(machine: int, python_dlls: list[bytes] | None = None) -> bytes:
    pe_off = 0x80
    data = bytearray(pe_off + 0x400)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, pe_off)
    data[pe_off : pe_off + 4] = b"PE\0\0"
    struct.pack_into("<H", data, pe_off + 4, machine)
    for dll in python_dlls or []:
        data += b"\0" + dll + b"\0"
    return bytes(data)


class TestPeMachineSelection:
    @pytest.mark.parametrize(
        ("tag", "machine", "ok"),
        [
            ("windows-x86_64", AMD64, True),
            ("windows-x86_64", ARM64, False),
            ("windows-x86_64t", AMD64, True),
            ("windows-x86_64t", ARM64, False),
            ("windows-arm64", ARM64, True),
            ("windows-arm64", AMD64, False),
            ("windows-arm64t", ARM64, True),
            ("windows-arm64t", AMD64, False),
        ],
    )
    def test_machine_match(self, tag: str, machine: int, ok: bool):
        result_ok, report = _verify.check_pe(_pe(machine), tag)
        assert result_ok is ok
        assert report["machine"] == f"{machine:#x}"
        if not ok:
            assert "error" in report

    def test_unknown_windows_tag_fails_closed(self):
        result_ok, report = _verify.check_pe(_pe(AMD64), "windows-rtx")
        assert result_ok is False
        assert "no known PE machine expectation" in report["error"]

    def test_stable_abi_forwarder_is_accepted(self):
        data = _pe(ARM64, [b"python3.dll"])
        result_ok, report = _verify.check_pe(data, "windows-arm64")
        assert result_ok is True
        assert report["python_dll_imports"] == ["python3.dll"]

    def test_versioned_python_dll_is_rejected(self):
        data = _pe(ARM64, [b"python3.dll", b"python312.dll"])
        result_ok, report = _verify.check_pe(data, "windows-arm64")
        assert result_ok is False
        assert "python312.dll" in report["error_libpython"]

    def test_amd64_still_rejected_as_arm64(self):
        # Real x86_64 artifacts must not pass the windows-arm64 verification.
        data = _pe(AMD64, [b"python3.dll"])
        result_ok, report = _verify.check_pe(data, "windows-arm64")
        assert result_ok is False


class TestBaseTag:
    @pytest.mark.parametrize(
        ("tag", "base"),
        [
            ("windows-x86_64", "windows-x86_64"),
            ("windows-x86_64t", "windows-x86_64"),
            ("windows-arm64", "windows-arm64"),
            ("windows-arm64t", "windows-arm64"),
            ("linux-x86_64t", "linux-x86_64"),
            ("macos-universal2t", "macos-universal2"),
        ],
    )
    def test_flavour_suffix_is_stripped(self, tag: str, base: str):
        assert _verify._base_tag(tag) == base
