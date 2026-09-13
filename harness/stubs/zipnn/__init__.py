"""Harness stub of `zipnn` (the real package needs torch + a C++ build).

Reversible zlib-based stand-in with the exact API surface py/compress.py uses.
"""

import zlib

from . import util_header, util_safetensors, util_torch  # noqa: F401


class ZipNN:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.threads = 2

    def compress(self, tensor):
        payload = tensor.payload if hasattr(tensor, "payload") else bytes(tensor)
        return b"ZNSTUB" + zlib.compress(payload, 6)

    def decompress(self, tensor):
        payload = tensor.payload if hasattr(tensor, "payload") else bytes(tensor)
        assert payload.startswith(b"ZNSTUB"), "not a stub-compressed buffer"
        raw = zlib.decompress(payload[len(b"ZNSTUB"):])
        from safetensors import StubTensor

        return StubTensor("float32", [len(raw)], raw)
