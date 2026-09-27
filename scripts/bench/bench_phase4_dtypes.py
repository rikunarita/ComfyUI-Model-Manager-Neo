#!/usr/bin/env python3
"""Phase 4 dtype coverage bench — the K14 evidence (Plan §2.2 K14, §6.2 Phase 4).

For EVERY safetensors 0.8 dtype (all 22 spellings) this builds a synthetic
weight-style tensor, runs it through the REAL production pipeline
(``mm_core.zipnn_compress`` / ``zipnn_decompress``) and records:

* the compression ratio (stored blob bytes / raw tensor bytes),
* the ZN header facts actually written (dtype code, byte_reorder mode —
  the truncation selection is visible here),
* round-trip verification (``verified == sha256`` + byte-exact restore).

The payloads are deterministic weight-style patterns (concentrated
sign/exponent floats, small-magnitude integers, sparse masks) — the same
"realistic-ish" class the L4 corpus uses; ratios on random noise would only
re-prove the huff0 threshold rule. Integer cases include BOTH a truncatable
and a full-range variant so the mode selection shows up in the record.

Usage::

    python3 scripts/bench/bench_phase4_dtypes.py \
        [--json-out scripts/bench/results/phase4_dtypes.json]

Requires: the built native binary (``scripts/build-native.sh --target <tag>``).
No torch needed (pure-struct fixtures). Exits non-zero when any dtype fails
the byte-exact round trip (the gate this bench exists for).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import struct
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# safetensors 0.8 dtype -> element bits (reference `Dtype::bitsize`)
BITS = {
    "BOOL": 8,
    "U8": 8,
    "I8": 8,
    "F8_E5M2": 8,
    "F8_E4M3": 8,
    "F8_E8M0": 8,
    "F8_E4M3FNUZ": 8,
    "F8_E5M2FNUZ": 8,
    "F4": 4,
    "F6_E2M3": 6,
    "F6_E3M2": 6,
    "I16": 16,
    "U16": 16,
    "F16": 16,
    "BF16": 16,
    "I32": 32,
    "U32": 32,
    "F32": 32,
    "C64": 64,
    "F64": 64,
    "I64": 64,
    "U64": 64,
}

# the compatibility band (official-decodable) — everything else is Neo
COMPAT = {"F32", "F16", "BF16", "F8_E4M3", "F8_E5M2"}


def write_safetensors(path: str, tensors: dict, metadata: dict | None) -> None:
    """Canonical safetensors writer (compact JSON, 8B space padding)."""
    header: dict = {}
    offset = 0
    if metadata is not None:
        header["__metadata__"] = metadata
    for name, (dtype, shape, data) in tensors.items():
        header[name] = {"dtype": dtype, "shape": shape, "data_offsets": [offset, offset + len(data)]}
        offset += len(data)
    hb = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    hb += b" " * ((8 - len(hb) % 8) % 8)
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(hb)))
        f.write(hb)
        for _, (_, _, data) in tensors.items():
            f.write(data)


def read_safetensors(path: str):
    with open(path, "rb") as f:
        img = f.read()
    (hlen,) = struct.unpack("<Q", img[:8])
    header = json.loads(img[8 : 8 + hlen])
    data = img[8 + hlen :]
    out = {}
    for name, spec in header.items():
        if name == "__metadata__":
            continue
        lo, hi = spec["data_offsets"]
        out[name] = (spec["dtype"], list(spec["shape"]), data[lo:hi])
    return header.get("__metadata__") or {}, out


class Rng:
    """The harness LCG (deterministic, dependency-free)."""

    def __init__(self, seed: int):
        self.x = seed & 0xFFFFFFFF

    def next(self) -> int:
        self.x = (self.x * 1103515245 + 12345) & 0x7FFFFFFF
        return self.x


def _floats(dtype: str, n: int, seed: int) -> bytes:
    """Weight-style floats: magnitudes in ~[2^-3, 2^-1] (concentrated
    sign/exponent bytes — the ZipNN target pattern), signs alternating."""
    r = Rng(seed)
    out = bytearray()
    if dtype == "F32":
        for _ in range(n):
            v = ((r.next() >> 8) / 8388608.0 - 1.0) * 0.05
            out += struct.pack("<f", v)
    elif dtype == "F64":
        for _ in range(n):
            v = ((r.next() >> 8) / 8388608.0 - 1.0) * 0.05
            out += struct.pack("<d", v)
    elif dtype == "BF16":
        for _ in range(n):
            v = 0x3F80 | ((r.next() >> 9) & 0x7F)  # |x| ≈ 1.0, mantissa noise
            out += struct.pack("<H", v)
    elif dtype == "F16":
        for _ in range(n):
            v = 0x3C00 | ((r.next() >> 10) & 0x1FF)  # |x| ≈ 1.0 (f16 bias)
            out += struct.pack("<H", v)
    elif dtype == "C64":
        for _ in range(n):
            re = math.cos(r.next() / 1000.0) * 0.25
            im = math.sin(r.next() / 1000.0) * 0.25
            out += struct.pack("<ff", re, im)
    return bytes(out)


def _payload(dtype: str, nelem: int, seed: int) -> bytes:
    """Deterministic weight/index/mask-style payload per dtype."""
    r = Rng(seed)
    if dtype in ("F32", "F64", "BF16", "F16", "C64"):
        return _floats(dtype, nelem, seed)
    nbytes = nelem * BITS[dtype] // 8
    if dtype == "BOOL":
        return bytes(1 if i % 4 == 0 else 0 for i in range(nelem))  # 25 % masks
    if dtype in ("I8",):
        return bytes(((r.next() % 16) - 8) & 0xFF for _ in range(nelem))
    if dtype in ("U8", "F8_E4M3", "F8_E5M2", "F8_E4M3FNUZ", "F8_E5M2FNUZ", "F8_E8M0", "F4", "F6_E2M3", "F6_E3M2"):
        # opaque low-entropy byte payloads (8 symbols → ~3 bits/byte)
        return bytes(0x38 | ((r.next() >> 12) & 0x07) for _ in range(nbytes))
    if dtype in ("I16", "U16"):
        # signed small-magnitude values (audio-PCM / quant-scale style):
        # the high byte is 0x00/0xFF (collapses under huff0) while both
        # planes stay NON-zero, so no truncation applies — the canonical
        # 2-plane path with a realistic ratio
        return b"".join(struct.pack("<h", r.next() % 201 - 100) for _ in range(nelem))
    if dtype in ("I32", "U32"):
        return b"".join(struct.pack("<I", r.next() % 100_000) for _ in range(nelem))
    if dtype in ("I64", "U64"):
        return b"".join(struct.pack("<Q", r.next() % 1_000_000) for _ in range(nelem))
    raise AssertionError(dtype)


def platform_tag() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux" and machine in ("x86_64", "amd64"):
        return "linux-x86_64"
    if system == "linux" and machine in ("aarch64", "arm64"):
        return "linux-aarch64"
    if system == "darwin":
        return "macos-universal2"
    if system == "windows" and machine in ("x86_64", "amd64"):
        return "windows-x86_64"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--elements", type=int, default=1 << 18, help="elements per dtype fixture")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    tag = platform_tag()
    bin_dir = os.path.join(REPO, "native", "native-bin", tag or "")
    if tag is None or not os.path.isdir(bin_dir):
        print(f"SKIP: no native binary for this platform at {bin_dir}")
        return 0
    sys.path.insert(0, bin_dir)
    import mm_core

    print(f"mm_core {mm_core.core_version()} (api {mm_core.api_version()})")

    tmp = tempfile.mkdtemp(prefix="mmneo-p4bench-")

    def job(handle, timeout=600.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _d, _t, phase = mm_core.job_progress(handle)
            if phase in ("done", "failed"):
                break
            time.sleep(0.005)
        err = mm_core.job_error(handle)
        if err:
            raise RuntimeError(err)
        assert phase == "done"
        return json.loads(mm_core.job_result(handle))

    n = args.elements
    records: dict[str, dict] = {}
    failures: list[str] = []
    dtypes = sorted(BITS, key=lambda d: (d not in COMPAT, d))
    for dtype in dtypes:
        bits = BITS[dtype]
        nelem = max(n, 4096)
        if bits == 4:
            nelem *= 2  # F4: shape counts nibbles
        elif bits == 6:
            nelem = (max(n, 4096) * 8) // 6 // 4 * 4  # byte-boundary element count
        payload = _payload(dtype, nelem, seed=1000 + len(dtype))
        src = os.path.join(tmp, f"{dtype}.safetensors")
        write_safetensors(src, {"w": (dtype, [nelem], payload)}, {"format": "pt"})
        raw = os.path.getsize(src)
        znn = os.path.join(tmp, f"{dtype}.znn.safetensors")
        t0 = time.monotonic()
        job(mm_core.zipnn_compress(src, znn, {"threads": 0}))
        t1 = time.monotonic()
        back = os.path.join(tmp, f"{dtype}.back.safetensors")
        dres = job(mm_core.zipnn_decompress(znn, back, {"threads": 0}))
        t2 = time.monotonic()

        meta, tensors = read_safetensors(znn)
        with open(back, "rb") as f:
            restored = f.read()
        with open(src, "rb") as f:
            original = f.read()
        byte_exact = restored == original
        stored_blob = tensors["w"][0] == "U8"
        blob_len = len(tensors["w"][2]) if stored_blob else None
        rec = {
            "band": "compat" if dtype in COMPAT else "neo",
            "elements": nelem,
            "rawBytes": len(payload),
            "storedAsBlob": stored_blob,
            "blobBytes": blob_len,
            "ratio": round(blob_len / len(payload), 4) if blob_len else None,
            "dtypeCode": tensors["w"][2][15] if stored_blob else None,
            "byteReorderMode": tensors["w"][2][5] if stored_blob else None,
            "extendedMarker": meta.get("znn_neo_extended") == "1",
            "verified": dres["verified"],
            "byteExact": byte_exact,
            "compressSec": round(t1 - t0, 3),
            "decompressSec": round(t2 - t1, 3),
            "fileSizeBytes": raw,
        }
        records[dtype] = rec
        ok = byte_exact and dres["verified"] == "sha256"
        expect_marker = (dtype not in COMPAT) and stored_blob
        if rec["extendedMarker"] != expect_marker:
            failures.append(f"{dtype}: marker {rec['extendedMarker']} != expected {expect_marker}")
        if not ok:
            failures.append(f"{dtype}: round trip failed ({dres['verified']}, exact={byte_exact})")
        print(
            f"{dtype:12s} {rec['band']:6s} code={rec['dtypeCode']} mode={rec['byteReorderMode']} "
            f"ratio={rec['ratio']} verified={rec['verified']} exact={byte_exact} "
            f"c={rec['compressSec']}s d={rec['decompressSec']}s"
        )

    # a truncation-selection showcase: full-range vs zero-topped integers
    trunc_cases = {
        "I32-trunc9(<2^16)": ("I32", b"".join(struct.pack("<I", 256 + (i * 61) % 60_000) for i in range(n)), 9),
        "I32-trunc1(<2^8)": ("I32", b"".join(struct.pack("<I", i % 200) for i in range(n)), 1),
        "U16-trunc8(mult-of-256)": ("U16", b"".join(struct.pack("<H", (i % 200) * 256) for i in range(n)), 8),
    }
    for ci, (label, (dtype, payload, want_mode)) in enumerate(trunc_cases.items()):
        nelem = len(payload) * 8 // BITS[dtype]
        src = os.path.join(tmp, f"trunc{ci}.safetensors")
        write_safetensors(src, {"w": (dtype, [nelem], payload)}, None)
        znn = os.path.join(tmp, f"trunc{ci}.znn.safetensors")
        job(mm_core.zipnn_compress(src, znn, {"threads": 0}))
        back = os.path.join(tmp, f"trunc{ci}.back.safetensors")
        dres = job(mm_core.zipnn_decompress(znn, back, {"threads": 0}))
        _m, t2 = read_safetensors(znn)
        blob = t2["w"][2]
        with open(back, "rb") as f, open(src, "rb") as g:
            exact = f.read() == g.read()
        records[label] = {
            "band": "neo",
            "elements": nelem,
            "rawBytes": len(payload),
            "storedAsBlob": True,
            "blobBytes": len(blob),
            "ratio": round(len(blob) / len(payload), 4),
            "byteReorderMode": blob[5],
            "verified": dres["verified"],
            "byteExact": exact,
        }
        if blob[5] != want_mode or not exact:
            failures.append(f"{label}: mode {blob[5]} (want {want_mode}) exact={exact}")
        print(f"{label:20s} mode={blob[5]} ratio={records[label]['ratio']} exact={exact}")

    covered = len([d for d in records if d in BITS])
    print(
        f"\nK14 coverage: {covered}/{len(BITS)} safetensors dtypes round-tripped ({'PASS' if not failures else 'FAIL'})"
    )

    out = {
        "env": {
            "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "platform": f"{platform.system()} {platform.machine()}",
            "python": platform.python_version(),
            "coreVersion": mm_core.core_version(),
            "elements": n,
        },
        "dtypes": records,
        "coverage": f"{covered}/{len(BITS)}",
        "failures": failures,
        "gate": not failures,
    }
    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print("report →", args.json_out)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
