"""External-change detection for the model library (Plan §4.7.2-2, Phase 6).

The `models_changed` invalidation of Phase 5 covers every change the UI itself
makes (download / rename / move / delete / ZipNN). Files added by *external*
tools - a `cp` into `models/loras`, a downloader in another terminal, a mounted
volume that fills up overnight - were only picked up by the 30 s TTL
revalidation, and only while the manager window was open (Plan §1.2.2 #14).

This module adds the OPTIONAL `watch_roots` feature on top of that:

* the Rust core (`mm_core.watch_*`, `znn_codec::watch`) arms `notify` +
  `notify-debouncer-full` on the model roots with a **500 ms debounce**
  (Plan §4.7.2-2);
* one asyncio task polls the session every [POLL_INTERVAL] seconds, maps the
  changed paths to model types and broadcasts the SAME `models_changed
  {type, reason}` event Phase 5 introduced - so the frontend listener is reused
  **unchanged** (Plan §6.2 Phase 6: the frontend reuses the Phase-5
  `models_changed` listener with no modification);
* **default OFF** - a ComfyUI setting (`ModelManager.Scan.WatchModelFolders`)
  with an `MM_WATCH_ROOTS` environment override, exactly like the ZipNN
  paranoid switch. The 30 s TTL revalidation stays the correctness floor and is
  NOT replaced;
* **degrades instead of failing**: a network-mounted root is skipped (notify
  documents that network filesystems "may not emit any events", so watching one
  buys nothing and costs inotify budget), an exhausted `fs.inotify.
  max_user_watches` ceiling stops the session and retries later, and a missing
  or too-old native core simply leaves the TTL path in charge.

Nothing here is on a request path: the watcher is started from the server's
`on_startup` hook (or lazily on the first model listing) and stopped on
`on_cleanup`.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from . import config, native, utils

#: How often the asyncio task drains the native session. The Rust debounce is
#: 500 ms (Plan §4.7.2-2), so an external change reaches the client in ~1.5 s
#: worst case - well inside the 30 s TTL it supplements.
POLL_INTERVAL = 1.0

#: Minimum seconds between two `models_changed` broadcasts for the SAME type.
#: A bulk copy into a library would otherwise re-scan that type once per poll
#: cycle; the frontend's generation guard absorbs overlapping scans, but the
#: scan itself is the expensive part (Plan §4.7.1).
TYPE_COOLDOWN = 2.0

#: After a watch-budget exhaustion (or any degraded session) wait this long
#: before arming the roots again - the ceiling is per-user and other processes
#: may release watches in the meantime.
DEGRADE_RETRY = 600.0

#: How long the on/off setting is cached. Reading it means opening and parsing
#: ComfyUI's `comfy.settings.json`, and the poll loop runs once a second *while
#: the feature is OFF by default* - so without a cache the extension would do a
#: synchronous file read on the event loop every second for every user who never
#: enables the watcher. Five seconds of switch latency is nothing for a setting
#: that only decides whether inotify watches are armed.
SETTING_TTL = 5.0

#: Transient artefacts of Neo's own atomic writes: their final rename produces
#: the event that matters, so the `.tmp` churn is filtered out.
_IGNORED_SUFFIXES = (".tmp",)

#: Cooldown-map key of the "everything changed" broadcast (`type: null`), which
#: has no model type to key on.
RESCAN_KEY = "*"

# Linux filesystem types that are network-backed (the mountinfo `fstype` field).
# notify's own docs: "Network mounted filesystems like NFS may not emit any
# events for notify to listen to."
_NETWORK_FSTYPES = frozenset(
    {
        "nfs",
        "nfs4",
        "cifs",
        "smb2",
        "smb3",
        "smbfs",
        "afs",
        "kafs",
        "ceph",
        "lustre",
        "gfs2",
        "ocfs2",
        "9p",
        "fuse.sshfs",
        "fuse.rclone",
        "fuse.gdrive",
        "fuse.s3fs",
        "fuse.juicefs",
        "fuse.davfs2",
        "fuse.curlftpfs",
        "webdav",
        "davfs",
    }
)


def env_override() -> bool | None:
    """`MM_WATCH_ROOTS` (``1``/``0``), or None to follow the setting."""
    raw = os.environ.get("MM_WATCH_ROOTS")
    if raw is None:
        return None
    raw = raw.strip().lower()
    if raw in ("0", "off", "false", "no"):
        return False
    if raw in ("1", "on", "true", "yes"):
        return True
    return None


def is_enabled_setting() -> bool:
    """The persisted setting, read without a request.

    ComfyUI resolves the user from the request only in `--multi-user` mode
    (`UserManager.get_request_user_id` returns ``"default"`` without touching
    the request otherwise), so a background task CAN read the setting with
    ``request=None``. Under `--multi-user` that lookup raises, `get_setting_value`
    swallows it and returns the default - i.e. the watcher stays OFF, which is
    the safe answer for a per-user setting read from a process-wide task.
    """
    override = env_override()
    if override is not None:
        return override
    return bool(utils.get_setting_value(None, "scan.watch_model_folders", False))


def network_mount_of(path: str) -> str | None:
    """The network filesystem `path` lives on, or None (local / unknown).

    Linux only, from `/proc/self/mountinfo` (the longest matching mount point
    wins, so a bind-mounted subdirectory of an NFS share is still detected).
    Windows answers for UNC paths and `GetDriveTypeW == DRIVE_REMOTE`. Every
    other platform returns None: a false "local" only means the watcher is
    armed for a mount that may not deliver events, and the 30 s TTL still
    refreshes - the conservative direction.
    """
    try:
        if os.name == "nt":
            return _windows_remote_of(path)
        if not os.path.isfile("/proc/self/mountinfo"):
            return None
        return _linux_network_mount(path)
    except Exception as e:  # detection is best effort by design
        utils.print_debug(f"watcher: network-mount detection failed: {e}")
        return None


#: How long a read `/proc/self/mountinfo` body is reused. The watcher polls once
#: a second and asks about every root, so without this it re-read the file once
#: per root per second; mounts change rarely, and a stale answer only means a
#: root is armed (or skipped) up to a minute late - the 30 s TTL revalidation
#: covers freshness either way.
MOUNTINFO_TTL = 60.0

_mountinfo_cache: tuple[float, str | None] = (0.0, None)


def _read_mountinfo() -> str | None:
    global _mountinfo_cache
    now = time.monotonic()
    cached_at, cached = _mountinfo_cache
    if cached is not None and now - cached_at < MOUNTINFO_TTL:
        return cached
    try:
        with open("/proc/self/mountinfo", encoding="utf-8", errors="replace") as f:
            body: str | None = f.read()
    except OSError:
        body = None
    _mountinfo_cache = (now, body)
    return body


def _linux_network_mount(path: str) -> str | None:
    mountinfo = _read_mountinfo()
    if mountinfo is None:
        return None
    return network_mount_in_mountinfo(os.path.realpath(path), mountinfo)


def network_mount_in_mountinfo(target: str, mountinfo: str) -> str | None:
    """The network mount `target` lives on, from a `/proc/self/mountinfo` body.

    Split out of the file read so the parse is testable against recorded lines:
    the LONGEST matching mount point wins (a local sub-directory bind-mounted
    out of a network share is resolved correctly), and its fstype is matched
    against [_NETWORK_FSTYPES].

    Line format: ``id parent major:minor root mountpoint options ... - fstype
    source super`` (the ``-`` separator is mandatory in the format).
    """
    best_mount = ""
    best_fstype = ""
    for line in mountinfo.splitlines():
        if " - " not in line:
            continue
        parts = line.split()
        if len(parts) < 10:
            continue
        separator = parts.index("-")
        mount_point = _unescape_mountinfo(parts[4])
        fstype = parts[separator + 1] if separator + 1 < len(parts) else ""
        if not (target == mount_point or target.startswith(mount_point.rstrip("/") + "/")):
            continue
        if len(mount_point) > len(best_mount):
            best_mount, best_fstype = mount_point, fstype
    if best_fstype in _NETWORK_FSTYPES:
        return f"{best_fstype} on {best_mount}"
    return None


def _unescape_mountinfo(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 3 < len(value) and value[i + 1 : i + 4].isdigit():
            out.append(chr(int(value[i + 1 : i + 4], 8)))
            i += 4
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _windows_remote_of(path: str) -> str | None:
    if path.startswith("\\\\"):
        return "unc path"
    try:
        import ctypes

        drive = os.path.splitdrive(os.path.abspath(path))[0]
        if not drive:
            return None
        DRIVE_REMOTE = 4  # winbase.h GetDriveTypeW
        kind = ctypes.windll.kernel32.GetDriveTypeW(drive + "\\")  # type: ignore[attr-defined]
        return "remote drive" if kind == DRIVE_REMOTE else None
    except Exception:
        return None


def local_roots(base_paths: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    """(watchable roots, skipped descriptions) for a base-path map."""
    roots: list[str] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for model_type, paths in base_paths.items():
        for path in paths:
            if not path or path in seen:
                continue
            seen.add(path)
            if not os.path.isdir(path):
                continue
            network = network_mount_of(path)
            if network:
                # Plan §4.7.2-2: a network root is auto-disabled and left to
                # the TTL polling fallback.
                skipped.append(f"{model_type}: {path} ({network})")
                continue
            roots.append(path)
    return roots, skipped


def type_matcher(base_paths: dict[str, list[str]]):
    """A `path -> [model types]` mapper with the roots resolved ONCE.

    `types_for_path` re-`realpath`ed every root for every changed path, which a
    burst of events (a bulk copy into the library) turned into
    ``len(paths) x len(roots)`` syscalls on the event loop. The mapper keeps the
    resolved roots, longest first, so one burst costs one `realpath` per path.
    """
    roots: list[tuple[int, str, str]] = []
    for model_type, paths in base_paths.items():
        for base in paths:
            if not base:
                continue
            root = os.path.realpath(base)
            roots.append((len(root), root, model_type))
    roots.sort(key=lambda item: -item[0])
    prefixed = [(root, root.rstrip(os.sep) + os.sep, model_type) for _len, root, model_type in roots]

    def match(path: str) -> list[str]:
        target = os.path.realpath(path)
        ordered: list[str] = []
        for root, prefix, model_type in prefixed:
            if model_type in ordered:
                continue
            if target == root or target.startswith(prefix):
                ordered.append(model_type)
        return ordered

    return match


def types_for_path(path: str, base_paths: dict[str, list[str]]) -> list[str]:
    """The model types whose root contains `path` (longest match first)."""
    return type_matcher(base_paths)(path)


def _interesting(path: str) -> bool:
    return not path.endswith(_IGNORED_SUFFIXES)


class ModelWatcher:
    """The single process-wide watcher service (created on import)."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._handle: int | None = None
        self._armed: list[str] = []
        self._setting_cache: tuple[float, bool] | None = None
        #: Roots already reported as skipped (network mounts), so a permanent
        #: network root is logged ONCE instead of once per second.
        self._logged_skipped: set[str] = set()
        # The native module that armed the current session: the session is
        # stopped by the SAME module even if the loader state changes in between
        # (a leaked notify thread would keep holding inotify watches).
        self._mm: Any = None
        self._last_type_broadcast: dict[str, float] = {}
        self._degraded_until = 0.0
        self._reported_unavailable = False
        self._stopped = False
        self.stats: dict[str, int] = {"polls": 0, "events": 0, "broadcasts": 0, "degrades": 0}

    def enabled(self) -> bool:
        """The on/off switch, cached for [SETTING_TTL] seconds."""
        now = time.monotonic()
        cached = self._setting_cache
        if cached is not None and now - cached[0] < SETTING_TTL:
            return cached[1]
        value = is_enabled_setting()
        self._setting_cache = (now, value)
        return value

    # -- lifecycle ----------------------------------------------------------
    def ensure_task(self) -> None:
        """Start the polling task if the loop is running and it is not up."""
        if self._stopped:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop yet (called at import time) - on_startup retries
        if self._task is not None and not self._task.done():
            return
        self._task = loop.create_task(self._run(), name="mm-model-watcher")

    async def stop(self) -> None:
        """Stop the task and release the native session (app cleanup)."""
        self._stopped = True
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            # Shutdown must not raise: CancelledError is expected, anything else
            # is a watcher bug that must not take the server down with it.
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                utils.print_debug(f"watcher: task ended with {e}")
        # The task's own `finally` already released the session; this covers a
        # stop() before the task ever ran (and is a no-op afterwards).
        await self._release_session()

    def _core(self):
        """The native core when it exposes the watch surface, else None.

        The watcher is an OPTIONAL feature: an unavailable core (missing
        binary, unsupported platform, failed handshake) simply degrades it to
        OFF with the loader's reason in the diagnostics — nothing raises.
        """
        try:
            mm = native.core_if_enabled()
        except Exception as e:  # defensive: a broken loader must not kill the poll
            utils.print_debug(f"watcher: native core unavailable ({e})")
            return None
        if mm is None:
            return None
        if not all(hasattr(mm, name) for name in ("watch_start", "watch_poll", "watch_stop")):
            return None
        return mm

    async def _release_session(self) -> None:
        """Stop the native session and forget its handle (idempotent).

        Runs the native call in the io executor: `watch_stop` joins the notify
        thread's shutdown path, which must not happen on the event loop.
        """
        if self._handle is None:
            return
        handle, self._handle = self._handle, None
        self._armed = []
        mm, self._mm = self._mm, None
        if mm is None or not hasattr(mm, "watch_stop"):
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(utils.io_executor(), mm.watch_stop, handle)
        except Exception as e:
            utils.print_debug(f"watcher: stop failed: {e}")

    # -- the polling loop ---------------------------------------------------
    async def _run(self) -> None:
        utils.print_info("model watcher task started (setting-gated, default OFF)")
        try:
            while not self._stopped:
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # a watcher must never kill the server
                    utils.print_warning(f"model watcher tick failed: {e}")
                await asyncio.sleep(POLL_INTERVAL)
        except asyncio.CancelledError:
            pass
        finally:
            # `shield`: this task is being cancelled, but the release MUST still
            # complete - a leaked notify thread would keep watching (and holding
            # inotify watches) forever. `_release_session` clears the handle
            # synchronously before its executor hop, so even a cancellation
            # racing the await cannot leave a stale handle behind.
            try:
                await asyncio.shield(self._release_session())
            except asyncio.CancelledError:
                pass

    async def _tick(self) -> None:
        if not self.enabled():
            if self._handle is not None:
                utils.print_info("model watcher disabled by setting - releasing the watches")
                await self._release_session()
            return
        if time.monotonic() < self._degraded_until:
            return  # degraded: wait out the retry window (TTL covers freshness)

        mm = self._core()
        if mm is None:
            if not self._reported_unavailable:
                self._reported_unavailable = True
                utils.print_info(
                    "model watcher unavailable (no native core with watch support) - "
                    "the 30 s TTL revalidation stays in charge"
                )
            return

        base_paths = utils.resolve_model_base_paths()
        roots, skipped = local_roots(base_paths)
        for note in skipped:
            if note in self._logged_skipped:
                continue
            self._logged_skipped.add(note)
            utils.print_info(
                f"model watcher: skipping network root {note} "
                "(notify receives no events from network filesystems; the 30 s TTL refresh covers it)"
            )
        # a mount that went away stops being reported (and can be logged again)
        self._logged_skipped &= set(skipped)
        if not roots:
            if self._handle is not None:
                await self._release_session()
            return
        if self._handle is None or set(roots) != set(self._armed):
            # Roots changed (a volume appeared, a folder was added): re-arm.
            await self._release_session()
            try:
                # Arming is the expensive part: notify adds one watch per
                # directory and the file-id cache walks the tree, so a large
                # library takes seconds. It runs in the io executor - doing it
                # on the loop would freeze every websocket for the whole walk
                # (the same defect class the Phase-5 audit fixed in the download
                # resume path). The GIL is released inside, so the other
                # executor workers and the loop keep running.
                loop = asyncio.get_running_loop()
                self._handle = int(await loop.run_in_executor(utils.io_executor(), mm.watch_start, roots))
                self._armed = roots
                self._mm = mm
                utils.print_info(f"model watcher armed on {len(roots)} root(s)")
            except Exception as e:
                self._handle = None
                self._degraded_until = time.monotonic() + DEGRADE_RETRY
                self.stats["degrades"] += 1
                utils.print_warning(
                    f"model watcher could not arm ({e}); falling back to the TTL refresh for {int(DEGRADE_RETRY)} s"
                )
                return

        try:
            payload: Any = mm.watch_poll(self._handle)
        except Exception as e:
            utils.print_warning(f"model watcher poll failed ({e}); releasing the session")
            await self._release_session()
            return
        self.stats["polls"] += 1
        try:
            report = json.loads(payload) if isinstance(payload, str) else (payload or {})
        except Exception:
            report = {}
        if not isinstance(report, dict):
            report = {}

        degraded = report.get("degraded")
        if degraded:
            self.stats["degrades"] += 1
            self._degraded_until = time.monotonic() + DEGRADE_RETRY
            utils.print_warning(
                f"model watcher degraded ({degraded}); falling back to the TTL refresh for {int(DEGRADE_RETRY)} s"
            )
            await self._release_session()
            return
        for error in report.get("errors") or []:
            utils.print_debug(f"model watcher: {error}")

        paths = [str(p) for p in (report.get("paths") or []) if _interesting(str(p))]
        rescan = bool(report.get("rescan"))
        if not paths and not rescan:
            return
        self.stats["events"] += len(paths)

        types: list[str] = []
        if rescan:
            # The backend may have missed events: invalidate everything. The
            # cooldown applies here too - a backend that keeps reporting a
            # rescan (a persistently overflowing queue) must not trigger a full
            # library sweep once a second.
            now = time.monotonic()
            if now - self._last_type_broadcast.get(RESCAN_KEY, 0.0) >= TYPE_COOLDOWN:
                self._last_type_broadcast[RESCAN_KEY] = now
                await self._broadcast(None, "fs-watch-rescan")
            return
        match = type_matcher(base_paths)
        for path in paths:
            for model_type in match(path):
                if model_type not in types:
                    types.append(model_type)
        if not types:
            # A watched root changed but no type claims the path (a root that
            # was removed from folder_paths mid-flight): full invalidation.
            await self._broadcast(None, "fs-watch")
            return
        now = time.monotonic()
        for model_type in types:
            last = self._last_type_broadcast.get(model_type, 0.0)
            if now - last < TYPE_COOLDOWN:
                continue
            self._last_type_broadcast[model_type] = now
            await self._broadcast(model_type, "fs-watch")

    async def _broadcast(self, model_type: str | None, reason: str) -> None:
        self.stats["broadcasts"] += 1
        await utils.notify_models_changed(model_type, reason)

    # -- diagnostics --------------------------------------------------------
    def diagnostics(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "enabled": self.enabled(),
            "running": self._task is not None and not self._task.done(),
            "armedRoots": len(self._armed),
            "degraded": time.monotonic() < self._degraded_until,
            **self.stats,
        }
        try:
            mm = self._core()
            if mm is not None and hasattr(mm, "watch_diagnostics"):
                out["native"] = dict(mm.watch_diagnostics())
        except Exception:
            pass
        return out


#: The process-wide service (imported by `__init__.py` and the status route).
watcher = ModelWatcher()


def install_server_hooks() -> None:
    """Start on server startup, stop on cleanup (best effort).

    ComfyUI creates `PromptServer.instance` (and its aiohttp app) BEFORE the
    extensions are imported, so the hooks registered here run with the server.
    Anything unexpected - an older ComfyUI without `app`, a test stub - simply
    leaves the lazy start in `manager.scan_models` as the entry point.
    """
    try:
        app = getattr(config.serverInstance, "app", None)
        if app is None:
            return

        async def _on_startup(_app):
            watcher.ensure_task()

        async def _on_cleanup(_app):
            await watcher.stop()

        app.on_startup.append(_on_startup)
        app.on_cleanup.append(_on_cleanup)
    except Exception as e:
        utils.print_debug(f"watcher: server hooks not installed ({e})")
