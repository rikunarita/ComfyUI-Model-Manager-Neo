"""Harness stub of `safetensors.torch`."""

import base64
import json

from . import StubTensor


def save_file(tensors, path, metadata=None):
    doc = {
        "metadata": dict(metadata or {}),
        "tensors": {
            name: {
                "dtype": str(t.dtype),
                "shape": list(t.shape),
                "data_b64": base64.b64encode(t.payload).decode("ascii"),
            }
            for name, t in tensors.items()
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
