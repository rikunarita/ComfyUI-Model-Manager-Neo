"""Phase 3 KPI bench: the NATIVE delta pipeline vs the LEGACY delta path.

Measures Plan §2.2 **K4** (delta peak RAM — the legacy path reads BOTH files
fully into RAM, pads, numpy-XORs and hands whole buffers to the C core:
Phase 0 measured +173 MiB ≈ 5.4x the fine-tune on a 32 MB pair, BENCH §4.2;
the native path streams 1 MiB XOR chunks off two mmaps and must stay
O(chunk)) and **K5** (the Appendix-C SEGFAULT class: `total % 256 KiB ∈
{1,2,3}` killed the vendored C core through the PRODUCTION legacy delta
route — Phase 0 `delta-segfault-demo`, signal 11; the native route must
complete the same pairs byte-exactly).

Methodology (the Phase-1/2 gate protocol, MEMO 2026-09-23): every timed
phase runs in an isolated subprocess (kernel-recorded VmHWM peak), the two
engines alternate inside ONE session on the SAME fixtures (this shared host
swings 2-3x between sessions — only same-session comparisons are valid),
per-side minimums are the reported values, and every window records the
host steal ticks. The native child imports ONLY ``mm_core`` (no torch); the
legacy child pays the ~240 MiB torch baseline before anything moves.

Usage::

    FIXTURES=/tmp/mm-bench ./scripts/bench/bench_native_delta.py \
        [--pair-mb 32] [--rounds 3] [--skip-legacy] \
        [--json-out scripts/bench/results/native_delta.json]

Requires: the built native binary (scripts/build-native.sh --target <tag>);
the legacy comparison side needs torch + the vendored zipnn (skipped with a
loud note when unavailable).
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
from bench_delta import _handbuilt_pair  # the Phase-0 SEGFAULT-class builder
from bench_zipnn import common_env  # same env block as the Phase-0 result JSONs


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


def _native_core():
    sys.path.insert(0, REPO)
    common.install_comfyui_stubs()
    common.import_extension()
    from py import config as _config

    _config.extension_uri = REPO
    from py import native

    native._module = None
    native._reason = None
    native._attempted = False
    if not native.load():
        raise RuntimeError(f"native core unavailable: {native.reason()}")
    return native.core()


def _job(mm, handle: int) -> dict:
    while True:
        _done, _total, phase = mm.job_progress(handle)
        if phase in ("done", "failed"):
            break
        time.sleep(0.005)
    err = mm.job_error(handle)
    if err:
        raise RuntimeError(err)
    return json.loads(mm.job_result(handle))


def _child_native(spec: dict) -> dict:
    """One native delta phase through the PRODUCTION loader (py/native)."""
    mm = _native_core()
    phase = spec["phase"]
    baseline_rss = _peak_rss_mib()  # mm_core import only (no torch)
    noop_meta = spec.get("meta")

    steal0 = _steal_ticks()
    t0 = time.monotonic()
    opts = {"threads": spec.get("threads", 0)}
    if phase == "compress":
        result = _job(mm, mm.zipnn_delta_compress(spec["base"], spec["ft"], spec["out"], opts))
    else:
        meta = noop_meta
        if meta is None:
            with open(f"{spec['delta']}.neo-delta.json", encoding="utf-8") as f:
                meta = json.load(f)
        result = _job(mm, mm.zipnn_delta_decompress(spec["base"], spec["delta"], spec["out"], meta, opts))
    seconds = time.monotonic() - t0
    steal1 = _steal_ticks()

    out = {
        "kind": f"native-delta-{phase}",
        "seconds": seconds,
        "result": result,
        "baselineRssMib": baseline_rss,
        "peakRssMib": _peak_rss_mib(),
        "stealTicks": (steal1 - steal0) if (steal0 is not None and steal1 is not None) else None,
    }
    if phase == "compress":
        out["deltaBytes"] = os.path.getsize(spec["out"])
        out["ftBytes"] = os.path.getsize(spec["ft"])
        out["ratio"] = out["deltaBytes"] / max(1, out["ftBytes"])
        # joined string (not a list): keeps the JSON prettier-stable
        out["sidecarKeys"] = ",".join(sorted(result.get("meta") or {}))
    else:
        out["restoredBytes"] = os.path.getsize(spec["out"])
        out["verified"] = result.get("verified")
        if spec.get("ftSha256"):
            out["restoredByteExact"] = _sha256_file(spec["out"]) == spec["ftSha256"]
    return out


def _child_legacy(spec: dict) -> dict:
    """One legacy delta phase (py/compress functions — torch + vendored C)."""
    common.install_comfyui_stubs()
    common.import_extension()
    from py import compress

    compress.ensure_zipnn()
    baseline_rss = _peak_rss_mib()  # torch + zipnn resident (~240 MiB)
    noop = lambda *_a: None  # noqa: E731
    phase = spec["phase"]

    steal0 = _steal_ticks()
    t0 = time.monotonic()
    if phase == "compress":
        stats = compress.delta_compress_files(spec["base"], spec["ft"], spec["out"], noop)
    else:
        stats = compress.delta_decompress_file(spec["base"], spec["delta"], spec["out"], noop)
    seconds = time.monotonic() - t0
    steal1 = _steal_ticks()

    out = {
        "kind": f"legacy-delta-{phase}",
        "seconds": seconds,
        "stats": stats,
        "baselineRssMib": baseline_rss,
        "peakRssMib": _peak_rss_mib(),
        "stealTicks": (steal1 - steal0) if (steal0 is not None and steal1 is not None) else None,
    }
    if phase == "compress":
        out["deltaBytes"] = os.path.getsize(spec["out"])
        out["ftBytes"] = os.path.getsize(spec["ft"])
        out["ratio"] = out["deltaBytes"] / max(1, out["ftBytes"])
    else:
        out["restoredBytes"] = os.path.getsize(spec["out"])
        if spec.get("ftSha256"):
            out["restoredByteExact"] = _sha256_file(spec["out"]) == spec["ftSha256"]
    return out


_CHILDREN = {"native": _child_native, "legacy": _child_legacy}


def _run_child(side: str, spec: dict) -> dict:
    payload = json.dumps(spec)
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--child-side", side, "--child", payload],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=3600,
    )
    if proc.returncode != 0:
        return {
            "kind": spec.get("kind", side),
            "error": f"child died rc={proc.returncode}: {proc.stderr[-800:]}",
            "signalDeath": -proc.returncode if proc.returncode < 0 else None,
        }
    for line in reversed(proc.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    return {"kind": spec.get("kind", side), "error": f"no result line: {proc.stdout[-400:]}"}


def _summary(r: dict) -> str:
    if "error" in r:
        return f"ERROR: {r['error'][:160]}"
    peak = r.get("peakRssMib", -1)
    base = r.get("baselineRssMib", -1)
    parts = [f"{r['seconds']:.3f}s", f"peak {peak:.0f}MiB (+{peak - base:.0f})"]
    if "deltaBytes" in r:
        parts.append(f"delta {r['deltaBytes']}B ratio {r.get('ratio', 0):.4f}")
    if "restoredByteExact" in r:
        parts.append(f"byteExact={r['restoredByteExact']}")
    if "verified" in r:
        parts.append(f"verified={r['verified']}")
    if r.get("stealTicks") is not None:
        parts.append(f"steal={r['stealTicks']}")
    return "  ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child-side", help=argparse.SUPPRESS)
    ap.add_argument("--child", help=argparse.SUPPRESS)
    ap.add_argument("--fixtures", default=os.environ.get("FIXTURES", "/tmp/mm-bench"))
    ap.add_argument("--pair-mb", type=int, default=32, help="the Phase-0 K4 pair size")
    ap.add_argument("--rounds", type=int, default=3, help="interleaved rounds per side (min wins)")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--skip-legacy", action="store_true")
    ap.add_argument("--skip-segfault-class", action="store_true")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    if args.child_side:
        print(json.dumps(_CHILDREN[args.child_side](json.loads(args.child))))
        return

    os.makedirs(args.fixtures, exist_ok=True)
    out_dir = os.path.join(args.fixtures, "native-delta-out")
    os.makedirs(out_dir, exist_ok=True)
    results: dict = {"env": common_env(), "rounds": args.rounds, "measurements": []}

    # the SAME pair fixture as the Phase-0 K4 baseline (bench_delta.py)
    base = os.path.join(args.fixtures, f"pair-base-{args.pair_mb}mb.safetensors")
    ft = os.path.join(args.fixtures, f"pair-ft-{args.pair_mb}mb.safetensors")
    if not (os.path.exists(base) and os.path.exists(ft)):
        import gen_synthetic

        gen_synthetic.gen_pair(base, ft, args.pair_mb, 4242)
    ft_sha = _sha256_file(ft)
    results["ftSha256"] = ft_sha

    legacy_ok = not args.skip_legacy
    if legacy_ok:
        probe = _run_child(
            "legacy",
            {"kind": "probe", "phase": "compress", "base": base, "ft": ft, "out": os.path.join(out_dir, "probe.znn")},
        )
        if "error" in probe:
            print(f"note: legacy side unavailable ({probe['error'][:200]}) — native only", file=sys.stderr)
            legacy_ok = False
        else:
            results["measurements"].append(probe)
            for p in (os.path.join(out_dir, "probe.znn"), os.path.join(out_dir, "probe.znn.neo-delta.json")):
                if os.path.exists(p):
                    os.unlink(p)

    # interleaved rounds: native first each round (page-cache symmetry)
    for rnd in range(1, args.rounds + 1):
        nd = os.path.join(out_dir, f"pair.n{rnd}.znn")
        r = _run_child(
            "native",
            {
                "kind": "native-delta-compress",
                "phase": "compress",
                "base": base,
                "ft": ft,
                "out": nd,
                "threads": args.threads,
            },
        )
        r["round"] = rnd
        results["measurements"].append(r)
        print(f"[native-delta-compress   r{rnd}] {_summary(r)}")

        nr = os.path.join(out_dir, f"pair.n{rnd}.restored.safetensors")
        d = _run_child(
            "native",
            {
                "kind": "native-delta-decompress",
                "phase": "decompress",
                "base": base,
                "delta": nd,
                "out": nr,
                "ftSha256": ft_sha,
                "threads": args.threads,
            },
        )
        d["round"] = rnd
        results["measurements"].append(d)
        print(f"[native-delta-decompress r{rnd}] {_summary(d)}")
        if d.get("restoredByteExact") is not True:
            print("!! NATIVE DELTA RESTORE NOT BYTE-EXACT — KPI invalid, investigate", file=sys.stderr)
        for p in (nd, f"{nd}.neo-delta.json", nr):
            if os.path.exists(p):
                os.unlink(p)

        if legacy_ok:
            ld = os.path.join(out_dir, f"pair.l{rnd}.znn")
            lr = _run_child(
                "legacy",
                {
                    "kind": "legacy-delta-compress",
                    "phase": "compress",
                    "base": base,
                    "ft": ft,
                    "out": ld,
                    "threads": args.threads,
                },
            )
            lr["round"] = rnd
            results["measurements"].append(lr)
            print(f"[legacy-delta-compress   r{rnd}] {_summary(lr)}")
            lnr = os.path.join(out_dir, f"pair.l{rnd}.restored.safetensors")
            ldd = _run_child(
                "legacy",
                {
                    "kind": "legacy-delta-decompress",
                    "phase": "decompress",
                    "base": base,
                    "delta": ld,
                    "out": lnr,
                    "ftSha256": ft_sha,
                    "threads": args.threads,
                },
            )
            ldd["round"] = rnd
            results["measurements"].append(ldd)
            print(f"[legacy-delta-decompress r{rnd}] {_summary(ldd)}")
            if ldd.get("restoredByteExact") is not True:
                print("!! LEGACY DELTA RESTORE NOT BYTE-EXACT — investigate", file=sys.stderr)
            for p in (ld, f"{ld}.neo-delta.json", lnr):
                if os.path.exists(p):
                    os.unlink(p)

    # --- K5: the Appendix-C SEGFAULT class through the NATIVE delta route --
    # (the legacy demo of bench_delta.py kills the child with signal 11 on
    # these pairs; the native pipeline must complete them byte-exactly)
    if not args.skip_segfault_class:
        demo_dir = os.path.join(args.fixtures, "segdemo-native")
        results["segfaultClass"] = []
        for remainder in (1, 2, 3):
            b, f = _handbuilt_pair(demo_dir, remainder=remainder)
            f_sha = _sha256_file(f)
            out = os.path.join(demo_dir, f"k5-{remainder}.znn")
            c = _run_child(
                "native",
                {"kind": "k5-compress", "phase": "compress", "base": b, "ft": f, "out": out, "threads": args.threads},
            )
            restored = os.path.join(demo_dir, f"k5-{remainder}.restored")
            rec = {"remainder": remainder, "compress": c}
            if "error" not in c:
                drec = _run_child(
                    "native",
                    {
                        "kind": "k5-decompress",
                        "phase": "decompress",
                        "base": b,
                        "delta": out,
                        "out": restored,
                        "ftSha256": f_sha,
                        "threads": args.threads,
                    },
                )
                rec["decompress"] = drec
                rec["survived"] = "error" not in drec and drec.get("restoredByteExact") is True
            else:
                rec["survived"] = False
            results["segfaultClass"].append(rec)
            print(f"[K5 native delta total%256KiB=={remainder}] survived+byteExact={rec['survived']}  " + _summary(c))
            for p in (out, f"{out}.neo-delta.json", restored):
                if os.path.exists(p):
                    os.unlink(p)

    # --- reported minima (per side, per phase) ------------------------------
    def best(kind: str, key: str, pick: str):
        vals = [m[key] for m in results["measurements"] if m.get("kind") == kind and key in m and "error" not in m]
        if not vals:
            return None
        return min(vals) if pick == "min" else max(vals)

    report = {}
    kinds = (
        "native-delta-compress",
        "native-delta-decompress",
        "legacy-delta-compress",
        "legacy-delta-decompress",
    )
    for kind in kinds:
        entry = {}
        for key, pick in (("seconds", "min"), ("peakRssMib", "min")):
            v = best(kind, key, pick)
            if v is not None:
                entry[key] = round(v, 4)
        base_rss = best(kind, "baselineRssMib", "min")
        if entry.get("peakRssMib") is not None and base_rss is not None:
            entry["limitRssMib"] = round(entry["peakRssMib"] - base_rss, 3)
        if entry:
            report[kind] = entry
    results["best"] = report

    ft_bytes = os.path.getsize(ft)
    if "native-delta-compress" in report:
        limit = report["native-delta-compress"].get("limitRssMib", 0)
        report["k4LimitRatioNative"] = round(limit * 1024 * 1024 / ft_bytes, 4)
    if "legacy-delta-compress" in report:
        limit = report["legacy-delta-compress"].get("limitRssMib", 0)
        report["k4LimitRatioLegacy"] = round(limit * 1024 * 1024 / ft_bytes, 4)
    if results.get("segfaultClass"):
        report["k5AllSurvivedByteExact"] = all(r.get("survived") for r in results["segfaultClass"])

    print("\nbest per side:", json.dumps(report, indent=2))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fp:
            json.dump(results, fp, indent=2)
            fp.write("\n")  # prettier-stable (the CI Format gate)
        print(f"results -> {args.json_out}")


if __name__ == "__main__":
    main()
