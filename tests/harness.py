"""Shared test/bench harness: extension imports, fake requests, safetensors I/O.

Pure-Python safetensors container I/O is deliberately NOT built on the
safetensors library so tests control the exact bytes (key order, padding):
the Rust writer's byte-exact restoration guarantee (Plan §4.7.4) is only
testable against known input bytes. Large synthetic models for the benches
are generated with torch/numpy instead (scripts/bench/gen_fixtures.py) —
the byte-level helpers here are for small, exact fixtures.
"""

from __future__ import annotations

import importlib
import json
import math
import struct
import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Extension module imports (ComfyUI stubs are installed by conftest.py /
# scripts/bench before this is used)
# ---------------------------------------------------------------------------
def import_ext(name: str):
    """Import ``py.<name>`` through the synthetic ``mmneo_py`` package.

    The extension modules use relative imports (``from . import config``),
    which only work inside a package; ``mmneo_py.__path__`` points at
    ``<repo>/py`` so the real ComfyUI entry point ``__init__.py`` (pip
    installs, web-dist downloads) is never executed.

    ``config.extension_uri`` is pointed at the repository root (idempotent):
    modules like ``py.native`` / ``py.compress`` resolve on-disk locations
    (``native/native-bin``, ``third_party``) through it.
    """
    pkg_name = "mmneo_py"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(REPO_ROOT / "py")]  # type: ignore[attr-defined]
        sys.modules[pkg_name] = pkg
    module = importlib.import_module(f"{pkg_name}.{name}")
    config = importlib.import_module(f"{pkg_name}.config")
    if not config.extension_uri:
        config.extension_uri = str(REPO_ROOT)
    return module


class FakeRequest:
    """Minimal aiohttp request stand-in for route handler tests."""

    def __init__(self, match_info: dict[str, str] | None = None, body: dict | None = None):
        self.match_info = match_info or {}
        self._body = body or {}
        self.query: dict[str, str] = {}
        self.headers: dict[str, str] = {}

    async def json(self) -> dict:
        return self._body

    async def post(self) -> dict:
        return self._body

    async def text(self) -> str:
        return json.dumps(self._body)

    def get(self, key: str, default: Any = None) -> Any:
        return self._body.get(key, default)


def json_body(response) -> dict:
    """Decode an aiohttp web.json_response payload."""
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# safetensors container (byte-exact control)
# ---------------------------------------------------------------------------
# safetensors 0.8 dtype name -> element size
DTYPE_SIZES = {
    "BOOL": 1,
    "U8": 1,
    "I8": 1,
    "F8_E5M2": 1,
    "F8_E4M3": 1,
    "F8_E4M3FNUZ": 1,
    "F8_E5M2FNUZ": 1,
    "F8_E8M0": 1,
    "F4": 1,
    "F6_E2M3": 1,
    "F6_E3M2": 1,
    "I16": 2,
    "U16": 2,
    "F16": 2,
    "BF16": 2,
    "I32": 4,
    "U32": 4,
    "F32": 4,
    "C64": 8,
    "F64": 8,
    "I64": 8,
    "U64": 8,
}

# torch dtype string (as recorded by znn_compressed_vectors) <-> safetensors name
TORCH_TO_ST = {
    "float32": "F32",
    "float16": "F16",
    "bfloat16": "BF16",
    "float64": "F64",
    "float8_e4m3fn": "F8_E4M3",
    "float8_e5m2": "F8_E5M2",
    "int8": "I8",
    "uint8": "U8",
    "int16": "I16",
    "int32": "I32",
    "int64": "I64",
    "bool": "BOOL",
    "complex64": "C64",
}


def write_safetensors(
    path: str | Path,
    tensors: dict[str, tuple[str, list[int], bytes]],
    metadata: dict[str, str] | None = None,
    sort_keys: bool = False,
) -> None:
    """Write a CANONICAL safetensors file. tensors: name -> (dtype, shape, raw bytes).

    Canonical = byte-identical to what the reference Rust serializer
    (`safetensors` 0.8 / `torch.save_file`) produces for the same logical
    content: compact JSON (no insignificant whitespace), `__metadata__`
    first, raw UTF-8 (ensure_ascii=False — serde_json keeps non-ASCII raw),
    and the header region space-padded to a multiple of 8 bytes. Neo's
    byte-exact restore guarantee is tested against THIS form.

    Key order follows dict insertion order unless ``sort_keys`` (the official
    library sorts by dtype-alignment-descending, then name); both orders must
    survive Neo's compress/decompress cycle byte-exactly.
    """
    header: dict[str, object] = {}
    names = sorted(tensors) if sort_keys else list(tensors)
    offset = 0
    if metadata is not None:
        header["__metadata__"] = metadata
    for name in names:
        dtype, shape, data = tensors[name]
        elem = DTYPE_SIZES[dtype]
        expected = elem * (math.prod(shape) if shape else 1)
        assert len(data) == expected, f"{name}: {len(data)} bytes != {expected}"
        header[name] = {"dtype": dtype, "shape": shape, "data_offsets": [offset, offset + len(data)]}
        offset += len(data)
    header_bytes = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    header_bytes += b" " * ((8 - len(header_bytes) % 8) % 8)  # reference 8-byte alignment
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(header_bytes)))
        f.write(header_bytes)
        for name in names:
            f.write(tensors[name][2])


def read_safetensors(path: str | Path) -> tuple[dict[str, Any], dict[str, tuple[str, list[int], bytes]]]:
    """Parse a safetensors file -> (header dict, name -> (dtype, shape, bytes))."""
    with open(path, "rb") as f:
        blob = f.read()
    (hlen,) = struct.unpack("<Q", blob[:8])
    header = json.loads(blob[8 : 8 + hlen])
    data_start = 8 + hlen
    tensors: dict[str, tuple[str, list[int], bytes]] = {}
    for name, spec in header.items():
        if name == "__metadata__":
            continue
        lo, hi = spec["data_offsets"]
        tensors[name] = (spec["dtype"], list(spec["shape"]), blob[data_start + lo : data_start + hi])
    return header, tensors


def sha256_file(path: str | Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Synthetic tensor payloads (small exact fixtures; large models: gen_fixtures)
# ---------------------------------------------------------------------------
def synth_bytes(n: int, seed: int = 1, low_entropy: bool = False) -> bytes:
    """n pseudo-random bytes (low_entropy: highly repetitive, compresses well)."""
    rng_state = seed & 0xFFFFFFFF
    out = bytearray()
    if low_entropy:
        pattern = bytes(((seed + i) & 0x03) | 0x3C for i in range(64))
        while len(out) < n:
            out += pattern
        return bytes(out[:n])
    for _ in range(n):
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        out.append((rng_state >> 16) & 0xFF)
    return bytes(out)


def synth_bf16(n: int, seed: int = 1, low_entropy: bool = False) -> bytes:
    """n bf16 values. low_entropy: normal-range weights (repeating exponents)."""
    out = bytearray()
    rng_state = seed & 0xFFFFFFFF
    for i in range(n):
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        weight = 0x3F80 | ((rng_state >> 9) & 0x007F) | (0x0100 if i & 1 else 0)  # ~1.0, alternating sign
        v = weight if low_entropy else ((rng_state >> 7) & 0xFFFF)
        out += struct.pack("<H", v)
    return bytes(out)


def synth_f32(n: int, seed: int = 1, low_entropy: bool = False) -> bytes:
    """n f32 values. low_entropy: Gaussian-ish weights around 0.25."""
    out = bytearray()
    rng_state = seed & 0xFFFFFFFF
    for i in range(n):
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        bits = (
            0x3E800000 | ((rng_state >> 8) & 0x007FFFFF) | (0x80000000 if (i % 7 == 3) else 0)
            if low_entropy
            else rng_state
        )
        out += struct.pack("<I", bits)
    return bytes(out)


def synth_f16(n: int, seed: int = 1, low_entropy: bool = False) -> bytes:
    out = bytearray()
    rng_state = seed & 0xFFFFFFFF
    for _i in range(n):
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        v = 0x3200 | ((rng_state >> 9) & 0x03FF) if low_entropy else (rng_state >> 7) & 0xFFFF  # ~0.25 with noise
        out += struct.pack("<H", v)
    return bytes(out)


def synth_fp8(n: int, seed: int = 1, low_entropy: bool = False) -> bytes:
    """n float8_e4m3fn-ish bytes (opaque payload; values are not interpreted)."""
    out = bytearray()
    rng_state = seed & 0xFFFFFFFF
    for _ in range(n):
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        if low_entropy:
            out.append(0x38 | ((rng_state >> 12) & 0x07))
        else:
            out.append((rng_state >> 16) & 0x7F)  # avoid 0x7F/0xFF NaN-ish variety
    return bytes(out)


# ---------------------------------------------------------------------------
# L4 model corpus (Plan §5.1 L4 / §6.2 Phase 2)
#
# Synthetic stand-ins for the corpus classes of the plan (sd1.5-fp16,
# sdxl-fp16, flux-fp8, LLM-bf16, VAE-f32, MoE huge-header, complex64 audio,
# f64 synth) — same dtypes / naming patterns / header shapes at CI-friendly
# sizes. The 12 GB-scale KPI runs use scripts/bench fixtures instead (the
# RAM ceiling of the dev sandbox, MEMO 2026-09-23); every file here must
# compress→decompress byte-exactly (sha256) through BOTH code paths.
# ---------------------------------------------------------------------------
def synth_u8(n: int, seed: int = 1) -> bytes:
    return synth_bytes(n, seed)


def synth_i32(n: int, seed: int = 1) -> bytes:
    out = bytearray()
    rng_state = seed & 0xFFFFFFFF
    for _ in range(n):
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        out += struct.pack("<i", (rng_state % 2000) - 1000)
    return bytes(out)


def synth_i64(n: int, seed: int = 1) -> bytes:
    out = bytearray()
    rng_state = seed & 0xFFFFFFFF
    for _ in range(n):
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        out += struct.pack("<q", rng_state % 50_000)  # small positives: high bytes zero
    return bytes(out)


def synth_c64(n: int, seed: int = 1) -> bytes:
    """n complex64 values (2 x f32) — audio-model style (pass-through class)."""
    out = bytearray()
    rng_state = seed & 0xFFFFFFFF
    for _ in range(n):
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        re = math.cos(rng_state / 1000.0) * 0.5
        im = math.sin(rng_state / 1000.0) * 0.5
        out += struct.pack("<ff", re, im)
    return bytes(out)


def synth_f64(n: int, seed: int = 1) -> bytes:
    """n float64 values — the f64 synth class (pass-through until Phase 4)."""
    out = bytearray()
    rng_state = seed & 0xFFFFFFFF
    for _ in range(n):
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        out += struct.pack("<d", (rng_state / 1000.0 - 1000.0) * 0.001)
    return bytes(out)


def build_corpus(root: str | Path) -> dict[str, Path]:
    """Write the L4 corpus under `root`; returns name → path.

    Key order is deliberately NOT the safetensors-rust sort order in half of
    the files (the harness writer preserves insertion order): Neo's restore
    must be byte-exact for unsorted-order files too — something the legacy
    torch round-trip cannot do (its save_file re-sorts).
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}

    def w(name: str, tensors, metadata=None, sort_keys=False):
        p = root / f"{name}.safetensors"
        write_safetensors(p, tensors, metadata, sort_keys=sort_keys)
        files[name] = p

    # sd1.5-fp16-like (F16 UNet blocks + I64 cond + U8 mask, unsorted keys)
    w(
        "sd15-fp16",
        {
            "unet.mid.attn.q.weight": ("F16", [32, 16], synth_f16(32 * 16, 11, low_entropy=True)),
            "cond_stage.embed.weight": ("F16", [64, 32], synth_f16(64 * 32, 12, low_entropy=True)),
            "pos.ids": ("I64", [24], synth_i64(24, 13)),
            "mask": ("U8", [16, 16], synth_u8(256, 14)),
        },
        {"format": "pt", "sd_version": "1.5"},
    )
    # sdxl-fp16-like (BF16 + F32 norm weights, sorted keys, empty-ish metadata)
    w(
        "sdxl-bf16",
        {
            "blocks.0.ff.weight": ("BF16", [64, 64], synth_bf16(64 * 64, 21, low_entropy=True)),
            "blocks.0.norm.weight": ("F32", [64], synth_f32(64, 22, low_entropy=True)),
            "time.embed": ("BF16", [128], synth_bf16(128, 23, low_entropy=True)),
        },
        {"format": "pt"},
        sort_keys=True,
    )
    # flux-fp8-like (F8_E4M3 + F8_E5M2 mixed)
    w(
        "flux-fp8",
        {
            "txt.attn.q": ("F8_E4M3", [128, 64], synth_fp8(128 * 64, 31, low_entropy=True)),
            "img.attn.k": ("F8_E5M2", [128, 64], synth_fp8(128 * 64, 32, low_entropy=True)),
            "scale": ("F32", [], synth_f32(1, 33)),  # scalar shape []
        },
        None,
    )
    # LLM-bf16-like (BF16 experts + I32 vocab + BOOL attention mask)
    w(
        "llm-bf16",
        {
            "model.embed_tokens.weight": ("BF16", [128, 96], synth_bf16(128 * 96, 41, low_entropy=True)),
            "model.layers.0.mlp.gate.weight": ("BF16", [96, 128], synth_bf16(96 * 128, 42, low_entropy=True)),
            "lm_head.weight": ("BF16", [128, 96], synth_bf16(128 * 96, 43, low_entropy=True)),
            "vocab": ("I32", [100], synth_i32(100, 44)),
            "causal_mask": ("BOOL", [8, 8], bytes((i * 7) % 2 for i in range(64))),
        },
        {"format": "pt", "transformers_version": "4.57.0"},
    )
    # VAE-f32-like
    w(
        "vae-f32",
        {
            "encoder.conv_in.weight": ("F32", [16, 4, 3, 3], synth_f32(16 * 4 * 3 * 3, 51, low_entropy=True)),
            "decoder.conv_out.bias": ("F32", [12], synth_f32(12, 52, low_entropy=True)),
        },
        {},  # explicit EMPTY metadata map (`"__metadata__":{}` must survive)
    )
    # MoE huge-header-like: many tiny tensors → header-dominated file
    moe = {}
    for i in range(600):
        # 128 elements = 256 B per expert: big enough that the ZN blob beats
        # the "not worth it" overhead rule, small enough to stay CI-friendly
        moe[f"experts.{i}.w"] = ("BF16", [16, 8], synth_bf16(128, 100 + i, low_entropy=True))
    w("moe-header", moe, {"format": "pt", "num_experts": "600"})
    # complex64 audio-like (C64 passes through untouched — out of band)
    w(
        "audio-c64",
        {
            "spec.weight": ("C64", [32, 16], synth_c64(32 * 16, 61)),
            "gain": ("F32", [256], synth_f32(256, 62, low_entropy=True)),
        },
        {"format": "pt"},
    )
    # f64 synth (F64 passes through in Phase 2 — the legacy path RAISES on
    # these files; Neo must not)
    w(
        "f64-synth",
        {
            "grid": ("F64", [24, 12], synth_f64(24 * 12, 71)),
            "w": ("BF16", [32, 32], synth_bf16(32 * 32, 72, low_entropy=True)),
        },
        {"format": "pt"},
    )
    # non-ASCII tensor names + unicode metadata (json.dumps escaping parity)
    w(
        "unicode-names",
        {
            "層.weight": ("BF16", [64, 32], synth_bf16(64 * 32, 81, low_entropy=True)),
            "emb🙂": ("F32", [256], synth_f32(256, 82, low_entropy=True)),
        },
        {"format": "pt", "author": "日本語テスト"},
    )
    return files
