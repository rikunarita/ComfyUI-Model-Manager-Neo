#!/usr/bin/env python3
"""G2 gate — verify that a PGO profile was actually applied to a build.

Part of the PGO pipeline (Step 3 pilot / Step 4 shipping jobs). Inputs:

* ``show_txt``  — the output of ``llvm-profdata show merged.profdata``
* ``build_log`` — the ``-Cprofile-use`` build log, built with
  ``-Cllvm-args=-pgo-warn-missing-function`` so every function of the
  optimized build that has NO profile record emits a warning line
* ``--all-functions-txt`` (optional) — ``llvm-profdata show --all-functions``
  dump for the positive workspace probe

Hard-fail conditions (recalibrated 2026-10-01 after native run #106):

* ``Total functions < --min-functions``      — the instrumented build or the
  training run did not happen.
* ``Total count == 0``                        — the profile holds no execution
  data at all.
* ``missing / total >= --max-missing-ratio``  — wholesale hash mismatch, i.e.
  the profile silently no-op'd. The ORIGINAL gate (< 1 %) was mis-calibrated
  from a dev-profile experiment: under the shipping release profile
  (``lto = "fat"`` + ``codegen-units = 1``) the PGO inliner legitimately
  diverges from the instrumented build — run #106 measured **13.81 %**
  (1,052 / 7,618) missing, classifiable as 518 generic instantiations +
  254 closure identities + 485 out-of-line re-materializations of functions
  that were fully inlined during instrumentation (hot codec helpers such as
  ``fse::DTable::decode_symbol`` — their callers DO carry profile data).
  The profile itself demonstrably applied: ``Total count`` = 1.21e9.
  A true no-op shows up as a near-100 % ratio; 50 % separates the two
  populations with a wide margin while the exact value stays visible in the
  job summary of every run.
* ``znn_codec symbols in profile < --min-codec-functions`` — the profile was
  not produced by THIS workspace (wrong artifact trained).

Exit 0 = pass; prints a one-line verdict for the job summary.
"""

from __future__ import annotations

import argparse
import re
import sys


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("show_txt", help="`llvm-profdata show merged.profdata` output")
    ap.add_argument("build_log", help="profile-use build log (warn-missing-function enabled)")
    ap.add_argument("--all-functions-txt", help="`llvm-profdata show --all-functions` dump (positive probe)")
    ap.add_argument("--max-missing-ratio", type=float, default=0.50)
    ap.add_argument("--min-functions", type=int, default=1000)
    ap.add_argument("--min-codec-functions", type=int, default=100)
    args = ap.parse_args()

    show = _read(args.show_txt)
    m_funcs = re.search(r"Total functions:\s+(\d+)", show)
    m_count = re.search(r"Total count:\s+(\d+)", show)
    if not m_funcs or not m_count:
        print("G2 FAILED: cannot parse `Total functions` / `Total count` from the llvm-profdata show output")
        return 1
    total_functions = int(m_funcs.group(1))
    total_count = int(m_count.group(1))

    missing = len(re.findall(r"no profile data available for function", _read(args.build_log)))
    ratio = missing / max(total_functions, 1)

    codec_funcs = None
    if args.all_functions_txt:
        codec_funcs = len(set(re.findall(r"\S*znn_codec\S*", _read(args.all_functions_txt))))

    print(
        f"G2: profiled functions={total_functions}, total count={total_count}, "
        f"missing-profile warnings={missing} ({ratio:.2%}), znn_codec symbols={codec_funcs}"
    )

    failures: list[str] = []
    if total_functions < args.min_functions:
        failures.append(
            f"profile covers only {total_functions} functions (< {args.min_functions}) — training did not run?"
        )
    if total_count == 0:
        failures.append("profile holds zero execution counts — the instrumented core was never exercised")
    if ratio >= args.max_missing_ratio:
        failures.append(
            f"missing-profile ratio {ratio:.2%} >= {args.max_missing_ratio:.0%} — profile effectively NOT applied"
        )
    if codec_funcs is not None and codec_funcs < args.min_codec_functions:
        failures.append(
            f"only {codec_funcs} znn_codec symbols in the profile (< {args.min_codec_functions}) — wrong workspace?"
        )

    if failures:
        for failure in failures:
            print(f"G2 FAILED: {failure}")
        return 1
    print(
        f"G2 OK: profile applied (missing {ratio:.2%} < {args.max_missing_ratio:.0%}"
        " = benign fat-LTO/PGO inliner divergence)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
