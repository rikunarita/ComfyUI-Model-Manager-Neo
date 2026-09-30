"""Plan Phase 7 / T1 - the upload duplicate-preflight SHA-256 goes native.

``py/upload_hf.py`` used to hash the whole model with a Python ``hashlib`` 1 MiB
loop (``hash_local_file``) inside the Hugging Face / ModelScope duplicate
preflight. T1 replaces that with the EXISTING native ``mm_core.hash_file``
(one pass, GIL released, SHA-NI/AVX2) behind ``_sha256_of_file`` - lower-cased
to match the Hub's LFS ``sha256`` - and SPLITS the preflight into a network
stage (``preflight_remote`` on the io pool) and a CPU hash stage (on the cpu
pool). These tests pin:

* the golden contract ``_sha256_of_file == hashlib.sha256(...).hexdigest()`` on
  BOTH the native path and the Python fallback (a missing native core must not
  change the digest);
* ``HfBackend.preflight_remote``'s branches (same-size LFS object -> needs_hash,
  size mismatch / missing target / missing LFS / API error -> None = go);
* the JUNCTION (MEMO §4.5): ``run_hub_upload`` wires preflight_remote ->
  _sha256_of_file -> compare, so a remote sha equal to the local file's sha256
  dedupes the file (``upload_one`` never runs).

No native API was added (``api_version`` is unchanged); the native path skips
to the fallback where no artifact is present (ci.yml), so every test here runs
with OR without a built ``mm_core``.
"""

from __future__ import annotations

import hashlib
import os
import types

import pytest
from harness import REPO_ROOT, import_ext


def _reset_native_loader():
    """Point py.native at the repo's native-bin and clear its attempt state so
    ``core_if_enabled()`` re-probes (the built artifact, when present)."""
    config = import_ext("config")
    config.extension_uri = str(REPO_ROOT)
    native = import_ext("native")
    native._module = None
    native._reason = None
    native._attempted = False
    return native


# ---------------------------------------------------------------------------
# golden: _sha256_of_file == hashlib (both engines)
# ---------------------------------------------------------------------------
def test_sha256_of_file_matches_hashlib(tmp_path):
    """The native single-pass hash, lower-cased, is byte-identical to the
    Python ``hashlib`` digest it replaced (the T1 golden gate)."""
    _reset_native_loader()
    upload_hf = import_ext("upload_hf")
    data = os.urandom(3 * 1024 * 1024 + 17)  # spans several 1 MiB chunks
    path = tmp_path / "blob.bin"
    path.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()  # lower-case
    assert upload_hf._sha256_of_file(str(path)) == expected


def test_sha256_of_file_falls_back_to_python_without_native(tmp_path, monkeypatch):
    """With no native core the digest is unchanged (the Python hashlib loop),
    so the preflight answer never depends on which engine ran."""
    native = _reset_native_loader()
    upload_hf = import_ext("upload_hf")
    monkeypatch.setattr(native, "core_if_enabled", lambda: None)
    data = os.urandom(1024 * 1024 + 3)
    path = tmp_path / "blob.bin"
    path.write_bytes(data)
    assert upload_hf._sha256_of_file(str(path)) == hashlib.sha256(data).hexdigest()


def test_sha256_of_file_is_lower_case_native_path(tmp_path):
    """The native notation is UPPER-case (py/identify.py); the Hub's LFS sha256
    is lower-case, so _sha256_of_file must lower-case it (a regression here
    would silently defeat every duplicate check)."""
    native = _reset_native_loader()
    upload_hf = import_ext("upload_hf")
    if native.core_if_enabled() is None:
        pytest.skip("native core not built here (fallback is trivially lower-case)")
    path = tmp_path / "blob.bin"
    path.write_bytes(b"neo" * 4096)
    digest = upload_hf._sha256_of_file(str(path))
    assert digest == digest.lower()
    assert digest == hashlib.sha256(b"neo" * 4096).hexdigest()


# ---------------------------------------------------------------------------
# preflight_remote (network stage) branches
# ---------------------------------------------------------------------------
def _fake_api(sha, size, rfilename="m.safetensors"):
    sibling = types.SimpleNamespace(
        rfilename=rfilename,
        lfs=types.SimpleNamespace(sha256=sha, size=size),
        size=size,
    )
    info = types.SimpleNamespace(siblings=[sibling])
    return types.SimpleNamespace(model_info=lambda **_kw: info)


def test_preflight_remote_needs_hash_on_a_same_size_lfs_object():
    upload_hf = import_ext("upload_hf")
    backend = upload_hf.HfBackend("tok", "owner/repo")
    api = _fake_api("a" * 64, 100)
    remote = backend.preflight_remote(api, "owner/repo", "m.safetensors", 100)
    assert remote == {
        "needs_hash": True,
        "remote_sha": "a" * 64,
        "url": "https://huggingface.co/owner/repo/blob/main/m.safetensors",
    }


def test_preflight_remote_goes_on_size_mismatch_missing_target_or_no_lfs():
    upload_hf = import_ext("upload_hf")
    backend = upload_hf.HfBackend("tok", "owner/repo")
    # size mismatch -> go (None)
    assert backend.preflight_remote(_fake_api("a" * 64, 100), "owner/repo", "m.safetensors", 101) is None
    # a different file in the repo -> target not found -> go
    assert backend.preflight_remote(_fake_api("a" * 64, 100), "owner/repo", "other.safetensors", 100) is None
    # no LFS metadata -> go
    no_lfs = types.SimpleNamespace(siblings=[types.SimpleNamespace(rfilename="m.safetensors", lfs=None, size=100)])
    api = types.SimpleNamespace(model_info=lambda **_kw: no_lfs)
    assert backend.preflight_remote(api, "owner/repo", "m.safetensors", 100) is None


def test_preflight_remote_swallows_api_errors():
    """A failing model_info degrades to 'go' (None), never raises - the upload
    proceeds and the Hub decides, exactly as the pre-T1 preflight did."""
    upload_hf = import_ext("upload_hf")
    backend = upload_hf.HfBackend("tok", "owner/repo")

    def boom(**_kw):
        raise RuntimeError("network down")

    api = types.SimpleNamespace(model_info=boom)
    assert backend.preflight_remote(api, "owner/repo", "m.safetensors", 100) is None


# ---------------------------------------------------------------------------
# junction: run_hub_upload dedupes through the split preflight
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_hub_upload_dedupes_via_the_split_preflight(tmp_path, monkeypatch):
    """The JUNCTION (MEMO §4.5): run_hub_upload must wire preflight_remote
    (network, io pool) -> _sha256_of_file (hash, cpu pool) -> compare. A remote
    LFS sha equal to the local file's sha256 dedupes the file, so upload_one is
    never called and the task completes as 'skipped'/'deduplicated'."""
    _reset_native_loader()
    upload_hf = import_ext("upload_hf")
    utils = import_ext("utils")

    sent: list[tuple] = []

    async def fake_send_json(event, data, sid=None):
        sent.append((event, data))

    monkeypatch.setattr(utils, "send_json", fake_send_json)

    data = os.urandom(2 * 1024 * 1024 + 5)
    path = tmp_path / "m.safetensors"
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    size = len(data)

    uploaded: list[str] = []

    class FakeBackend(upload_hf.HfBackend):
        streams_upload_progress = True

        def make_api(self, token):
            return _fake_api(sha, size)

        def ensure_repo(self, api, repo_id, private):
            return False

        def upload_one(self, api, payload, in_repo):
            uploaded.append(in_repo)
            return (size, False)

        def file_url(self, repo_id, in_repo):
            return f"https://huggingface.co/{repo_id}/blob/main/{in_repo}"

    backend = FakeBackend("tok", "owner/repo")
    await upload_hf.run_hub_upload(
        task_id="t-dedup",
        token="tok",
        files=[{"local_path": str(path), "path_in_repo": "m.safetensors"}],
        repo_id="owner/repo",
        path_in_repo="m.safetensors",
        private=False,
        total_size=size,
        backend=backend,
    )
    assert uploaded == [], "a byte-identical remote object must be deduped (no transfer)"
    complete = [d for ev, d in sent if ev == "hf_upload_complete"]
    assert complete and complete[0]["deduplicated"] is True
    assert complete[0]["skipped"] is True
    assert complete[0]["transferredBytes"] == 0.0


@pytest.mark.asyncio
async def test_run_hub_upload_transfers_when_the_hash_differs(tmp_path, monkeypatch):
    """Complement of the dedup junction: a same-SIZE remote object whose sha
    differs must NOT dedupe - the hash stage runs and the transfer proceeds."""
    _reset_native_loader()
    upload_hf = import_ext("upload_hf")
    utils = import_ext("utils")

    async def fake_send_json(event, data, sid=None):
        return None

    monkeypatch.setattr(utils, "send_json", fake_send_json)

    data = os.urandom(1024 * 1024 + 11)
    path = tmp_path / "m.safetensors"
    path.write_bytes(data)
    size = len(data)

    uploaded: list[str] = []

    class FakeBackend(upload_hf.HfBackend):
        streams_upload_progress = True

        def make_api(self, token):
            return _fake_api("f" * 64, size)  # same size, DIFFERENT sha

        def ensure_repo(self, api, repo_id, private):
            return False

        def upload_one(self, api, payload, in_repo):
            uploaded.append(in_repo)
            return (size, False)

        def file_url(self, repo_id, in_repo):
            return f"https://huggingface.co/{repo_id}/blob/main/{in_repo}"

    await upload_hf.run_hub_upload(
        task_id="t-transfer",
        token="tok",
        files=[{"local_path": str(path), "path_in_repo": "m.safetensors"}],
        repo_id="owner/repo",
        path_in_repo="m.safetensors",
        private=False,
        total_size=size,
        backend=FakeBackend("tok", "owner/repo"),
    )
    assert uploaded == ["m.safetensors"], "a differing hash must proceed to transfer"


@pytest.mark.asyncio
async def test_run_hub_upload_degrades_to_go_when_the_hash_stage_fails(tmp_path, monkeypatch):
    """JUNCTION parity (the comment in run_hub_upload promises it): pre-T1 the
    preflight caught a hash failure inside its OWN try/except and degraded to
    "go" (skip duplicate detection, still upload). Now that the hash is a
    separate cpu-pool stage, a failing ``_sha256_of_file`` (unreadable file,
    native panic-guard, disk error) must NOT abort the upload - the file
    transfers and the Hub decides. Removing the ``except -> go`` degradation
    in run_hub_upload fails this test.
    """
    _reset_native_loader()
    upload_hf = import_ext("upload_hf")
    utils = import_ext("utils")

    sent: list[tuple] = []

    async def fake_send_json(event, data, sid=None):
        sent.append((event, data))

    monkeypatch.setattr(utils, "send_json", fake_send_json)

    def boom(_path):
        raise OSError("hash stage on fire")

    monkeypatch.setattr(upload_hf, "_sha256_of_file", boom)

    data = os.urandom(512 * 1024 + 7)
    path = tmp_path / "m.safetensors"
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    size = len(data)

    uploaded: list[str] = []

    class FakeBackend(upload_hf.HfBackend):
        streams_upload_progress = True

        def make_api(self, token):
            return _fake_api(sha, size)  # same size AND sha -> needs_hash=True

        def ensure_repo(self, api, repo_id, private):
            return False

        def upload_one(self, api, payload, in_repo):
            uploaded.append(in_repo)
            return (size, False)

        def file_url(self, repo_id, in_repo):
            return f"https://huggingface.co/{repo_id}/blob/main/{in_repo}"

    await upload_hf.run_hub_upload(
        task_id="t-hashfail",
        token="tok",
        files=[{"local_path": str(path), "path_in_repo": "m.safetensors"}],
        repo_id="owner/repo",
        path_in_repo="m.safetensors",
        private=False,
        total_size=size,
        backend=FakeBackend("tok", "owner/repo"),
    )
    assert uploaded == ["m.safetensors"], "a hash failure degrades to 'go' - the upload proceeds"
    complete = [d for ev, d in sent if ev == "hf_upload_complete"]
    assert complete and complete[0]["deduplicated"] is False
    assert not any(ev == "hf_upload_error" for ev, _ in sent), "the degradation must not surface an error"
