"""Baseline: hashing paths (Plan §2.2 K7/K8, §1.2.2 #11).

* K8 — `py/identify.py compute_hashes()`: the single-pass 5-notation hash
  (SHA256 + AutoV2 + AutoV1 window + CRC32 + BLAKE3 when installed) measured
  on a --size-mb file; MB/s recorded for the 10 GB extrapolation.
* K7 — `py/download.py _sha256_of()`: the FULL re-read Civitai verification
  does after a download completes (1 MiB chunks). Its seconds-per-byte is the
  "extra I/O" the Rust inline hasher (B1) removes entirely.
* Reference: a bare hashlib sha256 pass with the same chunking, to separate
  "algorithm cost" from "the 5-in-1 pass cost".

Forked subprocesses again (VmHWM per measurement).

Usage:
  python3 scripts/bench/bench_hash.py --fixtures /tmp/mm-bench \\
      [--size-mb 256] [--json-out out.json]
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


def _child_hash(spec: dict) -> dict:
    what = spec["what"]
    path = spec["path"]
    size = os.path.getsize(path)
    common.install_comfyui_stubs()
    common.import_extension()

    if what == "compute_hashes":
        from py import identify

        try:
            import blake3  # noqa: F401

            has_blake3 = True
        except ImportError:
            has_blake3 = False
        t0 = time.monotonic()
        hashes = identify.compute_hashes(path)
        seconds = time.monotonic() - t0
        return {
            "kind": "hash",
            "what": what,
            "bytes": size,
            "seconds": seconds,
            "MBps": size / seconds / (1024 * 1024),
            "algos": sorted(hashes),
            "blake3Available": has_blake3,
            "sha256": hashes.get("SHA256"),
            "peakRssMib": common.PeakRSS.mib(),
        }
    if what == "sha256_of":
        from py import download

        t0 = time.monotonic()
        digest = download._sha256_of(path)
        seconds = time.monotonic() - t0
        return {
            "kind": "hash",
            "what": what,
            "bytes": size,
            "seconds": seconds,
            "MBps": size / seconds / (1024 * 1024),
            "sha256": (digest or "").upper(),
            "peakRssMib": common.PeakRSS.mib(),
        }
    if what == "sha256_reference":
        import hashlib

        t0 = time.monotonic()
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha.update(chunk)
        seconds = time.monotonic() - t0
        return {
            "kind": "hash",
            "what": what,
            "bytes": size,
            "seconds": seconds,
            "MBps": size / seconds / (1024 * 1024),
            "sha256": sha.hexdigest().upper(),
            "peakRssMib": common.PeakRSS.mib(),
        }
    raise ValueError(f"unknown measurement {what!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child", help=argparse.SUPPRESS)
    ap.add_argument("--fixtures", default="/tmp/mm-bench")
    ap.add_argument("--size-mb", type=int, default=256)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    if args.child:
        print(json.dumps(_child_hash(json.loads(args.child))))
        return

    path = os.path.join(args.fixtures, f"hash-target-{args.size_mb}mb.bin")
    if not os.path.exists(path):
        print(f"generating {path} ...", file=sys.stderr)
        with open(path, "wb") as f:
            for _ in range(args.size_mb):
                f.write(os.urandom(1024 * 1024))

    results: dict = {"env": common_env(), "sizeMb": args.size_mb, "measurements": []}
    digests = {}
    for what in ("compute_hashes", "sha256_of", "sha256_reference"):
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--child", json.dumps({"what": what, "path": path})],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if proc.returncode != 0:
            print(proc.stderr[-2000:], file=sys.stderr)
            raise SystemExit(f"{what} child failed rc={proc.returncode}")
        r = json.loads(proc.stdout.strip().splitlines()[-1])
        results["measurements"].append(r)
        if r.get("sha256"):
            digests[what] = r["sha256"]
        print(
            f"[{what:18s}] {r['seconds']:.3f}s  {r['MBps']:.1f} MB/s  peak={r['peakRssMib']:.0f}MiB"
            + (f"  algos={r['algos']}" if "algos" in r else "")
        )

    same = len(set(digests.values())) == 1
    results["sha256CrossCheck"] = {"values": digests, "allEqual": same}
    print(f"sha256 cross-check: {'MATCH' if same else 'MISMATCH!!'} {digests}")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"results -> {args.json_out}")


if __name__ == "__main__":
    main()
