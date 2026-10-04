"""ZipNN compression / decompression for local safetensors models.

Every operation runs on the **pure-Rust native core** (``mm_core``, built from
``native/crates/znn-codec``): mmap-driven, parallel, GIL-released, with the
whole pipeline (header parse → per-tensor codec → integrity sha → atomic
rename) inside one Rust job this module submits and polls at 10 Hz.

The core compresses EVERY safetensors 0.8 dtype through the two
interoperability bands: compatibility-band blobs stay
official-decodable, Neo-extension blobs (f64, complex64, integers, BOOL, MX
floats) are marked ``znn_neo_extended="1"`` and refused with an explicit error
by official tools. Per-tensor records live in the file metadata under
``znn_compressed_vectors`` (the official ``zipnn.util_safetensors.METADATA_KEY``
layout) and a tensor whose compressed form is not smaller is stored untouched —
so ``<base>.znn.safetensors`` files stay readable by the official ZipNN tools
within the compatibility band.

Phase 8 removed the transition-era dual path: there is no vendored C core, no
source build, no pip cascade and no ``MM_NATIVE`` switch any more. The prebuilt
``mm_core`` under ``native/native-bin/<platform tag>/`` is the single engine;
when it cannot load (an unsupported platform, a broken installation) the ZipNN
routes fail with the loader's ``reason()`` — a clear, actionable message.
"""

import asyncio
import json
import os
import time
import uuid
from collections.abc import Callable
from typing import Any

from aiohttp import web

from . import native, utils

ZNN_SUFFIX = ".znn.safetensors"
SAFE_SUFFIX = ".safetensors"

# Neo extension to the official ZipNN metadata layout: the pre-compression
# on-disk size of the source file, recorded at compress time so the UI can
# show the original size / compressed size / ratio breakdown for a compressed
# model (the original file itself is gone by then). Other ZipNN tools ignore
# unknown metadata keys, and decompression removes it again, so the restored
# file carries exactly the metadata the original had.
ZNN_ORIGINAL_SIZE_KEY = "znn_neo_original_bytes"

# Phase 2 (native pipeline) integrity records — written by the Rust core
# and stripped by BOTH decompressors so a restored file never
# leaks Neo bookkeeping:
#   znn_neo_src_sha256        SHA-256 of the whole source file (verified on
#                             restore — default ON; mismatch on a byte-exact
#                             capable file keeps the compressed source and
#                             retreats the restore to `.corrupt`)
#   znn_neo_exact             "1" when the source header was canonical, i.e.
#                             the restore is byte-exact and the sha is
#                             ENFORCED; "0" downgrades to the structural
#                             minimum guarantee
#   znn_neo_src_meta_absent   "1" when the source had no __metadata__ at all
#   znn_neo_extended          "1" when Neo-extension-band blobs are stored
#                             (Phase 4, implemented: written by the native
#                             engine; stripped here already so extended
#                             files round-trip through both paths)
ZNN_SRC_SHA_KEY = "znn_neo_src_sha256"
ZNN_EXACT_KEY = "znn_neo_exact"
ZNN_SRC_META_ABSENT_KEY = "znn_neo_src_meta_absent"
ZNN_EXTENDED_KEY = "znn_neo_extended"

# Every Neo/ZipNN metadata key the RESTORE must strip (both paths).
ZNN_NEO_METADATA_KEYS = (
    ZNN_ORIGINAL_SIZE_KEY,
    ZNN_SRC_SHA_KEY,
    ZNN_EXACT_KEY,
    ZNN_SRC_META_ABSENT_KEY,
    ZNN_EXTENDED_KEY,
)

# task_id -> bookkeeping, same shape as the HF upload tasks
ZIPNN_TASKS: dict[str, dict] = {}

# Strong references to the in-flight background workers. asyncio keeps only
# WEAK references to tasks, so a `create_task` result nobody stores can be
# garbage-collected mid-run - a multi-gigabyte compression could silently
# vanish. Each task discards itself from the set when it finishes.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn_background(loop: asyncio.AbstractEventLoop, coro) -> None:
    task = loop.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


ProgressCb = Callable[[int, int, str], None]

# ---------------------------------------------------------------------------
# Native (Rust `mm_core`) job path — the Phase 2 switchover.
#
# The Rust core runs the whole pipeline (mmap → per-tensor codec → integrity
# sha → atomic rename) on its own thread; this side only POLLS the atomic
# progress at 10 Hz (no GIL-reacquiring callbacks) and keeps the
# ws event / stats contract byte-identical to the legacy path.
# ---------------------------------------------------------------------------

# Native phases → the legacy ws `phase` vocabulary the UI understands
# (`prepare`/`tensors`/`done`); `write`/`verify` are short assembly steps
# that read as "tensors" to the frontend, `failed` never surfaces as a phase
# (it becomes a `zipnn_complete` error).
_WS_PHASE_FOR_NATIVE = {
    "prepare": "prepare",
    "tensors": "tensors",
    "write": "tensors",
    "verify": "tensors",
    "delta": "delta",
    "done": "done",
    "failed": "tensors",
}

# Delta routes report their whole in-flight vocabulary as the legacy
# "delta" phase (the legacy delta worker only ever sent prepare/delta/done).
_WS_PHASE_FOR_DELTA = {
    "prepare": "delta",
    "tensors": "delta",
    "write": "delta",
    "verify": "delta",
    "delta": "delta",
    "done": "done",
    "failed": "delta",
}

# 10 Hz polling ("AtomicU64 を Python 側 10 Hz ポーリング").
_NATIVE_POLL_INTERVAL = 0.1


def native_core():
    """The loaded ``mm_core`` — REQUIRED for every ZipNN operation (Phase 8).

    The native core is the single engine: when it cannot load (an unsupported
    platform, a missing/corrupt binary, a failed API handshake) this raises a
    ``RuntimeError`` carrying the loader's ``reason()``, which the routes turn
    into a ``zipnn_complete`` error — a clear, actionable message instead of a
    silent fallback to an engine that no longer exists.
    """
    mm = native.core_if_enabled()
    if mm is None:
        raise RuntimeError(f"the native core is unavailable: {native.reason()}")
    return mm


def paranoid_enabled(request=None) -> bool:
    """Compress-then-immediately-decompress-and-verify.

    Default OFF. Switches, in precedence order: the ``MM_ZNN_PARANOID``
    environment variable (QA/automation), then the persisted user setting
    ``ModelManager.ZipNN.Paranoid`` (a frontend toggle can be added without
    backend changes; until then the default applies).
    """
    env = os.environ.get("MM_ZNN_PARANOID", "").strip().lower()
    if env in ("1", "on", "true", "yes"):
        return True
    if env in ("0", "off", "false", "no"):
        return False
    if request is not None:
        return bool(utils.get_setting_value(request, "zipnn.paranoid", False))
    return False


# ---------------------------------------------------------------------------
# Startup cleanup of crash/kill leftovers
# ---------------------------------------------------------------------------

# Only delete `.tmp` leftovers OLDER than this: both pipelines commit via
# rename and a live run's `.tmp` is continuously written, so a 15-minute-old
# partial in a model folder is dead by definition — while a foreign tool's
# in-flight `*.safetensors.tmp` download (they exist) is never touched.
_STRAY_TMP_MIN_AGE_S = 900.0


def _cleanup_delta_failure(dst: str, mode: str) -> None:
    """Delta-route failure cleanup (the native pipeline's own partials are the
    Rust Drop guard's job — a blind Python sweep could destroy a CONCURRENT
    job's tmp, the Phase-2 lesson — so this only handles the committed-delta
    exception).

    Compressed-delta case: when the job died AFTER the delta file was renamed
    into place but BEFORE its sidecar landed (an ENOSPC on the tiny JSON), the
    artifact would be unrestorable whenever padding was involved — remove it to
    keep the "a failed run leaves no artifact" invariant. ``dst`` can only be
    ours here: the route checked its absence when the task was created, and
    delta names live inside the base model's own ``*_DeltaZNN`` folder.
    """
    if mode == "compress" and os.path.exists(dst) and not os.path.exists(_delta_meta_path(dst)):
        try:
            os.remove(dst)
        except OSError:
            pass


def _is_stray_tmp_name(name: str) -> bool:
    """A ZipNN pipeline partial: `<model>.tmp` / `<delta>.znn.tmp` / the
    native pipeline's `.verify.tmp` / `.tmp.fix` siblings."""
    if not name.endswith((".tmp", ".tmp.fix")):
        return False
    return SAFE_SUFFIX in name or ".znn" in name


def _is_corrupt_name(name: str) -> bool:
    """A failed-verification restore diagnostic (`<model>.corrupt`)."""
    return name.endswith(".corrupt") and (SAFE_SUFFIX in name or ".znn" in name)


def cleanup_stray_files() -> dict[str, Any]:
    """Sweep dead `.tmp` partials from the model roots; list `.corrupt` files.

    Runs in the background at extension start-up (see `__init__.py`) so a
    slow/network library never delays the boot. `.tmp` files are removed
    (they are uncommitted partials of a crashed or killed run — a committed
    model never ends in `.tmp`); `.corrupt` files are only REPORTED: they are
    deliberate diagnostics whose compressed source was kept intact, so
    deleting them automatically could destroy the only copy of a failed
    restore (manual QA item "強制終了復旧").
    """
    removed: list[str] = []
    corrupt: list[str] = []
    errors: list[str] = []
    now = time.time()
    roots: set[str] = set()
    try:
        for paths in utils.resolve_model_base_paths().values():
            roots.update(paths)
    except Exception as e:  # a broken folder_paths must not kill the sweep
        return {"removed": removed, "corrupt": corrupt, "errors": [str(e)]}
    for root in sorted(roots):
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                # utils.join_path keeps the slash-normalized form the rest of
                # the backend reports (model roots arrive normalized — raw
                # os.path.join would mix separators on Windows)
                full = utils.join_path(dirpath, name)
                try:
                    if _is_stray_tmp_name(name):
                        if now - os.path.getmtime(full) >= _STRAY_TMP_MIN_AGE_S:
                            os.remove(full)
                            removed.append(full)
                    elif _is_corrupt_name(name):
                        corrupt.append(full)
                except OSError as e:
                    errors.append(f"{full}: {e}")
    if removed:
        shown = ", ".join(os.path.basename(p) for p in removed[:5])
        utils.print_warning(f"startup cleanup: removed {len(removed)} stale ZipNN .tmp file(s): {shown}")
    if corrupt:
        shown = ", ".join(os.path.basename(p) for p in corrupt[:5])
        utils.print_warning(
            f"found {len(corrupt)} .corrupt diagnostic file(s) from failed ZipNN restores "
            f"(the compressed models were kept; inspect and remove manually): {shown}"
        )
    return {"removed": removed, "corrupt": corrupt, "errors": errors}


def is_safetensors(name: str) -> bool:
    return name.endswith(SAFE_SUFFIX)


def is_compressed_name(name: str) -> bool:
    return name.endswith(ZNN_SUFFIX)


def _sidecar_move(old_model: str, new_model: str) -> None:
    """Move previews + notes from one model file to another (same directory)."""
    directory = os.path.dirname(old_model)
    names = utils.get_dir_names(directory)
    old_base = os.path.splitext(os.path.basename(old_model))[0]
    new_base = os.path.splitext(os.path.basename(new_model))[0]
    for preview in utils.previews_in_names(names, old_base):
        ext = preview[len(old_base) :]
        src = utils.join_path(directory, preview)
        dst = utils.join_path(directory, f"{new_base}{ext}")
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)
    for desc in utils.get_model_all_descriptions(old_model):
        src = utils.join_path(directory, desc)
        dst = utils.join_path(directory, f"{new_base}{os.path.splitext(desc)[1]}")
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)


# ---------------------------------------------------------------------------
# Folder batch processing (official `scripts/zipnn_compress_path.py` semantics:
# every compressible file in the folder tree, in place) and file-level delta
# compression (official `scripts/zipnn_compress_file_delta.py` /
# `zipnn_decompress_file_delta.py` semantics).
# ---------------------------------------------------------------------------


def _is_bundle_dir_name(name: str) -> bool:
    """True for ZipNN bundle folders (`*_DeltaZNN`, legacy `*_ZNN`)."""
    return utils.is_bundle_folder_name(name)


def _bundle_dst_root(folder: str, is_type_root: bool) -> str:
    """`<parent>/<name>_DeltaZNN` - where a batch compress moves its output.

    Model-type roots get the bundle *inside* themselves
    (`T/<T-name>_DeltaZNN`): a sibling of a type root would live outside every
    ComfyUI-mapped path and disappear from both the loader and the manager.
    """
    folder = folder.rstrip(os.sep) or folder
    parent = folder if is_type_root else os.path.dirname(folder)
    name = os.path.basename(folder)
    return utils.join_path(parent, f"{name}{utils.DELTA_FOLDER_SUFFIX}")


def _plain_name(name: str) -> str:
    """`x.znn.safetensors` -> `x.safetensors`."""
    return name[: -len(ZNN_SUFFIX)] + SAFE_SUFFIX


def _locate_bundle(path: str, walk_root: str) -> tuple[str, list[str]] | None:
    """Nearest bundle-named ancestor dir of `path` under `walk_root`.

    Returns (bundle_dir, dir parts between the bundle and the file), or None
    when the file does not live inside a bundle sub-tree.
    """
    rel = os.path.relpath(path, walk_root)
    parts = rel.split(os.sep)
    dir_parts = parts[:-1]
    for index in range(len(dir_parts) - 1, -1, -1):
        if _is_bundle_dir_name(dir_parts[index]):
            bundle = os.path.join(walk_root, *dir_parts[: index + 1])
            return bundle, dir_parts[index + 1 :]
    return None


def _batch_restore_root(bundle: str) -> str:
    """The folder a batch bundle empties back into.

    * sibling bundle `P/X_DeltaZNN` (or legacy `P/X_ZNN`): back into `P/X`;
    * inner bundle `T/T_DeltaZNN` (a model-type root keeps its bundle inside
      itself): back into `T` - recognised by the parent dir carrying exactly
      the name the bundle was derived from.
    """
    bundle = bundle.rstrip(os.sep)
    parent = os.path.dirname(bundle)
    source = os.path.basename(bundle)
    for suffix in (utils.DELTA_FOLDER_SUFFIX, utils.ZNN_FOLDER_SUFFIX):
        if source.endswith(suffix):
            source = source[: -len(suffix)]
            break
    if os.path.basename(parent.rstrip(os.sep)) == source:
        return parent
    return utils.join_path(parent, source)


def _decompress_target(path: str, walk_root: str, out_name: str, is_delta: bool) -> str:
    """Where a decompressed file lands.

    * batch content (`*.znn.safetensors`) inside a bundle sub-tree `B`: back
      into the folder `B` was named after (`_batch_restore_root`), keeping the
      path relative to the bundle;
    * delta content (`*_delta_*.znn` inside `B=<base>_DeltaZNN`): beside the
      base model, i.e. `parent(B)` - the fine-tune lived next to its base;
    * the walked root itself is a bundle: same rules one level up;
    * anywhere else (legacy in-place compressed type root): in place.
    """
    located = _locate_bundle(path, walk_root)
    rel = os.path.relpath(path, walk_root)
    dir_parts = rel.split(os.sep)[:-1]
    if located is not None:
        bundle, inner = located
        root = os.path.dirname(bundle.rstrip(os.sep)) if is_delta else _batch_restore_root(bundle)
        return os.path.join(root, *inner, out_name)
    if _is_bundle_dir_name(os.path.basename(walk_root.rstrip(os.sep))):
        root = os.path.dirname(walk_root.rstrip(os.sep)) if is_delta else _batch_restore_root(walk_root)
        return os.path.join(root, *dir_parts, out_name)
    return os.path.join(os.path.dirname(path), out_name)


def _compress_target(path: str, walk_root: str, bundle_root: str) -> str:
    """Mirror of `_decompress_target`: the file's place inside the bundle."""
    rel = os.path.relpath(path, walk_root)
    return os.path.join(bundle_root, rel[: -len(SAFE_SUFFIX)] + ZNN_SUFFIX)


def _prune_empty_dirs(folder: str, remove_root: bool) -> None:
    """Delete directories the batch emptied, bottom-up (best effort)."""
    for root, dirs, _names in os.walk(folder, topdown=False):
        for name in dirs:
            path = os.path.join(root, name)
            try:
                if not os.listdir(path):
                    os.rmdir(path)
            except OSError:
                pass
    if remove_root:
        try:
            if not os.listdir(folder):
                os.rmdir(folder)
        except OSError:
            pass


def _run_native_job_sync(mm: Any, task_id: str | None, submit: Callable[..., Any], label: str) -> dict[str, Any]:
    """Submit one native job and block-poll it (batch/executor side).

    The batch flow runs inside ``cpu_executor`` (a sync context), so it
    polls the same 10 Hz contract the async routes use (``time.sleep``
    releases the GIL — the ComfyUI loop keeps breathing). Registering the
    handle in ``ZIPNN_TASKS`` makes the running file cancellable through
    ``POST /model-manager/zipnn/cancel`` (a cancelled job fails with
    "cancelled by user" like any other failure, failing the batch).

    Returns the job's stats dict; raises RuntimeError with the job error.
    """
    handle = submit()
    if task_id is not None and task_id in ZIPNN_TASKS:
        ZIPNN_TASKS[task_id]["handle"] = handle
    try:
        while True:
            time.sleep(_NATIVE_POLL_INTERVAL)
            _done, _total, phase = mm.job_progress(handle)
            if phase == "failed":
                err = None
                try:
                    err = mm.job_error(handle)
                except Exception:
                    err = None
                raise RuntimeError(err or "native job failed")
            if phase == "done":
                break
        result = json.loads(mm.job_result(handle))
    finally:
        if task_id is not None and task_id in ZIPNN_TASKS:
            ZIPNN_TASKS[task_id].pop("handle", None)
    for warning in result.get("warnings") or []:
        utils.print_warning(f"zipnn[{label}]: {warning}")
    stats = result.get("stats")
    if not isinstance(stats, dict):
        raise RuntimeError("native job returned no stats")
    return stats


def _walk_files(folder: str, mode: str, mm: Any) -> list[str]:
    """The batch file set for `mode` — the Rust parallel walk
    (``mm.walk_models``, the Phase 3 batch primitive), in the stable
    sorted order. The bundle-semantics constants come from ``py/utils`` so
    the Python side stays the single source of truth.
    """
    import folder_paths

    opts: dict[str, Any] = {
        "mode": mode,
        "bundleSuffixes": [utils.DELTA_FOLDER_SUFFIX, utils.ZNN_FOLDER_SUFFIX],
        "deltaFolderSuffix": utils.DELTA_FOLDER_SUFFIX,
    }
    if mode == "compress":
        opts["skipBundles"] = True
    elif mode == "blockers":
        opts["extensions"] = sorted(folder_paths.supported_pt_extensions)
    return [str(p) for p in json.loads(mm.walk_models(folder, opts))]


def _in_place_compressed(folder: str, mm: Any) -> list[str]:
    """In-place compressed models outside bundle sub-trees.

    The decompress walk sees every ``.znn.safetensors``; dropping the ones that
    live inside a bundle sub-tree leaves exactly the in-place set (single-model
    button, auto-compress settings, older versions). Single source of truth for
    the Option-1 collect set (batch job) AND the route's compress guard.
    """
    return [
        p for p in _walk_files(folder, "decompress", mm) if p.endswith(ZNN_SUFFIX) and _locate_bundle(p, folder) is None
    ]


def batch_process_folder(
    folder: str,
    mode: str,
    is_type_root: bool,
    progress: ProgressCb,
    mm: Any,
    task_id: str | None = None,
    paranoid: bool = False,
) -> dict[str, Any]:
    """Batch-compress / batch-decompress every eligible file under `folder`.

    compress: every plain `.safetensors` becomes `.znn.safetensors` and MOVES
    into the bundle folder `<parent>/<name>_DeltaZNN` (previews/notes follow;
    directories the batch emptied are removed, so `X` is replaced by
    `X_DeltaZNN`). Model-type roots keep themselves and get the bundle inside
    (`T/T_DeltaZNN`). Already-compressed models left in place outside bundle
    sub-trees (single-model button, auto-compress, older versions) MOVE into
    the bundle untouched - no re-compression - so the sealed bundle gathers
    every ZipNN content and no compressed straggler survives beside it.

    decompress: the exact mirror - bundle content moves back to the folder the
    bundle was named after, delta files (`*_delta_*.znn` inside
    `*_DeltaZNN`) are restored to their fine-tuned models beside the base, and
    the emptied bundle folder disappears. Legacy in-place compressed files
    (type roots of older versions) decompress where they are.

    A failed run leaves already-processed files moved (each file is committed
    atomically via its `.tmp` + rename); unprocessed files are untouched.
    """
    folder = folder.rstrip(os.sep) or folder
    if mode == "compress":
        bundle = _bundle_dst_root(folder, is_type_root)
        if os.path.exists(bundle):
            raise RuntimeError(f"target already exists: {os.path.basename(bundle)}")
        files = _walk_files(folder, "compress", mm)
        # Already-compressed models left IN PLACE (single-model button, the
        # auto-compress settings, or pre-bundle versions) are ZipNN content
        # too, and the sealed-bundle model wants them inside the bundle: the
        # decompress walk sees every `.znn.safetensors`, and dropping the ones
        # that live inside a bundle sub-tree leaves exactly the in-place set.
        # They MOVE (no re-compression); the bundle accepts `*.znn.*`.
        in_place = _in_place_compressed(folder, mm)
        work = files + in_place
        total = max(1, len(work))
        for index, path in enumerate(work):
            if path.endswith(ZNN_SUFFIX):
                target = utils.join_path(bundle, os.path.relpath(path, folder))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.replace(path, target)
                mm.move_with_sidecars(path, target)
            else:
                target = _compress_target(path, folder, bundle)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                opts = {"threads": 0, "paranoid": bool(paranoid)}
                _run_native_job_sync(
                    mm,
                    task_id,
                    lambda p=path, t=target, o=opts: mm.zipnn_compress(p, t, o),
                    f"batch-compress {os.path.basename(path)}",
                )
                mm.move_with_sidecars(path, target)
                os.remove(path)
            progress(index + 1, total, "files")
        _prune_empty_dirs(folder, remove_root=not is_type_root)
        return {"files": len(work), "folder": bundle}

    files = _walk_files(folder, "decompress", mm)
    total = max(1, len(files))
    restored = 0
    skipped = 0
    for index, path in enumerate(files):
        name = os.path.basename(path)
        if name.endswith(ZNN_SUFFIX):
            target = _decompress_target(path, folder, _plain_name(name), False)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            _run_native_job_sync(
                mm,
                task_id,
                lambda p=path, t=target: mm.zipnn_decompress(p, t, {"threads": 0}),
                f"batch-decompress {name}",
            )
            mm.move_with_sidecars(path, target)
            os.remove(path)
            restored += 1
        else:
            # A delta file: restore the fine-tuned model beside its base.
            delta_dir = os.path.dirname(path)
            base_base = os.path.basename(delta_dir)[: -len(utils.DELTA_FOLDER_SUFFIX)]
            suffix = f"_delta_{base_base}.znn"
            if not name.endswith(suffix):
                utils.print_warning(f"batch decompress: skipping {name} (not a delta file)")
                skipped += 1
                progress(index + 1, total, "files")
                continue
            ft_base = name[: -len(suffix)]
            located = _locate_bundle(path, folder)
            base_dir = os.path.dirname(located[0].rstrip(os.sep)) if located is not None else os.path.dirname(delta_dir)
            base_path = os.path.join(base_dir, f"{base_base}{SAFE_SUFFIX}")
            if not os.path.isfile(base_path):
                raise RuntimeError(f"base model not found for {name}: {base_base}")
            target = _decompress_target(path, folder, f"{ft_base}{SAFE_SUFFIX}", True)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            meta = _read_delta_meta(path)
            _run_native_job_sync(
                mm,
                task_id,
                lambda b=base_path, p=path, t=target, m=meta: mm.zipnn_delta_decompress(b, p, t, m, {"threads": 0}),
                f"batch-delta {name}",
            )
            mm.move_with_sidecars(path, target)
            os.remove(path)
            sidecar = _delta_meta_path(path)
            if os.path.exists(sidecar):
                try:
                    os.remove(sidecar)
                except OSError:
                    pass
            restored += 1
        progress(index + 1, total, "files")
    _prune_empty_dirs(folder, remove_root=_is_bundle_dir_name(os.path.basename(folder)))
    return {"files": restored, "skipped": skipped, "folder": folder}


def _delta_meta_path(delta_path: str) -> str:
    return f"{delta_path}.neo-delta.json"


def _read_delta_meta(delta_path: str) -> dict[str, Any]:
    """The parsed ``.neo-delta.json`` sidecar ({} when missing/corrupt).

    A missing/corrupt sidecar degrades to {} — the length checks of the delta
    codec then fail with their usual wording unless the pads genuinely were
    zero (the historic behaviour every reader of the sidecar relied on).
    """
    try:
        with open(_delta_meta_path(delta_path), encoding="utf-8") as f:
            meta = json.load(f)
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}


def _delta_sidecar_move(src_model: str, dst_model: str) -> None:
    """Move previews/notes between *different* directories.

    `_sidecar_move` renames sidecars inside one directory, but delta files live
    in the base model's `<base>_DeltaZNN/` folder while the fine-tune's
    previews/notes live beside the fine-tune - so the delta flow needs a
    cross-directory move (fine-tune dir -> delta dir on compress, and back on
    decompress). Without it the sidecars kept their `_delta_` names forever
    (reported bug: "previews/notes disappear after delta decompress").
    """
    src_dir = os.path.dirname(src_model)
    dst_dir = os.path.dirname(dst_model)
    src_base = os.path.splitext(os.path.basename(src_model))[0]
    dst_base = os.path.splitext(os.path.basename(dst_model))[0]
    names = utils.get_dir_names(src_dir)
    for preview in utils.previews_in_names(names, src_base):
        ext = preview[len(src_base) :]
        src = utils.join_path(src_dir, preview)
        dst = utils.join_path(dst_dir, f"{dst_base}{ext}")
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(dst_dir, exist_ok=True)
            os.rename(src, dst)
    for desc in utils.get_model_all_descriptions(src_model):
        src = utils.join_path(src_dir, desc)
        dst = utils.join_path(dst_dir, f"{dst_base}{os.path.splitext(desc)[1]}")
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(dst_dir, exist_ok=True)
            os.rename(src, dst)


# ---------------------------------------------------------------------------
# Phase 4: dtype-band classification for the UI
# ---------------------------------------------------------------------------

# The safetensors dtypes whose ZN blobs stay in the UPSTREAM COMPATIBILITY
# band (codes 1-30 - official ZipNN tools decode them). Every other
# safetensors 0.8 dtype is compressed through the Neo extension band
# (codes 128-146): the resulting file carries `znn_neo_extended="1"` and is
# rejected with an explicit error by official tools. This set mirrors the
# compatibility table of the Rust core (`znn_tensor.rs`); the parity is
# pinned mechanically by tests/test_phase4_dtypes.py (the engine-written
# marker is compared against this classifier for every dtype).
COMPAT_ST_DTYPES = frozenset({"F32", "F16", "BF16", "F8_E4M3", "F8_E5M2"})


def inspect_safetensors_dtypes(path: str) -> dict[str, Any]:
    """dtype breakdown of a model file (synchronous - run in an executor).

    Plain ``.safetensors``: counts the header dtypes and reports whether
    compressing would produce a Neo-extension file (any dtype outside
    ``COMPAT_ST_DTYPES``). Compressed ``.znn.safetensors``: reads the
    recorded ``znn_neo_extended`` marker and aggregates the torch dtype
    names from ``znn_compressed_vectors``.

    Header-only work (no tensor data is read) through the native header parse
    (``mm_core.safetensors_header`` — the B4 single route, jiter-backed and
    independent of ComfyUI's ``comfy.utils`` API); errors are returned as
    ``{"error": ...}`` so the confirm dialog can fall back to its generic
    message instead of blocking on a diagnosis.
    """
    out: dict[str, Any] = {"compressed": is_compressed_name(os.path.basename(path))}
    mm = native.core_if_enabled()
    if mm is None:
        return {"error": f"the native core is unavailable: {native.reason()}"}
    try:
        header = json.loads(mm.safetensors_header(path))
    except Exception as e:
        return {"error": f"safetensors header parse failed: {e}"}
    if not isinstance(header, dict):
        return {"error": "safetensors header is not a JSON object"}

    metadata = header.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    tensors = header.get("tensors")
    tensors = tensors if isinstance(tensors, list) else []

    if out["compressed"]:
        # compressed file: the truth is in the metadata (the stored tensors
        # are all U8 blob vectors)
        out["extended"] = metadata.get(ZNN_EXTENDED_KEY) == "1"
        infos_raw = metadata.get("znn_compressed_vectors")
        counts: dict[str, int] = {}
        try:
            infos = json.loads(infos_raw) if isinstance(infos_raw, str) else {}
            for spec in infos.values():
                if isinstance(spec, dict):
                    name = str(spec.get("dtype", "?"))
                    counts[name] = counts.get(name, 0) + 1
        except Exception:
            counts = {}
        out["dtypes"] = counts
        out["compressedTensors"] = sum(counts.values())
        return out

    # plain file: count the header dtypes; any dtype outside the
    # compatibility band means the compressed output would be Neo-extended
    counts = {}
    for spec in tensors:
        if not isinstance(spec, dict):
            continue
        dtype = str(spec.get("dtype", "?"))
        counts[dtype] = counts.get(dtype, 0) + 1
    out["dtypes"] = counts
    out["tensors"] = sum(counts.values())
    extended = sorted(d for d in counts if d not in COMPAT_ST_DTYPES and d != "?")
    out["extended"] = bool(extended)
    out["extendedDtypes"] = extended
    return out


class ZipNNRoutes:
    def add_routes(self, routes):
        @routes.get("/model-manager/zipnn/available")
        async def zipnn_status(request):
            # Phase 8: the native core IS the capability (single engine — the
            # vendored C core is gone). The probe is cheap and cached (the
            # loader is idempotent), so this diagnostic route never blocks the
            # event loop. The response shape is unchanged for wire
            # compatibility; `engine` is "native" or null.
            engine = None
            reason = None
            try:
                if native.core_if_enabled() is not None:
                    engine = "native"
                else:
                    reason = native.reason()
            except Exception as e:  # diagnostics must never explode
                reason = str(e)
            return web.json_response(
                {
                    "success": True,
                    "data": {
                        "available": engine is not None,
                        "engine": engine,
                        "reason": reason,
                    },
                }
            )

        @routes.post("/model-manager/zipnn/compress")
        async def zipnn_compress(request):
            return await self._run(request, "compress")

        @routes.post("/model-manager/zipnn/decompress")
        async def zipnn_decompress(request):
            return await self._run(request, "decompress")

        @routes.post("/model-manager/zipnn/batch-folder")
        async def zipnn_batch_folder(request):
            return await self._run_batch(request)

        @routes.post("/model-manager/zipnn/delta-compress")
        async def zipnn_delta_compress(request):
            return await self._run_delta(request, "compress")

        @routes.post("/model-manager/zipnn/delta-decompress")
        async def zipnn_delta_decompress(request):
            return await self._run_delta(request, "decompress")

        @routes.post("/model-manager/zipnn/inspect")
        async def zipnn_inspect(request):
            """Phase 4: the dtype breakdown behind the compress
            confirmation ("official-compatible" vs "Neo extended format").

            Header-only and cheap, but still off the event loop (K12 lesson:
            MoE headers are megabytes of JSON). Any failure answers
            ``success: true`` with an ``error`` field so the dialog can fall
            back to its generic message — this route must never block a
            compression the user asked for."""
            data = await utils.get_request_body(request)
            model_type = data.get("type")
            path_index = int(data.get("pathIndex") or 0)
            fullname = data.get("fullname")
            if not model_type or not fullname:
                return web.json_response({"success": False, "error": "type and fullname are required"})
            try:
                src = utils.get_valid_full_path(model_type, path_index, fullname)
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})
            if src is None:
                return web.json_response({"success": False, "error": "model not found"})
            loop = asyncio.get_running_loop()
            try:
                info = await loop.run_in_executor(utils.io_executor(), inspect_safetensors_dtypes, src)
            except Exception as e:  # diagnostics must never explode
                info = {"error": str(e)}
            return web.json_response({"success": True, "data": info})

        @routes.post("/model-manager/zipnn/cancel")
        async def zipnn_cancel(request):
            """Cooperative cancellation of a running NATIVE job.

            The worker observes the flag at tensor/chunk boundaries, removes
            its partial output and reports ``zipnn_complete {ok: false,
            error: "cancelled by user"}`` like any other failure.
            """
            data = await utils.get_request_body(request)
            task_id = str(data.get("taskId") or "")
            entry = ZIPNN_TASKS.get(task_id)
            if entry is None:
                return web.json_response({"success": False, "error": "unknown task"})
            handle = entry.get("handle")
            if handle is None:
                # The job has not been submitted yet (the task is registered
                # before its worker starts) or it has already finished.
                return web.json_response(
                    {
                        "success": False,
                        "error": "this task has no cancellable native job (not started or already finished)",
                    }
                )
            mm = native.core()
            if mm is None:
                return web.json_response({"success": False, "error": "the native core is no longer loaded"})
            try:
                was_running = bool(mm.job_cancel(handle))
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})
            return web.json_response({"success": True, "data": {"wasRunning": was_running}})

    async def _run_native_job(self, mm, task_id: str, mode: str, src: str, dst: str, paranoid: bool):
        """Drive one compress/decompress job on the Rust core (Phase 2 path).

        Submits the job, then hands over to [`_poll_native_job`]. Returns
        the stats dict on success, or None after reporting the failure
        through `_fail`.

        NO python-side `.tmp` cleanup here (unlike the legacy path): the Rust
        pipeline removes its own partials on EVERY failure route (AtomicWriter
        Drop guard, cancellation, panic unwind), and a blind sweep could
        delete the tmp of a CONCURRENT job for the same target (the writer's
        create-new guard rejects the second job — its failure handler must
        not then destroy the first job's file). `.corrupt` diagnostics of a
        failed verification are deliberately kept.
        """
        opts = {"threads": 0, "paranoid": bool(paranoid)}
        try:
            handle = mm.zipnn_compress(src, dst, opts) if mode == "compress" else mm.zipnn_decompress(src, dst, opts)
        except Exception as e:
            await self._fail(task_id, src, f"native job could not start: {e}")
            return None
        return await self._poll_native_job(mm, task_id, mode, src, handle, _WS_PHASE_FOR_NATIVE)

    async def _run_native_delta_job(self, mm, task_id: str, mode: str, src: str, second: str, dst: str, paranoid: bool):
        """Drive one delta job on the Rust core (Phase 3 path).

        compress: `src` = base model, `second` = fine-tune → `dst` delta
        file (+ `.neo-delta.json` sidecar, written by the job itself with
        the new `ftSha256` integrity key). decompress: `src` = base model,
        `second` = delta file → `dst` restored fine-tune; the sidecar is
        parsed HERE (same missing/corrupt degradation as the legacy reader)
        and passed across the boundary.
        """
        try:
            if mode == "compress":
                opts = {"threads": 0, "paranoid": bool(paranoid)}
                handle = mm.zipnn_delta_compress(src, second, dst, opts)
            else:
                meta = _read_delta_meta(second)
                handle = mm.zipnn_delta_decompress(src, second, dst, meta, {"threads": 0})
        except Exception as e:
            await self._fail(task_id, second, f"native job could not start: {e}")
            return None
        return await self._poll_native_job(mm, task_id, mode, second, handle, _WS_PHASE_FOR_DELTA)

    async def _poll_native_job(self, mm, task_id: str, mode: str, src: str, handle, phase_map: dict[str, str]):
        """Poll a submitted native job at 10 Hz and re-emit the legacy ws
        contract (`update_zipnn_progress` with the same payload shape;
        phases mapped through `phase_map`). Returns the stats dict on
        success, or None after reporting the failure through `_fail`."""
        ZIPNN_TASKS[task_id]["handle"] = handle

        last_sent: tuple[float, str] | None = None
        while True:
            await asyncio.sleep(_NATIVE_POLL_INTERVAL)
            try:
                done, total, phase = mm.job_progress(handle)
            except Exception as e:
                await self._fail(task_id, src, f"native job vanished: {e}")
                return None
            if phase not in ("done", "failed"):
                pct = (done / total * 100) if total else 0.0
                ws_phase = phase_map.get(phase, "tensors")
                event = (round(pct, 3), ws_phase)
                if event != last_sent:
                    last_sent = event
                    await utils.send_json(
                        "update_zipnn_progress",
                        {"taskId": task_id, "progress": pct, "phase": ws_phase, "mode": mode},
                    )
            if phase == "failed":
                try:
                    err = mm.job_error(handle)
                except Exception:
                    err = None
                await self._fail(task_id, src, err or "native job failed")
                return None
            if phase == "done":
                break

        try:
            result = json.loads(mm.job_result(handle))
        except Exception as e:
            await self._fail(task_id, src, f"native job result unreadable: {e}")
            return None
        for warning in result.get("warnings") or []:
            utils.print_warning(f"zipnn[{mode}]: {warning}")
        stats = result.get("stats")
        if not isinstance(stats, dict):
            await self._fail(task_id, src, "native job returned no stats")
            return None
        return stats

    async def _run(self, request, mode: str):
        data = await utils.get_request_body(request)
        model_type = data.get("type")
        path_index = int(data.get("pathIndex") or 0)
        fullname = data.get("fullname")
        if not model_type or not fullname:
            return web.json_response({"success": False, "error": "type and fullname are required"})
        if not is_safetensors(fullname):
            return web.json_response(
                {
                    "success": False,
                    "error": "ZipNN compression supports .safetensors files only",
                }
            )
        try:
            src = utils.get_valid_full_path(model_type, path_index, fullname)
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)})
        if src is None:
            return web.json_response({"success": False, "error": "model not found"})

        if mode == "compress":
            if is_compressed_name(fullname):
                return web.json_response({"success": False, "error": "model is already compressed"})
            base = src[: -len(SAFE_SUFFIX)]
            dst = f"{base}{ZNN_SUFFIX}"
        else:
            if not is_compressed_name(fullname):
                return web.json_response({"success": False, "error": "model is not ZipNN compressed"})
            base = src[: -len(ZNN_SUFFIX)]
            dst = f"{base}{SAFE_SUFFIX}"
        if os.path.exists(dst):
            return web.json_response({"success": False, "error": f"target already exists: {os.path.basename(dst)}"})

        paranoid = paranoid_enabled(request)
        task_id = uuid.uuid4().hex
        ZIPNN_TASKS[task_id] = {"mode": mode, "status": "running", "src": src, "dst": dst}
        await utils.send_json(
            "update_zipnn_progress",
            {"taskId": task_id, "progress": 0.0, "phase": "prepare", "mode": mode},
        )

        loop = asyncio.get_running_loop()

        async def worker():
            # ANY escaping exception must flip the task to "error" and emit
            # zipnn_complete — a worker that dies silently would leave the UI
            # spinner running forever (`_schedule` only logs).
            try:
                await worker_body()
            except Exception as e:
                try:
                    await self._fail(task_id, src, f"zipnn worker crashed: {e}")
                except Exception:
                    utils.print_error(f"zipnn worker crash could not be reported: {e}")

        async def worker_body():
            try:
                mm = native_core()
            except RuntimeError as e:
                # Unavailable core: the reason() text is actionable (missing
                # binary / failed handshake) — surface it.
                await self._fail(task_id, src, str(e))
                return

            stats = await self._run_native_job(mm, task_id, mode, src, dst, paranoid)
            if stats is None:
                return  # failure/cancellation already reported

            # The model entry moves to the new file: previews and notes follow.
            try:
                _sidecar_move(src, dst)
                os.remove(src)
            except Exception as e:
                await self._fail(task_id, src, str(e))
                return

            ZIPNN_TASKS[task_id]["status"] = "complete"
            await utils.send_json(
                "update_zipnn_progress",
                {"taskId": task_id, "progress": 100.0, "phase": "done", "mode": mode},
            )
            await utils.send_json(
                "zipnn_complete",
                {
                    "taskId": task_id,
                    "mode": mode,
                    "ok": True,
                    "stats": stats,
                    "fullname": os.path.basename(dst),
                },
            )

        _spawn_background(loop, self._schedule(worker()))
        return web.json_response({"success": True, "data": {"taskId": task_id}})

    async def _run_batch(self, request):
        """Batch-compress / batch-decompress a whole folder (selection bar).

        compress: every plain `.safetensors` under `X` is compressed and moved
        into the bundle folder `X_DeltaZNN` (a model-type root `T` gets the
        bundle inside itself: `T/T_DeltaZNN`, because a sibling of a type root
        would fall outside every ComfyUI-mapped path). decompress: the exact
        mirror - bundle content moves back to the folder the bundle was named
        after, `*_delta_*.znn` files are restored to their fine-tuned models,
        and the emptied bundle folder is removed. `mode="auto"` lets the
        server pick the direction from the folder content (plain models
        present -> compress, only compressed ones -> decompress).
        """
        data = await utils.get_request_body(request)
        if not isinstance(data, dict) or not data:
            # Defensive: some proxies/middlewares re-encode JSON bodies; fall
            # back to form parsing so a legit click can never die here.
            try:
                data = dict(await request.post())
            except Exception:
                data = {}
        mode = data.get("mode")
        model_type = data.get("type")
        path_index = int(data.get("pathIndex") or 0)
        rel_folder = str(data.get("folder") or data.get("fullname") or "").strip("/")
        if mode not in ("compress", "decompress", "auto") or not model_type or not rel_folder:
            utils.print_warning(
                f"batch-folder request rejected; received keys: {sorted(data.keys()) if data else '<empty body>'}"
            )
            return web.json_response(
                {
                    "success": False,
                    "error": (
                        "mode, type and folder are required (received: "
                        f"{', '.join(sorted(data.keys())) if data else 'empty body'})"
                    ),
                }
            )
        try:
            folder = utils.get_full_path(model_type, path_index, rel_folder)
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)})
        # '.' is the relative path of a model-type root folder; normpath folds
        # it into the base path so the type-root detection below works.
        folder = os.path.normpath(folder)
        if not os.path.isdir(folder):
            return web.json_response({"success": False, "error": "folder not found"})
        bases = utils.resolve_model_base_paths().get(model_type, [])
        is_type_root = path_index < len(bases) and utils.normalize_path(folder) == utils.normalize_path(
            bases[path_index]
        )

        folder_name = os.path.basename(folder.rstrip("/"))
        # The native core drives the validation walks AND the worker, so an
        # unavailable core is answered here as a plain request error (a task
        # that could only fail is never created).
        try:
            mm = native_core()
        except RuntimeError as e:
            return web.json_response({"success": False, "error": str(e)})
        paranoid = paranoid_enabled(request)
        if mode == "auto":
            if _walk_files(folder, "compress", mm):
                mode = "compress"
            elif _walk_files(folder, "decompress", mm):
                mode = "decompress"
            else:
                return web.json_response(
                    {
                        "success": False,
                        "error": "folder holds no compressible or compressed models",
                    }
                )
        if mode == "compress":
            if _is_bundle_dir_name(folder_name):
                return web.json_response(
                    {
                        "success": False,
                        "error": (
                            "folder is already a ZipNN bundle "
                            f"(*{utils.DELTA_FOLDER_SUFFIX}): batch-decompress it instead"
                        ),
                    }
                )
            blockers = _walk_files(folder, "blockers", mm)
            if blockers:
                names = ", ".join(os.path.basename(b) for b in blockers[:5])
                return web.json_response(
                    {
                        "success": False,
                        "error": (
                            "folder holds models ZipNN cannot convert "
                            f"({names}); a *{utils.DELTA_FOLDER_SUFFIX} folder "
                            "may only contain *.znn.* / *.znn models"
                        ),
                    }
                )
            files = _walk_files(folder, "compress", mm)
            # Option 1: a folder whose only content is in-place compressed
            # models is a valid compress target too (they move into the
            # bundle untouched), so the guard must consider both sets.
            if not files and not _in_place_compressed(folder, mm):
                return web.json_response({"success": False, "error": "no .safetensors files to compress"})
            # Every compressed file MOVES into `<name>_DeltaZNN`; model-type
            # roots get the bundle inside themselves (a sibling of a type root
            # would fall outside every ComfyUI-mapped path).
            dst_folder = _bundle_dst_root(folder, is_type_root)
        else:
            # Bundles empty back into the folder they were named after;
            # legacy in-place compressed folders decompress where they are.
            dst_folder = folder
            files = _walk_files(folder, "decompress", mm)
            if not files:
                return web.json_response(
                    {
                        "success": False,
                        "error": "no .znn.safetensors / delta files to decompress",
                    }
                )
        if dst_folder != folder and os.path.exists(dst_folder):
            return web.json_response(
                {
                    "success": False,
                    "error": f"target already exists: {os.path.basename(dst_folder)}",
                }
            )

        task_id = uuid.uuid4().hex
        ZIPNN_TASKS[task_id] = {
            "mode": f"batch-{mode}",
            "status": "running",
            "src": folder,
            "dst": dst_folder,
        }
        await utils.send_json(
            "update_zipnn_progress",
            {"taskId": task_id, "progress": 0.0, "phase": "prepare", "mode": mode},
        )
        loop = asyncio.get_running_loop()

        async def worker():
            # ANY escaping exception must flip the task to "error" and emit
            # zipnn_complete — a worker that dies silently would leave the UI
            # spinner running forever (`_schedule` only logs).
            try:
                await worker_body()
            except Exception as e:
                try:
                    await self._fail(task_id, folder, f"zipnn worker crashed: {e}")
                except Exception:
                    utils.print_error(f"zipnn worker crash could not be reported: {e}")

        async def worker_body():
            try:
                mm_run = native_core()
            except RuntimeError as e:
                # The core was available at validation time and vanished (a
                # hot-unplugged install): actionable reason() via _fail.
                await self._fail(task_id, folder, str(e))
                return

            def progress(done: int, total: int, phase: str):
                asyncio.run_coroutine_threadsafe(
                    utils.send_json(
                        "update_zipnn_progress",
                        {
                            "taskId": task_id,
                            "progress": (done / total * 100) if total else 0.0,
                            "phase": phase,
                            "mode": mode,
                        },
                    ),
                    loop,
                )

            try:
                stats = await loop.run_in_executor(
                    utils.cpu_executor(),
                    batch_process_folder,
                    folder,
                    mode,
                    is_type_root,
                    progress,
                    mm_run,
                    task_id,
                    paranoid,
                )
            except Exception as e:
                await self._fail(task_id, folder, str(e))
                return

            ZIPNN_TASKS[task_id]["status"] = "complete"
            await utils.send_json(
                "update_zipnn_progress",
                {"taskId": task_id, "progress": 100.0, "phase": "done", "mode": mode},
            )
            await utils.send_json(
                "zipnn_complete",
                {
                    "taskId": task_id,
                    "mode": mode,
                    "kind": "folder",
                    "ok": True,
                    "stats": stats,
                    "fullname": os.path.basename(dst_folder),
                },
            )

        _spawn_background(loop, self._schedule(worker()))
        return web.json_response({"success": True, "data": {"taskId": task_id}})

    async def _run_delta(self, request, mode: str):
        """Delta (de)compression of a fine-tuned model against its base.

        compress: base + FT -> `<base>_DeltaZNN/<ft>_delta_<base>.znn`, then the
        FT original is removed (its bytes are recoverable from base + delta).
        decompress: base + delta -> the exact FT file back beside the base.
        """
        data = await utils.get_request_body(request)
        model_type = data.get("type")
        path_index = int(data.get("pathIndex") or 0)
        if not model_type:
            return web.json_response({"success": False, "error": "type is required"})

        if mode == "compress":
            base_full = data.get("baseFullname")
            ft_full = data.get("fullname")
            if not base_full or not ft_full:
                return web.json_response({"success": False, "error": "baseFullname and fullname are required"})
            try:
                base_path = utils.get_valid_full_path(model_type, path_index, base_full)
                ft_path = utils.get_valid_full_path(model_type, path_index, ft_full)
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})
            if not base_path or not ft_path:
                return web.json_response({"success": False, "error": "base or fine-tuned model not found"})
            if base_path == ft_path:
                return web.json_response({"success": False, "error": "base and fine-tuned model must differ"})
            for candidate in (base_path, ft_path):
                if not is_safetensors(candidate) or is_compressed_name(candidate):
                    return web.json_response(
                        {
                            "success": False,
                            "error": "delta compression needs plain .safetensors inputs",
                        }
                    )
            base_base = os.path.basename(base_path)[: -len(SAFE_SUFFIX)]
            ft_base = os.path.basename(ft_path)[: -len(SAFE_SUFFIX)]
            delta_dir = utils.join_path(os.path.dirname(base_path), f"{base_base}{utils.DELTA_FOLDER_SUFFIX}")
            out_path = utils.join_path(delta_dir, f"{ft_base}_delta_{base_base}.znn")
            if os.path.exists(out_path):
                return web.json_response(
                    {
                        "success": False,
                        "error": f"target already exists: {os.path.basename(out_path)}",
                    }
                )
            src, second, dst = base_path, ft_path, out_path
        else:
            delta_full = data.get("fullname")
            if not delta_full:
                return web.json_response({"success": False, "error": "fullname is required"})
            try:
                delta_path = utils.get_valid_full_path(model_type, path_index, delta_full)
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)})
            if not delta_path:
                return web.json_response({"success": False, "error": "delta file not found"})
            delta_dir = os.path.dirname(delta_path)
            delta_folder = os.path.basename(delta_dir)
            if not delta_folder.endswith(utils.DELTA_FOLDER_SUFFIX):
                return web.json_response({"success": False, "error": "not inside a *_DeltaZNN folder"})
            base_base = delta_folder[: -len(utils.DELTA_FOLDER_SUFFIX)]
            delta_name = os.path.basename(delta_path)
            suffix = f"_delta_{base_base}.znn"
            if not delta_name.endswith(suffix):
                return web.json_response({"success": False, "error": "unexpected delta file name"})
            ft_base = delta_name[: -len(suffix)]
            base_path = utils.join_path(os.path.dirname(delta_dir), f"{base_base}{SAFE_SUFFIX}")
            if not os.path.isfile(base_path):
                return web.json_response({"success": False, "error": f"base model not found: {base_base}"})
            out_path = utils.join_path(os.path.dirname(delta_dir), f"{ft_base}{SAFE_SUFFIX}")
            if os.path.exists(out_path):
                return web.json_response(
                    {
                        "success": False,
                        "error": f"target already exists: {os.path.basename(out_path)}",
                    }
                )
            src, second, dst = base_path, delta_path, out_path

        task_id = uuid.uuid4().hex
        ZIPNN_TASKS[task_id] = {
            "mode": f"delta-{mode}",
            "status": "running",
            "src": second,
            "dst": dst,
        }
        await utils.send_json(
            "update_zipnn_progress",
            {"taskId": task_id, "progress": 0.0, "phase": "prepare", "mode": mode},
        )
        loop = asyncio.get_running_loop()
        paranoid = paranoid_enabled(request)

        async def worker():
            # ANY escaping exception must flip the task to "error" and emit
            # zipnn_complete — a worker that dies silently would leave the UI
            # spinner running forever (`_schedule` only logs).
            try:
                await worker_body()
            except Exception as e:
                try:
                    await self._fail(task_id, second, f"zipnn worker crashed: {e}")
                except Exception:
                    utils.print_error(f"zipnn worker crash could not be reported: {e}")

        async def worker_body():
            try:
                mm = native_core()
            except RuntimeError as e:
                # Unavailable core: the reason() text is actionable (missing
                # binary / failed handshake) — surface it.
                await self._fail(task_id, second, str(e))
                return

            stats = await self._run_native_delta_job(mm, task_id, mode, src, second, dst, paranoid)
            if stats is None:
                # failure already reported; the Rust Drop guard removed
                # its own partials — only the committed-delta-without-
                # sidecar case needs Python's help
                _cleanup_delta_failure(dst, mode)
                return

            try:
                if mode == "compress":
                    # previews/notes of the fine-tuned model travel with the
                    # delta file, then the (now redundant) original goes away.
                    _delta_sidecar_move(second, dst)
                    os.remove(second)
                else:
                    _delta_sidecar_move(second, dst)
                    os.remove(second)
                    sidecar_meta = _delta_meta_path(second)
                    if os.path.exists(sidecar_meta):
                        try:
                            os.remove(sidecar_meta)
                        except OSError:
                            pass
                    try:
                        if not os.listdir(delta_dir):
                            os.rmdir(delta_dir)
                    except OSError:
                        pass
            except Exception as e:
                await self._fail(task_id, second, str(e))
                return

            ZIPNN_TASKS[task_id]["status"] = "complete"
            await utils.send_json(
                "update_zipnn_progress",
                {"taskId": task_id, "progress": 100.0, "phase": "done", "mode": mode},
            )
            await utils.send_json(
                "zipnn_complete",
                {
                    "taskId": task_id,
                    "mode": mode,
                    "kind": "delta",
                    "ok": True,
                    "stats": stats,
                    "fullname": os.path.basename(dst),
                },
            )

        _spawn_background(loop, self._schedule(worker()))
        return web.json_response({"success": True, "data": {"taskId": task_id}})

    async def _schedule(self, coro):
        try:
            await coro
        except Exception as e:  # pragma: no cover - defensive
            utils.print_error(f"zipnn worker crashed: {e}")

    async def _fail(self, task_id: str, src: str, error: str):
        ZIPNN_TASKS[task_id]["status"] = "error"
        utils.print_error(f"zipnn failed for {src}: {error}")
        await utils.send_json(
            "zipnn_complete",
            {
                "taskId": task_id,
                "ok": False,
                "error": error,
            },
        )
