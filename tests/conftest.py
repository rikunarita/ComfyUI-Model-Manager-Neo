"""Pytest configuration: installs the ComfyUI stubs and shared fixtures.

See tests/stubs.py for the stub semantics (verified against ComfyUI master)
and tests/harness.py for extension imports / fake requests / safetensors I/O.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import stubs

stubs.install()

from harness import import_ext


@pytest.fixture
def prompt_server():
    """Fresh PromptServer stub (routes + websocket event log) per test."""
    from server import PromptServer

    instance = PromptServer()
    PromptServer.instance = instance  # type: ignore[misc]
    # py.config captured the instance at import time - refresh both handles.
    config = import_ext("config")
    config.serverInstance = instance
    config.routes = instance.routes
    return instance


@pytest.fixture
def model_lib(tmp_path, prompt_server):
    """A model library rooted at tmp_path with a 'checkpoints' type folder."""
    import folder_paths

    root = tmp_path / "models"
    (root / "checkpoints").mkdir(parents=True)
    folder_paths.folder_names_and_paths.clear()
    folder_paths.folder_names_and_paths["checkpoints"] = ([str(root / "checkpoints")], {".safetensors"})
    # Defensive: drop the utils.resolve_model_base_paths() memo (its signature
    # check would also detect the change, but tests must not depend on that).
    utils = import_ext("utils")
    utils._base_paths_signature = None
    utils._base_paths_cache = {}
    return root
