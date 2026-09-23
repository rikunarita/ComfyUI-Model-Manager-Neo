"""Synthetic fixture generation for the KPI baselines (Plan §2.2 / Phase 0).

Real multi-GB models cannot be materialised on every machine (this baseline
ran on a 2 vCPU / 1 GiB container); the fixtures below reproduce the *shape*
of the real workload at a measurable scale:

* `--moe-header`  : a safetensors file whose JSON header is ~8 MB of
                    DeepSeek-style MoE tensor entries (K11 / json-bench input).
* `--raw-dtype`   : raw tensor-byte fixtures (Gaussian weights — the entropy
                    profile real checkpoints have) for the direct C-core bench.
* `--model`       : a real .safetensors model file (torch/numpy written).
* `--pair`        : a base + fine-tuned .safetensors pair with identical
                    tensor layout (delta compression input, K4).
* `--library`     : a model-library tree of N tiny models with sidecars and
                    previews (scan bench input, K9/K10).

Everything is deterministic per seed. Files are written wherever `--out`
points (keep them OUTSIDE the repository — /tmp is the default).
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys

import numpy as np

# Tensor-name style of a large MoE checkpoint (DeepSeek-V3-like): the header
# SIZE is what K11 measures, and long expert names are what makes real MoE
# headers reach megabytes.
_MOE_EXPERT_PROJS = ("gate_proj", "up_proj", "down_proj")


def _write_safetensors_raw(path: str, header: dict, data: bytes) -> None:
    blob = json.dumps(header, separators=(",", ":"), sort_keys=True).encode()
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(struct.pack("<Q", len(blob)))
        f.write(blob)
        f.write(data)
    os.replace(tmp, path)


def gen_moe_header(out: str, target_bytes: int, seed: int) -> dict:
    """Build a safetensors file with a ~target_bytes JSON header.

    The data section is a stub (zeros): Neo's header parsing paths
    (`comfy.utils.safetensors_header` + `json.loads`) never read past the
    header, and the Rust json-bench consumes the extracted header JSON.
    data_offsets are internally consistent with the *described* tensors.
    """
    rng = np.random.default_rng(seed)
    del rng  # layout is deterministic by construction; seed kept for the API
    header: dict[str, object] = {"__metadata__": {"format": "pt"}}
    offset = 0
    layer = 0
    while True:
        # One MoE layer: attention block + 256 experts x 3 projections.
        for name, shape in (
            (f"model.layers.{layer}.self_attn.q_proj.weight", [7168, 16384]),
            (f"model.layers.{layer}.self_attn.k_proj.weight", [7168, 4096]),
            (f"model.layers.{layer}.self_attn.v_proj.weight", [7168, 4096]),
            (f"model.layers.{layer}.self_attn.o_proj.weight", [16384, 7168]),
            (f"model.layers.{layer}.mlp.gate.weight", [256, 7168]),
            (f"model.layers.{layer}.mlp.shared_experts.gate_proj.weight", [2048, 7168]),
            (f"model.layers.{layer}.mlp.shared_experts.up_proj.weight", [2048, 7168]),
            (f"model.layers.{layer}.mlp.shared_experts.down_proj.weight", [7168, 2048]),
            (f"model.layers.{layer}.input_layernorm.weight", [7168]),
        ):
            nbytes = 2 * int(np.prod(shape))  # BF16
            header[name] = {
                "dtype": "BF16",
                "shape": shape,
                "data_offsets": [offset, offset + nbytes],
            }
            offset += nbytes
        for expert in range(256):
            for proj in _MOE_EXPERT_PROJS:
                shape = [2048, 7168] if proj != "down_proj" else [7168, 2048]
                nbytes = 2 * int(np.prod(shape))
                header[f"model.layers.{layer}.mlp.experts.{expert}.{proj}.weight"] = {
                    "dtype": "BF16",
                    "shape": shape,
                    "data_offsets": [offset, offset + nbytes],
                }
                offset += nbytes
        layer += 1
        size = len(json.dumps(header, separators=(",", ":"), sort_keys=True))
        if size >= target_bytes:
            break
        if layer > 4096:  # runaway guard (never hit for 8 MB)
            raise RuntimeError("MoE header generator exceeded 4096 layers")

    _write_safetensors_raw(out, header, b"")
    header_bytes = os.path.getsize(out) - 8
    # Also emit the bare header JSON (json-bench input).
    with open(f"{out}.json", "w", encoding="utf-8") as f:
        json.dump(header, f, separators=(",", ":"), sort_keys=True)
    return {
        "file": out,
        "headerJsonFile": f"{out}.json",
        "headerBytes": header_bytes,
        "tensors": len(header) - 1,
        "layers": layer,
        "describedDataBytes": offset,
    }


def _gaussian_bytes(n_elements: int, dtype: str, seed: int) -> bytes:
    """Weight-like bytes for `dtype` (Gaussian, sigma 0.02 — the profile of
    trained checkpoints; random uniform data would compress far worse and
    misrepresent the baseline).

    Generated in 4 M-element blocks into a preallocated buffer: transient RAM
    stays O(block) no matter how big the fixture is (this baseline ran on a
    1 GiB machine)."""
    # Stable per-dtype seed offset (str hash() is salted per process).
    seed = seed + sorted(_DTYPE_INFO).index(dtype)
    rng = np.random.default_rng(seed)
    elem = _DTYPE_INFO[dtype][1]
    out = np.empty(n_elements * elem, dtype=np.uint8)
    block = 4 * 1024 * 1024
    done = 0
    while done < n_elements:
        n = min(block, n_elements - done)
        f32 = rng.standard_normal(n, dtype=np.float32)
        f32 *= 0.02
        if dtype == "f32":
            out[done * 4 : (done + n) * 4] = f32.view(np.uint8)
        elif dtype == "f16":
            # Generator.standard_normal has no float16; the f32 -> f16 cast
            # keeps the distribution (values ~N(0, 0.02), inside f16 range).
            out[done * 2 : (done + n) * 2] = f32.astype(np.float16).view(np.uint8)
        elif dtype == "bf16":
            # bf16 = the high 16 bits of an f32 (truncation vs torch's
            # round-to-nearest is irrelevant at this entropy level).
            hi16 = (f32.view(np.uint32) >> 16).astype(np.uint16)
            out[done * 2 : (done + n) * 2] = hi16.view(np.uint8)
        elif dtype == "fp8e4m3":
            import torch  # lazy: only this dtype needs it

            t = torch.from_numpy(f32).to(torch.float8_e4m3fn)
            out[done : done + n] = t.view(torch.uint8).numpy()
        else:
            raise ValueError(f"unknown dtype {dtype!r}")
        done += n
    return out.tobytes()


_DTYPE_INFO = {
    # name: (safetensors dtype, element size, torch dtype string for metadata)
    "f32": ("F32", 4),
    "f16": ("F16", 2),
    "bf16": ("BF16", 2),
    "fp8e4m3": ("F8_E4M3", 1),
}


def gen_raw(out_dir: str, dtypes: list[str], size_mb: int, seed: int) -> list[dict]:
    """Raw tensor-byte fixtures for the direct C-core benchmark."""
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for dtype in dtypes:
        st_dtype, elem = _DTYPE_INFO[dtype]
        n = (size_mb * 1024 * 1024) // elem
        path = os.path.join(out_dir, f"gauss-{dtype}-{size_mb}mb.bin")
        data = _gaussian_bytes(n, dtype, seed)
        with open(path, "wb") as f:
            f.write(data)
        made.append({"dtype": dtype, "safetensorsDtype": st_dtype, "path": path, "bytes": len(data)})
    return made


def gen_model(out: str, dtype: str, size_mb: int, seed: int) -> dict:
    """A real .safetensors model file (tensor-per-block layout, metadata)."""
    elem = _DTYPE_INFO[dtype][1]
    total_elements = (size_mb * 1024 * 1024) // elem
    # Split into <=16 MB blocks so generation stays RAM-friendly, with
    # checkpoint-style names.
    block = max(1, min(total_elements, (16 * 1024 * 1024) // elem))
    tensors: dict[str, object] = {}
    done = 0
    i = 0
    while done < total_elements:
        n = min(block, total_elements - done)
        side = int(n**0.5) or 1
        shape = [side, n // side] if n // side > 1 else [n]
        count = shape[0] * shape[-1] if len(shape) == 2 else shape[0]
        raw = _gaussian_bytes(count, dtype, seed + i)
        tensors[f"model.blocks.{i}.weight"] = (shape, raw)
        done += count
        i += 1

    if dtype in ("bf16", "fp8e4m3"):
        import torch
        from safetensors.torch import save_file

        t_tensors = {}
        for name, (shape, raw) in tensors.items():
            if dtype == "bf16":
                t = torch.frombuffer(bytearray(raw), dtype=torch.uint16).view(torch.bfloat16)
            else:
                t = torch.frombuffer(bytearray(raw), dtype=torch.uint8).view(torch.float8_e4m3fn)
            t_tensors[name] = t.reshape(shape)
        save_file(t_tensors, out, metadata={"format": "pt"})
    else:
        from safetensors.numpy import save_file

        np_map = {"f32": np.float32, "f16": np.float16}
        n_tensors = {
            name: np.frombuffer(raw, dtype=np_map[dtype]).reshape(shape) for name, (shape, raw) in tensors.items()
        }
        save_file(n_tensors, out, metadata={"format": "pt"})
    return {"file": out, "dtype": dtype, "bytes": os.path.getsize(out), "tensors": len(tensors)}


def gen_pair(out_base: str, out_ft: str, size_mb: int, seed: int) -> dict:
    """base + fine-tune pair: identical layout, small per-element drift.

    Mirrors a real full fine-tune: every weight moved a little, so the XOR
    delta is dominated by low mantissa bytes — the profile Neo's delta
    compression is used on (Plan §1.1). The fine-tune also gains a metadata
    key, so the two HEADERS differ in length — exercising the padding path
    of py/compress.py `_delta_aligned_bytes`.
    """
    elem = 4  # f32
    total = (size_mb * 1024 * 1024) // elem
    rng = np.random.default_rng(seed)
    base_arr = (rng.standard_normal(total, dtype=np.float32) * 0.02).reshape(4, total // 4)
    ft_arr = base_arr + (rng.standard_normal(base_arr.shape, dtype=np.float32) * 0.0002)

    from safetensors.numpy import save_file

    names = [f"model.blocks.{i}.weight" for i in range(4)]
    save_file(
        {n: base_arr[i] for i, n in enumerate(names)},
        out_base,
        metadata={"format": "pt"},
    )
    save_file(
        {n: ft_arr[i] for i, n in enumerate(names)},
        out_ft,
        metadata={"format": "pt", "finetune_of": os.path.basename(out_base)},
    )
    return {
        "base": out_base,
        "ft": out_ft,
        "baseBytes": os.path.getsize(out_base),
        "ftBytes": os.path.getsize(out_ft),
    }


_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)

_MD_TEMPLATE = """---
modelPage: https://civitai.com/models/{i}
website: civitai
hashes:
  SHA256: {sha}
baseModel: SD 1.5
format: SafeTensor
precision: fp16
---

# model {i}

Synthetic scan-bench fixture (scripts/bench/gen_synthetic.py).
"""


def gen_library(root: str, n_models: int, seed: int) -> dict:
    """A model-library tree: n_models tiny .safetensors spread over type
    dirs/subfolders; ~20 % carry .md sidecars with front-matter, ~30 % a
    preview .png, plus a few hygiene-scan fixtures (orphan sidecar, empty
    dir). Model files are 10-byte stubs (the scan only stats them)."""
    rng = np.random.default_rng(seed)
    types = ["checkpoints", "loras", "vae", "controlnet", "embeddings", "upscale_models"]
    made = {"models": 0, "md": 0, "png": 0, "dirs": 0}
    stub = struct.pack("<Q", 2) + b"{}"
    per_type = max(1, n_models // len(types))
    for t in types:
        base = os.path.join(root, t)
        sub_count = 6
        for s in range(sub_count):
            sub = os.path.join(base, f"pack{s}" if s else "")
            os.makedirs(sub or base, exist_ok=True)
            made["dirs"] += 1
            target = per_type if s == 0 else max(1, per_type // sub_count)
            for i in range(target):
                if made["models"] >= n_models:
                    break
                idx = made["models"]
                name = f"model-{t}-{s}-{i}"
                with open(os.path.join(sub or base, f"{name}.safetensors"), "wb") as f:
                    f.write(stub)
                made["models"] += 1
                if rng.random() < 0.2:
                    sha = "".join(f"{b:02X}" for b in rng.integers(0, 256, 32))
                    with open(os.path.join(sub or base, f"{name}.md"), "w", encoding="utf-8") as f:
                        f.write(_MD_TEMPLATE.format(i=idx, sha=sha))
                    made["md"] += 1
                if rng.random() < 0.3:
                    with open(os.path.join(sub or base, f"{name}.png"), "wb") as f:
                        f.write(_PNG_1PX)
                    made["png"] += 1
            if made["models"] >= n_models:
                break
        if made["models"] >= n_models:
            break
    # Hygiene fixtures: an orphaned sidecar and an empty folder.
    orphan_dir = os.path.join(root, "checkpoints")
    with open(os.path.join(orphan_dir, "orphaned-note.md"), "w", encoding="utf-8") as f:
        f.write("# orphan\n")
    os.makedirs(os.path.join(root, "loras", "empty-pack"), exist_ok=True)
    return {"root": root, **made}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--moe-header", metavar="OUT.safetensors")
    ap.add_argument("--header-mb", type=float, default=8.0)
    ap.add_argument("--raw-dtype", nargs="*", default=None, metavar="DTYPE")
    ap.add_argument("--raw-size-mb", type=int, default=192)
    ap.add_argument("--model", metavar="OUT.safetensors")
    ap.add_argument("--model-dtype", default="bf16", choices=sorted(_DTYPE_INFO))
    ap.add_argument("--model-size-mb", type=int, default=64)
    ap.add_argument("--pair", nargs=2, metavar=("BASE.safetensors", "FT.safetensors"))
    ap.add_argument("--pair-size-mb", type=int, default=32)
    ap.add_argument("--library", metavar="ROOT_DIR")
    ap.add_argument("--library-models", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=20260923)
    ap.add_argument("--out-dir", default="/tmp/mm-bench")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    results: list[object] = []
    if args.moe_header:
        results.append(gen_moe_header(args.moe_header, int(args.header_mb * 1024 * 1024), args.seed))
    if args.raw_dtype:
        results.extend(gen_raw(args.out_dir, args.raw_dtype, args.raw_size_mb, args.seed))
    if args.model:
        results.append(gen_model(args.model, args.model_dtype, args.model_size_mb, args.seed))
    if args.pair:
        results.append(gen_pair(args.pair[0], args.pair[1], args.pair_size_mb, args.seed))
    if args.library:
        results.append(gen_library(args.library, args.library_models, args.seed))
    if not results:
        ap.print_help()
        sys.exit(2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
