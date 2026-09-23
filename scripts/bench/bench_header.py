"""Baseline: safetensors header parsing (Plan §2.2 K11/K12, §1.2.2 #6/#10).

Measures the REAL `py/utils.py` functions on a synthetic ~8 MB MoE header
(gen_synthetic.py --moe-header; DeepSeek-style names, ~64k tensor entries):

* `get_model_tensors()`  — full parse + tensor list build (K11). The current
  implementation = `comfy.utils.safetensors_header` (8-byte length read +
  header read) + Python `json.loads` + a dict-comprehension walk.
* `get_model_metadata()` — 1 MiB max_size guard: for MoE headers ABOVE 1 MiB
  it returns {} without parsing (a behaviour worth recording alongside K11).
* Sub-step breakdown (read vs json.loads vs list build) to show where the
  milliseconds go.

K12: before Quick Win A1 (commit "fix: モデル詳細ルート…"), the entire
`get_model_info` route — this parse included — ran ON the event loop, so the
K11 milliseconds are exactly how long the whole server (websockets included)
used to freeze per model-detail open. A1 moved it to the IO executor; the
Rust header parser (Phase 2/5, K11 target <= 40 ms) removes the remaining
cost.

Usage:
  python3 scripts/bench/bench_header.py --model /tmp/mm-bench/moe-header.safetensors \
      [--repeat 7] [--json-out out.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common
from bench_zipnn import common_env


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="/tmp/mm-bench/moe-header.safetensors")
    ap.add_argument("--repeat", type=int, default=7)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    common.install_comfyui_stubs()
    common.import_extension()
    from py import utils

    path = args.model
    size = os.path.getsize(path)
    header_bytes_len = size - 8  # the file is header + empty data stub

    results: dict = {
        "env": common_env(),
        "model": path,
        "fileBytes": size,
        "headerBytes": header_bytes_len,
        "runs": [],
    }

    for i in range(args.repeat):
        run: dict = {}

        # (a) header read alone (comfy.utils stub == ComfyUI implementation)
        t0 = time.monotonic()
        raw = utils.comfy.utils.safetensors_header(path, max_size=32 * 1024 * 1024)
        run["readSec"] = time.monotonic() - t0

        # (b) json.loads of the raw header
        t0 = time.monotonic()
        header = json.loads(raw)
        run["jsonLoadsSec"] = time.monotonic() - t0

        # (c) the tensor-list build loop of get_model_tensors
        t0 = time.monotonic()
        tensors = [
            {"name": name, "dtype": spec.get("dtype", ""), "shape": spec.get("shape", [])}
            for name, spec in header.items()
            if name != "__metadata__" and isinstance(spec, dict)
        ]
        run["listBuildSec"] = time.monotonic() - t0
        run["tensorCount"] = len(tensors)

        # (d) the real function, end to end
        t0 = time.monotonic()
        real = utils.get_model_tensors(path)
        run["getModelTensorsSec"] = time.monotonic() - t0
        run["getModelTensorsCount"] = len(real)

        # (e) metadata path (1 MiB guard — returns {} for this header)
        t0 = time.monotonic()
        meta = utils.get_model_metadata(path)
        run["getModelMetadataSec"] = time.monotonic() - t0
        run["metadataEmptyDueToGuard"] = meta == {}

        run["peakRssMib"] = common.PeakRSS.mib()
        results["runs"].append(run)
        print(
            f"[header run {i}] read={run['readSec'] * 1000:.1f}ms "
            f"json.loads={run['jsonLoadsSec'] * 1000:.1f}ms "
            f"list={run['listBuildSec'] * 1000:.1f}ms "
            f"get_model_tensors={run['getModelTensorsSec'] * 1000:.1f}ms "
            f"tensors={run['tensorCount']} metadataGuard={run['metadataEmptyDueToGuard']}"
        )

    n = len(results["runs"])
    med = lambda key: sorted(r[key] for r in results["runs"])[n // 2]  # noqa: E731
    results["median"] = {
        "readSec": med("readSec"),
        "jsonLoadsSec": med("jsonLoadsSec"),
        "listBuildSec": med("listBuildSec"),
        "getModelTensorsSec": med("getModelTensorsSec"),
    }
    print(
        f"median get_model_tensors: {results['median']['getModelTensorsSec'] * 1000:.1f} ms "
        f"(read {results['median']['readSec'] * 1000:.1f} + json.loads "
        f"{results['median']['jsonLoadsSec'] * 1000:.1f} + list {results['median']['listBuildSec'] * 1000:.1f})"
    )
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"results -> {args.json_out}")


if __name__ == "__main__":
    main()
