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
import json
import os

import pytest
from harness import REPO_ROOT, import_ext


def _require_native():
    """The built mm_core, or a skip (same convention as test_phase5_scan.py)."""
    config = import_ext("config")
    config.extension_uri = str(REPO_ROOT)
    native = import_ext("native")
    native._module = None
    native._reason = None
    native._attempted = False
    if not native.load():
        pytest.skip(f"native core unavailable: {native.reason()}")
    return native.core()


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


# ---------------------------------------------------------------------------
# resume seeding (Phase 5 audit fix: the read moved off the event loop)
# ---------------------------------------------------------------------------
def test_seed_hasher_from_file_matches_a_whole_file_hash(tmp_path):
    """Seeding a resumed hasher with the partial file must give the same digest
    as hashing that file in one pass (the invariant `_download_complete` relies
    on: seed + the remaining chunks == the whole file)."""
    mm = _require_native()
    download = import_ext("download")
    data = bytes((i * 37) & 0xFF for i in range(3 * 1024 * 1024))  # > 2 chunks
    path = tmp_path / "partial.download"
    path.write_bytes(data)

    handle = mm.hasher_new(["SHA256"])
    assert download._seed_hasher_from_file(mm, handle, str(path)) is True
    staged = json.loads(mm.hasher_finalize(handle))["SHA256"]
    assert staged == hashlib.sha256(data).hexdigest().upper()
    assert staged == json.loads(mm.hash_file(str(path), ["SHA256"]))["SHA256"]


def test_seed_hasher_from_file_reports_an_unreadable_file(tmp_path):
    """A vanished partial must degrade to the re-read path, never raise."""
    mm = _require_native()
    download = import_ext("download")
    handle = mm.hasher_new(["SHA256"])
    assert download._seed_hasher_from_file(mm, handle, str(tmp_path / "missing.download")) is False
    # the handle is still usable (the caller decides whether to drop it)
    download._drop_hasher(mm, handle)
    # dropping an unknown handle is a no-op, not an exception
    download._drop_hasher(mm, handle)
    download._drop_hasher(mm, 123456789)


def test_hasher_update_on_a_lost_handle_raises_and_is_caught_by_the_loop(tmp_path):
    """The write loop guards `hasher_update`: a handle the native registry
    evicted must not fail a download whose bytes are fine."""
    mm = _require_native()
    # PyO3 maps the unknown-handle guard to KeyError (mm-core's PyKeyError).
    with pytest.raises(KeyError):
        mm.hasher_update(987654321, b"bytes")
