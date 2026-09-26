"""Plan Phase 2 (L4): the native safetensors pipeline through ``mm_core``.

Drives the REAL Rust artifact (``native/native-bin/<tag>/mm_core.abi3.so``,
built by ``scripts/build-native.sh`` / CI) via the production loader
(``py/native.py``): job submission, atomic-progress polling, cancellation,
the integrity pipeline (``znn_neo_src_sha256`` recording, default-ON
verification, ``.corrupt`` retreat, paranoid mode) and the byte-exact
restore guarantee over the L4 model corpus (``harness.build_corpus`` —
the plan's corpus classes as synthetic stand-ins, MEMO 2026-09-23).

Skips cleanly when no native binary exists for this platform (the CI verify
job); the native workflow's integration job runs it against the artifact.
"""

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path

import pytest
from harness import REPO_ROOT, build_corpus, import_ext, read_safetensors, sha256_file

# The corpus is built ONCE per session (read-only usage; tests copy what they
# need to mutate).
_CORPUS: dict[str, Path] | None = None


def _corpus_dir(tmp_path_factory) -> dict[str, Path]:
    global _CORPUS
    if _CORPUS is None:
        _CORPUS = build_corpus(tmp_path_factory.mktemp("l4-corpus"))
    return _CORPUS


@pytest.fixture(scope="session")
def corpus(tmp_path_factory) -> dict[str, Path]:
    return _corpus_dir(tmp_path_factory)


@pytest.fixture
def mm(tmp_path, monkeypatch):
    """The real ``mm_core`` through the production loader (or skip)."""
    monkeypatch.delenv("MM_NATIVE", raising=False)
    sys.modules.pop("mm_core", None)
    native = import_ext("native")
    config = import_ext("config")
    config.extension_uri = str(REPO_ROOT)
    # reset the loader's cached attempt state (module state is shared across
    # the whole pytest session — the Phase-0 loader tests mutate it too)
    native._module = None
    native._reason = None
    native._attempted = False
    if not native.load():
        pytest.skip(f"native core unavailable: {native.reason()} (build it: scripts/build-native.sh)")
    core = native.core()
    assert core is not None
    assert core.api_version() == native.MIN_API_VERSION == 3
    return core


def _run_job(mm, handle: int, timeout: float = 120.0) -> tuple[str, dict | None, str | None]:
    """Poll a job to a terminal phase; returns (phase, result_json, error)."""
    deadline = time.monotonic() + timeout
    last = (-1, -1, "")
    while time.monotonic() < deadline:
        done, total, phase = mm.job_progress(handle)
        assert 0 <= done <= total or total == 0, (done, total)
        assert done >= last[0] or phase == "prepare", f"progress went backwards {last} -> {(done, total, phase)}"
        last = (done, total, phase)
        if phase in ("done", "failed"):
            break
        time.sleep(0.01)
    else:
        raise TimeoutError(f"job {handle} did not finish in {timeout}s (last {last})")
    err = mm.job_error(handle)
    if phase == "done":
        assert err is None, f"done job reports error: {err}"
        return phase, json.loads(mm.job_result(handle)), None
    return phase, None, err


def _compress(mm, src: Path, dst: Path, **opts) -> dict:
    handle = mm.zipnn_compress(str(src), str(dst), {"threads": 0, **opts})
    phase, result, err = _run_job(mm, handle)
    assert phase == "done", f"compress failed: {err}"
    assert result is not None
    return result


def _decompress(mm, src: Path, dst: Path, **opts) -> dict:
    handle = mm.zipnn_decompress(str(src), str(dst), {"threads": 0, **opts})
    phase, result, err = _run_job(mm, handle)
    assert phase == "done", f"decompress failed: {err}"
    assert result is not None
    return result


# ---------------------------------------------------------------------------
# Corpus round trips (the L4 gate: 圧縮→解凍→原本 SHA-256 一致)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "sd15-fp16",
        "sdxl-bf16",
        "flux-fp8",
        "llm-bf16",
        "vae-f32",
        "moe-header",
        "audio-c64",
        "f64-synth",
        "unicode-names",
    ],
)
def test_corpus_roundtrip_is_byte_exact(mm, corpus, tmp_path, name):
    src = corpus[name]
    original_sha = sha256_file(src)
    znn = tmp_path / f"{name}.znn.safetensors"
    back = tmp_path / f"{name}.restored.safetensors"

    cres = _compress(mm, src, znn)
    stats = cres["stats"]
    assert stats["tensors"] > 0
    assert stats["compressedBytes"] <= stats["originalBytes"]
    assert znn.exists() and znn.stat().st_size > 0
    # the compressed artifact must itself be a valid safetensors file
    header, _tensors = read_safetensors(znn)
    assert "__metadata__" in header

    dres = _decompress(mm, znn, back)
    assert dres["verified"] == "sha256", dres
    assert sha256_file(back) == original_sha, f"{name}: restore is not byte-exact"
    assert dres["stats"]["decompressedTensors"] == stats["compressedTensors"]


def test_moe_header_heavy_file_keeps_all_tensors(mm, corpus, tmp_path):
    src = corpus["moe-header"]
    znn = tmp_path / "moe.znn.safetensors"
    back = tmp_path / "moe.back.safetensors"
    cres = _compress(mm, src, znn)
    assert cres["stats"]["tensors"] == 600
    assert cres["stats"]["compressedTensors"] == 600  # every expert compresses
    _decompress(mm, znn, back)
    assert sha256_file(back) == sha256_file(src)


def test_passthrough_classes_are_stored_verbatim(mm, corpus, tmp_path):
    # C64 (audio) and F64 are OUT of the Phase-2 compression band: stored
    # as-is (the legacy path RAISES on f64 — Neo is strictly more capable)
    for name, passthrough in [("audio-c64", ["spec.weight"]), ("f64-synth", ["grid"])]:
        src = corpus[name]
        znn = tmp_path / f"{name}.znn.safetensors"
        _compress(mm, src, znn)
        header, tensors = read_safetensors(znn)
        infos = json.loads(header["__metadata__"]["znn_compressed_vectors"])
        for tname in passthrough:
            assert tname not in infos, f"{name}: {tname} must pass through"
            assert tensors[tname][0] in ("C64", "F64")
        # the compressible companion tensor IS compressed
        assert len(infos) >= 1


# ---------------------------------------------------------------------------
# The metadata contract (legacy-parity golden checks)
# ---------------------------------------------------------------------------


def test_compressed_metadata_matches_the_legacy_contract(mm, corpus, tmp_path):
    src = corpus["sd15-fp16"]
    znn = tmp_path / "sd15.znn.safetensors"
    _compress(mm, src, znn)
    header, _ = read_safetensors(znn)
    meta = header["__metadata__"]
    # source metadata survives (original keys/values)
    assert meta["format"] == "pt"
    assert meta["sd_version"] == "1.5"
    # Neo records
    assert meta["znn_neo_original_bytes"] == str(src.stat().st_size)
    assert meta["znn_neo_src_sha256"] == sha256_file(src)
    assert meta["znn_neo_exact"] == "1"
    # infos: EXACTLY the python json.dumps rendering (sorted names, dtype +
    # shape strings) — byte-identical to what the legacy pipeline writes
    infos = json.loads(meta["znn_compressed_vectors"])
    expected_names = sorted(n for n in ("unet.mid.attn.q.weight", "cond_stage.embed.weight"))
    assert sorted(infos) == expected_names
    for tname, info in infos.items():
        assert set(info) == {"dtype", "shape"}
        assert info["dtype"] == "float16"
        assert info["shape"] == "[32, 16]" if tname == "unet.mid.attn.q.weight" else "[64, 32]"
    # the value string itself must equal Python's json.dumps output
    rebuilt = json.dumps({n: infos[n] for n in sorted(infos)})
    assert meta["znn_compressed_vectors"] == rebuilt


def test_unicode_infos_match_python_json_dumps(mm, corpus, tmp_path):
    # ensure_ascii escaping parity for non-ASCII tensor names
    src = corpus["unicode-names"]
    znn = tmp_path / "unicode.znn.safetensors"
    _compress(mm, src, znn)
    header, _ = read_safetensors(znn)
    value = header["__metadata__"]["znn_compressed_vectors"]
    infos = json.loads(value)
    assert set(infos) == {"層.weight", "emb🙂"}
    # Python's json.dumps(ensure_ascii=True) is the golden renderer
    assert value == json.dumps({n: infos[n] for n in sorted(infos)}), value
    assert "\\u" in value  # really escaped, not raw UTF-8
    # … and the round trip still works
    back = tmp_path / "unicode.back.safetensors"
    res = _decompress(mm, znn, back)
    assert res["verified"] == "sha256"
    assert sha256_file(back) == sha256_file(src)


def test_empty_metadata_map_survives(mm, corpus, tmp_path):
    # vae-f32 carries `"__metadata__":{}` — the restore must keep the KEY
    # with an empty map (the reference writer distinguishes {} from absent)
    src = corpus["vae-f32"]
    znn = tmp_path / "vae.znn.safetensors"
    _compress(mm, src, znn)
    back = tmp_path / "vae.back.safetensors"
    _decompress(mm, znn, back)
    assert sha256_file(back) == sha256_file(src)
    header, _ = read_safetensors(back)
    assert header.get("__metadata__") == {}


def test_no_metadata_source_restores_without_the_key(mm, corpus, tmp_path):
    # flux-fp8 has NO __metadata__ — the restored file must not gain one
    src = corpus["flux-fp8"]
    znn = tmp_path / "flux.znn.safetensors"
    _compress(mm, src, znn)
    back = tmp_path / "flux.back.safetensors"
    _decompress(mm, znn, back)
    assert sha256_file(back) == sha256_file(src)
    with open(back, "rb") as f:
        (hlen,) = struct.unpack("<Q", f.read(8))
        raw = f.read(hlen)
    assert b"__metadata__" not in raw


# ---------------------------------------------------------------------------
# The integrity pipeline (Plan §4.4.3)
# ---------------------------------------------------------------------------


def test_corrupted_payload_retreats_to_corrupt_and_keeps_source(mm, corpus, tmp_path):
    src = corpus["sd15-fp16"]
    znn = tmp_path / "sd15.znn.safetensors"
    _compress(mm, src, znn)
    data = bytearray(znn.read_bytes())
    # flip bits deep in the data region (past header + first blob metadata)
    at = len(data) - 300
    data[at] ^= 0xFF
    data[at + 1] ^= 0x5A
    znn.write_bytes(bytes(data))

    back = tmp_path / "sd15.back.safetensors"
    handle = mm.zipnn_decompress(str(znn), str(back), None)
    phase, result, err = _run_job(mm, handle)
    assert phase == "failed", "a corrupted blob must fail verification or decode"
    assert result is None
    assert err and ("znn_neo_src_sha256" in err or "corrupt" in err.lower() or "huff0" in err.lower()), err
    # the compressed source is KEPT, no unverified model appears, and a
    # sha-verification failure leaves the `.corrupt` diagnostic
    assert znn.exists()
    assert not back.exists()
    corrupt = Path(str(back) + ".corrupt")
    if corrupt.exists():
        assert corrupt.stat().st_size > 0


def test_paranoid_mode_verifies_before_commit(mm, corpus, tmp_path):
    src = corpus["sdxl-bf16"]
    znn = tmp_path / "sdxl.znn.safetensors"
    res = _compress(mm, src, znn, paranoid=True)
    assert res["exact"] is True
    assert not Path(str(znn) + ".verify.tmp").exists(), "verify artifact cleaned up"
    back = tmp_path / "sdxl.back.safetensors"
    dres = _decompress(mm, znn, back)
    assert dres["verified"] == "sha256"
    assert sha256_file(back) == sha256_file(src)


def test_noncanonical_source_downgrades_verification(mm, tmp_path):
    # a hand-written header (json.dumps spacing) is valid safetensors but not
    # canonical → compress records exact=0, decompress verifies STRUCTURALLY
    src = tmp_path / "loose.safetensors"
    payload = bytes((0x3F80 | (i % 128)) & 0xFFFF for i in range(0))  # placeholder
    import harness

    payload = harness.synth_bf16(2048, 5, low_entropy=True)
    header = json.dumps({"w": {"dtype": "BF16", "shape": [64, 32], "data_offsets": [0, len(payload)]}}, indent=None)
    header = header.replace('":"', '": "').replace('","', '", "')  # json.dumps default spacing
    hb = header.encode()
    hb += b" " * ((8 - len(hb) % 8) % 8)
    with open(src, "wb") as f:
        f.write(struct.pack("<Q", len(hb)))
        f.write(hb)
        f.write(payload)

    znn = tmp_path / "loose.znn.safetensors"
    cres = _compress(mm, src, znn)
    assert cres["exact"] is False
    assert any("canonical" in w for w in cres["warnings"]), cres["warnings"]

    back = tmp_path / "loose.back.safetensors"
    dres = _decompress(mm, znn, back)
    assert dres["verified"] == "structural"
    assert any("structural" in w for w in dres["warnings"])
    # the tensor payload survived exactly (semantic guarantee, Plan §4.7.4)
    _hdr, tensors = read_safetensors(back)
    assert tensors["w"][2] == payload


def test_official_style_file_without_sha_skips_verification(mm, corpus, tmp_path):
    # Rebuild a compressed file WITHOUT the Neo keys (official-CLI shape):
    # verification must skip (with a note), the restore must still work.
    src = corpus["sdxl-bf16"]
    znn = tmp_path / "sdxl.znn.safetensors"
    _compress(mm, src, znn)
    header, tensors = read_safetensors(znn)
    meta = dict(header["__metadata__"])
    for key in ("znn_neo_src_sha256", "znn_neo_exact", "znn_neo_src_meta_absent", "znn_neo_original_bytes"):
        meta.pop(key, None)
    official = tmp_path / "sdxl.official.znn.safetensors"
    from harness import write_safetensors

    write_safetensors(official, {n: (t[0], t[1], t[2]) for n, t in tensors.items()}, meta)
    back = tmp_path / "sdxl.official.back.safetensors"
    dres = _decompress(mm, official, back)
    assert dres["verified"] == "skipped"
    assert any("skipped" in w for w in dres["warnings"])
    # tensor-wise the restore still equals the original model
    _h1, t1 = read_safetensors(src)
    _h2, t2 = read_safetensors(back)
    assert t1 == t2


# ---------------------------------------------------------------------------
# Job API contract (Plan §4.2.2)
# ---------------------------------------------------------------------------


def test_job_api_error_contract(mm, tmp_path):
    with pytest.raises(KeyError):
        mm.job_progress(2**63)
    with pytest.raises(KeyError):
        mm.job_cancel(2**63)
    with pytest.raises(KeyError):
        mm.job_result(2**63)
    with pytest.raises(KeyError):
        mm.job_error(2**63)

    # a failing job: missing source → terminal `failed`, error text, and
    # job_result raises while job_error returns the message
    handle = mm.zipnn_compress(str(tmp_path / "nope.safetensors"), str(tmp_path / "nope.znn"), None)
    phase, failed_result, err = _run_job(mm, handle)
    assert phase == "failed" and failed_result is None
    assert err and ("No such file" in err or "reading" in err)
    with pytest.raises(RuntimeError):
        mm.job_result(handle)
    assert mm.job_error(handle) == err


def test_cancellation_cleans_up(mm, corpus, tmp_path):
    # a big-enough file that the cancel lands mid-run on any machine
    big = tmp_path / "big.safetensors"
    import harness

    harness.write_safetensors(
        big,
        {"w": ("BF16", [2048, 1024], harness.synth_bf16(2048 * 1024, 9, low_entropy=True))},
        {"format": "pt"},
    )
    znn = tmp_path / "big.znn.safetensors"
    handle = mm.zipnn_compress(str(big), str(znn), {"threads": 1})
    was_running = mm.job_cancel(handle)
    phase, _result, err = _run_job(mm, handle)
    if was_running:
        assert phase == "failed" and err == "cancelled by user", (phase, err)
        assert not znn.exists()
        assert not Path(str(znn) + ".tmp").exists(), "partial output removed"
    else:  # cancelled after completion on a very fast machine — still valid
        assert phase == "done"
    # cancelling an unknown/finished job is a safe no-op boolean
    assert mm.job_cancel(handle) is False


def test_destination_exists_is_refused(mm, corpus, tmp_path):
    src = corpus["sd15-fp16"]
    znn = tmp_path / "occupied.znn.safetensors"
    znn.write_bytes(b"sentinel")
    handle = mm.zipnn_compress(str(src), str(znn), None)
    phase, _result, err = _run_job(mm, handle)
    assert phase == "failed" and "already exists" in (err or "")
    assert znn.read_bytes() == b"sentinel", "the occupied target is never touched"
