"""K5 — Appendix C reproduction: the vendored C core's memory-safety defects.

Runs the documented crash cases against the SHIPPED prebuilt
`third_party/zipnn-core-bin/linux-x86_64/zipnn_core.cpython-3XX*.so` — each
case in its own subprocess so a SIGSEGV is observable as an exit code and can
never take the bench harness down with it:

  * dtype32 path (num_buf=4, bit_reorder=1, byte_reorder=220): total lengths
    with `total % 262144 ∈ {1,2,3}` → deterministic SEGFAULT (NULL-plane
    write, Plan appendix C.4-1);
  * controls: chunk-boundary and %4≥4 final chunks → must succeed AND
    round-trip byte-exactly through `combine_dtype` (appendix C.3/C.4-3);
  * dtype16 path (num_buf=2, byte_reorder=10): boundary lengths + odd length
    → documented as surviving (UB in source analysis, no crash).

The Rust port must answer every one of these with "error or correct result"
— never a crash (KPI K5); this script's JSONL is the C-side baseline.

Relationship to bench_zipnn.py: that script reproduces the three headline
crash cases (262145/6/7) plus the PRODUCTION delta-path reachability; this
script runs the FULL Plan Appendix C.3 matrix (22 cases) so the whole
documented behaviour table is re-runnable in one command — every case must
match the appendix ("segv" where documented, "ok + byte-exact roundtrip"
elsewhere). Phase 1 pins the same matrix as Rust regression tests.

Run: python3 scripts/bench/bench_c_defects.py [--json-out results/c_defects.json]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from bench_zipnn import common_env

REPO = Path(__file__).resolve().parents[2]
BIN_DIR = REPO / "third_party" / "zipnn-core-bin" / "linux-x86_64"

CHILD = r"""
import os, sys
sys.path.insert(0, r"{bin_dir}")
import zipnn_core

L = int(sys.argv[1]); num_buf = int(sys.argv[2]); bits = int(sys.argv[3]); mode = int(sys.argv[4])
entropy = sys.argv[5]
if entropy == "low":
    data = bytearray((b"\x3c\x3d\x3e\x3f" * 8192) * (L // 32768 + 1))[:L]
else:
    data = bytearray(os.urandom(L))
original = bytes(data)
H = b"ZN" + bytes(30)
comp = zipnn_core.zipnn_core(H, data, num_buf, bits, mode, 0, 262144, 0.95, 10, 1)
payload = comp[len(H):]
back = zipnn_core.combine_dtype(memoryview(payload), num_buf, bits, mode, 262144, L, 1)
print("ROUNDTRIP", "OK" if bytes(back) == original else "MISMATCH")
"""

# (length, num_buf, bit_reorder, byte_reorder, entropy, expected)
CASES: list[tuple[int, int, int, int, str, str]] = [
    # Appendix C.3: deterministic SEGFAULT (final chunk 1/2/3 bytes, dtype32)
    (262144 + 1, 4, 1, 220, "rand", "segv"),
    (262144 + 2, 4, 1, 220, "rand", "segv"),
    (262144 + 3, 4, 1, 220, "rand", "segv"),
    (524288 + 1, 4, 1, 220, "rand", "segv"),
    (524288 + 2, 4, 1, 220, "rand", "segv"),
    (524288 + 3, 4, 1, 220, "rand", "segv"),
    # entropy of the data makes no difference (C.3): compressible chunk too
    (262144 + 1, 4, 1, 220, "low", "segv"),
    (262144 + 2, 4, 1, 220, "low", "segv"),
    # controls: exact boundary and %4==0 / >=4-byte final chunks → OK
    (262144, 4, 1, 220, "rand", "ok"),
    (262144 + 4, 4, 1, 220, "rand", "ok"),
    (262148, 4, 1, 220, "rand", "ok"),
    (1000000, 4, 1, 220, "rand", "ok"),
    (1000001, 4, 1, 220, "rand", "ok"),
    (1000002, 4, 1, 220, "rand", "ok"),
    (1000003, 4, 1, 220, "rand", "ok"),
    (64, 4, 1, 220, "rand", "ok"),
    (67, 4, 1, 220, "rand", "ok"),
    # dtype16 path (bf16: 2 planes + bit reorder): boundaries + odd length
    (262144, 2, 1, 10, "rand", "ok"),
    (262146, 2, 1, 10, "rand", "ok"),
    (1000002, 2, 1, 10, "rand", "ok"),
    (65, 2, 1, 10, "rand", "ok"),
    (262145, 2, 1, 10, "rand", "ok"),
]


def run_case(length: int, num_buf: int, bits: int, mode: int, entropy: str) -> tuple[int, str]:
    code = CHILD.format(bin_dir=str(BIN_DIR))
    proc = subprocess.run(
        [sys.executable, "-c", code, str(length), str(num_buf), str(bits), str(mode), entropy],
        capture_output=True,
        text=True,
        timeout=120,
    )
    tail = next((ln for ln in proc.stdout.splitlines() if ln.startswith("ROUNDTRIP")), "")
    return proc.returncode, tail


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    results: dict = {"env": common_env(), "coreSo": str(BIN_DIR), "cases": []}
    if not BIN_DIR.is_dir():
        results["skipped"] = f"no prebuilt dir at {BIN_DIR}"
        print(json.dumps(results, indent=1))
        return
    crashes = oks = mismatches = unexpected = 0
    for length, num_buf, bits, mode, entropy, expected in CASES:
        rc, roundtrip = run_case(length, num_buf, bits, mode, entropy)
        segv = rc == -11  # SIGSEGV
        ok = rc == 0 and roundtrip == "ROUNDTRIP OK"
        if segv:
            crashes += 1
        elif ok:
            oks += 1
        else:
            mismatches += 1
        hit = (segv and expected == "segv") or (ok and expected == "ok")
        if not hit:
            unexpected += 1
        case = {
            "length": length,
            "path": f"num_buf={num_buf},bits={bits},mode={mode}",
            "entropy": entropy,
            "expected": expected,
            "result": "segv" if segv else "ok" if ok else f"other(rc={rc})",
            "roundtrip": roundtrip,
            "asDocumented": hit,
        }
        results["cases"].append(case)
        print(
            f"[{case['result']:>10}] len={length:>8} {case['path']:26} "
            f"entropy={entropy:5} expected={expected:5} roundtrip={roundtrip or '-'}"
        )
    results["summary"] = {
        "cases": len(CASES),
        "segv": crashes,
        "okRoundtrip": oks,
        "other": mismatches,
        "unexpected": unexpected,
        "appendixCReproduced": unexpected == 0 and crashes >= 6,
    }
    print(json.dumps({"summary": results["summary"]}))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1)
        print(f"results -> {args.json_out}")
    # Exit 0 even when segfaults reproduce: THAT is the expected C baseline.
    sys.exit(0)


if __name__ == "__main__":
    os.chdir(REPO)
    main()
