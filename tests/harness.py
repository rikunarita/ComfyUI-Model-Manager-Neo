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
    """Write a safetensors file. tensors: name -> (dtype, shape, raw bytes).

    Key order follows dict insertion order unless ``sort_keys`` (the official
    library sorts); both orders must survive Neo's compress/decompress cycle.
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
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
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
