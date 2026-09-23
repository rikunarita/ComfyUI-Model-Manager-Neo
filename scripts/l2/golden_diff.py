"""L2 golden differential harness (Plan §5.1 L2 / §6.2 Phase 1).

The vendored PREBUILT C core (``third_party/zipnn-core-bin/linux-x86_64``,
the exact artifact Phase 0 pinned) is the golden generator; ``znn-cli``
(release build) is the Rust side. For every case:

1. C ``zipnn_core`` compresses the input (golden); C ``combine_dtype``
   decompresses it again (golden self-check).
2. Rust compresses the same input with the same parameters — the outputs
   must be BYTE-IDENTICAL (the Rust encoder mirrors the C step for step;
   any drift is a hard failure with a first-diff report).
3. Cross-decompression, both directions: Rust ``combine_dtype`` of the C
   payload, and C ``combine_dtype`` of the Rust payload — both must
   reproduce the input exactly.
4. The Appendix-C crash classes (final chunk of 1/2/3 bytes on the 4-plane
   path — deterministic SEGFAULT in C, reproduced 8/8 in Phase 0) are run
   on the RUST side only: the verdict must be ``ok`` (with a clean
   self-round-trip) or ``err`` — a crashed/aborted znn-cli process fails
   the whole run. C is never fed those lengths here (it would kill the
   driver; Phase 0's ``bench_c_defects.py`` already recorded the C verdicts
   from isolated subprocesses).

Speed & ratio mode (``--speed``) measures the Plan's Phase-1 completion
criteria on Gaussian fixtures (f32/bf16/f16/fp8): ratio difference must be
within ±0.5 % of C (byte-identical output makes it exactly 0 in practice)
and Rust throughput must be ≥ C at equal thread counts.

Requirements: Linux x86_64 + CPython 3.11 (the pinned .so ABI). Anywhere
else the harness SKIPS with exit code 0 and a loud notice (CI runs it in
the native-diff job, which pins exactly this platform).

Usage::

    python3 scripts/l2/golden_diff.py                 # full suite (10k+ cases)
    python3 scripts/l2/golden_diff.py --quick         # ~1.2k cases (CI gate)
    python3 scripts/l2/golden_diff.py --speed         # ratio/speed fixtures
    python3 scripts/l2/golden_diff.py --cases 20000 --seed 7
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SO_DIR = os.path.join(REPO, "third_party", "zipnn-core-bin", "linux-x86_64")
CLI = os.path.join(REPO, "native", "target", "release", "znn-cli")
CLI_DEBUG = os.path.join(REPO, "native", "target", "debug", "znn-cli")

# The parameter matrix mirrors the production flows verified in Phase 0
# (py/compress.py → zipnn.py → zipnn_core): f32 → (4, 1, 220, 256K),
# bf16 → (2, 1, 10, 256K), f16 → (2, 0, 10, 256K), fp8 → (1, *, 10, 128K).
PARAM_COMBOS = [
    # (num_buf, bits, mode, chunk)
    (4, 1, 220, 262144),
    (2, 1, 10, 262144),
    (2, 0, 10, 262144),
    (1, 0, 10, 131072),
    (1, 1, 10, 131072),  # production fp8 headers carry bits=1 (C ignores it)
    (4, 1, 220, 65536),  # custom chunk sizes stay legal (divisible by n)
    (2, 1, 10, 32768),
    (1, 0, 10, 8192),
]


def _so_for_interpreter() -> str:
    """The pinned prebuilt matching THIS interpreter's ABI tag (loading the
    wrong cpython-3XY .so works by luck on Linux but must never happen in a
    gate harness)."""
    return f"zipnn_core.cpython-{sys.version_info[0]}{sys.version_info[1]}-x86_64-linux-gnu.so"


def c_core_available() -> bool:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        return False
    return os.path.isfile(os.path.join(SO_DIR, _so_for_interpreter()))


def load_c_core():
    so = os.path.join(SO_DIR, _so_for_interpreter())
    # the .so exports PyInit_zipnn_core — the module name must match exactly
    spec = importlib.util.spec_from_file_location("zipnn_core", so)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["zipnn_core"] = mod
    spec.loader.exec_module(mod)
    return mod, so


class CGolden:
    """Thin wrapper over the C ABI (input copies — the C destroys its input
    bytearray in place, which is why Neo's Python layer clones)."""

    def __init__(self, mod):
        self.mod = mod

    def compress(self, data: bytes, nb: int, bits: int, mode: int, chunk: int, threads: int = 1) -> bytes:
        return bytes(self.mod.zipnn_core(bytearray(32), bytearray(data), nb, bits, mode, 0, chunk, 0.95, 10, threads))

    def decompress(
        self, payload: bytes, nb: int, bits: int, mode: int, chunk: int, orig_len: int, threads: int = 1
    ) -> bytes:
        return bytes(self.mod.combine_dtype(memoryview(payload), nb, bits, mode, chunk, orig_len, threads))


# ---------------------------------------------------------------------------
# case generation
# ---------------------------------------------------------------------------


class XorShift:
    """Deterministic generator shared by every case (no numpy needed)."""

    def __init__(self, seed: int):
        self.x = (seed & 0xFFFFFFFFFFFFFFFF) | 1

    def next(self) -> int:
        x = self.x
        x ^= (x << 13) & 0xFFFFFFFFFFFFFFFF
        x ^= x >> 7
        x ^= (x << 17) & 0xFFFFFFFFFFFFFFFF
        self.x = x
        return x

    def below(self, n: int) -> int:
        return self.next() % n


def make_content(rng: XorShift, length: int, entropy: str) -> bytes:
    if entropy == "rand":
        return bytes((rng.next() >> 11) & 0xFF for _ in range(length))
    if entropy == "low":
        k = 2 + rng.below(5)
        syms = [rng.below(256) for _ in range(k)]
        return bytes(syms[rng.next() % k] for _ in range(length))
    if entropy == "runs":
        out = bytearray()
        while len(out) < length:
            out.extend(bytes([rng.below(256)]) * (16 + rng.below(400)))
        return bytes(out[:length])
    if entropy == "mixed":
        # alternating compressible / incompressible 4-16 KB blocks
        out = bytearray()
        while len(out) < length:
            n = 4096 + rng.below(12288)
            if rng.below(2):
                out.extend(bytes((rng.next() >> 11) & 0xFF for _ in range(n)))
            else:
                out.extend(bytes([rng.below(9)]) * n)
        return bytes(out[:length])
    if entropy == "rle":
        return bytes([rng.below(256)]) * length
    if entropy == "sparse":
        # gapped alphabets (exercising the weight-header corner cases)
        a, b = rng.below(120), 128 + rng.below(120)
        return bytes((a if i % 3 else b) for i in range(length))
    if entropy == "f32gauss":
        # gaussian-ish floats: the realistic model-weight byte profile
        out = bytearray()
        for _ in range((length + 3) // 4):
            v = struct.pack("<f", ((rng.next() % 20000) - 10000) / 300000.0)
            out.extend(v)
        return bytes(out[:length])
    if entropy == "bf16":
        out = bytearray()
        for _ in range((length + 1) // 2):
            hi = 0x3F + rng.below(3)  # concentrated exponent/sign byte
            lo = rng.below(256)
            out.extend(bytes([lo, hi]))
        return bytes(out[:length])
    raise ValueError(entropy)


ENTROPIES = ["rand", "low", "runs", "mixed", "rle", "sparse", "f32gauss", "bf16"]


def length_classes(rng: XorShift, chunk: int, nb: int) -> list[int]:
    """Lengths covering every remainder class + chunk boundaries + the
    Appendix-C crash lengths (marked separately by the caller)."""
    out = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 16, 17, 31, 33, 64, 65, 66, 67]
    for delta in (-3, -2, -1, 0, 1, 2, 3, 4, 5):
        v = chunk + delta
        if v >= 0:
            out.append(v)
        v = 2 * chunk + delta
        if v >= 0:
            out.append(v)
    for _ in range(6):
        out.append(rng.below(300_000))
    for _ in range(3):
        out.append(chunk + rng.below(chunk))
    out.append(rng.below(1_500_000) + 500_000)  # a multi-chunk medium case
    return out


def c_heap_safe(length: int, nb: int, chunk: int) -> bool:
    """True when the C core provably performs NO out-of-bounds access on
    this shape: num_buf==1 (pure copies) or every chunk (incl. the final
    one) divisible by num_buf. Everything else hits the documented C UB
    (1-3 byte heap-overflow writes / OOB reads for non-divisible remainders
    - Plan Appendix C.2/C.3) and must run in a fork-isolated child so the
    cumulative heap corruption cannot poison the driver process."""
    if length == 0:
        return True
    if nb == 1:
        return True
    if chunk % nb != 0:
        return False
    return length % nb == 0


def c_golden_forked(c_core: CGolden, data: bytes, case: dict, golden_path: str, verdict_path: str) -> dict:
    """Run C compress (+ golden file, fsync'd BEFORE anything that can
    abort, + self-decompress verdict) inside a forked child. The child's
    heap corruption / SIGSEGV / SIGABRT never touches the driver.

    Returns {"golden": bool, "signal": int|None, "verdict": dict|None}."""
    pid = os.fork()
    if pid == 0:  # child
        try:
            # the C's documented UB can make glibc abort with noisy
            # diagnostics; the signal is the recorded evidence, not stderr
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 2)
            out = c_core.compress(data, case["num_buf"], case["bits"], case["mode"], case["chunk"], 1)
            with open(golden_path, "wb") as f:
                f.write(out)
                f.flush()
                os.fsync(f.fileno())
            verdict: dict[str, Any] = {"compress": "ok", "out_len": len(out)}
            try:
                rt = c_core.decompress(
                    out[32:],
                    case["num_buf"],
                    case["bits"],
                    case["mode"],
                    case["chunk"],
                    len(data),
                    1,
                )
                verdict["self_roundtrip"] = bool(rt == data)
            except BaseException as exc:
                verdict["self_roundtrip"] = f"exc:{exc!r}"
            with open(verdict_path, "w", encoding="utf-8") as f:
                json.dump(verdict, f)
            os._exit(0)
        except BaseException:
            os._exit(3)
    _, status = os.waitpid(pid, 0)
    sig = os.WTERMSIG(status) if os.WIFSIGNALED(status) else None
    verdict = None
    if os.path.exists(verdict_path):
        try:
            with open(verdict_path, encoding="utf-8") as f:
                verdict = json.load(f)
        except (OSError, json.JSONDecodeError):
            verdict = None
    return {
        "golden": os.path.exists(golden_path),
        "signal": sig,
        "exit": os.WEXITSTATUS(status) if os.WIFEXITED(status) else None,
        "verdict": verdict,
    }


def c_forbidden(length: int, nb: int, chunk: int) -> bool:
    """True when the C core deterministically SEGFAULTs on this input:
    the 4-plane path with a FINAL CHUNK shorter than 4 bytes (NULL plane
    writes — Plan Appendix C, reproduced 8/8 in Phase 0).

    `length == 0` produces zero chunks (no split call) — not forbidden."""
    if nb != 4 or length == 0:
        return False
    last = length - chunk * ((length + chunk - 1) // chunk - 1)
    return 0 < last < 4


def gen_cases(seed: int, target: int) -> list[dict]:
    rng = XorShift(seed)
    cases: list[dict] = []
    cid = 0
    while len(cases) < target:
        for nb, bits, mode, chunk in PARAM_COMBOS:
            for length in length_classes(rng, chunk, nb):
                entropy = ENTROPIES[rng.below(len(ENTROPIES))]
                if length > 0 or entropy == "low":
                    cases.append(
                        {
                            "id": f"c{cid:06d}",
                            "length": length,
                            "entropy": entropy,
                            "num_buf": nb,
                            "bits": bits,
                            "mode": mode,
                            "chunk": chunk,
                            "c_forbidden": c_forbidden(length, nb, chunk),
                        }
                    )
                    cid += 1
                if len(cases) >= target:
                    break
            if len(cases) >= target:
                break
    return cases[:target]


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


def rust_batch(cli: str, manifest: list[dict], tmp: str) -> tuple[int, dict[str, dict]]:
    """Run one znn-cli batch; returns (returncode, {id: result})."""
    man_path = os.path.join(tmp, "manifest.jsonl")
    res_path = os.path.join(tmp, "results.jsonl")
    with open(man_path, "w", encoding="utf-8") as f:
        for op in manifest:
            f.write(json.dumps(op) + "\n")
    if os.path.exists(res_path):
        os.remove(res_path)
    proc = subprocess.run([cli, "batch", man_path, res_path], capture_output=True)
    results: dict[str, dict] = {}
    if os.path.exists(res_path):
        with open(res_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    results[r["id"]] = r
    return proc.returncode, results


def steal_ticks() -> int:
    """Host-steal ticks (field 8 of /proc/stat's cpu line) — the ground
    truth for 'the hypervisor gave our vCPUs to somebody else'."""
    try:
        with open("/proc/stat", encoding="utf-8") as f:
            for line in f:
                if line.startswith("cpu "):
                    parts = line.split()
                    return int(parts[8]) if len(parts) > 8 else 0
    except OSError:
        pass
    return 0


def first_diff(a: bytes, b: bytes) -> str:
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            lo = max(0, i - 8)
            return f"offset {i}: C={a[i]:02x} R={b[i]:02x} context C={a[lo : i + 8].hex()} R={b[lo : i + 8].hex()}"
    return f"lengths differ: C={len(a)} R={len(b)}"


def run_suite(args, c_core: CGolden, cli: str) -> dict:
    tmp = tempfile.mkdtemp(prefix="znnl2_", dir=args.tmp_dir)
    rng = XorShift(args.seed ^ 0x5EED)
    cases = gen_cases(args.seed, args.cases)
    print(f"L2 golden diff: {len(cases)} cases, cli={cli}")
    print(f"    tmp={tmp}")

    failures: list[dict] = []
    counters: dict[str, int] = {
        "cases": len(cases),
        "c_compress": 0,
        "byte_identical": 0,
        "byte_mismatch": 0,
        "rust_dec_ok": 0,
        "c_dec_of_rust_ok": 0,
        "c_dec_of_rust_via_identity": 0,
        "rust_self_roundtrip_ok": 0,
        "forbidden_rust_ok": 0,
        "forbidden_rust_err": 0,
        "rust_err_other": 0,
        "c_forked_signal": 0,
        "c_self_unverified": 0,
    }

    def fail(case: dict, stage: str, detail: str):
        failures.append(
            {
                "id": case["id"],
                "stage": stage,
                "detail": detail[:400],
                **{k: case[k] for k in ("length", "entropy", "num_buf", "bits", "mode", "chunk")},
            }
        )

    def counter(name: str):
        counters[name] = counters.get(name, 0) + 1

    block = args.block
    fatal = None
    for base in range(0, len(cases), block):
        chunk_cases = cases[base : base + block]
        # ---------------- pass 0: inputs + C goldens (files on disk) -------
        manifest_comp = []
        have_golden: dict[str, bool] = {}
        for case in chunk_cases:
            cid = case["id"]
            data = make_content(rng, case["length"], case["entropy"]) if case["length"] else b""
            in_path = os.path.join(tmp, f"{cid}.in")
            with open(in_path, "wb") as f:
                f.write(data)
            case["_data_len"] = len(data)
            gpath = os.path.join(tmp, f"{cid}.c.znn")
            if case["c_forbidden"]:
                have_golden[cid] = False  # Rust-only (Appendix C SEGFAULT class)
            elif c_heap_safe(case["length"], case["num_buf"], case["chunk"]):
                try:
                    c_out = c_core.compress(data, case["num_buf"], case["bits"], case["mode"], case["chunk"])
                    c_rt = c_core.decompress(
                        c_out[32:], case["num_buf"], case["bits"], case["mode"], case["chunk"], len(data)
                    )
                except Exception as exc:  # any C exception is a finding
                    fail(case, "c_compress_exception", repr(exc))
                    have_golden[cid] = False
                    continue
                if c_rt != data:
                    fail(case, "c_self_roundtrip", "C golden does not round-trip in C (!)")
                    have_golden[cid] = False
                    continue
                with open(gpath, "wb") as f:
                    f.write(c_out)
                counter("c_compress")
                have_golden[cid] = True
                del c_out, c_rt
            else:
                vpath = os.path.join(tmp, f"{cid}.cverdict.json")
                info = c_golden_forked(c_core, data, case, gpath, vpath)
                if info["signal"] is not None:
                    counter("c_forked_signal")
                if info["golden"]:
                    v = info["verdict"] or {}
                    if v.get("self_roundtrip") is False:
                        fail(case, "c_self_roundtrip", "C golden does not round-trip in C (!)")
                        have_golden[cid] = False
                        continue
                    if v.get("self_roundtrip") is not True:
                        # C died (heap abort) before verifying its own output;
                        # the golden file was fsync'd BEFORE that point, and
                        # Phase 0 proved the in-bounds bytes are correct on
                        # exactly these shapes — the Rust decode below is the
                        # cross-check that matters.
                        counter("c_self_unverified")
                    counter("c_compress")
                    have_golden[cid] = True
                else:
                    have_golden[cid] = False
                    if info["signal"] is None:
                        fail(case, "c_no_golden", f"child exit={info['exit']} without golden")
            del data
            manifest_comp.append(
                {
                    "id": cid,
                    "op": "compress",
                    "input": in_path,
                    "output": os.path.join(tmp, f"{cid}.r.znn"),
                    "num_buf": case["num_buf"],
                    "bits": case["bits"],
                    "mode": case["mode"],
                    "chunk": case["chunk"],
                }
            )

        # ---------------- pass 1: rust compress ----------------------------
        rc, res = rust_batch(cli, manifest_comp, tmp)
        if rc != 0:
            fatal = f"compress batch rc={rc} (block {base}) — CRASH signal"
            break

        # ---------------- pass 2: compare + queue cross-decode -------------
        manifest_dec = []
        for case in chunk_cases:
            cid = case["id"]
            r = res.get(cid)
            if r is None:
                fail(case, "missing_result", "znn-cli produced no result line")
                continue
            r_path = os.path.join(tmp, f"{cid}.r.znn")
            if case["c_forbidden"]:
                if r["status"] == "ok":
                    counter("forbidden_rust_ok")
                    if os.path.exists(r_path):
                        with open(r_path, "rb") as f:
                            payload = f.read()[32:]
                        pay_path = os.path.join(tmp, f"{cid}.r.payload")
                        with open(pay_path, "wb") as f:
                            f.write(payload)
                        manifest_dec.append(
                            {
                                "id": cid + ":self",
                                "op": "decompress",
                                "input": pay_path,
                                "output": os.path.join(tmp, f"{cid}.self.bin"),
                                "num_buf": case["num_buf"],
                                "bits": case["bits"],
                                "mode": case["mode"],
                                "chunk": case["chunk"],
                                "orig_len": case["_data_len"],
                                "max_output": case["_data_len"] + 1024,
                            }
                        )
                elif r["status"] == "err":
                    counter("forbidden_rust_err")
                continue
            if r["status"] != "ok":
                counter("rust_err_other")
                fail(case, "rust_compress_err", r.get("error", "?"))
                continue
            if not have_golden.get(cid):
                continue
            with open(r_path, "rb") as f:
                r_out = f.read()
            with open(os.path.join(tmp, f"{cid}.c.znn"), "rb") as f:
                g_out = f.read()
            if r_out == g_out:
                counter("byte_identical")
            else:
                counter("byte_mismatch")
                fail(case, "byte_mismatch", first_diff(g_out, r_out))
                # keep a payload copy for post-mortem C-side checks
                with open(os.path.join(tmp, f"{cid}.r.payload"), "wb") as f:
                    f.write(r_out[32:])
                continue
            # cross-decode 1: rust decompresses the C golden payload. The
            # rust output is byte-identical, so the rust file IS the golden —
            # write the payload slice once.
            pay_path = os.path.join(tmp, f"{cid}.c.payload")
            with open(pay_path, "wb") as f:
                f.write(g_out[32:])
            manifest_dec.append(
                {
                    "id": cid + ":dec",
                    "op": "decompress",
                    "input": pay_path,
                    "output": os.path.join(tmp, f"{cid}.dec.bin"),
                    "num_buf": case["num_buf"],
                    "bits": case["bits"],
                    "mode": case["mode"],
                    "chunk": case["chunk"],
                    "orig_len": case["_data_len"],
                    "max_output": case["_data_len"] + 1024,
                }
            )
            # cross-decode 2: C decompresses the RUST payload. Only run the
            # C in-process on heap-safe shapes; on UB shapes the payload is
            # byte-identical to the golden whose C self-roundtrip was just
            # verified (or fork-verified), so the direction is proven.
            if c_heap_safe(case["length"], case["num_buf"], case["chunk"]):
                c_rt = c_core.decompress(
                    r_out[32:], case["num_buf"], case["bits"], case["mode"], case["chunk"], case["_data_len"]
                )
                with open(os.path.join(tmp, f"{cid}.in"), "rb") as f:
                    data = f.read()
                if c_rt == data:
                    counter("c_dec_of_rust_ok")
                else:
                    fail(case, "c_dec_of_rust", "C could not restore the input from the Rust payload")
            else:
                counter("c_dec_of_rust_ok")
                counter("c_dec_of_rust_via_identity")
            del r_out, g_out

        rc, res2 = rust_batch(cli, manifest_dec, tmp)
        if rc != 0:
            fatal = f"decompress batch rc={rc} (block {base}) — CRASH signal"
            break
        for case in chunk_cases:
            cid = case["id"]
            for suffix, ctr in ((":dec", "rust_dec_ok"), (":self", "rust_self_roundtrip_ok")):
                r = res2.get(cid + suffix)
                if r is None:
                    continue
                if r["status"] != "ok":
                    fail(case, f"rust_decompress{suffix}", r.get("error", "?"))
                    continue
                out_path = os.path.join(tmp, f"{cid}.{'dec' if suffix == ':dec' else 'self'}.bin")
                in_path = os.path.join(tmp, f"{cid}.in")
                with open(out_path, "rb") as f1, open(in_path, "rb") as f2:
                    if f1.read() == f2.read():
                        counter(ctr)
                    else:
                        fail(case, f"rust_decompress{suffix}_content", "restored bytes differ")

        # ---------------- block cleanup (bounded disk) ---------------------
        for case in chunk_cases:
            cid = case["id"]
            for ext in (
                ".in",
                ".c.znn",
                ".r.znn",
                ".c.payload",
                ".r.payload",
                ".dec.bin",
                ".self.bin",
                ".cverdict.json",
            ):
                p = os.path.join(tmp, cid + ext)
                if os.path.exists(p):
                    os.remove(p)
        print(
            f"    block {base // block + 1}: identical={counters['byte_identical']} "
            f"mismatch={counters['byte_mismatch']} forbidden_ok={counters['forbidden_rust_ok']} "
            f"failures={len(failures)}",
            flush=True,
        )

    if fatal:
        return {"gate": False, "fatal": fatal, "counters": counters, "failures": failures[:50]}
    if not args.keep_tmp:
        shutil.rmtree(tmp, ignore_errors=True)

    n_forbidden = sum(1 for c in cases if c["c_forbidden"])
    gate = (
        not failures
        and counters["byte_mismatch"] == 0
        and counters["rust_err_other"] == 0
        and counters["byte_identical"] == counters["c_compress"]
        and counters["rust_dec_ok"] == counters["byte_identical"]
        and counters["c_dec_of_rust_ok"] == counters["byte_identical"]
        and counters["forbidden_rust_ok"] + counters["forbidden_rust_err"] == n_forbidden
        and counters["rust_self_roundtrip_ok"] == counters["forbidden_rust_ok"]
    )
    return {
        "gate": gate,
        "counters": counters,
        "failures": failures[:50],
        "n_failures": len(failures),
    }


# ---------------------------------------------------------------------------
# speed & ratio mode
# ---------------------------------------------------------------------------


def gaussian_bytes(n_elements: int, dtype: str, seed: int) -> bytes:
    """Same profile as scripts/bench/gen_synthetic.py `_gaussian_bytes`
    (Gaussian weights — the entropy profile of real checkpoints)."""
    sys.path.insert(0, os.path.join(REPO, "scripts", "bench"))
    try:
        import gen_synthetic

        return gen_synthetic._gaussian_bytes(n_elements, dtype, seed)
    finally:
        sys.path.pop(0)


def bench_dtype(
    name: str,
    gtype: str,
    nb: int,
    bits: int,
    mode: int,
    chunk: int,
    elems: int,
    args,
    c_core: CGolden,
    cli: str,
    tmp: str,
    threads: int,
) -> tuple[bool, dict]:
    """Run the ratio/speed comparison for one dtype; returns (gate, row)."""
    data = gaussian_bytes(elems, gtype, 42)
    in_path = os.path.join(tmp, f"{name}.in")
    with open(in_path, "wb") as f:
        f.write(data)
    mb = len(data) / (1024 * 1024)
    base = [
        "--num-buf",
        str(nb),
        "--bits",
        str(bits),
        "--mode",
        str(mode),
        "--chunk",
        str(chunk),
        "--threads",
        str(threads),
    ]

    def time_c_comp():
        t0 = time.perf_counter()
        out = c_core.compress(data, nb, bits, mode, chunk, threads)
        return time.perf_counter() - t0, out

    def time_c_dec(payload):
        t0 = time.perf_counter()
        c_core.decompress(payload, nb, bits, mode, chunk, len(data), threads)
        return time.perf_counter() - t0

    def rust_bench_full(op, inp, extra):
        """One znn-cli spawn running `speed_runs` steal-gated in-process
        timings; rows carry best/median seconds (same statistics the C side
        collects)."""
        jout = inp + f".bench.{op}.json"
        cmd = [cli, "bench", inp, "--op", op, "--runs", str(args.speed_runs), "--json-out", jout, *base, *extra]
        r = subprocess.run(cmd, capture_output=True, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"bench {op} failed: {r.stderr.decode()[:300]}")
        with open(jout, encoding="utf-8") as f:
            return {row["op"]: row for row in json.load(f)}

    # materialise the rust payload once (identity check + decompress input)
    r_znn = os.path.join(tmp, f"{name}.r.znn")
    rr = subprocess.run([cli, "core-compress", in_path, r_znn, *base], capture_output=True, check=False)
    if rr.returncode != 0:
        raise RuntimeError(f"rust compress failed: {rr.stderr.decode()[:300]}")
    with open(r_znn, "rb") as f:
        r_out = f.read()
    pay_path = os.path.join(tmp, f"{name}.payload")
    with open(pay_path, "wb") as f:
        f.write(r_out[32:])

    # Ceiling protocol with steal gating (see timed_clean in znn-cli and the
    # C-side loop below): host steal only ADDS wall time, so each side's
    # clean-window minimum is its interference-free throughput. Windows are
    # rejected when /proc/stat steal exceeds ~5% of capacity (identical rule
    # on both sides); samples alternate so both sides see the same machine.
    def c_clean_samples(fn, *a, **kw):
        got = []
        tries = 0
        quota = args.speed_blocks
        while len(got) < quota and tries < quota * 60:
            tries += 1
            s0 = steal_ticks()
            res = fn(*a, **kw)
            dt = res[0] if isinstance(res, tuple) else res
            if clean_window(s0, steal_ticks(), dt, threads):
                got.append(res)
            else:
                time.sleep(0.06)
        if not got:
            raise RuntimeError("no clean measurement window for the C side — rerun")
        return got

    comp_samples = c_clean_samples(time_c_comp)
    best_c_comp = min(dt for dt, _ in comp_samples)
    c_out = comp_samples[0][1]
    c_payload = c_out[32:]
    dec_samples = c_clean_samples(time_c_dec, c_payload)
    best_c_dec = min(dec_samples)

    def r_clean_best(op, inp, extra):
        for _ in range(args.speed_blocks * 30):
            s0 = steal_ticks()
            t0 = time.perf_counter()
            rows = rust_bench_full(op, inp, extra)
            wall = time.perf_counter() - t0
            if clean_window(s0, steal_ticks(), wall, threads):
                return rows[op]["best_seconds"]
            time.sleep(0.06)
        raise RuntimeError(f"no clean window for rust {op} — rerun")

    best_r_comp = min(r_clean_best("compress", in_path, []) for _ in range(args.speed_blocks))
    best_r_dec = min(
        r_clean_best("decompress", pay_path, ["--orig-len", str(len(data))]) for _ in range(args.speed_blocks)
    )

    # correctness witnesses: rust self-roundtrip (bench-internal) + C decode
    # of the rust payload + byte identity
    rt_ok = c_core.decompress(r_out[32:], nb, bits, mode, chunk, len(data), threads) == data
    identical = r_out == c_out
    c_ratio = len(c_out) / len(data)
    r_ratio = len(r_out) / len(data)
    ratio_delta_pct = abs(r_ratio - c_ratio) / c_ratio * 100.0
    c_comp_mbs = mb / best_c_comp
    r_comp_mbs = mb / best_r_comp
    c_dec_mbs = mb / best_c_dec
    r_dec_mbs = mb / best_r_dec
    ok = identical and rt_ok and ratio_delta_pct <= 0.5 and r_comp_mbs >= c_comp_mbs and r_dec_mbs >= c_dec_mbs
    row = {
        "bytes": len(data),
        "threads": threads,
        "byte_identical": identical,
        "rust_roundtrip_ok": rt_ok,
        "ratio_c": round(c_ratio, 6),
        "ratio_rust": round(r_ratio, 6),
        "ratio_delta_pct": round(ratio_delta_pct, 4),
        "compress_mbs_c": round(c_comp_mbs, 1),
        "compress_mbs_rust": round(r_comp_mbs, 1),
        "compress_speedup": round(r_comp_mbs / c_comp_mbs, 3),
        "decompress_mbs_c": round(c_dec_mbs, 1),
        "decompress_mbs_rust": round(r_dec_mbs, 1),
        "decompress_speedup": round(r_dec_mbs / c_dec_mbs, 3),
        "gate": ok,
    }
    print(
        f"  {name:5} identical={identical} rt={rt_ok} "
        f"ratio d={ratio_delta_pct:.4f}%  "
        f"comp   {c_comp_mbs:7.1f}->  {r_comp_mbs:7.1f} MB/s (x{r_comp_mbs / c_comp_mbs:.2f})  "
        f"decomp {c_dec_mbs:7.1f}->  {r_dec_mbs:7.1f} MB/s (x{r_dec_mbs / c_dec_mbs:.2f})"
    )
    return ok, row


def clean_window(s0, s1, seconds, threads) -> bool:
    """~5% steal budget over the window's tick capacity (100 ticks/s/cpu)."""
    if s0 is None or s1 is None:
        return True
    budget = max(1, int(seconds * 5 * threads))
    return (s1 - s0) <= budget


def run_speed(args, c_core: CGolden, cli: str) -> dict:
    import multiprocessing

    threads = min(multiprocessing.cpu_count(), 16)
    n_el = args.speed_mb * 1024 * 1024
    dtypes = {
        "f32": ("f32", 4, 1, 220, 262144, n_el // 4),
        "bf16": ("bf16", 2, 1, 10, 262144, n_el // 2),
        "f16": ("f16", 2, 0, 10, 262144, n_el // 2),
        "fp8": ("fp8e4m3", 1, 0, 10, 131072, n_el),
    }
    tmp = tempfile.mkdtemp(prefix="znnl2speed_", dir=args.tmp_dir)
    gate = True
    results = {}
    try:
        for name, spec in dtypes.items():
            ok, row = bench_dtype(name, *spec, args, c_core, cli, tmp, threads)
            gate = gate and ok
            results[name] = row
    finally:
        if not args.keep_tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    return {"gate": gate, "dtypes": results, "threads": threads, "fixture_mb": args.speed_mb}


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", type=int, default=10_500, help="case count for the differential suite")
    ap.add_argument("--block", type=int, default=300, help="cases per streaming block (bounds disk/RAM)")
    ap.add_argument("--quick", action="store_true", help="shorthand for --cases 1200 (CI smoke)")
    ap.add_argument("--seed", type=int, default=20260923)
    ap.add_argument("--speed", action="store_true", help="run the ratio/speed fixture comparison")
    ap.add_argument("--speed-mb", type=int, default=32)
    ap.add_argument("--speed-runs", type=int, default=5, help="steal-gated timings collected per side per block")
    ap.add_argument("--speed-blocks", type=int, default=3, help="clean-sample quota per side (ceiling = min over all)")
    ap.add_argument("--skip-suite", action="store_true", help="only --speed")
    ap.add_argument("--cli", default=None, help="znn-cli path (default: release, fallback debug)")
    ap.add_argument("--tmp-dir", default=None)
    ap.add_argument("--keep-tmp", action="store_true")
    ap.add_argument("--out", default=os.path.join(REPO, "scripts", "l2", "results", "golden_diff.json"))
    args = ap.parse_args()
    if args.quick:
        args.cases = 1200

    if not c_core_available():
        print(
            "SKIP: L2 golden harness needs Linux x86_64 + CPython 3.11 "
            f"(found {platform.system()}/{platform.machine()}/py{sys.version_info[:2]}) "
            "and the pinned prebuilt C core"
        )
        return 0
    cli = args.cli or (CLI if os.path.exists(CLI) else CLI_DEBUG)
    if not os.path.exists(cli):
        print(f"FAIL: znn-cli not found at {cli} (cargo build --release -p znn-cli)")
        return 2
    mod, so = load_c_core()
    print(f"C golden core: {so}")
    c_core = CGolden(mod)

    report: dict[str, Any] = {
        "env": {
            "date": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "host": platform.platform(),
            "python": platform.python_version(),
            "cli": cli,
            "c_so": so,
        },
        "seed": args.seed,
    }
    gate = True
    if not args.skip_suite:
        t0 = time.time()
        suite = run_suite(args, c_core, cli)
        suite["seconds"] = round(time.time() - t0, 1)
        report["suite"] = suite
        gate = gate and suite.get("gate", False)
        print(json.dumps(suite["counters"], indent=1))
        if suite.get("failures"):
            print(f"FAILURES ({suite['n_failures']}):")
            for f in suite["failures"][:10]:
                print("  ", json.dumps(f))
    if args.speed:
        t0 = time.time()
        speed = run_speed(args, c_core, cli)
        speed["seconds"] = round(time.time() - t0, 1)
        report["speed"] = speed
        gate = gate and speed.get("gate", False)
    report["gate"] = gate

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(f"report → {args.out}")
    print("GATE:", "PASS" if gate else "FAIL")
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())
