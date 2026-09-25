"""Phase 2 KPI bench: the NATIVE safetensors pipeline vs the LEGACY e2e path.

Measures the Plan §2.2 KPIs K1 (compress peak RAM), K2 (compress throughput),
K3 (decompress throughput) and K13 (import cost) for the Rust pipeline
(``mm_core`` jobs — the production path ``py/compress.py`` switches to) on the
SAME machine, SAME session and SAME fixtures as the legacy
``compress_safetensors``/``decompress_safetensors`` run (the methodology the
Phase-1 speed gate established, MEMO 2026-09-23: this shared 2 vCPU host
swings 2-3x between sessions, so only same-session comparisons are valid;
each side reports its MINIMUM over interleaved rounds, and every window
records the host steal ticks so dirty windows are visible).

Every timed phase runs in a SUBPROCESS (clean kernel-recorded VmHWM peak,
like the Phase-0 suite): the native child imports ONLY ``mm_core`` (no
torch), which is itself the K13/K1 story — the legacy child pays the
~240 MiB torch baseline before a single tensor moves.

Usage::

    FIXTURES=/tmp/mm-bench ./scripts/bench/bench_native_e2e.py \
        [--model /path/real.safetensors] [--size-mb 64] [--rounds 3] \
        [--json-out scripts/bench/results/native_e2e.json]

Requires: the built native binary (scripts/build-native.sh --target <tag>),
and — for the legacy comparison side — torch + the vendored zipnn (skips the
legacy side with a loud note when unavailable, e.g. non-linux CI).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import common
from bench_zipnn import common_env  # same env block as the Phase-0 result JSONs


# ---------------------------------------------------------------------------
# child processes (one timed phase each; results as one JSON line on stdout)
# ---------------------------------------------------------------------------
def _peak_rss_mib() -> float:
    with open("/proc/self/status", encoding="utf-8") as f:
        for line in f:
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) / 1024.0
    return -1.0


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _steal_ticks() -> int | None:
    try:
        with open("/proc/stat", encoding="utf-8") as f:
            for line in f:
                if line.startswith("cpu "):
                    return int(line.split()[8])
    except OSError:
        pass
    return None


def _child_native(spec: dict) -> dict:
    """One native pipeline phase through the PRODUCTION loader (py/native)."""
    sys.path.insert(0, REPO)
    # stubs only for py.utils/py.config imports (no ComfyUI here)
    common.install_comfyui_stubs()
    common.import_extension()
    from py import config as _config

    _config.extension_uri = REPO  # the loader resolves native-bin through it
    from py import native

    native._module = None
    native._reason = None
    native._attempted = False
    if not native.load():
        return {"kind": spec["kind"], "error": f"native core unavailable: {native.reason()}"}
    mm = native.core()

    phase = spec["phase"]
    src, dst = spec["src"], spec["dst"]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    baseline_rss = _peak_rss_mib()  # after mm_core import ONLY (no torch)

    steal0 = _steal_ticks()
    t0 = time.monotonic()
    handle = (
        mm.zipnn_compress(src, dst, {"threads": spec.get("threads", 0), "paranoid": spec.get("paranoid", False)})
        if phase == "compress"
        else mm.zipnn_decompress(src, dst, {"threads": spec.get("threads", 0)})
    )
    while True:
        _done, _total, job_phase = mm.job_progress(handle)
        if job_phase in ("done", "failed"):
            break
        time.sleep(0.005)
    seconds = time.monotonic() - t0
    steal1 = _steal_ticks()
    err = mm.job_error(handle)
    if err:
        return {"kind": spec["kind"], "error": err, "seconds": seconds}
    result = json.loads(mm.job_result(handle))

    src_size = os.path.getsize(src)
    out = {
        "kind": f"native-{phase}",
        "model": src,
        "base": spec.get("base", os.path.basename(src)),
        "srcBytes": src_size,
        "dstBytes": os.path.getsize(dst),
        "seconds": seconds,
        "MBps": src_size / seconds / (1024 * 1024),
        "result": result,
        "baselineRssMib": baseline_rss,
        "peakRssMib": _peak_rss_mib(),
        "stealTicks": (steal1 - steal0) if (steal0 is not None and steal1 is not None) else None,
    }
    if phase == "decompress" and spec.get("originalSha256"):
        out["restoredByteExact"] = _sha256_file(dst) == spec["originalSha256"]
    if phase == "compress":
        out["originalSha256"] = result.get("srcSha256")
        out["exact"] = result.get("exact")
    return out


def _child_legacy(spec: dict) -> dict:
    """One legacy e2e phase (py/compress functions — torch + vendored C)."""
    common.install_comfyui_stubs()
    common.import_extension()
    from py import compress

    compress.ensure_zipnn()
    baseline_rss = _peak_rss_mib()  # torch + zipnn resident (~240 MiB)

    phase = spec["phase"]
    src, dst = spec["src"], spec["dst"]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    noop = lambda *_a: None  # noqa: E731

    steal0 = _steal_ticks()
    t0 = time.monotonic()
    src_size = os.path.getsize(src)
    if phase == "compress":
        stats = compress.compress_safetensors(src, dst, noop)
    else:
        stats = compress.decompress_safetensors(src, dst, noop)
    seconds = time.monotonic() - t0
    steal1 = _steal_ticks()

    out = {
        "kind": f"legacy-{phase}",
        "model": src,
        "base": spec.get("base", os.path.basename(src)),
        "srcBytes": src_size,
        "dstBytes": os.path.getsize(dst),
        "seconds": seconds,
        "MBps": src_size / seconds / (1024 * 1024),
        "stats": stats,
        "baselineRssMib": baseline_rss,
        "peakRssMib": _peak_rss_mib(),
        "stealTicks": (steal1 - steal0) if (steal0 is not None and steal1 is not None) else None,
    }
    if phase == "decompress" and spec.get("originalSha256"):
        out["restoredByteExact"] = _sha256_file(dst) == spec["originalSha256"]
    return out


_CHILDREN = {"native": _child_native, "legacy": _child_legacy}


def _run_child(side: str, spec: dict) -> dict:
    payload = json.dumps(spec)
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--child-side", side, "--child", payload],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    if proc.returncode != 0:
        return {"kind": spec["kind"], "error": f"child died rc={proc.returncode}: {proc.stderr[-800:]}"}
    for line in reversed(proc.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    return {"kind": spec["kind"], "error": f"no result line: {proc.stdout[-400:]}"}


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child-side", help=argparse.SUPPRESS)
    ap.add_argument("--child", help=argparse.SUPPRESS)
    ap.add_argument("--fixtures", default=os.environ.get("FIXTURES", "/tmp/mm-bench"))
    ap.add_argument("--model", action="append", default=None, help="real .safetensors model(s)")
    ap.add_argument("--size-mb", type=int, default=64, help="synthetic bf16 fixture size")
    ap.add_argument("--rounds", type=int, default=3, help="interleaved rounds per side (min wins)")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--skip-legacy", action="store_true")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    if args.child_side:
        print(json.dumps(_CHILDREN[args.child_side](json.loads(args.child))))
        return

    os.makedirs(args.fixtures, exist_ok=True)
    out_dir = os.path.join(args.fixtures, "native-e2e-out")
    os.makedirs(out_dir, exist_ok=True)

    results: dict = {"env": common_env(), "rounds": args.rounds, "measurements": []}

    # fixture list: the synthetic bf16 model (same generator as the Phase-0
    # e2e baseline) + any real models handed in
    models = []
    synth = os.path.join(args.fixtures, f"model-bf16-{args.size_mb}mb.safetensors")
    if not os.path.exists(synth):
        import gen_synthetic

        gen_synthetic.gen_model(synth, "bf16", args.size_mb, 777)
    models.append(synth)
    for m in args.model or []:
        if os.path.exists(m):
            models.append(m)
        else:
            print(f"!! model missing: {m}", file=sys.stderr)

    legacy_ok = not args.skip_legacy
    if legacy_ok:
        probe = _run_child(
            "legacy",
            {
                "kind": "probe",
                "phase": "compress",
                "src": models[0],
                "dst": os.path.join(out_dir, "probe.znn.safetensors"),
            },
        )
        if "error" in probe:
            print(f"note: legacy side unavailable ({probe['error'][:200]}) — native only", file=sys.stderr)
            legacy_ok = False
        else:
            results["measurements"].append(probe)

    for model in models:
        base = os.path.splitext(os.path.basename(model))[0]
        original_sha = _sha256_file(model) if os.path.getsize(model) <= 512 * 1024 * 1024 else None
        results.setdefault("originalSha", {})[base] = original_sha

        # interleaved rounds: native first each round (page-cache symmetry),
        # every phase an isolated subprocess; the per-side MINIMUM of the
        # clean windows is the reported value (Phase-1 gate protocol)
        for rnd in range(1, args.rounds + 1):
            znn = os.path.join(out_dir, f"{base}.r{rnd}.znn.safetensors")
            r = _run_child(
                "native",
                {
                    "kind": "native-compress",
                    "phase": "compress",
                    "src": model,
                    "dst": znn,
                    "threads": args.threads,
                    "base": base,
                },
            )
            r["round"] = rnd
            results["measurements"].append(r)
            print(f"[native-compress   r{rnd} {base}] {_summary(r)}")

            back = os.path.join(out_dir, f"{base}.r{rnd}.restored.safetensors")
            d = _run_child(
                "native",
                {
                    "kind": "native-decompress",
                    "phase": "decompress",
                    "src": znn,
                    "dst": back,
                    "threads": args.threads,
                    "originalSha256": original_sha,
                    "base": base,
                },
            )
            d["round"] = rnd
            results["measurements"].append(d)
            print(f"[native-decompress r{rnd} {base}] {_summary(d)}")
            if d.get("restoredByteExact") is False:
                print("!! NATIVE RESTORE NOT BYTE-EXACT — KPI invalid, investigate", file=sys.stderr)
            for p in (znn, back):
                if os.path.exists(p):
                    os.unlink(p)

            if legacy_ok:
                lznn = os.path.join(out_dir, f"{base}.l{rnd}.znn.safetensors")
                lr = _run_child(
                    "legacy",
                    {
                        "kind": "legacy-compress",
                        "phase": "compress",
                        "src": model,
                        "dst": lznn,
                        "threads": args.threads,
                        "base": base,
                    },
                )
                lr["round"] = rnd
                results["measurements"].append(lr)
                print(f"[legacy-compress   r{rnd} {base}] {_summary(lr)}")
                lback = os.path.join(out_dir, f"{base}.l{rnd}.restored.safetensors")
                ld = _run_child(
                    "legacy",
                    {
                        "kind": "legacy-decompress",
                        "phase": "decompress",
                        "src": lznn,
                        "dst": lback,
                        "threads": args.threads,
                        "originalSha256": original_sha,
                        "base": base,
                    },
                )
                ld["round"] = rnd
                results["measurements"].append(ld)
                print(f"[legacy-decompress r{rnd} {base}] {_summary(ld)}")
                for p in (lznn, lback):
                    if os.path.exists(p):
                        os.unlink(p)

    # verdict table: per-side minima + ratios (the KPI judgement basis)
    verdicts = []
    for model in models:
        base = os.path.splitext(os.path.basename(model))[0]
        v: dict = {"model": base}
        for side in ("native", "legacy"):
            for phase in ("compress", "decompress"):
                rows = [
                    m
                    for m in results["measurements"]
                    if m.get("kind") == f"{side}-{phase}" and m.get("base") == base and "MBps" in m
                ]
                if rows:
                    # per-side BEST (minimum-time / maximum-throughput window —
                    # the Phase-1 gate protocol, MEMO 2026-09-23)
                    v[f"{side}-{phase}-MBps-best"] = max(r["MBps"] for r in rows)
                    v[f"{side}-{phase}-peakRssMib-min"] = min(r["peakRssMib"] for r in rows)
                    v[f"{side}-{phase}-baselineRssMib"] = rows[0]["baselineRssMib"]
        if "native-compress-MBps-best" in v and "legacy-compress-MBps-best" in v:
            v["K2-ratio"] = v["native-compress-MBps-best"] / v["legacy-compress-MBps-best"]
        if "native-decompress-MBps-best" in v and "legacy-decompress-MBps-best" in v:
            v["K3-ratio"] = v["native-decompress-MBps-best"] / v["legacy-decompress-MBps-best"]
        verdicts.append(v)
    results["verdicts"] = verdicts
    for v in verdicts:
        print("VERDICT " + json.dumps(v))

    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out), exist_ok=True)
        # indent=2 + trailing newline = prettier-stable (the repo's Format
        # gate checks committed result JSONs)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
            f.write("\n")
        print(f"report → {args.json_out}")


def _summary(r: dict) -> str:
    if "error" in r:
        return f"ERROR: {r['error'][:160]}"
    parts = [
        f"{r['MBps']:.1f} MB/s",
        f"{r['seconds']:.3f}s",
        f"peak {r['peakRssMib']:.0f} MiB (base {r['baselineRssMib']:.0f})",
    ]
    if r.get("restoredByteExact") is not None:
        parts.append(f"byteExact={r['restoredByteExact']}")
    if r.get("stealTicks") is not None:
        parts.append(f"steal={r['stealTicks']}")
    return " | ".join(parts)


if __name__ == "__main__":
    main()
