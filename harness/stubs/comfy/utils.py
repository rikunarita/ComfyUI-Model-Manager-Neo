"""Minimal `comfy.utils` stub for the verification harness."""


def safetensors_header(filename: str, max_size: int = 1024 * 1024):
    # The harness models carry no real safetensors header.
    return None
