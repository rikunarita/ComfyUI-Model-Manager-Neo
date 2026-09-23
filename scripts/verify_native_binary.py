#!/usr/bin/env python3
"""Verify a built mm_core extension binary (Plan §3.3, risk R3).

Pure-stdlib container parsing (no readelf/objdump on minimal hosts or CI):

* ELF64 (linux-x86_64 / linux-aarch64): e_machine must match the tag, every
  DT_NEEDED entry is printed (a versioned ``libpython3.*`` dependency is a
  HARD FAIL — abi3 + extension-module must not link libpython), and the
  maximum required GLIBC symbol version must be <= the floor (2.28 for the
  shipped zigbuild artifacts — wider coverage than the legacy C prebuilds'
  glibc >= 2.34).
* Mach-O / fat Mach-O (macos-universal2): both x86_64 and arm64 slices must
  be present.
* PE (windows-x86_64): machine must be x86_64; the ONLY python import
  allowed is the stable-ABI forwarder ``python3.dll``.

Usage: verify_native_binary.py <tag> <file> [--glibc-floor 2.28]
Exit code 0 = all checks passed; the JSON report is printed either way.
"""

from __future__ import annotations

import json
import re
import struct
import sys

EM_X86_64 = 62
EM_AARCH64 = 183
SHT_DYNAMIC = 6
SHT_GNU_VERNEED = 0x6FFFFFFE
DT_NEEDED = 1
DT_NULL = 0
MH_MAGIC_64 = 0xFEEDFACF
MH_CIGAM_64 = 0xCFFAEDFE
FAT_MAGIC = 0xCAFEBABE
FAT_MAGIC_64 = 0xCAFEBABF
CPU_TYPE_X86_64 = 0x01000007
CPU_TYPE_ARM64 = 0x0100000C
IMAGE_FILE_MACHINE_AMD64 = 0x8664


def _glibc_key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def check_elf(data: bytes, tag: str, glibc_floor: str) -> tuple[bool, dict]:
    report: dict[str, object] = {"format": "elf64"}
    ok = True
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        return False, {"format": "elf64", "error": "not a little-endian ELF64 file"}
    e_machine = struct.unpack_from("<H", data, 18)[0]
    expected = EM_X86_64 if tag == "linux-x86_64" else EM_AARCH64 if tag == "linux-aarch64" else None
    report["e_machine"] = e_machine
    if expected is not None and e_machine != expected:
        report["error"] = f"e_machine {e_machine} != expected {expected} for {tag}"
        ok = False
    e_shoff = struct.unpack_from("<Q", data, 0x28)[0]
    e_shentsize = struct.unpack_from("<H", data, 0x3A)[0]
    e_shnum = struct.unpack_from("<H", data, 0x3C)[0]
    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        sh_type = struct.unpack_from("<I", data, off + 4)[0]
        sh_offset = struct.unpack_from("<Q", data, off + 0x18)[0]
        sh_size = struct.unpack_from("<Q", data, off + 0x20)[0]
        sh_link = struct.unpack_from("<I", data, off + 0x28)[0]
        sections.append((sh_type, sh_offset, sh_size, sh_link))

    def cstr(strtab_off: int, str_off: int) -> str:
        end = data.index(b"\0", strtab_off + str_off)
        return data[strtab_off + str_off : end].decode("ascii", "replace")

    needed: list[str] = []
    glibc_versions: list[str] = []
    for sh_type, sh_offset, sh_size, sh_link in sections:
        if sh_type == SHT_DYNAMIC:
            strtab_off = sections[sh_link][1]
            for pos in range(sh_offset, sh_offset + sh_size, 16):
                d_tag, d_val = struct.unpack_from("<qQ", data, pos)
                if d_tag == DT_NULL:
                    break
                if d_tag == DT_NEEDED:
                    needed.append(cstr(strtab_off, d_val))
        elif sh_type == SHT_GNU_VERNEED:
            strtab_off = sections[sh_link][1]
            pos = sh_offset
            while pos < sh_offset + sh_size:
                _vn_version, vn_cnt, _vn_file, vn_aux, vn_next = struct.unpack_from("<HHIII", data, pos)
                aptr = pos + vn_aux
                for _ in range(vn_cnt):
                    _vna_hash, _vna_flags, _vna_other, vna_name, vna_next = struct.unpack_from("<IHHII", data, aptr)
                    glibc_versions.append(cstr(strtab_off, vna_name))
                    if vna_next == 0:
                        break
                    aptr += vna_next
                if vn_next == 0:
                    break
                pos += vn_next
    report["needed"] = needed
    bad = [n for n in needed if n.startswith("libpython")]
    if bad:
        report["error_libpython"] = f"links libpython (abi3 violation): {bad}"
        ok = False
    if glibc_versions:
        # Only GLIBC_* symbol versions bound the runtime floor; the same
        # section also carries e.g. GCC_4.2.0 (libgcc_s) and GLIBCXX_*
        # references, which are irrelevant to the glibc requirement.
        glibc_only = [v for v in glibc_versions if v.startswith("GLIBC_")]
        report["symbol_versions"] = sorted(set(glibc_versions), key=_glibc_key)
        if glibc_only:
            maxv = max(glibc_only, key=_glibc_key)
            report["max_glibc"] = maxv
            if _glibc_key(maxv) > _glibc_key(glibc_floor):
                report["error_glibc"] = f"requires {maxv} > floor GLIBC_{glibc_floor}"
                ok = False
    return ok, report


def check_macho(data: bytes, tag: str) -> tuple[bool, dict]:
    magic = struct.unpack_from(">I", data, 0)[0]
    archs: list[int] = []
    if magic in (FAT_MAGIC, FAT_MAGIC_64):
        nfat = struct.unpack_from(">I", data, 4)[0]
        for i in range(nfat):
            cputype = struct.unpack_from(">i", data, 8 + i * 20)[0]
            archs.append(cputype)
    elif magic in (MH_MAGIC_64, MH_CIGAM_64):
        archs.append(struct.unpack_from("<i", data, 4)[0])
    else:
        return False, {"format": "macho", "error": f"unknown magic {magic:#x}"}
    report: dict[str, object] = {"format": "macho", "archs": [f"{a:#x}" for a in archs]}
    ok = True
    if tag == "macos-universal2":
        missing = [n for n, t in (("x86_64", CPU_TYPE_X86_64), ("arm64", CPU_TYPE_ARM64)) if t not in archs]
        if missing:
            report["error"] = f"universal2 missing slices: {missing}"
            ok = False
    return ok, report


def check_pe(data: bytes, tag: str) -> tuple[bool, dict]:
    if data[:2] != b"MZ":
        return False, {"format": "pe", "error": "not a PE file"}
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off : pe_off + 4] != b"PE\0\0":
        return False, {"format": "pe", "error": "bad PE signature"}
    machine = struct.unpack_from("<H", data, pe_off + 4)[0]
    report: dict[str, object] = {"format": "pe", "machine": f"{machine:#x}"}
    ok = machine == IMAGE_FILE_MACHINE_AMD64
    if not ok:
        report["error"] = f"machine {machine:#x} != AMD64"
    pydlls = sorted({m.group(0).decode() for m in re.finditer(rb"python3\d*\.dll", data)})
    report["python_dll_imports"] = pydlls
    bad = [d for d in pydlls if d != "python3.dll"]
    if bad:
        report["error_libpython"] = f"versioned python DLL reference(s): {bad} (abi3 must use python3.dll only)"
        ok = False
    return ok, report


def main() -> int:
    argv = sys.argv[1:]
    floor = "2.28"
    pos: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--glibc-floor"):
            if "=" in a:
                floor = a.split("=", 1)[1]
            else:
                i += 1
                floor = argv[i]
        else:
            pos.append(a)
        i += 1
    if len(pos) != 2:
        print(__doc__)
        return 2
    tag, path = pos
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] == b"\x7fELF":
        ok, report = check_elf(data, tag, floor)
    elif data[:2] == b"MZ":
        ok, report = check_pe(data, tag)
    else:
        ok, report = check_macho(data, tag)
    report.update({"tag": tag, "path": path, "size_bytes": len(data), "ok": ok})
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
