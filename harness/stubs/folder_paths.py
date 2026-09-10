"""Minimal `folder_paths` stub for the verification harness.

Mirrors only the API surface the extension touches:
  - folder_names_and_paths
  - supported_pt_extensions
  - get_folder_paths()
  - filter_files_extensions()
"""

import os

supported_pt_extensions: set[str] = {
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".bin",
    ".gguf",
    ".onnx",
    ".pkl",
    ".pickle",
    ".sft",
}

# Filled in by the harness before the extension is imported.
folder_names_and_paths: dict[str, tuple[list[str], set[str]]] = {}


def get_folder_paths(folder: str) -> list[str]:
    return list(folder_names_and_paths[folder][0])


def filter_files_extensions(files: list[str], extensions: list[str]) -> list[str]:
    return [
        f
        for f in files
        if os.path.splitext(f)[1].lower() in extensions
        or os.path.splitext(f)[1] in extensions
    ]
