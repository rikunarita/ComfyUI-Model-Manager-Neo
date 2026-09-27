"""Plan Phase 4 (L4): the Neo extension dtype band end-to-end.

Every safetensors 0.8 dtype (all 22 spellings) compresses through the
native pipeline: the five compatibility-band floats exactly like before
(official-decodable blobs, no marker), everything else through the Neo
extension band (codes 128-146, ``znn_neo_extended="1"`` marker, explicit
rejection by official tools — pinned by ``scripts/l5`` section E).

Gates covered here (Plan §6.2 Phase 4 完了条件 "全拡張 dtype 往復 green"):

* per-dtype round trip: compress → decompress → SHA-256 byte-exact,
  infos torch-name spelling, U8 blob storage, marker presence per band;
* the Python-side band classifier of the ``/zipnn/inspect`` route agrees
  with the ENGINE-written marker for every dtype (the two tables can never
  drift silently — one of them is golden-pinned to the other);
* truncation modes surface end-to-end (header byte 5 = 41/9/1/8 for
  zero-topped integer tensors) with byte-exact restore;
* sub-byte dtypes (F4 = 4-bit, F6_* = 6-bit packed) honour the reference
  shape semantics (``nelem * bits / 8`` bytes);
* the legacy (vendored zipnn) path fails CLEANLY on extension-band files
  (``ValueError: Unsupported Dtype``) — the documented migration behaviour;
* the inspect route contract (plain + compressed files, error paths).

Skips cleanly when no native binary exists for this platform (the CI verify
job); the native workflow's integration job runs it against the artifact.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest
from harness import (
    REPO_ROOT,
    import_ext,
    read_safetensors,
    sha256_file,
    synth_bf16,
    synth_bool,
    synth_c64,
    synth_f16,
    synth_f32,
    synth_f64,
    synth_fp8,
    synth_i16,
    synth_i64,
    synth_opaque_bytes,
    synth_u32,
    write_safetensors,
)
from test_phase2_native_pipeline import _compress, _decompress
from test_phase2_native_pipeline import mm as _imported_mm  # noqa: F401  (fixture re-export)
from test_phase2_routes import _legacy_available, _post_zipnn


@pytest.fixture
def mm(_imported_mm):  # noqa: F811 — pytest fixture wiring, not a redefinition
    """The real mm_core through the production loader (phase-2 fixture)."""
    return _imported_mm


# ---------------------------------------------------------------------------
# Per-dtype fixtures: (st dtype, torch name in infos, shape, payload bytes).
# Payloads are low-entropy so every tensor BEATS the "not worth it" size
# rule and is actually stored as a blob (otherwise the test proves nothing).
# ---------------------------------------------------------------------------
def _u16_concentrated(n: int, seed: int = 31) -> bytes:
    """u16 values 0x3F00-0x3FFF: the high byte is CONSTANT (huff0 collapses
    it), the low byte carries 8 bits of noise — the canonical (untruncated)
    2-plane integer layout still wins the size rule."""
    out = bytearray()
    x = seed & 0xFFFFFFFF
    for _ in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out += struct.pack("<H", 0x3F00 | (x & 0xFF))
    return bytes(out)


def _u32_concentrated(n: int, seed: int = 37) -> bytes:
    """u32 values 0x3F80xxxx: two constant high bytes + 16 noisy bits."""
    out = bytearray()
    x = seed & 0xFFFFFFFF
    for _ in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out += struct.pack("<I", 0x3F800000 | (x & 0xFFFF))
    return bytes(out)


DTYPE_CASES: list[tuple[str, str, list[int], bytes]] = [
    # --- compatibility band (official-decodable; NO marker) ---
    ("F32", "float32", [4096], synth_f32(4096, 2, low_entropy=True)),
    ("F16", "float16", [8192], synth_f16(8192, 3, low_entropy=True)),
    ("BF16", "bfloat16", [8192], synth_bf16(8192, 4, low_entropy=True)),
    ("F8_E4M3", "float8_e4m3fn", [16384], synth_fp8(16384, 5, low_entropy=True)),
    ("F8_E5M2", "float8_e5m2", [16384], synth_fp8(16384, 6, low_entropy=True)),
    # --- Neo extension band (marker REQUIRED) ---
    ("F64", "float64", [4096], synth_f64(4096, 7, low_entropy=True)),
    ("C64", "complex64", [4096], synth_c64(4096, 8)),
    ("I8", "int8", [16384], synth_opaque_bytes(16384, 9)),
    ("U8", "uint8", [16384], synth_opaque_bytes(16384, 10)),
    ("BOOL", "bool", [16384], synth_bool(16384, 11)),
    ("I16", "int16", [8192], _u16_concentrated(8192)),
    ("U16", "uint16", [8192], _u16_concentrated(8192, 33)),
    ("I32", "int32", [8192], _u32_concentrated(8192)),
    ("U32", "uint32", [8192], _u32_concentrated(8192, 39)),
    ("I64", "int64", [4096], synth_i64(4096, 14)),
    ("U64", "uint64", [4096], synth_i64(4096, 15)),
    ("F8_E4M3FNUZ", "float8_e4m3fnuz", [16384], synth_opaque_bytes(16384, 16)),
    ("F8_E5M2FNUZ", "float8_e5m2fnuz", [16384], synth_opaque_bytes(16384, 17)),
    ("F8_E8M0", "float8_e8m0fnu", [16384], synth_opaque_bytes(16384, 18)),
    # sub-byte packed types: shape counts ELEMENTS (nibbles / sextets)
    ("F4", "float4_e2m1fn_x2", [16384], synth_opaque_bytes(8192, 19)),
    ("F6_E2M3", "F6_E2M3", [8192], synth_opaque_bytes(6144, 20)),  # 8192*6/8
    ("F6_E3M2", "F6_E3M2", [8192], synth_opaque_bytes(6144, 21)),
]

COMPAT = {"F32", "F16", "BF16", "F8_E4M3", "F8_E5M2"}

INSPECT_ROUTE = ("POST", "/model-manager/zipnn/inspect")

CASE_IDS = [c[0] for c in DTYPE_CASES]


def _build(tmp_path: Path, st: str, shape: list[int], payload: bytes, name: str = "model") -> Path:
    src = tmp_path / f"{name}-{st}.safetensors"
    write_safetensors(src, {"w": (st, shape, payload)}, {"format": "pt"})
    return src


@pytest.mark.parametrize("st,torch_name,shape,payload", DTYPE_CASES, ids=CASE_IDS)
def test_dtype_roundtrip_and_marker(mm, tmp_path, st, torch_name, shape, payload):
    """The K14 gate per dtype: compress → blob stored with the right infos
    spelling → decompress → byte-exact, marker present iff Neo band."""
    src = _build(tmp_path, st, shape, payload)
    original_sha = sha256_file(src)

    # the Python-side classifier (inspect route) must agree with the engine
    compress_mod = import_ext("compress")
    info = compress_mod.inspect_safetensors_dtypes(str(src))
    assert "error" not in info, info
    assert info["dtypes"] == {st: 1}
    assert info["extended"] is (st not in COMPAT)
    assert info["extendedDtypes"] == ([] if st in COMPAT else [st])

    znn = tmp_path / f"out-{st}.znn.safetensors"
    cres = _compress(mm, src, znn)
    assert cres["stats"]["compressedTensors"] == 1, f"{st} must beat the size rule"
    assert cres["stats"]["tensors"] == 1

    header, tensors = read_safetensors(znn)
    meta = header["__metadata__"]
    infos = json.loads(meta["znn_compressed_vectors"])
    assert infos == {"w": {"dtype": torch_name, "shape": json.dumps(shape).replace('"', "")}}
    assert tensors["w"][0] == "U8", "stored as a ZN blob vector"
    if st in COMPAT:
        assert "znn_neo_extended" not in meta, f"{st} stays official-compatible"
    else:
        assert meta["znn_neo_extended"] == "1", f"{st} must flag the file"

    back = tmp_path / f"back-{st}.safetensors"
    dres = _decompress(mm, znn, back)
    assert dres["verified"] == "sha256"
    assert sha256_file(back) == original_sha, f"{st} restore must be byte-exact"
    # restored metadata is clean (no Neo bookkeeping leaks)
    rheader, rtensors = read_safetensors(back)
    assert not any(k.startswith("znn_") for k in rheader["__metadata__"])
    assert rtensors["w"] == (st, shape, payload)


@pytest.mark.parametrize("st,torch_name,shape,payload", DTYPE_CASES, ids=CASE_IDS)
def test_classifier_parity_is_pinned_by_the_engine(mm, tmp_path, st, torch_name, shape, payload):
    """COMPAT_ST_DTYPES (py/compress.py) ⇄ the Rust band table: the marker
    the ENGINE writes is the golden truth for the classifier. (The per-dtype
    test above asserts both sides; this one pins the constant table itself
    so a future dtype lands in exactly one of the two sets.)"""
    compress_mod = import_ext("compress")
    assert (st in compress_mod.COMPAT_ST_DTYPES) == (st in COMPAT)


def test_truncation_modes_end_to_end(mm, tmp_path):
    """Zero-topped integer tensors pick the truncation modes (header byte 5)
    and still restore byte-exactly; full-range values stay canonical."""
    cases = [
        # (dtype, values, expected byte5)
        ("I32", synth_u32(20480, 41, max_val=200), 1),  # < 2^8 → keep byte0
        ("U32", synth_u32(20480, 42, max_val=60_000), 9),  # < 2^16 → keep 2
        ("I32", synth_u32(20480, 43, max_val=10_000_000), 41),  # < 2^24 → 3
        ("U16", synth_i16(20480, 44, high_zero=True), 1),  # < 2^8 → low byte
        ("I32", _u32_concentrated(20480, 45), 220),  # full width → canonical
    ]
    for i, (st, payload, mode) in enumerate(cases):
        nelem = len(payload) // (4 if "32" in st else 2)
        src = tmp_path / f"trunc{i}-{st}.safetensors"
        write_safetensors(src, {"ids": (st, [nelem], payload)}, None)
        znn = tmp_path / f"trunc{i}.znn.safetensors"
        cres = _compress(mm, src, znn)
        assert cres["stats"]["compressedTensors"] == 1
        _header, tensors = read_safetensors(znn)
        blob = tensors["ids"][2]
        assert blob[:2] == b"ZN"
        assert blob[5] == mode, f"case {i} ({st}): byte5 {blob[5]} != {mode}"
        assert blob[15] >= 128, "Neo band code"
        back = tmp_path / f"trunc{i}.back.safetensors"
        _decompress(mm, znn, back)
        assert sha256_file(back) == sha256_file(src), f"case {i} byte-exact"

    # I16 multiples of 256 → the high-byte mode 8
    payload = b"".join(struct.pack("<H", (i % 200) * 256) for i in range(20480))
    src = tmp_path / "trunc-u16-high.safetensors"
    write_safetensors(src, {"ids": ("U16", [20480], payload)}, None)
    znn = tmp_path / "trunc-u16-high.znn.safetensors"
    _compress(mm, src, znn)
    _header, tensors = read_safetensors(znn)
    assert tensors["ids"][2][5] == 8
    back = tmp_path / "trunc-u16-high.back.safetensors"
    _decompress(mm, znn, back)
    assert sha256_file(back) == sha256_file(src)


def test_bool_and_e8m0_compress_hard(tmp_path, mm):
    """Plan §4.6.2 promises: BOOL {0,1} ≈ 1/8 via huff0; opaque 1-plane
    types collapse to their symbol entropy (the fixture carries 8 distinct
    bytes → ~3 bits/byte ≈ 0.375 + overhead). Measured, not assumed — the
    numbers also feed docs/BENCH.md §9."""
    for st, payload, max_ratio in [
        ("BOOL", synth_bool(1 << 16, 51), 0.20),
        ("F8_E8M0", synth_opaque_bytes(1 << 14, 52), 0.45),
    ]:
        src = _build(tmp_path, st, [len(payload)], payload, name="ratio")
        znn = tmp_path / f"ratio-{st}.znn.safetensors"
        _compress(mm, src, znn)
        blob = read_safetensors(znn)[1]["w"][2]
        ratio = len(blob) / len(payload)
        assert ratio < max_ratio, f"{st}: blob/raw = {ratio:.3f} ≥ {max_ratio}"


def test_marker_absent_when_neo_tensors_pass_through(mm, tmp_path):
    """A file whose only Neo-band tensors are TOO SMALL to beat the size
    rule stores them verbatim → every blob is compat-band → NO marker (the
    file stays readable by official tools; marker semantics = "contains
    Neo-band BLOBS", not "contains Neo-band dtypes")."""
    src = tmp_path / "mixed.safetensors"
    write_safetensors(
        src,
        {
            "w": ("BF16", [256, 128], synth_bf16(256 * 128, 61, low_entropy=True)),
            "tiny": ("F64", [4], struct.pack("<4d", 1.0, 2.0, 3.0, 4.0)),
        },
        {"format": "pt"},
    )
    znn = tmp_path / "mixed.znn.safetensors"
    cres = _compress(mm, src, znn)
    assert cres["stats"]["compressedTensors"] == 1, "only the bf16 tensor"
    header, tensors = read_safetensors(znn)
    assert "znn_neo_extended" not in header["__metadata__"]
    assert tensors["tiny"][0] == "F64", "pass-through keeps its dtype"
    back = tmp_path / "mixed.back.safetensors"
    _decompress(mm, znn, back)
    assert sha256_file(back) == sha256_file(src)


def test_legacy_engine_fails_cleanly_on_extended_files(mm, tmp_path):
    """The vendored zipnn 0.5.4 path must REJECT Neo-extension files with
    its explicit ValueError (never silent corruption), and its compressor
    keeps refusing f64 sources — the documented migration behaviour until
    Phase 7 removes the legacy path."""
    if not _legacy_available():
        pytest.skip("vendored ZipNN C core unavailable on this platform")
    src = tmp_path / "f64model.safetensors"
    write_safetensors(
        src,
        {"grid": ("F64", [512, 8], synth_f64(512 * 8, 71, low_entropy=True))},
        {"format": "pt"},
    )
    znn = tmp_path / "f64model.znn.safetensors"
    _compress(mm, src, znn)
    assert read_safetensors(znn)[0]["__metadata__"]["znn_neo_extended"] == "1"

    compress = import_ext("compress")
    # legacy DEcompress of the extension-band file → explicit dtype error
    back = tmp_path / "f64model.legacy.back.safetensors"
    with pytest.raises(Exception, match="Unsupported Dtype"):
        compress.decompress_safetensors(str(znn), str(back), lambda *_: None)
    assert not back.exists() and not Path(str(back) + ".tmp").exists()
    # legacy COMPRESS of the f64 source → its documented ValueError
    out2 = tmp_path / "f64model.legacy.znn.safetensors"
    with pytest.raises(ValueError, match="Support only"):
        compress.compress_safetensors(str(src), str(out2), lambda *_: None)
    assert not out2.exists()


# ---------------------------------------------------------------------------
# The /zipnn/inspect route (the confirm-dialog data source)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inspect_route_plain_and_compressed(prompt_server, model_lib, mm, tmp_path):
    from test_phase2_routes import _wait_task

    root = model_lib / "checkpoints"
    # plain file with a Neo-band dtype
    src = root / "inspected.safetensors"
    write_safetensors(
        src,
        {
            "w": ("BF16", [256, 128], synth_bf16(256 * 128, 81, low_entropy=True)),
            "ids": ("I32", [2048], synth_u32(2048, 82, max_val=200)),
            "grid": ("F64", [1024], synth_f64(1024, 83, low_entropy=True)),
        },
        {"format": "pt"},
    )
    compress, payload = await _post_zipnn(
        prompt_server,
        INSPECT_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": "inspected.safetensors"},
    )
    assert payload["success"] is True, payload
    data = payload["data"]
    assert "error" not in data, data
    assert data["compressed"] is False
    assert data["dtypes"] == {"BF16": 1, "I32": 1, "F64": 1}
    assert data["tensors"] == 3
    assert data["extended"] is True
    assert data["extendedDtypes"] == ["F64", "I32"]

    # compress it, then inspect the COMPRESSED file (marker + infos truth)
    compress, payload = await _post_zipnn(
        prompt_server,
        ("POST", "/model-manager/zipnn/compress"),
        {"type": "checkpoints", "pathIndex": 0, "fullname": "inspected.safetensors"},
    )
    task_id = payload["data"]["taskId"]
    assert await _wait_task(compress, task_id) == "complete"

    _c, payload = await _post_zipnn(
        prompt_server,
        INSPECT_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": "inspected.znn.safetensors"},
    )
    data = payload["data"]
    assert data["compressed"] is True
    assert data["extended"] is True
    assert data["compressedTensors"] == 3
    assert data["dtypes"] == {"bfloat16": 1, "int32": 1, "float64": 1}

    # error paths: unknown model / missing fields
    _c, payload = await _post_zipnn(
        prompt_server,
        INSPECT_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": "nope.safetensors"},
    )
    assert payload["success"] is False
    _c, payload = await _post_zipnn(prompt_server, INSPECT_ROUTE, {"type": "checkpoints"})
    assert payload["success"] is False


@pytest.mark.asyncio
async def test_inspect_route_compat_only_file(prompt_server, model_lib):
    root = model_lib / "checkpoints"
    src = root / "compat.safetensors"
    write_safetensors(
        src,
        {"w": ("BF16", [256, 128], synth_bf16(256 * 128, 91, low_entropy=True))},
        {"format": "pt"},
    )
    _c, payload = await _post_zipnn(
        prompt_server,
        INSPECT_ROUTE,
        {"type": "checkpoints", "pathIndex": 0, "fullname": "compat.safetensors"},
    )
    data = payload["data"]
    assert data["extended"] is False
    assert data["extendedDtypes"] == []
    assert data["dtypes"] == {"BF16": 1}


def test_inspect_helper_survives_broken_files(tmp_path):
    """inspect must answer with an error FIELD (the confirm dialog falls
    back to its generic message) — never raise into the route."""
    compress = import_ext("compress")
    junk = tmp_path / "junk.safetensors"
    junk.write_bytes(b"not a safetensors file at all")
    out = compress.inspect_safetensors_dtypes(str(junk))
    assert "error" in out
    missing = tmp_path / "missing.safetensors"
    out = compress.inspect_safetensors_dtypes(str(missing))
    assert "error" in out
    # a header that is VALID JSON but not an object (hostile/corrupt file)
    import struct

    weird = tmp_path / "weird.safetensors"
    body = b"[1,2,3]"
    weird.write_bytes(struct.pack("<Q", len(body)) + body)
    out = compress.inspect_safetensors_dtypes(str(weird))
    assert "error" in out


# ---------------------------------------------------------------------------
# torch-based cross-check (ubuntu integration cell / local dev only): real
# torch tensors of every saveable dtype through safetensors.torch.save_file
# — the shape/dtype spellings of the ACTUAL reference writer, not just the
# harness's byte-exact imitation.
# ---------------------------------------------------------------------------


def test_torch_saved_dtypes_roundtrip(mm, tmp_path):
    torch = pytest.importorskip("torch")
    safetensors_torch = pytest.importorskip("safetensors.torch")

    tensors: dict[str, object] = {
        "f64": torch.randn(512, dtype=torch.float64) * 0.01,
        "c64": torch.view_as_complex(torch.randn(512, 2, dtype=torch.float32) * 0.01),
        "i8": torch.randint(-8, 8, (4096,), dtype=torch.int8),
        "u8": torch.randint(0, 8, (4096,), dtype=torch.uint8),
        "b16": torch.randint(-200, 200, (4096,), dtype=torch.int16),
        "u16": torch.randint(0, 400, (4096,), dtype=torch.uint16),
        "i32": torch.randint(-40_000, 40_000, (4096,), dtype=torch.int32),
        "u32": torch.randint(0, 80_000, (4096,), dtype=torch.uint32),
        "i64": torch.randint(-40_000, 40_000, (4096,), dtype=torch.int64),
        "u64": torch.randint(0, 80_000, (4096,), dtype=torch.uint64),
        "bo": (torch.randint(0, 4, (4096,)) == 0),
        "fnuz4": torch.zeros(4096, dtype=torch.uint8).view(torch.float8_e4m3fnuz),
        "fnuz5": torch.zeros(4096, dtype=torch.uint8).view(torch.float8_e5m2fnuz),
        "e8m0": torch.zeros(4096, dtype=torch.uint8).view(torch.float8_e8m0fnu),
        "f4": torch.zeros(4096, dtype=torch.uint8).view(torch.float4_e2m1fn_x2),
        "bf": torch.randn(2048, dtype=torch.bfloat16) * 0.05,
    }
    # deterministic payload bytes for the noisy floats (byte-exactness is the
    # gate, values are irrelevant — but keep them low-entropy-ish)
    src = tmp_path / "torch-model.safetensors"
    safetensors_torch.save_file({k: v.contiguous() for k, v in tensors.items()}, str(src))
    original_sha = sha256_file(src)

    znn = tmp_path / "torch-model.znn.safetensors"
    _compress(mm, src, znn)
    header, _ = read_safetensors(znn)
    assert header["__metadata__"]["znn_neo_extended"] == "1"
    back = tmp_path / "torch-model.back.safetensors"
    dres = _decompress(mm, znn, back)
    assert dres["verified"] == "sha256"
    assert sha256_file(back) == original_sha
    # the official loader still reads every tensor back correctly
    # (float4 has no torch.equal kernel — compare the packed bytes via a
    # uint8 view, which is exactly what byte-exactness means for it)
    loaded = safetensors_torch.load_file(str(back))
    for k, v in tensors.items():
        got, want = loaded[k], v
        if got.dtype == torch.float4_e2m1fn_x2:
            got, want = got.view(torch.uint8), want.view(torch.uint8)
        assert torch.equal(got, want), k


def test_repo_native_loader_still_pins_api_3():
    """Phase 4 adds NO new Python-facing API (the dtype work is inside the
    codec) — the loader's exact-range handshake must stay [3, 3]."""
    native = import_ext("native")
    assert (native.MIN_API_VERSION, native.MAX_API_VERSION) == (3, 3)
    if not (REPO_ROOT / "native" / "native-bin").exists():
        return
    sys.modules.pop("mm_core", None)
    if native.load():
        assert native.core().api_version() == 3
