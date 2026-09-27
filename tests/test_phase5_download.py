"""Phase 5 download inline-verification tests (Plan §4.8-B1 / K7).

The download write loop feeds a native hasher as bytes land, so a finished
Civitai download's SHA256 is verified WITHOUT the extra full re-read the legacy
`_sha256_of` did. These tests drive `_download_complete` directly (the digest
is staged in `_inline_sha256` exactly as the write loop does) and assert:

* a staged digest that MATCHES completes the download (file lands in the
  library, the staged value is consumed);
* a staged digest that MISMATCHES deletes the partial file and fails the task
  (the integrity gate still bites);
* with NO staged digest (legacy engine, resumed-complete file) it falls back to
  the `_sha256_of` re-read and still verifies correctly.

The hasher primitive itself (chunk-size-independent SHA256) is golden-tested
against `hash_file` in test_phase5_scan.py.
"""

from __future__ import annotations

import hashlib
import os

import pytest
from harness import import_ext


def _make_task(download_mod, md, task_id: str, data: bytes, sha_upper: str, tmp_file: str):
    content = download_mod.TaskContent(
        type="checkpoints",
        pathIndex=0,
        fullname="m.safetensors",
        description="note body",
        downloadPlatform="civitai",
        downloadUrl=None,
        sizeBytes=len(data),
        hashes={"SHA256": sha_upper},
    )
    md.set_task_content(task_id, content)
    with open(tmp_file, "wb") as f:
        f.write(data)


@pytest.fixture
def download_env(prompt_server, model_lib, tmp_path, monkeypatch):
    """Point the download dir at tmp_path (keep REPO_ROOT clean) and hand back
    the (download module, ModelDownload instance, tmp-file path)."""
    config = import_ext("config")
    monkeypatch.setattr(config, "extension_uri", str(tmp_path))
    download = import_ext("download")
    utils = import_ext("utils")
    md = download.ModelDownload()
    dl_path = utils.get_download_path()
    return download, md, utils, dl_path


@pytest.mark.asyncio
async def test_download_complete_accepts_a_matching_inline_sha(download_env):
    _download, md, utils, dl_path = download_env
    task_id = "inline-match"
    data = b"downloaded model bytes" * 100
    sha = hashlib.sha256(data).hexdigest().upper()
    tmp_file = utils.join_path(dl_path, f"{task_id}.download")
    _make_task(_download, md, task_id, data, sha, tmp_file)

    # The write loop staged the inline digest (uppercase, like hash_file).
    md._inline_sha256[task_id] = sha
    await md._download_complete(task_id)

    model_path = utils.get_full_path("checkpoints", 0, "m.safetensors")
    assert os.path.isfile(model_path), "the download landed in the library"
    assert not os.path.exists(tmp_file), "the .download partial is gone"
    assert task_id not in md._inline_sha256, "the staged digest was consumed"


@pytest.mark.asyncio
async def test_download_complete_rejects_a_mismatching_inline_sha(download_env):
    _download, md, utils, dl_path = download_env
    task_id = "inline-mismatch"
    data = b"corrupted bytes" * 100
    published = hashlib.sha256(b"the REAL bytes").hexdigest().upper()  # != data
    tmp_file = utils.join_path(dl_path, f"{task_id}.download")
    _make_task(_download, md, task_id, data, published, tmp_file)

    md._inline_sha256[task_id] = hashlib.sha256(data).hexdigest().upper()  # honest digest of the corrupt bytes
    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        await md._download_complete(task_id)
    assert not os.path.exists(tmp_file), "a mismatch deletes the partial file"
    model_path = utils.get_full_path("checkpoints", 0, "m.safetensors")
    assert not os.path.exists(model_path), "the corrupt file never enters the library"


@pytest.mark.asyncio
async def test_download_complete_falls_back_to_reread_without_inline_sha(download_env):
    _download, md, utils, dl_path = download_env
    task_id = "inline-fallback"
    data = b"some other model bytes" * 50
    sha = hashlib.sha256(data).hexdigest().upper()
    tmp_file = utils.join_path(dl_path, f"{task_id}.download")
    _make_task(_download, md, task_id, data, sha, tmp_file)

    # NO staged digest (legacy engine / resumed-complete): _sha256_of re-reads.
    assert task_id not in md._inline_sha256
    await md._download_complete(task_id)
    model_path = utils.get_full_path("checkpoints", 0, "m.safetensors")
    assert os.path.isfile(model_path), "the re-read fallback still verifies and completes"
    assert not os.path.exists(tmp_file)
