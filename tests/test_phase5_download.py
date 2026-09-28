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


def test_hasher_update_on_a_lost_handle_raises_keyerror(tmp_path):
    """The native-side PRECONDITION the write loop's guard relies on: a handle
    the registry evicted makes ``hasher_update`` raise (PyO3 maps mm-core's
    unknown-handle guard to KeyError). The loop's catch-and-abandon behaviour
    itself is driven end to end in
    [test_write_loop_survives_a_lost_hasher_handle_and_rereads]."""
    mm = _require_native()
    # PyO3 maps the unknown-handle guard to KeyError (mm-core's PyKeyError).
    with pytest.raises(KeyError):
        mm.hasher_update(987654321, b"bytes")


@pytest.mark.asyncio
async def test_write_loop_survives_a_lost_hasher_handle_and_rereads(download_env, monkeypatch):
    """Phase 5 audit #2, END TO END (the junction the unit test above only
    sets up): when ``hasher_update`` raises mid-stream (a lost handle), the
    write loop must CATCH it, abandon inline verification (``hasher = None``)
    and KEEP WRITING, so a download whose bytes are perfectly fine still
    completes - verified by the ``_sha256_of`` re-read fallback in
    ``_download_complete`` (no inline digest was staged). Uses a fake core, so
    it runs WITHOUT a built native binary (ci.yml's verify job covers it)."""
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    download, md, utils, dl_path = download_env

    data = bytes((i * 31) & 0xFF for i in range(1536 * 1024))  # 1.5 MiB = two 1 MiB chunks
    sha = hashlib.sha256(data).hexdigest().upper()
    task_id = "lost-handle"

    async def serve(_request):
        return web.Response(body=data, headers={"Content-Type": "application/octet-stream"})

    app = web.Application()
    app.router.add_get("/model.safetensors", serve)
    server = TestServer(app)
    await server.start_server()
    try:
        url = str(server.make_url("/model.safetensors"))
        md.set_task_content(
            task_id,
            download.TaskContent(
                type="checkpoints",
                pathIndex=0,
                fullname="m.safetensors",
                description="note body",
                downloadPlatform="civitai",
                downloadUrl=url,
                sizeBytes=len(data),
                hashes={"SHA256": sha},
            ),
        )

        class LostHandleCore:
            """`hasher_update` raises exactly like mm-core's evicted-handle
            KeyError; `hasher_finalize` must NEVER run (the loop drops the
            hasher on the first failure), so it fails the test if reached."""

            def hasher_new(self, algos):
                return 4242

            def hasher_update(self, handle, chunk):
                raise KeyError(handle)

            def hasher_finalize(self, handle):
                raise AssertionError("a dropped hasher must not be finalized")

        monkeypatch.setattr(download.native, "core_if_enabled", lambda: LostHandleCore())

        # the orchestrator (`download_model`) normally flips the task out of its
        # default "pause" state before streaming; this test drives the http
        # worker directly, so set it the same way (the write loop breaks on a
        # "pause" status by design - cooperative pause).
        md.get_task_status(task_id).status = "doing"

        pushed: list[float] = []

        async def progress_cb(status):
            pushed.append(status.downloadedSize)

        await md.download_model_file_http(task_id, {}, progress_cb, interval=0.0)

        # the guard let the download finish despite the lost handle ...
        model_path = utils.get_full_path("checkpoints", 0, "m.safetensors")
        assert os.path.isfile(model_path), "the write loop must not fail a download over a lost hasher"
        # ... with the CORRECT bytes (the re-read verified them against the published SHA)
        with open(model_path, "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest().upper() == sha
        # no inline digest was staged (the hasher was abandoned on the first chunk)
        assert task_id not in md._inline_sha256
        # the partial was renamed into the library, and progress reached 100%
        assert not os.path.exists(utils.join_path(dl_path, f"{task_id}.download"))
        assert pushed and pushed[-1] == len(data)
    finally:
        await server.close()
