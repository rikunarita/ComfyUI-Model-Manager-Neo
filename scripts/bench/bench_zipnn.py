"""Baseline: the current (vendored C-core) ZipNN stack — Plan §2.2 K1/K2/K3,
K5 reproduction and K13.

Every heavy measurement runs in a forked subprocess that reports its own
`VmHWM` peak RSS, so:
  * peaks are per measurement (no cross-contamination),
  * an OOM kill takes the child down, not the run,
  * the K5 SEGFAULT reproduction (Plan Appendix C) cannot kill the benchmark.

Layers
------
A. core-direct   `zipnn_core.zipnn_core()` / `combine_dtype()` on raw
                 Gaussian tensor bytes (bf16/f32/f16/fp8) — the C core's own
                 throughput (K2/K3) and RAM multiple (K1: input + planes ≈ 2x).
B. neo-e2e       `py/compress.py compress_safetensors()` /
                 `decompress_safetensors()` on real .safetensors files (the
                 path the UI actually triggers: torch tensors, per-tensor
                 clone, RAM dict, save_file).
C. segfault      Plan Appendix C.2 reproduction verbatim: `total % 256 KiB in
                 {1,2,3}` must kill the process with SIGSEGV (that death IS
                 the K5 baseline datum for the current stack).
D. startup       K13: `ensure_zipnn()` prebuilt path, first `import zipnn`
                 (pulls torch in), `import zipnn_core`, and — for contrast —
                 `import mm_core` of the Phase 0 Rust scaffold.

Usage
-----
  python3 scripts/bench/bench_zipnn.py --fixtures /tmp/mm-bench \\
      [--sizes-mb 32 96 192] [--model synthetic|PATH ...] [--json-out out.json]

Fixture prerequisites (gen_synthetic.py):
  <fixtures>/raw/gauss-{bf16,f32,f16,fp8e4m3}-<max>mb.bin
  <fixtures>/model-bf16.safetensors etc. via --model synthetic (generated on
  the fly) or an explicit path (e.g. a downloaded real checkpoint).
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
sys.path.insert(0, HERE)

import common

# dtype -> (ZipNNDtypeEnum code, num_buf, bit_reorder, byte_reorder) — values
# read from third_party/zipnn/zipnn.py compress()/util_header.py (no guesses).
_DTYPE_PARAMS = {
    "bf16": (6, 2, 1, 10),
    "f32": (1, 4, 1, 220),
    "f16": (4, 2, 0, 10),
    "fp8e4m3": (29, 1, 0, 10),
}


def _peak_rss_mib() -> float:
    return common.PeakRSS.mib()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# child entry points
# ---------------------------------------------------------------------------


def _child_core_compress(spec: dict) -> dict:
    """One C-core compression. Input is destroyed in place (that is the C
    core's documented behaviour and why Neo clones tensors)."""
    common.vendored_zipnn_on_path()
    import zipnn_core

    dtype = spec["dtype"]
    code, num_buf, bits, bytes_mode = _DTYPE_PARAMS[dtype]
    # Stream the fixture into the (mutable) input buffer while hashing it:
    # peak RAM stays 1x input before the C call, not 3x.
    buf = bytearray(spec["size"])
    sha = hashlib.sha256()
    view = memoryview(buf)
    with open(spec["fixture"], "rb") as f:
        pos = 0
        while pos < len(buf):
            n = f.readinto(view[pos:])
            if not n:
                break
            sha.update(view[pos : pos + n])
            pos += n
    if pos != len(buf):
        raise RuntimeError(f"fixture {spec['fixture']} shorter than {spec['size']} bytes")
    original_sha = sha.hexdigest()

    header = bytearray(32)
    header[0:2] = b"ZN"
    header[2], header[3], header[4] = 0, 5, 4
    header[5], header[6] = bytes_mode, bits
    header[7], header[8], header[9] = 1, 1, 0  # HUFFMAN, BYTE, no delta
    header[13], header[14] = 0, 18  # no streaming, 256 KiB chunks
    header[15] = code
    header[16:24] = len(buf).to_bytes(8, "little")
    chunk = min(128 * 1024, 256 * 1024) if num_buf == 1 else 256 * 1024
    threads = spec.get("threads") or min(os.cpu_count() or 1, 16)

    t0 = time.monotonic()
    comp = zipnn_core.zipnn_core(bytes(header), buf, num_buf, bits, bytes_mode, 0, chunk, 0.95, 10, threads)
    seconds = time.monotonic() - t0

    comp_path = spec["compOut"]
    with open(comp_path, "wb") as f:
        f.write(comp)
    return {
        "kind": "core-compress",
        "dtype": dtype,
        "origBytes": len(buf),
        "compBytes": len(comp),
        "ratio": len(comp) / max(1, len(buf)),
        "compressSec": seconds,
        "compressMBps": len(buf) / seconds / (1024 * 1024),
        "threads": threads,
        "chunk": chunk,
        "originalSha256": original_sha,
        "compFile": comp_path,
        "peakRssMib": _peak_rss_mib(),
    }


def _child_core_decompress(spec: dict) -> dict:
    common.vendored_zipnn_on_path()
    import zipnn_core

    dtype = spec["dtype"]
    code, num_buf, bits, bytes_mode = _DTYPE_PARAMS[dtype]
    del code
    with open(spec["compFile"], "rb") as f:
        comp = f.read()
    orig_len = spec["size"]
    chunk = min(128 * 1024, 256 * 1024) if num_buf == 1 else 256 * 1024
    threads = spec.get("threads") or min(os.cpu_count() or 1, 16)

    t0 = time.monotonic()
    decom = zipnn_core.combine_dtype(memoryview(comp)[32:], num_buf, bits, bytes_mode, chunk, orig_len, threads)
    seconds = time.monotonic() - t0

    match = _sha256(bytes(decom)) == spec["originalSha256"]
    return {
        "kind": "core-decompress",
        "dtype": dtype,
        "origBytes": orig_len,
        "decompressSec": seconds,
        "decompressMBps": orig_len / seconds / (1024 * 1024),
        "threads": threads,
        "roundtripSha256Match": match,
        "peakRssMib": _peak_rss_mib(),
    }


def _child_neo_phase(spec: dict) -> dict:
    """One Neo pipeline phase (compress or decompress) — separate processes
    so each phase gets its own clean VmHWM peak."""
    common.install_comfyui_stubs()
    common.import_extension()
    from py import compress

    # Production flow: the ZipNN routes call ensure_zipnn() on the CPU
    # executor before the worker runs (py/compress.py L1274).
    compress.ensure_zipnn()
    baseline_rss = _peak_rss_mib()  # after imports: torch/zipnn are resident

    phase = spec["phase"]
    src, dst = spec["src"], spec["dst"]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    noop = lambda *_a: None  # noqa: E731

    src_size = os.path.getsize(src)
    t0 = time.monotonic()
    if phase == "compress":
        stats = compress.compress_safetensors(src, dst, noop)
    else:
        stats = compress.decompress_safetensors(src, dst, noop)
    seconds = time.monotonic() - t0

    result = {
        "kind": f"neo-{phase}",
        "model": src,
        "srcBytes": src_size,
        "dstBytes": os.path.getsize(dst),
        "seconds": seconds,
        "MBps": src_size / seconds / (1024 * 1024),
        "stats": stats,
        "baselineRssMib": baseline_rss,
        "peakRssMib": _peak_rss_mib(),
    }
    if phase == "decompress" and "originalSha256" in spec:
        sha = hashlib.sha256()
        with open(dst, "rb") as f:
            for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
                sha.update(chunk)
        result["restoredByteExact"] = sha.hexdigest() == spec["originalSha256"]
    return result


def _child_segfault(spec: dict) -> dict:
    """Plan Appendix C.2 — verbatim. Reaching the return means NO crash
    (which would falsify the plan's finding on this platform)."""
    common.vendored_zipnn_on_path()
    import zipnn_core

    length = spec["length"]
    h = b"ZN" + bytes(30)
    data = bytearray(os.urandom(length))
    zipnn_core.zipnn_core(h, data, 4, 1, 220, 0, 262144, 0.95, 10, 1)
    return {"kind": "segfault", "length": length, "survived": True}


def _child_startup(spec: dict) -> dict:
    """K13 components, one per child (fresh interpreter each):

    * ``ensure-full``  — the whole first-run `ensure_zipnn()` (prebuilt path;
                         includes whatever it drags in: zipnn_available()
                         really IMPORTs zipnn → torch).
    * ``core-only``    — sys.path setup + `import zipnn_core` alone (no torch).
    * ``zipnn-pkg``    — `import zipnn` after the core (pulls torch in).
    * ``mm-core``      — py/native.py load() of the Phase 0 Rust core.
    """
    what = spec["what"]
    if what == "ensure-full":
        common.install_comfyui_stubs()
        common.import_extension()
        from py import compress

        t0 = time.monotonic()
        compress.ensure_zipnn()
        seconds = time.monotonic() - t0
    elif what == "core-only":
        t0 = time.monotonic()
        common.vendored_zipnn_on_path()
        import zipnn_core

        seconds = time.monotonic() - t0
    elif what == "zipnn-pkg":
        common.vendored_zipnn_on_path()
        import zipnn_core  # noqa: F401

        t0 = time.monotonic()
        import zipnn  # noqa: F401

        seconds = time.monotonic() - t0
    elif what == "mm-core":
        common.install_comfyui_stubs()
        common.import_extension()
        from py import config, native

        config.extension_uri = common.REPO_ROOT
        t0 = time.monotonic()
        ok = native.load()
        seconds = (time.monotonic() - t0) if ok else None
    else:
        raise ValueError(f"unknown startup measurement {what!r}")
    return {"kind": "startup", "what": what, "seconds": seconds, "peakRssMib": _peak_rss_mib()}


_CHILDREN = {
    "core-compress": _child_core_compress,
    "core-decompress": _child_core_decompress,
    "neo-compress": _child_neo_phase,
    "neo-decompress": _child_neo_phase,
    "segfault": _child_segfault,
    "startup": _child_startup,
}


def _run_child(spec: dict) -> dict:
    """Fork one measurement; survive signal death (K5) and OOM alike."""
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
            # 139/-11 = SIGSEGV, 137/-9 = SIGKILL (the OOM killer)
            "signalDeath": -proc.returncode if proc.returncode < 0 else None,
            "stderr": proc.stderr[-2000:],
        }
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child", help=argparse.SUPPRESS)
    ap.add_argument("--fixtures", default="/tmp/mm-bench")
    ap.add_argument("--sizes-mb", type=int, nargs="*", default=[32, 96, 192])
    ap.add_argument(
        "--model",
        action="append",
        default=None,
        metavar="PATH",
        help="real .safetensors model(s) for the Neo e2e layer (repeatable)",
    )
    ap.add_argument("--neo-synthetic-mb", type=int, default=64)
    ap.add_argument("--skip-segfault", action="store_true")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    if args.child:
        spec = json.loads(args.child)
        result = _CHILDREN[spec["kind"]](spec)
        print(json.dumps(result))
        return

    env = common_env()
    results: dict = {"env": env, "measurements": []}
    max_mb = max(args.sizes_mb)

    # --- A. C core direct --------------------------------------------------
    for dtype in ("bf16", "f32", "f16", "fp8e4m3"):
        fixture = os.path.join(args.fixtures, "raw", f"gauss-{dtype}-{max_mb}mb.bin")
        if not os.path.exists(fixture):
            print(
                f"!! fixture missing ({fixture}) — run gen_synthetic.py --raw-dtype ... --raw-size-mb {max_mb}",
                file=sys.stderr,
            )
            continue
        for size_mb in args.sizes_mb:
            size = size_mb * 1024 * 1024
            comp_out = os.path.join(args.fixtures, f"core-{dtype}-{size_mb}mb.znn")
            spec = {"kind": "core-compress", "dtype": dtype, "fixture": fixture, "size": size, "compOut": comp_out}
            r = _run_child(spec)
            results["measurements"].append(r)
            print(f"[core-compress  {dtype:8s} {size_mb:5d} MB] " + _summary(r))
            if "compFile" in r:
                d = _run_child(
                    {
                        "kind": "core-decompress",
                        "dtype": dtype,
                        "compFile": r["compFile"],
                        "size": size,
                        "originalSha256": r["originalSha256"],
                    }
                )
                results["measurements"].append(d)
                print(f"[core-decompress {dtype:8s} {size_mb:5d} MB] " + _summary(d))
                os.unlink(r["compFile"])

    # --- B. Neo end-to-end -------------------------------------------------
    models = list(args.model or [])
    synth = os.path.join(args.fixtures, f"model-bf16-{args.neo_synthetic_mb}mb.safetensors")
    if not os.path.exists(synth):
        import gen_synthetic

        gen_synthetic.gen_model(synth, "bf16", args.neo_synthetic_mb, 777)
    models.insert(0, synth)
    out_dir = os.path.join(args.fixtures, "e2e-out")
    for model in models:
        if not os.path.exists(model):
            print(f"!! model missing: {model}", file=sys.stderr)
            continue
        base = os.path.splitext(os.path.basename(model))[0]
        znn = os.path.join(out_dir, f"{base}.znn.safetensors")
        restored = os.path.join(out_dir, f"{base}.restored.safetensors")
        original_sha = None
        if os.path.getsize(model) <= 512 * 1024 * 1024:
            sha = hashlib.sha256()
            with open(model, "rb") as f:
                for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
                    sha.update(chunk)
            original_sha = sha.hexdigest()
        r = _run_child({"kind": "neo-compress", "phase": "compress", "src": model, "dst": znn})
        results["measurements"].append(r)
        print(f"[neo-compress   {os.path.basename(model)}] " + _summary(r))
        if "dstBytes" in r:
            d = _run_child(
                {
                    "kind": "neo-decompress",
                    "phase": "decompress",
                    "src": znn,
                    "dst": restored,
                    "originalSha256": original_sha,
                }
            )
            results["measurements"].append(d)
            print(f"[neo-decompress {os.path.basename(model)}] " + _summary(d))
            ratio = r["dstBytes"] / max(1, r["srcBytes"])
            print(f"                ratio={ratio:.4f} (znn {r['dstBytes']} / src {r['srcBytes']})")
            results["measurements"][-1]["ratio"] = ratio
            os.unlink(znn)
            os.unlink(restored)

    # --- C. K5 SEGFAULT reproduction (Plan Appendix C.2) --------------------
    if not args.skip_segfault:
        for length in (262144 + 1, 262144 + 2, 262144 + 3):
            r = _run_child({"kind": "segfault", "length": length})
            results["measurements"].append(r)
            print(f"[segfault len={length}] " + _summary(r))

    # --- D. K13 startup ----------------------------------------------------
    for what in ("ensure-full", "core-only", "zipnn-pkg", "mm-core"):
        r = _run_child({"kind": "startup", "what": what})
        results["measurements"].append(r)
        print(f"[startup {what}] " + _summary(r))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"results -> {args.json_out}")


def _summary(r: dict) -> str:
    kind = r.get("kind", "?")
    if "error" in r or "childReturncode" in r:
        sig = r.get("signalDeath")
        if sig == 11:
            return "SEGFAULT (signal 11) — reproduces Plan Appendix C"
        if sig == 9:
            return "OOM-killed (signal 9)"
        return f"child died rc={r.get('childReturncode')} {r.get('error', '')}".strip()
    if kind == "segfault":
        return "SURVIVED (plan finding NOT reproduced on this platform!)"
    parts = []
    for key, fmt in (
        ("ratio", "ratio {:.4f}"),
        ("compressMBps", "{:.1f} MB/s comp"),
        ("decompressMBps", "{:.1f} MB/s decom"),
        ("compressSec", "{:.2f}s comp"),
        ("decompressSec", "{:.2f}s decom"),
        ("MBps", "{:.1f} MB/s"),
        ("seconds", "{:.3f}s"),
        ("baselineRssMib", "base {:.0f} MiB"),
        ("peakRssMib", "peak {:.0f} MiB"),
        ("roundtripSha256Match", "roundtrip={}"),
        ("restoredByteExact", "byteExact={}"),
    ):
        if key in r and r[key] is not None:
            parts.append(fmt.format(r[key]))
    return " | ".join(parts)


def common_env() -> dict:
    import platform

    meminfo = {}
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                key, _, rest = line.partition(":")
                meminfo[key.strip()] = rest.strip()
    except OSError:
        pass
    return {
        "date": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": platform.platform(),
        "python": sys.version.split()[0],
        "cpus": os.cpu_count(),
        "memTotal": meminfo.get("MemTotal"),
        "machine": platform.machine(),
    }


if __name__ == "__main__":
    main()
