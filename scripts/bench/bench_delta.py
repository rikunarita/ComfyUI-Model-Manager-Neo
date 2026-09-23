"""Baseline: current delta compression (Plan §2.2 K4 + Appendix C reachability).

The delta path of py/compress.py (`delta_compress_files` /
`delta_decompress_file`) reads BOTH files fully into RAM, space-pads the
headers to equal length, XORs everything with numpy and hands the result to
the vendored C core in float32/4-plane mode — the ~=4-5x peak-RAM claim of
Plan §1.2.2 #5 is measured here per phase, in forked subprocesses (own
VmHWM each, same isolation as bench_zipnn.py).

`--skip-segfault-demo` OFF (the default) additionally proves the Appendix C
defect is reachable through Neo's *production* delta path, not just raw C
calls: a hand-built safetensors pair whose padded total length hits
`total % 262144 == 1` must kill the child with SIGSEGV (K5 baseline).
Hand-built because the safetensors Rust serializer 8-aligns headers, which
would make odd remainders unreachable — a real fine-tune with an arbitrary
JSON header length has no such restriction.

Usage:
  python3 scripts/bench/bench_delta.py --fixtures /tmp/mm-bench \\
      [--pair-mb 32] [--json-out out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common
from bench_zipnn import _summary, common_env


def _sha256_file(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _child_delta(spec: dict) -> dict:
    common.install_comfyui_stubs()
    common.import_extension()
    from py import compress

    compress.ensure_zipnn()
    baseline_rss = common.PeakRSS.mib()

    phase = spec["phase"]
    noop = lambda *_a: None  # noqa: E731
    t0 = time.monotonic()
    if phase == "compress":
        stats = compress.delta_compress_files(spec["base"], spec["ft"], spec["out"], noop)
    else:
        stats = compress.delta_decompress_file(spec["base"], spec["delta"], spec["out"], noop)
    seconds = time.monotonic() - t0

    result = {
        "kind": f"delta-{phase}",
        "baseBytes": os.path.getsize(spec["base"]),
        "ftBytes": os.path.getsize(spec["ft"]),
        "seconds": seconds,
        "stats": stats,
        "baselineRssMib": baseline_rss,
        "peakRssMib": common.PeakRSS.mib(),
    }
    if phase == "compress":
        result["deltaBytes"] = os.path.getsize(spec["out"])
        result["ratio"] = result["deltaBytes"] / max(1, result["ftBytes"])
        sidecar = f"{spec['out']}.neo-delta.json"
        result["sidecarExists"] = os.path.exists(sidecar)
        if result["sidecarExists"]:
            with open(sidecar, encoding="utf-8") as f:
                result["sidecarKeys"] = sorted(json.load(f))
    else:
        result["restoredBytes"] = os.path.getsize(spec["out"])
        if "ftSha256" in spec:
            result["restoredByteExact"] = _sha256_file(spec["out"]) == spec["ftSha256"]
    return result


def _child_segfault_demo(spec: dict) -> dict:
    """delta_compress_files on a pair with padded total % 262144 == 1."""
    common.install_comfyui_stubs()
    common.import_extension()
    from py import compress

    compress.ensure_zipnn()
    noop = lambda *_a: None  # noqa: E731
    compress.delta_compress_files(spec["base"], spec["ft"], spec["out"], noop)
    return {"kind": "delta-segfault-demo", "survived": True}


_CHILDREN = {"delta": _child_delta, "delta-segfault-demo": _child_segfault_demo}


def _handbuilt_pair(dirpath: str, remainder: int) -> tuple[str, str]:
    """base/ft safetensors pair whose padded total length % 262144 == remainder.

    Raw construction (8-byte length prefix + arbitrary header JSON + data):
    the same layout the safetensors serializer writes, but without its header
    alignment — the ft header carries a filler metadata key sized analytically
    (`"x" * e` grows the JSON blob by exactly `e` bytes) so the ft total lands
    on `remainder` and, being the longer file, becomes the padded delta length.
    """
    os.makedirs(dirpath, exist_ok=True)
    data_len = 512 * 1024
    base_data = bytes(range(256)) * (data_len // 256)
    ft_data = bytearray(base_data)
    for i in range(0, data_len, 4096):  # ~6 % of the bytes differ
        ft_data[i] ^= 0xFF
    ft_data = bytes(ft_data)

    def build(path: str, data: bytes, target_remainder: int | None) -> None:
        meta: dict[str, object] = {"format": "pt"}

        def blob() -> bytes:
            header = {
                "__metadata__": meta,
                "blob": {"dtype": "F32", "shape": [len(data) // 4], "data_offsets": [0, len(data)]},
            }
            return json.dumps(header, separators=(",", ":"), sort_keys=True).encode()

        if target_remainder is not None:
            meta["filler"] = ""
            extra = (target_remainder - (8 + len(blob()) + len(data))) % 262144
            meta["filler"] = "x" * extra
        payload = blob()
        if target_remainder is not None:
            total = 8 + len(payload) + len(data)
            if total % 262144 != target_remainder:
                raise RuntimeError(f"construction missed: total={total}")
        with open(path, "wb") as f:
            f.write(struct.pack("<Q", len(payload)))
            f.write(payload)
            f.write(data)

    base_path = os.path.join(dirpath, "segdemo-base.safetensors")
    ft_path = os.path.join(dirpath, "segdemo-ft.safetensors")
    build(base_path, base_data, None)
    build(ft_path, ft_data, remainder)
    # Sanity: the ft is the longer side, so the padded delta length is its own.
    if os.path.getsize(ft_path) <= os.path.getsize(base_path):
        raise RuntimeError("ft must be the longer file of the pair")
    return base_path, ft_path


def _run_child_here(spec: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--child", json.dumps(spec)],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    out = {**spec}
    if proc.returncode == 0:
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        out.update({"error": "child produced no result", "stderr": proc.stderr[-2000:]})
        return out
    out.update(
        {
            "childReturncode": proc.returncode,
            "signalDeath": -proc.returncode if proc.returncode < 0 else None,
            "stderr": proc.stderr[-2000:],
        }
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child", help=argparse.SUPPRESS)
    ap.add_argument("--fixtures", default="/tmp/mm-bench")
    ap.add_argument("--pair-mb", type=int, default=32)
    ap.add_argument("--skip-segfault-demo", action="store_true")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    if args.child:
        spec = json.loads(args.child)
        print(json.dumps(_CHILDREN[spec["kind"]](spec)))
        return

    results: dict = {"env": common_env(), "measurements": []}

    # --- K4: delta round-trip on a realistic pair --------------------------
    base = os.path.join(args.fixtures, f"pair-base-{args.pair_mb}mb.safetensors")
    ft = os.path.join(args.fixtures, f"pair-ft-{args.pair_mb}mb.safetensors")
    if not (os.path.exists(base) and os.path.exists(ft)):
        import gen_synthetic

        gen_synthetic.gen_pair(base, ft, args.pair_mb, 4242)
    ft_sha = _sha256_file(ft)
    delta = os.path.join(args.fixtures, "pair-delta.znn")
    restored = os.path.join(args.fixtures, "pair-restored.safetensors")

    r = _run_child_here({"kind": "delta", "phase": "compress", "base": base, "ft": ft, "out": delta})
    results["measurements"].append(r)
    print(f"[delta-compress   {args.pair_mb} MB pair] " + _summary(r))
    if os.path.exists(delta):
        d = _run_child_here(
            {
                "kind": "delta",
                "phase": "decompress",
                "base": base,
                "delta": delta,
                "out": restored,
                "ft": ft,
                "ftSha256": ft_sha,
            }
        )
        results["measurements"].append(d)
        print(f"[delta-decompress {args.pair_mb} MB pair] " + _summary(d))
        for p in (delta, f"{delta}.neo-delta.json", restored):
            if os.path.exists(p):
                os.unlink(p)

    # --- K5 reachability: production delta path must SEGFAULT --------------
    if not args.skip_segfault_demo:
        demo_dir = os.path.join(args.fixtures, "segdemo")
        b, f = _handbuilt_pair(demo_dir, remainder=1)
        out = os.path.join(demo_dir, "should-never-exist.znn")
        r = _run_child_here({"kind": "delta-segfault-demo", "base": b, "ft": f, "out": out})
        results["measurements"].append(r)
        print("[delta-segfault-demo total%256KiB==1] " + _summary(r))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fp:
            json.dump(results, fp, indent=2)
        print(f"results -> {args.json_out}")


if __name__ == "__main__":
    main()
