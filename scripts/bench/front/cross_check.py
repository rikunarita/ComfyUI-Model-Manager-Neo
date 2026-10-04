"""Rust <-> TypeScript tensor-tree cross-check helper (scripts/bench/front/k15.mjs).

Reads a JSON list of ``[name, dtype, shape]`` triples, writes them as a real
safetensors container (through the repository's own byte-exact test writer),
asks the built native core for its display tree and prints the payload as JSON
on stdout for the Node harness to compare against `buildTensorTreePayload`.

Deliberately dependency-free (stdlib + the built `mm_core`): it must run on any
machine that has a native binary, and it must NOT need the ComfyUI stubs - the
tree encoder only ever sees a file.

  python3 scripts/bench/front/cross_check.py --names names.json \
      --repo <repo root> --fixture /tmp/tree.safetensors

Prints either ``{"tree": {...}}`` or ``{"skipped": "<reason>"}`` (the harness
treats a skip as "not run", never as a failure).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path


def _platform_tag() -> str | None:
    """The `native/native-bin/<tag>` directory of this machine."""
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Linux" and machine in ("x86_64", "amd64"):
        return "linux-x86_64"
    if system == "Linux" and machine in ("aarch64", "arm64"):
        return "linux-aarch64"
    if system == "Windows" and machine in ("amd64", "x86_64"):
        return "windows-x86_64"
    if system == "Darwin" and machine in ("x86_64", "arm64"):
        return "macos-universal2"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", required=True, help="JSON list of [name, dtype, shape]")
    parser.add_argument("--repo", required=True, help="repository root")
    parser.add_argument("--fixture", required=True, help="where to write the safetensors fixture")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    tag = _platform_tag()
    bin_dir = repo / "native" / "native-bin" / (tag or "")
    if tag is None or not bin_dir.is_dir() or not any(bin_dir.iterdir()):
        print(json.dumps({"skipped": f"no native binary for {tag} ({bin_dir})"}))
        return 0
    sys.path.insert(0, str(bin_dir))
    sys.path.insert(0, str(repo / "tests"))
    try:
        import mm_core
    except Exception as exc:  # a stale/foreign binary must not fail the bench
        print(json.dumps({"skipped": f"mm_core import failed: {exc}"}))
        return 0
    if not hasattr(mm_core, "safetensors_tensor_tree"):
        print(json.dumps({"skipped": f"mm_core api_version {mm_core.api_version()} has no tensor tree"}))
        return 0

    try:
        from harness import write_safetensors
    except Exception as exc:
        print(json.dumps({"skipped": f"tests/harness unavailable: {exc}"}))
        return 0

    spec = json.loads(Path(args.names).read_text(encoding="utf-8"))
    tensors: dict[str, tuple[str, list[int], bytes]] = {}
    for name, dtype, shape in spec:
        elements = 1
        for dim in shape:
            elements *= dim
        bits = {
            "F32": 32,
            "F16": 16,
            "BF16": 16,
            "F64": 64,
            "I8": 8,
            "U8": 8,
            "I16": 16,
            "I32": 32,
            "I64": 64,
            "U16": 16,
            "U32": 32,
            "U64": 64,
            "BOOL": 8,
            "F8_E4M3": 8,
            "F8_E5M2": 8,
            "F8_E8M0": 8,
            "F8_E4M3FNUZ": 8,
            "F8_E5M2FNUZ": 8,
            "C64": 64,
            "F4": 4,
            "F6_E2M3": 6,
            "F6_E3M2": 6,
        }[dtype]
        nbytes = max(1, elements * bits // 8)
        # The tree only ever reads the HEADER, so the payload bytes are
        # irrelevant - zeros keep the fixture tiny and the writer fast.
        tensors[name] = (dtype, list(shape), bytes(nbytes))

    fixture = Path(args.fixture)
    fixture.parent.mkdir(parents=True, exist_ok=True)
    write_safetensors(fixture, tensors, metadata={"format": "pt"})

    tree = json.loads(mm_core.safetensors_tensor_tree(str(fixture)))
    print(json.dumps({"tree": tree, "tensors": len(tensors), "apiVersion": mm_core.api_version()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
