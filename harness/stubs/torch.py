"""Harness stub of `torch` (only what py/compress.py needs).

The real ComfyUI runtime always provides torch; the harness must not pull the
550 MB wheel into CI, so `torch.frombuffer` / `torch.uint8` are stubbed here.
"""

from safetensors import StubTensor

uint8 = "uint8"
float32 = "float32"


def frombuffer(buffer, dtype=None):
    raw = bytes(buffer)
    return StubTensor(dtype or uint8, [len(raw)], raw)
