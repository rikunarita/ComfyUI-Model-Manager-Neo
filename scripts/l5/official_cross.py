"""L5 interop gate (Plan §5.1 L5 / §6.2 Phase 2): Neo ⇄ OFFICIAL zipnn 0.5.4.

Runs against a pip-installed ``zipnn==0.5.4`` (the upstream release the
vendored copy mirrors — this script is the mechanical proof that they
behave identically) and the REAL Neo artifact (``native-bin`` →
``py.native`` → ``mm_core``):

* **Neo(Rust) compress → official decompress**: every tensor restored by the
  official ``ZipNN.decompress`` path must equal the original bytes
  (compatibility-band dtypes: f32/f16/bf16/fp8-e4m3/e5m2);
* **official compress → Neo decompress**: the file the official per-tensor
  recipe produces (``zipnn_compress_safetensors.py`` semantics: float tensors
  → ``ZipNN(input_format="torch")`` → uint8 vectors + infos metadata, others
  pass through) must restore through the Neo pipeline with every tensor
  byte-identical to the original (verification reports ``skipped`` — the
  official recipe records no ``znn_neo_src_sha256``, Plan §4.4.3-4).

Any mismatch exits non-zero with a first-difference report (CI gate).
Requires: linux + torch + safetensors + the built native binary. Skips
(exit 0 + loud notice) when the environment is incomplete — the CI
integration job pins exactly the right one.

Usage::

    pip install zipnn==0.5.4 torch safetensors
    python3 scripts/l5/official_cross.py [--keep-tmp DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import struct
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _have(mod: str) -> bool:
    return importlib.util.find_spec(mod) is not None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# minimal safetensors I/O (pure python — the fixtures are byte-controlled)
# ---------------------------------------------------------------------------
def write_st(path, tensors: dict, metadata: dict | None) -> None:
    header: dict = {}
    if metadata is not None:
        header["__metadata__"] = metadata
    blob = b""
    for name, (_dtype, _shape, raw) in tensors.items():
        header[name] = {
            "dtype": _dtype,
            "shape": _shape,
            "data_offsets": [len(blob), len(blob) + len(raw)],
        }
        blob += raw
    hb = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode()
    hb += b" " * ((8 - len(hb) % 8) % 8)
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(hb)))
        f.write(hb)
        f.write(blob)


def read_st(path):
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
    return header.get("__metadata__"), out


# ---------------------------------------------------------------------------
# fixtures: the compatibility band + pass-through companions
# ---------------------------------------------------------------------------
def _bf16(n, seed=7):
    x = seed
    out = bytearray()
    for _ in range(n):
        x = (x * 1664525 + 1013904223) & 0xFFFFFFFF
        out += struct.pack("<H", 0x3F80 | ((x >> 9) & 0x7F))
    return bytes(out)


def _f32(n, seed=11):
    x = seed
    out = bytearray()
    for _ in range(n):
        x = (x * 1664525 + 1013904223) & 0xFFFFFFFF
        v = ((x >> 8) & 0x007FFFFF) | 0x3E800000
        out += struct.pack("<I", v)
    return bytes(out)


def _f16(n, seed=13):
    x = seed
    out = bytearray()
    for _ in range(n):
        x = (x * 1664525 + 1013904223) & 0xFFFFFFFF
        out += struct.pack("<H", 0x3C00 | ((x >> 10) & 0x01FF))
    return bytes(out)


def _fp8(n, seed=17):
    x = seed
    out = bytearray()
    for _ in range(n):
        x = (x * 1664525 + 1013904223) & 0xFFFFFFFF
        out.append(0x38 | ((x >> 12) & 0x07))
    return bytes(out)


def build_fixture(path) -> dict:
    tensors = {
        "attn.q": ("BF16", [256, 64], _bf16(256 * 64)),
        "attn.k": ("F16", [256, 64], _f16(256 * 64)),
        "mlp.w": ("F32", [128, 96], _f32(128 * 96)),
        "img.q": ("F8_E4M3", [512, 8], _fp8(512 * 8)),
        "img.k": ("F8_E5M2", [512, 8], _fp8(512 * 8, 19)),
        "vocab": ("I32", [64], bytes(64 * 4)),
        "mask": ("U8", [64], bytes(range(64))),
    }
    write_st(path, tensors, {"format": "pt"})
    return tensors


# ---------------------------------------------------------------------------
# the official side (pip zipnn 0.5.4)
# ---------------------------------------------------------------------------
def official_decompress_check(znn_path: str, original: dict) -> list[str]:
    """Official-script decompression of a Neo-compressed file; returns the
    list of tensor mismatches (empty = PASS)."""
    from safetensors import safe_open
    from zipnn import ZipNN
    from zipnn.util_safetensors import (
        COMPRESSED_DTYPE,
        COMPRESSION_METHOD,
        get_compressed_tensors_metadata,
    )

    problems = []
    with safe_open(znn_path, "pt", "cpu") as f:
        infos = get_compressed_tensors_metadata(f.metadata() or {})
        znn = ZipNN(input_format="torch", bytearray_dtype=COMPRESSED_DTYPE, method=COMPRESSION_METHOD)
        for name in list(f.keys()):
            tensor = f.get_tensor(name)
            if name in infos:
                tensor = znn.decompress(tensor.contiguous().numpy())
            got_dtype, got_shape, got = _torch_bytes(tensor)
            want_dtype, want_shape, want = original[name]
            if got != want:
                problems.append(f"{name}: bytes differ (official decode of a Neo blob)")
            if got_dtype != want_dtype or got_shape != want_shape:
                problems.append(f"{name}: dtype/shape differ: {got_dtype}{got_shape} vs {want_dtype}{want_shape}")
    return problems


def _torch_bytes(tensor):
    import torch

    dt_map = {
        "torch.bfloat16": "BF16",
        "torch.float16": "F16",
        "torch.float32": "F32",
        "torch.float8_e4m3fn": "F8_E4M3",
        "torch.float8_e5m2": "F8_E5M2",
        "torch.int32": "I32",
        "torch.uint8": "U8",
        "torch.int64": "I64",
        "torch.bool": "BOOL",
    }
    st = dt_map.get(str(tensor.dtype), str(tensor.dtype))
    if tensor.dtype.is_floating_point:
        # bf16/fp8 have no numpy dtype — view the raw little-endian bytes
        np_t = tensor.contiguous().view(torch.uint8).numpy()
    else:
        np_t = tensor.contiguous().numpy()
    return st, [int(d) for d in tensor.shape], np_t.tobytes()


def official_compress(src_path: str, dst_path: str) -> None:
    """The official zipnn_compress_safetensors.py recipe (0.5.4 semantics):
    float tensors → ZipNN(input_format="torch") → uint8 vector + infos,
    non-float / not-worth-it → verbatim."""
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

    tensors: dict = {}
    infos: dict = {}
    with safe_open(src_path, "pt", "cpu") as f:
        for name in list(f.keys()):
            tensor = f.get_tensor(name)
            if not zipnn_is_floating_point(EnumFormat.TORCH.value, tensor, tensor.dtype):
                tensors[name] = tensor
                continue
            znn = ZipNN(input_format="torch", bytearray_dtype=tensor.dtype, method=COMPRESSION_METHOD)
            size = tensor.element_size() * tensor.nelement()
            buf = znn.compress(tensor.clone())
            if len(buf) >= size:
                tensors[name] = tensor
            else:
                tensors[name] = torch.frombuffer(bytearray(buf), dtype=COMPRESSED_DTYPE)
                infos[name] = build_compressed_tensor_info(tensor)
        metadata = f.metadata() or {}
    set_compressed_tensors_metadata(infos, metadata)
    save_file(tensors, dst_path, metadata)


# ---------------------------------------------------------------------------
# the Neo side (native pipeline through the production loader)
# ---------------------------------------------------------------------------
def neo_core():
    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "tests"))
    import stubs

    stubs.install()
    from harness import import_ext

    config = import_ext("config")
    config.extension_uri = REPO
    native = import_ext("native")
    native._module = None
    native._reason = None
    native._attempted = False
    if not native.load():
        raise RuntimeError(f"native core unavailable: {native.reason()}")
    return native.core()


def neo_job(mm, handle: int, timeout: float = 300.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _d, _t, phase = mm.job_progress(handle)
        if phase in ("done", "failed"):
            break
        time.sleep(0.01)
    else:
        raise TimeoutError("neo job stuck")
    err = mm.job_error(handle)
    if err:
        raise RuntimeError(err)
    return json.loads(mm.job_result(handle))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep-tmp", default=None)
    args = ap.parse_args()

    missing = [m for m in ("torch", "safetensors", "zipnn") if not _have(m)]
    if missing:
        print(f"L5 SKIP: missing pip packages {missing} (pip install zipnn==0.5.4 torch safetensors)")
        return 0
    import zipnn

    try:
        from importlib.metadata import version as _pkg_version

        version = _pkg_version("zipnn")
    except Exception:
        version = getattr(zipnn, "__version__", "?")
    print(f"L5 official cross-validation against pip zipnn {version}")

    tmp = args.keep_tmp or tempfile.mkdtemp(prefix="mmneo-l5-")
    os.makedirs(tmp, exist_ok=True)
    src = os.path.join(tmp, "l5.safetensors")
    original = build_fixture(src)
    failures: list[str] = []

    mm = neo_core()
    print("native core:", mm.core_version())

    # --- A. Neo compress → official decompress -----------------------------
    neo_znn = os.path.join(tmp, "l5.neo.znn.safetensors")
    res = neo_job(mm, mm.zipnn_compress(src, neo_znn, None))
    print("A. Neo compress ok:", res["stats"])
    problems = official_decompress_check(neo_znn, original)
    if problems:
        failures += [f"A: {p}" for p in problems]
    print(f"A. Neo → official decompress: {'PASS' if not problems else 'FAIL ' + str(problems)}")

    # --- B. official compress → Neo decompress ------------------------------
    off_znn = os.path.join(tmp, "l5.official.znn.safetensors")
    official_compress(src, off_znn)
    restored = os.path.join(tmp, "l5.restored.safetensors")
    res = neo_job(mm, mm.zipnn_decompress(off_znn, restored, None))
    print("B. Neo decompress of the official file:", res["stats"], "verified:", res["verified"])
    if res["verified"] != "skipped":
        failures.append(f"B: expected verification 'skipped' for an official file, got {res['verified']}")
    _meta, got = read_st(restored)
    for name, (dtype, shape, raw) in original.items():
        if name not in got:
            failures.append(f"B: tensor {name} missing in the Neo restore")
            continue
        g_dtype, g_shape, g_raw = got[name]
        if (g_dtype, g_shape, g_raw) != (dtype, shape, raw):
            first = next(
                (i for i, (a, b) in enumerate(zip(raw, g_raw, strict=False)) if a != b), min(len(raw), len(g_raw))
            )
            failures.append(f"B: tensor {name} differs (dtype/shape/bytes; first diff at {first})")
    print(f"B. official → Neo decompress: {'PASS' if not any(f.startswith('B') for f in failures) else 'FAIL'}")

    # --- C. blob parity: the two compressors store identical bytes ----------
    _m1, t1 = read_st(neo_znn)
    _m2, t2 = read_st(off_znn)
    shared = sorted(set(t1) & set(t2))
    diff = [n for n in shared if t1[n][2] != t2[n][2]]
    if diff:
        failures.append(f"C: stored tensor bytes differ between Neo and official compress: {diff}")
    print(f"C. blob parity on {len(shared)} tensors: {'PASS' if not diff else 'FAIL ' + str(diff)}")

    if failures:
        print("\nL5 GATE: FAIL")
        for f in failures:
            print(" -", f)
        return 1
    print("\nL5 GATE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
