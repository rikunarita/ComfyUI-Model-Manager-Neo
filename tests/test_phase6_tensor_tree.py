"""Phase 6 golden tests - the Rust-folded display tensor tree.

`safetensors_tensor_tree` moves the Information tab's tensor-tree fold out of
the browser (~0.73 s of main-thread JS for a 65k-tensor MoE header - BENCH
§11). Because it is a *display* structure the frontend renders directly, the
wire document is pinned here against an independent Python implementation of
the same rule:

* a name is split on ``.``; every segment but the last is a folder (an empty
  segment reads ``(unnamed)``), the last one is the leaf;
* nodes are emitted PRE-ORDER, root first, own leaves before children;
* ``[segment, childCount, tensorCount, totalCount, totalParams]`` with the two
  totals as SUBTREE aggregates;
* ``leaves`` holds indices into the ``tensors`` array of the SAME response, so
  the two lists are cross-checked against each other here (a stale or shifted
  index would render a wrong tensor name - the failure mode that matters).

Tests that need the built ``mm_core`` binary skip when it is absent (CI's
verify job); the native workflow's integration job runs them for real.
"""

from __future__ import annotations

import json
import os

import pytest
from harness import DTYPE_BITS, REPO_ROOT, import_ext, write_safetensors

UNNAMED = "(unnamed)"
TREE_VERSION = 1


# ---------------------------------------------------------------------------
# engine helpers (same conventions as test_phase5_scan.py)
# ---------------------------------------------------------------------------
def _reset_native_loader():
    config = import_ext("config")
    config.extension_uri = str(REPO_ROOT)
    native = import_ext("native")
    native._module = None
    native._reason = None
    native._attempted = False
    return native


def _require_native():
    native = _reset_native_loader()
    tag = native.platform_tag()
    if tag is None or not (REPO_ROOT / "native" / "native-bin" / tag).is_dir():
        pytest.skip("native binary not built (scripts/build-native.sh)")
    if not native.load():
        pytest.skip(f"native core unavailable: {native.reason()}")
    return native.core()


def _set_engine(monkeypatch, mode: str):
    """Engine selection by injection (the MM_NATIVE env switch is gone, Phase 8).

    ``"0"`` forces ``native.core_if_enabled`` to None — the resilience
    degradation the header path takes without a core (metadata/tensors from
    the Python parse, no Rust tree); ``"1"``/``"auto"`` restore the loader's
    real function so the prebuilt core serves all three fields.
    """
    native = import_ext("native")
    original = getattr(native, "_orig_core_if_enabled", None)
    if original is None:
        original = native.core_if_enabled
        native._orig_core_if_enabled = original
    if mode == "0":
        monkeypatch.setattr(native, "core_if_enabled", lambda: None)
    else:
        monkeypatch.setattr(native, "core_if_enabled", original)
    _reset_native_loader()


# ---------------------------------------------------------------------------
# the independent reference fold
# ---------------------------------------------------------------------------
def reference_tree(tensors: list[dict]) -> dict:
    """The wire document, computed in Python from a `get_model_tensors` list."""
    nodes: list[dict] = [{"segment": "", "children": [], "leaves": [], "count": 0, "params": 0}]
    parents: list[int] = [-1]
    by_path: dict[str, int] = {}
    for index, tensor in enumerate(tensors):
        segments = (tensor.get("name") or "").split(".")
        parent = 0
        path = ""
        for segment in segments[:-1]:
            name = segment or UNNAMED
            path = f"{path}.{name}" if path else name
            if path not in by_path:
                idx = len(nodes)
                nodes.append({"segment": name, "children": [], "leaves": [], "count": 0, "params": 0})
                parents.append(parent)
                nodes[parent]["children"].append(idx)
                by_path[path] = idx
            parent = by_path[path]
        nodes[parent]["leaves"].append(index)
        nodes[parent]["count"] += 1
        nodes[parent]["params"] += _params(tensor.get("shape") or [])
    for idx in range(len(nodes) - 1, 0, -1):
        ancestor = nodes[parents[idx]]
        ancestor["count"] += nodes[idx]["count"]
        ancestor["params"] += nodes[idx]["params"]

    out_nodes: list[list] = []
    out_leaves: list[int] = []
    stack: list[list[int]] = [[0, 0]]
    while stack:
        frame = stack[-1]
        node = nodes[frame[0]]
        if frame[1] == 0:
            out_nodes.append(
                [node["segment"], len(node["children"]), len(node["leaves"]), node["count"], node["params"]]
            )
            out_leaves.extend(node["leaves"])
        if frame[1] < len(node["children"]):
            child = node["children"][frame[1]]
            frame[1] += 1
            stack.append([child, 0])
        else:
            stack.pop()
    return {"v": TREE_VERSION, "nodes": out_nodes, "leaves": out_leaves}


def _params(shape: list[int]) -> int:
    total = 1
    for dim in shape:
        total *= dim
    return total


def _decode(payload: dict) -> tuple[list[list], list[int]]:
    assert payload["v"] == TREE_VERSION
    nodes = [list(entry) for entry in payload["nodes"]]
    leaves = [int(entry) for entry in payload["leaves"]]
    return nodes, leaves


def _walk(nodes: list[list], leaves: list[int]) -> tuple[list[tuple[str, int]], list[int]]:
    """(path, tensorIndex) pairs in display order - the decoder's own walk."""
    out: list[tuple[str, int]] = []
    sizes: list[int] = [1] * len(nodes)
    parents: list[int] = [-1] * len(nodes)
    stack: list[int] = []
    remaining = [node[1] for node in nodes]
    for i in range(len(nodes)):
        while stack and remaining[stack[-1]] == 0:
            stack.pop()
        parents[i] = stack[-1] if stack else -1
        if parents[i] >= 0:
            remaining[parents[i]] -= 1
        stack.append(i)
        remaining[i] = nodes[i][1]
    for i in range(len(nodes) - 1, 0, -1):
        sizes[parents[i]] += sizes[i]

    cursor = 0
    frame_stack: list[tuple[int, str, int]] = [(0, "", 0)]
    while frame_stack:
        index, path, next_child = frame_stack[-1]
        if next_child == 0:
            for _ in range(nodes[index][2]):
                out.append((path, leaves[cursor]))
                cursor += 1
        if next_child < nodes[index][1]:
            at = index + 1
            for _ in range(next_child):
                at += sizes[at]
            segment = nodes[at][0]
            child_path = f"{path}.{segment}" if path else segment
            frame_stack[-1] = (index, path, next_child + 1)
            frame_stack.append((at, child_path, 0))
        else:
            frame_stack.pop()
    assert cursor == len(leaves), "the walk must consume every leaf exactly once"
    return out, sizes


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _write(tmp_path, name: str, spec: dict[str, tuple[str, list[int]]], metadata=None):
    """Write a safetensors file (payload sized by the harness dtype table)."""
    tensors = {}
    for tensor_name, (dtype, shape) in spec.items():
        nelem = _params(shape)
        nbytes = max(1, nelem * DTYPE_BITS[dtype] // 8)
        tensors[tensor_name] = (dtype, shape, bytes(nbytes))
    path = tmp_path / name
    write_safetensors(path, tensors, metadata)
    return str(path)


NESTED = {
    "model.layers.0.self_attn.q_proj.weight": ("F32", [4, 4]),
    "model.layers.0.self_attn.k_proj.weight": ("F32", [4, 4]),
    "model.layers.10.mlp.experts.3.gate_proj.weight": ("F32", [2, 2]),
    "model.layers.2.mlp.down_proj.weight": ("F32", [8]),
    "lm_head.weight": ("F32", [4]),
    "scale": ("F32", []),  # scalar -> 1 parameter
    "bias": ("F32", [3]),  # no dot -> root leaf
}

EDGE_CASES = {
    "a..b.w": ("F32", [2]),  # empty level -> (unnamed)
    ".": ("F32", [1]),  # two empty segments
    "x": ("F32", [5]),
    "deep.1.2.3.4.5.6.7.8.9.leaf": ("F32", [1]),
}


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------
def test_tensor_tree_matches_the_reference_fold(tmp_path, monkeypatch):
    mm = _require_native()
    _set_engine(monkeypatch, "auto")
    utils = import_ext("utils")
    for name, spec in (("nested.safetensors", NESTED), ("edge.safetensors", EDGE_CASES)):
        path = _write(tmp_path, name, spec, metadata={"format": "pt"})
        tensors = utils.get_model_tensors(path)
        payload = json.loads(mm.safetensors_tensor_tree(path))
        assert payload == reference_tree(tensors), name


def test_tensor_tree_leaf_indices_address_the_same_tensors(tmp_path, monkeypatch):
    """The tree's leaf indices must name the tensor the frontend would show."""
    mm = _require_native()
    _set_engine(monkeypatch, "auto")
    utils = import_ext("utils")
    path = _write(tmp_path, "nested.safetensors", NESTED, metadata={"format": "pt"})
    tensors = utils.get_model_tensors(path)
    nodes, leaves = _decode(json.loads(mm.safetensors_tensor_tree(path)))

    placed, sizes = _walk(nodes, leaves)
    # every tensor appears exactly once
    assert sorted(index for _, index in placed) == list(range(len(tensors)))
    # the node path of a leaf is its own name minus the last segment, with the
    # historical `(unnamed)` substitution for an empty level (`a..b.w`)
    for path, index in placed:
        name = tensors[index]["name"]
        segments = name.split(".")
        expected = ".".join(seg or UNNAMED for seg in segments[:-1])
        assert path == expected, (name, path, expected)
    # root aggregates == the whole file
    assert nodes[0][3] == len(tensors)
    assert nodes[0][4] == sum(_params(t["shape"]) for t in tensors)
    # the subtree sizes the decoder derives are consistent with childCount
    assert sizes[0] == len(nodes)


def test_tensor_tree_scales_to_a_moe_header(tmp_path, monkeypatch):
    """A MoE-shaped header (many experts x layers) folds identically."""
    mm = _require_native()
    _set_engine(monkeypatch, "auto")
    utils = import_ext("utils")
    spec: dict[str, tuple[str, list[int]]] = {}
    for layer in range(12):
        spec[f"model.layers.{layer}.self_attn.q_proj.weight"] = ("BF16", [16, 8])
        for expert in range(16):
            for proj in ("gate_proj", "up_proj", "down_proj"):
                spec[f"model.layers.{layer}.mlp.experts.{expert}.{proj}.weight"] = ("BF16", [8, 4])
    path = _write(tmp_path, "moe.safetensors", spec, metadata={"format": "pt"})
    tensors = utils.get_model_tensors(path)
    assert len(tensors) == len(spec) == 12 * (1 + 48)
    payload = json.loads(mm.safetensors_tensor_tree(path))
    assert payload == reference_tree(tensors)
    # the expert folders exist, each with its 3 projection sub-folders
    nodes, _ = _decode(payload)
    expert_nodes = [node for node in nodes if node[0].isdigit() and node[1] == 3]
    assert len(expert_nodes) == 12 * 16
    assert all(node[3] == 3 for node in expert_nodes), "one tensor per projection"


def test_get_model_header_shape_and_degradation(tmp_path, monkeypatch):
    """`utils.get_model_header` serves all three fields, and degrades safely."""
    _require_native()
    utils = import_ext("utils")
    path = _write(tmp_path, "detail.safetensors", NESTED, metadata={"format": "pt", "fp": "fp32"})

    _set_engine(monkeypatch, "1")
    header = utils.get_model_header(path)
    assert header["metadata"] == {"format": "pt", "fp": "fp32"}
    assert len(header["tensors"]) == len(NESTED)
    assert header["tensorTree"] == reference_tree(header["tensors"])

    # legacy engine: metadata + tensors as before, no tree (the frontend folds)
    _set_engine(monkeypatch, "0")
    legacy = utils.get_model_header(path)
    assert legacy["metadata"] == header["metadata"]
    assert legacy["tensors"] == header["tensors"]
    assert legacy["tensorTree"] is None

    # a non-safetensors file yields the empty triple on both engines
    ckpt = tmp_path / "model.ckpt"
    ckpt.write_bytes(b"not a safetensors file")
    for mode in ("0", "1"):
        _set_engine(monkeypatch, mode)
        assert utils.get_model_header(str(ckpt)) == {"metadata": {}, "tensors": [], "tensorTree": None}
    # a missing file degrades instead of raising
    _set_engine(monkeypatch, "1")
    assert utils.get_model_header(str(tmp_path / "gone.safetensors")) == {
        "metadata": {},
        "tensors": [],
        "tensorTree": None,
    }


@pytest.mark.asyncio
async def test_model_info_route_carries_the_tree(prompt_server, model_lib, tmp_path, monkeypatch):
    """The detail route adds `tensorTree` without changing the other fields."""
    _require_native()
    _set_engine(monkeypatch, "auto")
    manager = import_ext("manager")
    from harness import FakeRequest

    target = model_lib / "checkpoints" / "detail.safetensors"
    src = _write(tmp_path, "detail.safetensors", NESTED, metadata={"format": "pt"})
    import shutil

    shutil.copyfile(src, target)

    instance = manager.ModelManager()
    instance.add_routes(prompt_server.routes)
    info = instance.get_model_info(str(target))
    assert set(info) == {"metadata", "description", "tensors", "tensorTree"}
    assert info["metadata"] == {"format": "pt"}
    assert info["tensorTree"] == reference_tree(info["tensors"])

    # and through the route (the JSON body the frontend receives)
    routes = prompt_server.routes.handlers
    handler = routes[("GET", "/model-manager/model/{type}/{index}/{filename:.*}")]
    request = FakeRequest(match_info={"type": "checkpoints", "index": "0", "filename": "detail.safetensors"})
    from harness import json_body

    body = json_body(await handler(request))
    assert body["success"] is True
    assert body["data"]["tensorTree"]["v"] == TREE_VERSION
    assert body["data"]["tensorTree"] == info["tensorTree"]


def test_tensor_tree_is_dropped_when_the_file_changes_mid_read(tmp_path, monkeypatch):
    """`tensors` and `tensorTree` come from two separate header parses.

    A file replaced in between (a ZipNN compress renaming into place, an
    external download landing) would pair a tree with the wrong tensor list, so
    the pair is stamped around the read and the tree is dropped on a mismatch -
    the frontend then folds it from `tensors`, which is always consistent.
    """
    mm = _require_native()
    _set_engine(monkeypatch, "1")
    utils = import_ext("utils")
    path = _write(tmp_path, "racy.safetensors", NESTED, metadata={"format": "pt"})

    # sanity: without the race the tree is served
    assert utils.get_model_header(path)["tensorTree"] is not None

    real_tree = mm.safetensors_tensor_tree

    def racing(p: str):
        out = real_tree(p)
        # the file is "replaced" behind our back: a new mtime is enough for the
        # guard (and `os.utime` keeps the fixture itself readable)
        st = os.stat(p)
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        return out

    monkeypatch.setattr(mm, "safetensors_tensor_tree", racing)
    header = utils.get_model_header(path)
    assert header["tensorTree"] is None, "a mid-read change must drop the tree"
    assert len(header["tensors"]) == len(NESTED), "the tensor list is still served"
    assert header["metadata"] == {"format": "pt"}
