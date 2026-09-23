"""Baseline: library scan & hygiene scan (Plan §2.2 K9/K10, §1.2.2 #9).

Runs the REAL `py/manager.py ModelManager.scan_models()` /
`scan_hygiene()` (with the ComfyUI stubs from common.py) over a synthetic
library of N models (default 5,000 — the KPI figure):

* cold  — fresh process, page cache dropped when possible (needs root; the
          attempt is recorded in the output either way),
* warm  — second scan in the SAME process (front-matter `_SITE_CACHE` hot),
          which is what the current code pays on every manual refresh:
          a full re-walk (K10 baseline: there is no differential scan),
* hygiene — `scan_hygiene()` over all type roots.

Usage:
  python3 scripts/bench/gen_synthetic.py --library /tmp/mm-bench/library --library-models 5000
  python3 scripts/bench/bench_scan.py --library /tmp/mm-bench/library --json-out out.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common
from bench_zipnn import common_env

_LIBRARY_TYPES = ("checkpoints", "loras", "vae", "controlnet", "embeddings", "upscale_models")


def _drop_caches() -> str:
    """Try to evict the page cache (true 'cold'). Returns what happened."""
    try:
        with open("/proc/sys/vm/drop_caches", "w", encoding="ascii") as f:
            f.write("3\n")
        return "drop_caches ok"
    except OSError as exc:
        return f"drop_caches unavailable ({exc.strerror or exc}); scan runs with a warm dentry cache"


def _child_scan(spec: dict) -> dict:
    roots = {t: [os.path.join(spec["library"], t)] for t in _LIBRARY_TYPES}
    common.install_comfyui_stubs(model_roots=roots)
    common.import_extension()
    from py import manager

    mm = manager.ModelManager()

    cold_note = _drop_caches() if spec.get("dropCaches") else "skipped (warm run)"
    t0 = time.monotonic()
    total_entries = 0
    per_type: dict[str, float] = {}
    for t in _LIBRARY_TYPES:
        tt = time.monotonic()
        entries = mm.scan_models(t, False)
        per_type[t] = time.monotonic() - tt
        total_entries += len(entries)
    cold_sec = time.monotonic() - t0

    # Warm: immediate re-scan, same process (_SITE_CACHE hot). The current
    # implementation has no differential path — this is a FULL walk again.
    t0 = time.monotonic()
    warm_entries = sum(len(mm.scan_models(t, False)) for t in _LIBRARY_TYPES)
    warm_sec = time.monotonic() - t0

    t0 = time.monotonic()
    hygiene = mm.scan_hygiene()
    hygiene_sec = time.monotonic() - t0

    return {
        "kind": "scan",
        "library": spec["library"],
        "entries": total_entries,
        "warmEntries": warm_entries,
        "coldScanSec": cold_sec,
        "coldNote": cold_note,
        "perTypeSec": per_type,
        "warmScanSec": warm_sec,
        "hygieneSec": hygiene_sec,
        "hygieneOrphans": len(hygiene["orphans"]),
        "hygieneEmpty": len(hygiene["empty"]),
        "peakRssMib": common.PeakRSS.mib(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child", help=argparse.SUPPRESS)
    ap.add_argument("--library", default="/tmp/mm-bench/library")
    ap.add_argument("--repeat", type=int, default=3, help="fresh-process repetitions (median reported)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    if args.child:
        print(json.dumps(_child_scan(json.loads(args.child))))
        return

    if not os.path.isdir(args.library):
        raise SystemExit(f"library fixture missing: {args.library} (run gen_synthetic.py --library ...)")

    results: dict = {"env": common_env(), "runs": []}
    for i in range(args.repeat):
        spec = {"library": args.library, "dropCaches": True}
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--child", json.dumps(spec)],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if proc.returncode != 0:
            print(proc.stderr[-2000:], file=sys.stderr)
            raise SystemExit(f"scan child failed rc={proc.returncode}")
        run = json.loads(proc.stdout.strip().splitlines()[-1])
        results["runs"].append(run)
        print(
            f"[scan run {i}] entries={run['entries']} cold={run['coldScanSec']:.3f}s "
            f"warm={run['warmScanSec']:.3f}s hygiene={run['hygieneSec']:.3f}s "
            f"peak={run['peakRssMib']:.0f}MiB ({run['coldNote']})"
        )

    cold = sorted(r["coldScanSec"] for r in results["runs"])[len(results["runs"]) // 2]
    warm = sorted(r["warmScanSec"] for r in results["runs"])[len(results["runs"]) // 2]
    results["median"] = {"coldScanSec": cold, "warmScanSec": warm}
    print(f"median: cold={cold:.3f}s warm={warm:.3f}s")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"results -> {args.json_out}")


if __name__ == "__main__":
    main()
