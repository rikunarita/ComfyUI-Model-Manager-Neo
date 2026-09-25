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
  official recipe records no ``znn_neo_src_sha256``, Plan §4.4.3-4);
* **delta cross-validation (Phase 3)**: Neo's streaming delta artifacts
  restore through the official ``ZipNN(delta_compressed_type="byte",
  is_streaming=True)`` path byte-exactly, and the official delta output —
  BOTH the single-container and the streaming form — restores through the
  Neo native delta decompressor byte-exactly.

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


# ---------------------------------------------------------------------------
# delta fixtures + the header-padding glue (pure struct — mirrors what BOTH
# sides require, so section D is a genuine engine-vs-engine cross-check)
# ---------------------------------------------------------------------------
def _st_split(path: str):
    with open(path, "rb") as f:
        img = f.read()
    (hlen,) = struct.unpack("<Q", img[:8])
    return hlen, img[8 : 8 + hlen], img[8 + hlen :]


def _padded_rendering(path: str, pad: int) -> bytes:
    hlen, header, data = _st_split(path)
    return struct.pack("<Q", hlen + pad) + header + b" " * pad + data


def _unpad(restored: bytes, pad: int) -> bytes:
    if not pad:
        return restored
    (padded_len,) = struct.unpack("<Q", restored[:8])
    original_len = padded_len - pad
    return struct.pack("<Q", original_len) + restored[8 : 8 + original_len] + restored[8 + padded_len :]


def build_delta_pair(base_path: str, ft_path: str) -> None:
    """base + fine-tune with an IDENTICAL tensor layout (delta-able) and
    different metadata (the headers differ in length → padding exercised)."""
    tensors = {
        "attn.q": ("BF16", [256, 64], _bf16(256 * 64)),
        "mlp.w": ("F32", [128, 96], _f32(128 * 96)),
    }
    write_st(base_path, tensors, {"format": "pt", "notes": "the base model checkpoint"})
    ft = {
        "attn.q": ("BF16", [256, 64], _bf16(256 * 64, seed=9)),
        "mlp.w": ("F32", [128, 96], _f32(128 * 96)),
    }
    write_st(ft_path, ft, {"format": "pt"})


def official_delta_compress(
    base: str, ft: str, out: str, streaming: bool, method: str | None = None
) -> tuple[int, int]:
    """The official byte-delta recipe (``zipnn_compress_file_delta.py``
    semantics via the pip library): pad both sides, XOR, FLOAT32 byte
    containers. ``method=None`` uses the zipnn.py API DEFAULT ("AUTO" →
    header byte 7 = 0 — the value the official decompressor ignores); the
    delta CLI's default is "HUFFMAN" (byte 7 = 1). Returns the
    (basePad, ftPad) the decompressor needs."""
    from zipnn import ZipNN

    base_len, _base_header, _ = _st_split(base)
    ft_len, _ft_header, _ = _st_split(ft)
    pad_base = max(0, ft_len - base_len)
    pad_ft = max(0, base_len - ft_len)
    base_bytes = _padded_rendering(base, pad_base)
    ft_bytes = _padded_rendering(ft, pad_ft)
    kwargs = {} if method is None else {"method": method}
    zpn = ZipNN(
        bytearray_dtype="float32",
        delta_compressed_type="byte",
        is_streaming=streaming,
        streaming_chunk=1024 * 1024,
        **kwargs,
    )
    compressed = zpn.compress(ft_bytes, delta_second_data=base_bytes)
    with open(out, "wb") as f:
        f.write(compressed)
    return pad_base, pad_ft


def official_delta_decompress(base: str, delta_path: str, pad_base: int, pad_ft: int) -> bytes:
    """The official streaming/non-streaming byte-delta restore."""
    from zipnn import ZipNN

    with open(delta_path, "rb") as f:
        delta_bytes = f.read()
    base_bytes = _padded_rendering(base, pad_base)
    zpn = ZipNN(is_streaming=True, delta_compressed_type="byte")
    restored = zpn.decompress(delta_bytes, delta_second_data=base_bytes)
    return _unpad(bytes(restored), pad_ft)


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

    # --- D. delta cross-validation (Phase 3) --------------------------------
    d_base = os.path.join(tmp, "l5.base.safetensors")
    d_ft = os.path.join(tmp, "l5.ft.safetensors")
    build_delta_pair(d_base, d_ft)
    with open(d_ft, "rb") as f:
        ft_original = f.read()
    ft_sha = _sha256(ft_original)

    # D1. Neo native delta compress (official STREAMING chain + ftSha256
    #     sidecar) → official zipnn decompress (streaming path)
    d_neo = os.path.join(tmp, "l5.neo_delta.znn")
    res = neo_job(mm, mm.zipnn_delta_compress(d_base, d_ft, d_neo, None))
    with open(d_neo + ".neo-delta.json", encoding="utf-8") as f:
        sidecar = json.load(f)
    if sidecar.get("ftSha256") != ft_sha:
        failures.append(f"D1: sidecar ftSha256 {sidecar.get('ftSha256')} != {ft_sha}")
    d_problems = []
    try:
        got = official_delta_decompress(d_base, d_neo, int(sidecar["basePad"]), int(sidecar["ftPad"]))
        if got != ft_original:
            d_problems.append("official decompress of the Neo streaming delta differs")
    except Exception as e:
        d_problems.append(f"official decompress of the Neo streaming delta raised: {e}")
    failures += [f"D1: {p}" for p in d_problems]
    print(f"D1. Neo streaming delta → official decompress: {'PASS' if not d_problems else 'FAIL ' + str(d_problems)}")

    # D2. official delta compress (single-container AND streaming) → Neo
    #     native delta decompress (verified=skipped: no ftSha256 sidecar)
    # single-container with the API-default method (AUTO → byte 7 = 0) AND
    # streaming with the CLI default (HUFFMAN → byte 7 = 1): both official
    # spellings must restore through the Neo native decompressor
    for tag, streaming, method in (("single", False, None), ("stream", True, "HUFFMAN")):
        d_off = os.path.join(tmp, f"l5.official_delta_{tag}.znn")
        pad_base, pad_ft = official_delta_compress(d_base, d_ft, d_off, streaming, method)
        d_out = os.path.join(tmp, f"l5.official_delta_{tag}.restored")
        meta = {"basePad": pad_base, "ftPad": pad_ft}
        try:
            res = neo_job(mm, mm.zipnn_delta_decompress(d_base, d_off, d_out, meta, None))
            with open(d_out, "rb") as f:
                got = f.read()
            ok = got == ft_original and res["verified"] == "skipped"
            if not ok:
                failures.append(f"D2-{tag}: restore mismatch (bytes={got == ft_original}, verified={res['verified']})")
        except Exception as e:
            failures.append(f"D2-{tag}: Neo decompress of the official delta raised: {e}")
            ok = False
        form = "streaming" if streaming else "single container"
        print(f"D2-{tag}. official delta ({form}) → Neo decompress: {'PASS' if ok else 'FAIL'}")

    if failures:
        print("\nL5 GATE: FAIL")
        for f in failures:
            print(" -", f)
        return 1
    print("\nL5 GATE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
