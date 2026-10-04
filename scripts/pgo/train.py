#!/usr/bin/env python3
"""PGO training / measurement driver for the ``mm_core`` native core.

Part of the PGO pipeline. Three modes:

* **(default) train** — exercises every hot surface of ``mm_core`` against
  deterministic synthetic fixtures (compress / decompress / delta / scan /
  hygiene / hash / incremental hasher / safetensors header + tensor tree /
  WebP still + animation / walk / move-with-sidecars). Run against an
  *instrumented* build (``-Cprofile-generate``) this produces the ``.profraw``
  files that ``llvm-profdata merge`` turns into the PGO profile. The workload
  is seed-fixed and third-party-free (stdlib + ``mm_core`` + ``tests/harness``)
  so it runs inside maturin's ``--pgo`` temporary venv and on any runner.

* ``--bench-one`` — one timed workload against ``--lib-dir`` (subprocess
  isolation; called by ``--measure``, usable standalone).

* ``--measure`` — A/B throughput driver: alternates ``--bench-one``
  subprocesses between two built cores (``--a`` = baseline, ``--b`` = PGO),
  N rounds, steal-gated on Linux (contaminated rounds are discarded and
  retried) — the BENCH gate protocol reduced to a single runner
  session. Verdict statistic = the per-side **median** ratio (the G1
  verdict); the per-side minimum (worst window) and maximum (zero-interference
  ceiling) are reported alongside. The original min-only verdict was
  retired after run #108: min-of-N compares whichever unlucky round each
  side drew, so the verdict flipped (#107 PASS x1.126 / #108 NOT MET
  x0.7575) on an unchanged steady-state reality (compress ~x1.00 in both
  runs) — see BENCH §13.6.

Environment knobs (train mode): ``TRAIN_MB`` (compress fixture size, default
32), ``TRAIN_MODELS`` (scan library size, default 800), ``TRAIN_HASH_MB``
(default 128), ``TRAIN_ROUNDS`` (compress/decompress repetitions, default 2),
``TRAIN_WORKDIR`` (fixtures root; a temp dir by default, reused when set).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# tests/harness.py: the byte-exact safetensors writer + deterministic synth
# tensor payloads (stdlib-only, mirrored from the pytest suite).
sys.path.insert(0, str(REPO_ROOT / "tests"))

import harness  # (sys.path is set above)

# Production constants (py/utils.py) — duplicated so this script never
# imports the ComfyUI-dependent backend.
DELTA_FOLDER_SUFFIX = "_DeltaZNN"
ZNN_FOLDER_SUFFIX = "_ZNN"
NO_PREVIEW_URL = "/model-manager/no-preview.svg"
SUPPORTED_EXTENSIONS = sorted({".ckpt", ".pt", ".pt2", ".bin", ".pth", ".safetensors", ".pkl", ".sft", ".gguf", ".znn"})
HASH_ALGOS = ["SHA256", "AutoV2", "AutoV1", "CRC32", "BLAKE3"]
WEBP_QUALITY = 80.0
WEBP_METHOD = 4
POLL_INTERVAL_S = 0.01


# ---------------------------------------------------------------------------
# core loading
# ---------------------------------------------------------------------------
def load_core(lib_dir: str | None):
    """Import mm_core (optionally from an explicit directory) and sanity-check it."""
    if lib_dir:
        sys.path.insert(0, str(Path(lib_dir).resolve()))
    import mm_core

    api = mm_core.api_version()
    if api < 6:
        raise SystemExit(f"mm_core api_version {api} is too old for this trainer (need >= 6)")
    print(f"[train] mm_core api_version={api} core_version={mm_core.core_version()}", flush=True)
    return mm_core


def _job_wait(mm, handle, label: str) -> dict:
    """Poll one native job to completion (the production 10 Hz contract)."""
    while True:
        time.sleep(POLL_INTERVAL_S)
        _done, _total, phase = mm.job_progress(handle)
        if phase == "failed":
            raise SystemExit(f"[train] job failed ({label}): {mm.job_error(handle)}")
        if phase == "done":
            break
    result = json.loads(mm.job_result(handle))
    stats = result.get("stats")
    if not isinstance(stats, dict):
        raise SystemExit(f"[train] job returned no stats ({label})")
    return stats


def _peak_rss_kb() -> int | None:
    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports kB, macOS reports bytes; Windows lacks the field.
        return int(rss) if platform.system() != "Darwin" else int(rss // 1024)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# fixtures (deterministic — the profile shape must be reproducible)
# ---------------------------------------------------------------------------
def build_fixtures(root: Path, size_mb: int, n_models: int, hash_mb: int) -> dict[str, Path]:
    """Create the synthetic corpus. Returns a name -> path map."""
    if root.exists():
        shutil.rmtree(root)
    (root / "models" / "checkpoints" / "sub").mkdir(parents=True)
    (root / "idx").mkdir()
    fx: dict[str, Path] = {}

    n_elems_bf16 = size_mb * 1024 * 1024 // 2
    fx["bf16_low"] = root / "models" / "low.safetensors"
    harness.write_safetensors(
        fx["bf16_low"],
        {"w": ("BF16", [n_elems_bf16 // 4, 4], harness.synth_bf16(n_elems_bf16, 1, low_entropy=True))},
        {"format": "pt"},
    )
    rand_payload = harness.synth_bf16(n_elems_bf16, 2)
    fx["bf16_rand"] = root / "models" / "rand.safetensors"
    harness.write_safetensors(
        fx["bf16_rand"],
        {"w": ("BF16", [n_elems_bf16 // 4, 4], rand_payload)},
        {"format": "pt"},
    )
    n_f32 = 8 * 1024 * 1024 // 4
    fx["f32"] = root / "models" / "f32.safetensors"
    harness.write_safetensors(fx["f32"], {"w": ("F32", [n_f32], harness.synth_f32(n_f32, 3, low_entropy=True))})
    n_f16 = 8 * 1024 * 1024 // 2
    fx["f16"] = root / "models" / "f16.safetensors"
    harness.write_safetensors(fx["f16"], {"w": ("F16", [n_f16], harness.synth_f16(n_f16, 4))})
    n_fp8 = 4 * 1024 * 1024
    fx["fp8"] = root / "models" / "fp8.safetensors"
    harness.write_safetensors(fx["fp8"], {"w": ("F8_E4M3", [n_fp8], harness.synth_fp8(n_fp8, 5))})

    # delta pair: base + a lightly perturbed fine-tune. The perturbation is
    # applied to the TENSOR PAYLOAD before writing (never to the file bytes —
    # XORing the container header would desync the tensor-data sizes, which
    # the delta codec rejects up front). Both files go through the same writer
    # with identical keys/shapes/metadata, so their headers match byte for
    # byte and the delta alignment sees one identical layout.
    fx["delta_base"] = fx["bf16_rand"]
    ft_payload = bytearray(rand_payload)
    for i in range(0, len(ft_payload), 4096):  # ~0.02 % of the bytes differ
        ft_payload[i] ^= 0x5A
    fx["delta_ft"] = root / "models" / "ft.safetensors"
    harness.write_safetensors(
        fx["delta_ft"],
        {"w": ("BF16", [n_elems_bf16 // 4, 4], bytes(ft_payload))},
        {"format": "pt"},
    )

    # MoE-shaped header: many small tensors (header parse + tensor tree paths)
    moe = {f"layers.{i}.w": ("F32", [8, 8], harness.synth_f32(64, 100 + i)) for i in range(1200)}
    fx["moe"] = root / "models" / "moe.safetensors"
    harness.write_safetensors(fx["moe"], moe, {"format": "pt"})

    # scan library: many tiny models + front-matter sidecars + sub-folders
    lib = root / "models" / "checkpoints"
    for i in range(n_models):
        target = lib / "sub" if i % 7 == 0 else lib
        p = target / f"m{i:05d}.safetensors"
        harness.write_safetensors(p, {"w": ("F32", [4], harness.synth_f32(4, i))})
        if i % 3 == 0:
            (target / f"m{i:05d}.webp").write_bytes(b"preview-bytes")
        if i % 5 == 0:
            (target / f"m{i:05d}.md").write_text(
                "---\nmodelPage: https://civitai.com/models/1\nbaseModel: SD 1.5\n---\n# n\n",
                encoding="utf-8",
            )
    fx["scan_root"] = lib

    # hash target
    fx["hash_target"] = root / "hash.bin"
    with open(fx["hash_target"], "wb") as f:
        chunk = harness.synth_bytes(4 * 1024 * 1024, 7)
        for _ in range(hash_mb // 4):
            f.write(chunk)

    # WebP inputs (RGBA noise + a gradient)
    fx["webp_dir"] = root / "webp"
    fx["webp_dir"].mkdir()
    return fx


def _rgba(w: int, h: int, seed: int) -> bytes:
    return harness.synth_bytes(w * h * 4, seed)


# ---------------------------------------------------------------------------
# train mode
# ---------------------------------------------------------------------------
def train(mm, fx: dict[str, Path], root: Path, rounds: int) -> dict:
    t0_all = time.monotonic()
    timings: dict[str, float] = {}

    def timed(name: str, fn):
        t0 = time.monotonic()
        out = fn()
        timings[name] = round(time.monotonic() - t0, 3)
        return out

    opts = {"threads": 0, "paranoid": False}
    comp_dir = root / "compressed"
    comp_dir.mkdir(exist_ok=True)

    # 1. ZipNN compress/decompress round trips (the dominant hot path)
    for key in ("bf16_low", "bf16_rand", "f32", "f16", "fp8"):
        src = fx[key]
        original_sha = harness.sha256_file(src)
        for r in range(rounds):
            znn = comp_dir / f"{key}.{r}.znn.safetensors"
            stats = timed(
                f"compress.{key}.r{r}",
                lambda s=src, z=znn, k=key: _job_wait(mm, mm.zipnn_compress(str(s), str(z), opts), k),
            )
            # stats.originalBytes is the tensor payload total (not the file
            # size — the safetensors header is metadata); the SHA-256 round
            # trip below is the real correctness gate.
            assert stats["originalBytes"] > 0 and stats["tensors"] >= 1, stats
            out = comp_dir / f"{key}.{r}.restored.safetensors"
            timed(
                f"decompress.{key}.r{r}",
                lambda z=znn, o=out, k=key: _job_wait(mm, mm.zipnn_decompress(str(z), str(o), opts), k),
            )
            assert harness.sha256_file(out) == original_sha, f"{key} round {r}: restore mismatch"
            znn.unlink(missing_ok=True)
            out.unlink()

    # one paranoid round trip (re-decode-and-compare path)
    znn = comp_dir / "paranoid.znn.safetensors"
    _job_wait(mm, mm.zipnn_compress(str(fx["f16"]), str(znn), {"threads": 0, "paranoid": True}), "paranoid")
    out = comp_dir / "paranoid.restored"
    _job_wait(mm, mm.zipnn_decompress(str(znn), str(out), opts), "paranoid-restore")
    assert harness.sha256_file(out) == harness.sha256_file(fx["f16"])
    out.unlink()

    # 2. delta compress/decompress (streaming XOR + sidecar verification)
    ft_sha = harness.sha256_file(fx["delta_ft"])
    delta = comp_dir / "ft_delta_base.znn"
    timed(
        "delta.compress",
        lambda: _job_wait(
            mm, mm.zipnn_delta_compress(str(fx["delta_base"]), str(fx["delta_ft"]), str(delta), opts), "delta"
        ),
    )
    meta_path = Path(f"{delta}.neo-delta.json")
    assert meta_path.is_file(), "delta sidecar missing"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    restored = comp_dir / "ft.restored.safetensors"
    timed(
        "delta.decompress",
        lambda: _job_wait(
            mm,
            mm.zipnn_delta_decompress(str(fx["delta_base"]), str(delta), str(restored), meta, {"threads": 0}),
            "delta-restore",
        ),
    )
    assert harness.sha256_file(restored) == ft_sha, "delta restore mismatch"

    # 3. scan — WEIGHTED (run #107 evidence): with a single cold+warm pass the
    # profile is dominated by codec work and scan ended up x0.349 under PGO
    # (its rayon plumbing closures landed in the missing-profile population —
    # workload skew). PGO weight is proportional to execution
    # counts, so iterate: 5 cold scans (fresh index dir each time — the
    # production first-scan-after-startup path) + 20 warm scans (persistent
    # index hit — the refresh path). timings[] keeps the last iteration; the
    # repetition is for profile weight, not for reporting.
    scan_opts = {
        "includeHidden": False,
        "extensions": SUPPORTED_EXTENSIONS,
        "noPreviewUrl": NO_PREVIEW_URL,
        "previewUrlPrefix": "/model-manager/preview",
        "indexDir": str(root / "idx"),
    }
    roots = [str(fx["scan_root"]).replace(os.sep, "/")]
    idx_dir = root / "idx"

    def _scan():
        return json.loads(mm.scan_models("checkpoints", roots, scan_opts))

    cold = warm = None
    for _ in range(5):
        shutil.rmtree(idx_dir, ignore_errors=True)
        cold = timed("scan.cold", _scan)
    for _ in range(20):
        warm = timed("scan.warm", _scan)
    assert cold is not None and warm is not None, "scan did not run"
    assert len(cold) == len(warm) > 0, "scan produced no entries"

    # 4. hygiene sweep (orphans / empty dirs over the same tree) — x5 for the
    # same weighting reason as scan.
    base_paths = {"checkpoints": roots}
    for _ in range(5):
        timed("hygiene", lambda: json.loads(mm.scan_hygiene(base_paths, SUPPORTED_EXTENSIONS)))

    # 5. walk + move-with-sidecars (batch primitives)
    walk_opts = {
        "mode": "compress",
        "bundleSuffixes": [DELTA_FOLDER_SUFFIX, ZNN_FOLDER_SUFFIX],
        "deltaFolderSuffix": DELTA_FOLDER_SUFFIX,
        "skipBundles": True,
    }
    walked = None
    for _ in range(5):  # x5 — same weighting reason as scan/hygiene
        walked = timed("walk", lambda: json.loads(mm.walk_models(str(fx["scan_root"]), walk_opts)))
    assert walked is not None and len(walked) > 0
    # move_with_sidecars moves ONLY the sidecars (previews + .md/.txt notes)
    # onto the destination's base name — the model file itself is written by
    # the compression pipeline (production: py/compress.py batch flow). Mirror
    # that contract: dst wears the compressed name, the sidecars follow it.
    mv_src = comp_dir / "move-me.safetensors"
    shutil.copyfile(fx["f32"], mv_src)
    (comp_dir / "move-me.webp").write_bytes(b"p")
    (comp_dir / "move-me.md").write_text("# n")
    mv_dst = comp_dir / "moved" / "move-me.znn.safetensors"
    timed("move_with_sidecars", lambda: mm.move_with_sidecars(str(mv_src), str(mv_dst)))
    assert (mv_dst.parent / "move-me.znn.webp").is_file(), "preview sidecar did not follow"
    assert (mv_dst.parent / "move-me.znn.md").is_file(), "notes sidecar did not follow"
    assert mv_src.is_file() and not (comp_dir / "move-me.webp").exists()

    # 6. hashing: one-pass multi-algorithm + the incremental hasher
    hash_json = timed("hash_file", lambda: json.loads(mm.hash_file(str(fx["hash_target"]), HASH_ALGOS)))
    assert "SHA256" in hash_json, hash_json

    def _incremental():
        h = mm.hasher_new(["SHA256"])
        with open(fx["hash_target"], "rb") as f:
            while True:
                block = f.read(1024 * 1024)
                if not block:
                    break
                mm.hasher_update(h, block)
        return json.loads(mm.hasher_finalize(h))

    inc = timed("hasher_incremental", _incremental)
    assert inc["SHA256"].lower() == hash_json["SHA256"].lower(), "incremental != one-pass"

    # 7. safetensors header + display tensor tree (MoE-shaped, repeated)
    def _headers():
        for _ in range(20):
            json.loads(mm.safetensors_header(str(fx["moe"])))
            json.loads(mm.safetensors_tensor_tree(str(fx["moe"])))

    timed("header_tree_x20", _headers)

    # 8. WebP: still encode/decode + animation encode/decode
    def _webp():
        w = h = 256
        rgba = _rgba(w, h, 11)
        blob = mm.webp_encode(rgba, w, h, b"", WEBP_QUALITY, WEBP_METHOD, False)
        rgba2, w2, h2, _icc = mm.webp_decode(blob)
        assert (w2, h2) == (w, h) and len(rgba2) == w * h * 4
        frames = [_rgba(w, h, 20 + i) for i in range(4)]
        anim = mm.webp_encode_animation(frames, w, h, [100] * 4, 0, b"", WEBP_QUALITY, WEBP_METHOD, False)
        frames2, w3, h3, durations, _loop, _icc2 = mm.webp_decode_animation(anim)
        assert (w3, h3) == (w, h) and len(frames2) == 4 and len(durations) == 4

    for i in range(10):
        timed(f"webp.r{i}", _webp)

    total = round(time.monotonic() - t0_all, 3)
    return {"totalSeconds": total, "timings": timings, "scanEntries": len(cold), "peakRssKb": _peak_rss_kb()}


# ---------------------------------------------------------------------------
# bench-one / measure modes (Step 3's G1 gate)
# ---------------------------------------------------------------------------
BENCH_WORKLOADS = ("compress", "decompress", "hash", "scan")
MAX_STEAL_RETRIES = 5


def bench_one(mm, fx: dict[str, Path], root: Path, workload: str) -> dict:
    opts = {"threads": 0, "paranoid": False}
    comp_dir = root / "bench"
    comp_dir.mkdir(exist_ok=True)
    t0 = time.monotonic()
    nbytes = 0
    if workload == "compress":
        src = fx["bf16_low"]
        nbytes = src.stat().st_size
        dst = comp_dir / "b.znn.safetensors"
        dst.unlink(missing_ok=True)  # the pipeline creates the target exclusively
        _job_wait(mm, mm.zipnn_compress(str(src), str(dst), opts), "bench-compress")
    elif workload == "decompress":
        znn = comp_dir / "b.znn.safetensors"
        if not znn.is_file():
            _job_wait(mm, mm.zipnn_compress(str(fx["bf16_low"]), str(znn), opts), "bench-compress-setup")
        nbytes = fx["bf16_low"].stat().st_size
        out = comp_dir / "b.restored.safetensors"
        _job_wait(mm, mm.zipnn_decompress(str(znn), str(out), opts), "bench-decompress")
        out.unlink(missing_ok=True)
    elif workload == "hash":
        nbytes = fx["hash_target"].stat().st_size
        mm.hash_file(str(fx["hash_target"]), HASH_ALGOS)
    elif workload == "scan":
        scan_opts = {
            "includeHidden": False,
            "extensions": SUPPORTED_EXTENSIONS,
            "noPreviewUrl": NO_PREVIEW_URL,
            "previewUrlPrefix": "/model-manager/preview",
            "indexDir": str(root / "idx-bench"),
        }
        shutil.rmtree(root / "idx-bench", ignore_errors=True)
        entries = json.loads(mm.scan_models("checkpoints", [str(fx["scan_root"]).replace(os.sep, "/")], scan_opts))
        nbytes = len(entries)  # entries, not bytes — reported separately
    else:
        raise SystemExit(f"unknown workload: {workload}")
    seconds = time.monotonic() - t0
    unit = "entries/s" if workload == "scan" else "MB/s"
    rate = (nbytes / (1024 * 1024) / seconds) if workload != "scan" else (nbytes / seconds)
    return {
        "workload": workload,
        "seconds": round(seconds, 4),
        "amount": nbytes,
        "rate": round(rate, 2),
        "unit": unit,
        "peakRssKb": _peak_rss_kb(),
    }


def _steal_ticks() -> int | None:
    """Linux guest steal time (jiffies) from /proc/stat; None elsewhere."""
    try:
        with open("/proc/stat", encoding="utf-8") as f:
            for line in f:
                if line.startswith("cpu "):
                    fields = line.split()
                    return int(fields[8])  # steal is the 8th counter
    except Exception:
        pass
    return None


def summarize_workloads(samples: dict[tuple[str, str], list[float]]) -> dict[str, dict]:
    """Per-workload A/B statistics: min / median / best per side + ratios.

    The G1 verdict statistic is the per-side **median** ratio.
    ``ratio`` (kept as an alias of ``ratioMin``) preserves the JSON key that
    the run #107/#108 records reference; ``ratioBest`` is the
    zero-interference ceiling (per-side best window).

    Why not judge on the minimum (run #108, BENCH §13.6): min-of-N compares
    whichever unlucky round each side drew. #108's compress min ratio x0.7575
    came from the PGO side's noise-degraded round 3 (157.77 MB/s) against the
    baseline side's round-4 outlier (208.27 MB/s), while both sides' clean
    rounds sat at ~348-349 MB/s (parity) — the verdict flipped against #107
    (PASS x1.126) without any change in steady-state reality. The steal gate
    cannot catch this interference class (it reported 0 discarded windows),
    so a robust central statistic carries the verdict and min/best remain as
    worst-case / ceiling observations.
    """
    summary: dict[str, dict] = {}
    for wl in BENCH_WORKLOADS:
        a = samples[("a", wl)]
        b = samples[("b", wl)]
        row: dict = {
            "samplesA": len(a),
            "samplesB": len(b),
            # Raw per-round rates (run #107 lesson: summary ratios of short
            # workloads can be round-selection artifacts — same-binary
            # between-round variance reached 2.1x on scan, and round 0 is
            # systematically cold on BOTH sides. The per-round data must be
            # part of the report, not only the raw log).
            "roundsA": a,
            "roundsB": b,
        }
        if a and b:
            for tag, fn in (("Min", min), ("Med", statistics.median), ("Best", max)):
                a_stat, b_stat = fn(a), fn(b)
                row[f"baseline{tag}"] = a_stat
                row[f"pgo{tag}"] = b_stat
                row[f"ratio{tag}"] = round(b_stat / a_stat, 4) if a_stat else None
        else:
            for tag in ("Min", "Med", "Best"):
                row[f"baseline{tag}"] = row[f"pgo{tag}"] = row[f"ratio{tag}"] = None
        row["ratio"] = row["ratioMin"]  # legacy key (run #107/#108 records)
        summary[wl] = row
    return summary


def measure(a_dir: str, b_dir: str, rounds: int, json_out: str | None, workdir: Path) -> dict:
    """Alternate A/B subprocess runs; steal-gate on Linux; median verdict."""
    fx_root = workdir / "fixtures"
    size_mb = int(os.environ.get("TRAIN_MB", "32"))
    n_models = int(os.environ.get("TRAIN_MODELS", "800"))
    hash_mb = int(os.environ.get("TRAIN_HASH_MB", "128"))
    print(
        f"[measure] building shared fixtures ({size_mb} MB models, {n_models} models, {hash_mb} MB hash)...",
        flush=True,
    )
    build_fixtures(fx_root, size_mb, n_models, hash_mb)

    samples: dict[tuple[str, str], list[float]] = {(side, wl): [] for side in "ab" for wl in BENCH_WORKLOADS}
    contaminated = 0
    discarded = 0
    for r in range(rounds):
        for side, lib in (("a", a_dir), ("b", b_dir)):
            for wl in BENCH_WORKLOADS:
                result = None
                dirty = False
                # steal gate (BENCH protocol): a contaminated window
                # is DISCARDED AND RETRIED (not silently dropped — losing the
                # sample would leave the side without a minimum to judge).
                for attempt in range(MAX_STEAL_RETRIES):
                    steal0 = _steal_ticks()
                    wall0 = time.monotonic()
                    proc = subprocess.run(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--bench-one",
                            "--lib-dir",
                            lib,
                            "--workload",
                            wl,
                            "--workdir",
                            str(workdir),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=1800,
                    )
                    wall = time.monotonic() - wall0
                    if proc.returncode != 0:
                        raise SystemExit(f"[measure] bench-one failed ({side}/{wl}):\n{proc.stdout}\n{proc.stderr}")
                    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("{"))
                    result = json.loads(line)
                    steal1 = _steal_ticks()
                    dirty = False
                    if steal0 is not None and steal1 is not None:
                        stolen_s = (steal1 - steal0) / 100.0  # jiffies ~= 10 ms
                        if wall > 0 and stolen_s / wall > 0.05:
                            dirty = True
                            discarded += 1
                            time.sleep(0.2 * (attempt + 1))  # let the noisy neighbour pass
                            continue
                    break
                if result is None:
                    raise SystemExit(f"[measure] no sample for {side}/{wl}")
                if dirty:
                    contaminated += 1
                samples[(side, wl)].append(result["rate"])
                flag = " [steal-contaminated]" if dirty else ""
                rate, unit, secs = result["rate"], result["unit"], result["seconds"]
                print(f"[measure] round {r} side {side} {wl}: {rate} {unit} ({secs} s){flag}", flush=True)

    summary = summarize_workloads(samples)
    out = {
        "rounds": rounds,
        "discardedStealWindows": discarded,
        "contaminatedSamples": contaminated,
        "env": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpuCount": os.cpu_count(),
            "sizeMb": size_mb,
            "models": n_models,
            "hashMb": hash_mb,
        },
        "workloads": summary,
    }
    print("\n[measure] === summary (B/A ratios: min / median / best) ===")
    for wl, row in summary.items():
        print(
            f"  {wl:12} min={row['ratioMin']}  median={row['ratioMed']}  best={row['ratioBest']}"
            f"   (baseline med={row['baselineMed']}, pgo med={row['pgoMed']})"
        )
    blob = json.dumps(out, indent=2) + "\n"
    if json_out:
        Path(json_out).write_text(blob, encoding="utf-8")
        print(f"[measure] wrote {json_out}")
    else:
        print(blob)
    return out


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lib-dir", help="directory holding the mm_core binary (default: PYTHONPATH)")
    ap.add_argument("--workdir", help="fixtures/work directory (temp by default; reused when it exists)")
    ap.add_argument("--json-out", help="write the summary JSON here instead of stdout")
    ap.add_argument("--measure", action="store_true", help="A/B throughput measurement mode")
    ap.add_argument("--bench-one", action="store_true", help="single timed workload (internal)")
    ap.add_argument("--workload", choices=BENCH_WORKLOADS, default="compress")
    ap.add_argument("--a", help="measure: baseline core directory")
    ap.add_argument("--b", help="measure: PGO core directory")
    ap.add_argument("--rounds", type=int, default=int(os.environ.get("TRAIN_ROUNDS", "2")))
    args = ap.parse_args()

    if args.measure:
        if not args.a or not args.b:
            ap.error("--measure requires --a and --b")
        workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="mmneo-pgo-"))
        workdir.mkdir(parents=True, exist_ok=True)
        measure(args.a, args.b, args.rounds, args.json_out, workdir)
        return 0

    mm = load_core(args.lib_dir)

    if args.bench_one:
        workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="mmneo-pgo-"))
        fx_root = workdir / "fixtures"
        if not fx_root.exists():
            fx = build_fixtures(
                fx_root,
                int(os.environ.get("TRAIN_MB", "32")),
                int(os.environ.get("TRAIN_MODELS", "800")),
                int(os.environ.get("TRAIN_HASH_MB", "128")),
            )
        else:
            # rebuild the path map without touching the bytes (deterministic names)
            fx = {
                "bf16_low": fx_root / "models" / "low.safetensors",
                "hash_target": fx_root / "hash.bin",
                "scan_root": fx_root / "models" / "checkpoints",
            }
        print(json.dumps(bench_one(mm, fx, workdir, args.workload)))
        return 0

    size_mb = int(os.environ.get("TRAIN_MB", "32"))
    n_models = int(os.environ.get("TRAIN_MODELS", "800"))
    hash_mb = int(os.environ.get("TRAIN_HASH_MB", "128"))
    rounds = args.rounds
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="mmneo-pgo-"))
    workdir.mkdir(parents=True, exist_ok=True)
    fx_root = workdir / "fixtures"
    print(
        f"[train] fixtures: {size_mb}MB models / {n_models} lib / {hash_mb}MB hash / {rounds} rounds -> {fx_root}",
        flush=True,
    )
    t0 = time.monotonic()
    fx = build_fixtures(fx_root, size_mb, n_models, hash_mb)
    print(f"[train] fixtures built in {time.monotonic() - t0:.1f} s", flush=True)
    summary = train(mm, fx, workdir, rounds)
    summary["env"] = {"platform": platform.platform(), "python": platform.python_version(), "cpuCount": os.cpu_count()}
    blob = json.dumps(summary, indent=2) + "\n"
    if args.json_out:
        Path(args.json_out).write_text(blob, encoding="utf-8")
        print(f"[train] wrote {args.json_out}")
    else:
        print(blob)
    print(f"[train] done in {summary['totalSeconds']} s (fixtures+work)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
