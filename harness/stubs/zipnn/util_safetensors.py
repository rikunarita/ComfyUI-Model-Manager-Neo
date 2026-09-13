"""Harness stub of `zipnn.util_safetensors`."""

import json

METADATA_KEY = "znn_compressed_vectors"
COMPRESSION_METHOD = "HUFFMAN"
COMPRESSED_DTYPE = "uint8"


def build_compressed_tensor_info(tensor):
    return {"dtype": str(tensor.dtype).replace("torch.", ""), "shape": str(list(tensor.shape))}


def set_compressed_tensors_metadata(infos, metadata):
    if metadata is not None:
        metadata[METADATA_KEY] = json.dumps(infos)


def get_compressed_tensors_metadata(metadata):
    if metadata:
        return json.loads(metadata.get(METADATA_KEY) or "{}")
    return {}
