"""Harness stub of `safetensors` (no torch / no rust core needed).

Implements just enough of the API surface used by py/compress.py:
`safe_open(...)` with keys()/get_tensor()/metadata() and
`safetensors.torch.save_file`. The on-disk container is a plain JSON blob -
it is only ever read back by this same stub, so the harness can exercise the
whole ZipNN pipeline (routes, sidecars, progress, inversion) without pulling
torch (550 MB) into CI.
"""

import base64
import json


class StubTensor:
    def __init__(self, dtype: str, shape, payload: bytes):
        self.dtype = dtype
        self.shape = list(shape)
        self._payload = payload

    def element_size(self) -> int:
        return {"uint8": 1, "float16": 2, "bfloat16": 2, "float32": 4, "float64": 8}.get(
            str(self.dtype).replace("torch.", ""), 1
        )

    def nelement(self) -> int:
        n = 1
        for d in self.shape:
            n *= int(d)
        return n

    def contiguous(self):
        return self

    def numpy(self):
        return self

    def clone(self):
        return StubTensor(self.dtype, self.shape, self._payload)

    @property
    def payload(self) -> bytes:
        return self._payload


class _SafeOpen:
    def __init__(self, path):
        with open(path, "r", encoding="utf-8") as f:
            self._doc = json.load(f)
        self._tensors = {
            name: StubTensor(
                info["dtype"], info["shape"], base64.b64decode(info["data_b64"])
            )
            for name, info in self._doc["tensors"].items()
        }

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def keys(self):
        return list(self._tensors.keys())

    def get_tensor(self, name):
        return self._tensors[name]

    def metadata(self):
        meta = dict(self._doc.get("metadata") or {})
        return meta if meta else None


def safe_open(path, framework="pt", device="cpu"):
    return _SafeOpen(path)
