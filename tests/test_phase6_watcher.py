"""Phase 6 - the optional `watch_roots` library watcher (Plan §4.7.2-2).

Plan §6.2 Phase 6 states the acceptance condition: *"既定 OFF + degrade 動作 +
primitive テスト"*. The tests below cover exactly those three:

* **primitives** - the path -> model-type mapping, the network-root skip and
  the `/proc/self/mountinfo` parse (recorded lines, longest-match rule);
* **default OFF** - the setting/env switch, and that a disabled watcher never
  arms a native session;
* **degrade** - a `degraded` session (inotify budget exhausted) is released,
  reported and retried only after the cool-off, leaving the 30 s TTL refresh in
  charge;
* **end to end** (native binary required) - a file created by an EXTERNAL
  process under a model root produces the same `models_changed {type, reason}`
  websocket broadcast Phase 5 introduced, so the frontend listener needs no
  change.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from harness import REPO_ROOT, import_ext

# A real `/proc/self/mountinfo` excerpt (recorded on the dev container) plus the
# network shapes the detector exists for. Field 5 is the mount point, the fstype
# follows the mandatory " - " separator.
MOUNTINFO = """\
97 59 0:39 / / rw,relatime master:33 - overlay overlay rw,lowerdir=/lower,upperdir=/upper
98 97 0:42 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw
99 97 0:43 / /dev rw,nosuid - tmpfs tmpfs rw,size=65536k,mode=755
120 97 0:60 / /tmp mmneo rw,relatime - ext4 /dev/sda1 rw
130 97 0:61 / /mnt/nas rw,relatime - nfs 10.0.0.1:/srv/models rw,rsize=1048576
140 97 0:62 / /mnt/smb rw,relatime - cifs //fileserver/models rw,unc=\\\\fileserver\\models
150 97 0:63 / /mnt/local-under-nas rw,relatime - ext4 /dev/sdb1 rw
160 97 0:64 / /mnt/nas/share rw,relatime - fuse.sshfs user@host:/srv rw
170 97 0:65 / /mnt/space\\040dir rw,relatime - nfs 10.0.0.2:/export rw
"""


def _watcher_module():
    return import_ext("watcher")


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------
def test_mountinfo_parse_finds_network_mounts_with_longest_match():
    watcher = _watcher_module()
    parse = watcher.network_mount_in_mountinfo
    # local filesystems are not network mounts
    assert parse("/tmp/mm-bench/models", MOUNTINFO) is None
    assert parse("/", MOUNTINFO) is None
    assert parse("/proc/self", MOUNTINFO) is None
    # the network shapes
    assert parse("/mnt/nas/models/loras", MOUNTINFO) == "nfs on /mnt/nas"
    assert parse("/mnt/smb/checkpoints", MOUNTINFO) == "cifs on /mnt/smb"
    assert parse("/mnt/nas/share/a.safetensors", MOUNTINFO) == "fuse.sshfs on /mnt/nas/share"
    # the octal-escaped mount point ("space dir") is unescaped before matching
    assert parse("/mnt/space dir/x", MOUNTINFO) == "nfs on /mnt/space dir"
    # a LOCAL bind mount inside a network tree wins by longest match
    assert parse("/mnt/local-under-nas/sub", MOUNTINFO) is None
    # a sibling prefix must not match ("/mnt/nas2" is not under "/mnt/nas")
    assert parse("/mnt/nas2/x", MOUNTINFO) is None


def test_types_for_path_maps_the_longest_root_first(tmp_path):
    watcher = _watcher_module()
    root = tmp_path / "models"
    (root / "checkpoints").mkdir(parents=True)
    (root / "loras").mkdir(parents=True)
    nested = root / "checkpoints" / "extra"
    nested.mkdir()
    base_paths = {
        "checkpoints": [str(root / "checkpoints")],
        "loras": [str(root / "loras")],
        # a second root INSIDE the first: the longest match must win the order
        "extra": [str(nested)],
    }
    assert watcher.types_for_path(str(nested / "a.safetensors"), base_paths) == ["extra", "checkpoints"]
    assert watcher.types_for_path(str(root / "loras" / "b.safetensors"), base_paths) == ["loras"]
    assert watcher.types_for_path(str(tmp_path / "elsewhere.safetensors"), base_paths) == []


def test_local_roots_skips_missing_and_network_roots(tmp_path, monkeypatch):
    watcher = _watcher_module()
    (tmp_path / "ok").mkdir()
    (tmp_path / "nas").mkdir()
    base_paths = {
        "checkpoints": [str(tmp_path / "ok"), str(tmp_path / "missing")],
        "loras": [str(tmp_path / "nas")],
        # a duplicate root is armed once
        "vae": [str(tmp_path / "ok")],
    }
    monkeypatch.setattr(watcher, "network_mount_of", lambda path: "nfs on /nas" if path.endswith("nas") else None)
    roots, skipped = watcher.local_roots(base_paths)
    assert roots == [str(tmp_path / "ok")], "missing + network + duplicate roots are dropped"
    assert skipped == [f"loras: {tmp_path / 'nas'} (nfs on /nas)"]


def test_env_override_and_default_off(monkeypatch):
    watcher = _watcher_module()
    utils = import_ext("utils")
    # no env, no persisted setting (the stub server has no user_manager) → OFF
    monkeypatch.delenv("MM_WATCH_ROOTS", raising=False)
    assert watcher.env_override() is None
    assert watcher.is_enabled_setting() is False
    assert utils.get_setting_value(None, "scan.watch_model_folders", False) is False
    # the env switch wins over the setting in both directions
    for raw, expected in (("1", True), ("on", True), ("0", False), ("off", False), ("maybe", None)):
        monkeypatch.setenv("MM_WATCH_ROOTS", raw)
        assert watcher.env_override() is expected, raw
    monkeypatch.setenv("MM_WATCH_ROOTS", "1")
    assert watcher.is_enabled_setting() is True


def test_setting_key_is_registered():
    """The setting ID the frontend registers must resolve on the backend."""
    utils = import_ext("utils")
    assert utils.resolve_setting_key("scan.watch_model_folders") == "ModelManager.Scan.WatchModelFolders"


def test_tmp_artefacts_are_filtered():
    watcher = _watcher_module()
    assert watcher._interesting("/models/a.safetensors") is True
    assert watcher._interesting("/models/a.safetensors.tmp") is False


# ---------------------------------------------------------------------------
# the service
# ---------------------------------------------------------------------------
def _make_watcher(monkeypatch, tmp_path, enabled=True):
    """A fresh service instance wired to a temp library (never the singleton)."""
    watcher_mod = _watcher_module()
    utils = import_ext("utils")
    root = tmp_path / "models" / "checkpoints"
    root.mkdir(parents=True)
    monkeypatch.setenv("MM_WATCH_ROOTS", "1" if enabled else "0")
    monkeypatch.setattr(
        utils, "resolve_model_base_paths", lambda: {"checkpoints": [str(tmp_path / "models" / "checkpoints")]}
    )
    monkeypatch.setattr(utils, "_base_paths_cache", {}, raising=False)
    service = watcher_mod.ModelWatcher()
    return watcher_mod, service, root


@pytest.mark.asyncio
async def test_disabled_watcher_never_arms_a_session(tmp_path, monkeypatch):
    _, service, _ = _make_watcher(monkeypatch, tmp_path, enabled=False)
    armed: list[list[str]] = []

    class FakeCore:
        def watch_start(self, roots, opts=None):
            armed.append(list(roots))
            return 1

        def watch_poll(self, handle):
            return json.dumps({"paths": [], "rescan": False, "degraded": None})

        def watch_stop(self, handle):
            return None

    monkeypatch.setattr(service, "_core", lambda: FakeCore())
    await service._tick()
    await service._tick()
    assert armed == [], "MM_WATCH_ROOTS=0 must not arm inotify watches"
    assert service._handle is None
    assert service.diagnostics()["enabled"] is False


@pytest.mark.asyncio
async def test_external_change_broadcasts_models_changed(prompt_server, tmp_path, monkeypatch):
    """The whole point of the feature: an EXTERNAL write becomes the Phase-5
    `models_changed` event, so the frontend listener is reused unchanged."""
    _watcher_mod, service, root = _make_watcher(monkeypatch, tmp_path)
    if not _native_available():
        pytest.skip("native binary not built (scripts/build-native.sh)")
    mm = import_ext("native").core()
    monkeypatch.setattr(service, "_core", lambda: mm)

    await service._tick()  # arms the session
    assert service._handle is not None
    assert service.diagnostics()["armedRoots"] == 1
    assert prompt_server.sent == []

    # An external process drops a model into the library.
    (root / "external.safetensors").write_bytes(b"x" * 8)
    # 25 s bound: Linux inotify answers in ~0.6 s (500 ms debounce + 1 s poll),
    # macOS FSEvents and Windows ReadDirectoryChangesW can take a few seconds on
    # a loaded CI runner. The Rust L1 watch test (same event, 10 s bound) already
    # passed on all three OSes in native-test.
    deadline = time.monotonic() + 25.0
    while time.monotonic() < deadline and not prompt_server.sent:
        await service._tick()
        await asyncio.sleep(0.2)

    events = [(event, data) for event, data, _sid in prompt_server.sent]
    assert events, "the watcher never reported the external file"
    assert events[0][0] == "models_changed"
    assert events[0][1]["type"] == "checkpoints"
    assert events[0][1]["reason"] == "fs-watch"
    assert service.stats["events"] >= 1
    await service.stop()
    assert service._handle is None


@pytest.mark.asyncio
async def test_degraded_session_falls_back_to_the_ttl(prompt_server, tmp_path, monkeypatch):
    """An exhausted inotify budget must degrade, not fail (Plan §4.7.2-2)."""
    watcher_mod, service, _root = _make_watcher(monkeypatch, tmp_path)
    started: list[int] = []
    polls = {"n": 0}

    stopped: list[int] = []

    class DegradingCore:
        def watch_start(self, roots, opts=None):
            started.append(1)
            return 42

        def watch_poll(self, handle):
            polls["n"] += 1
            return json.dumps(
                {
                    "paths": [],
                    "rescan": False,
                    "degraded": "inotify watch budget exhausted while arming /models: os error 28",
                }
            )

        def watch_stop(self, handle):
            stopped.append(handle)

    core = DegradingCore()
    monkeypatch.setattr(service, "_core", lambda: core)
    monkeypatch.setattr(watcher_mod, "DEGRADE_RETRY", 30.0)

    await service._tick()  # arm
    await service._tick()  # poll → degraded
    assert started == [1]
    assert service._handle is None, "the session is released"
    assert stopped == [42], "the module that armed the session is the one that stops it"
    diagnostics = service.diagnostics()
    assert diagnostics["degraded"] is True
    assert service.stats["degrades"] == 1

    # during the cool-off no new session is armed (the TTL refresh is in charge)
    await service._tick()
    await service._tick()
    assert started == [1]
    assert polls["n"] == 1
    assert prompt_server.sent == []

    # after the cool-off it tries again
    service._degraded_until = 0.0
    await service._tick()
    assert started == [1, 1]


@pytest.mark.asyncio
async def test_missing_native_core_degrades_quietly(tmp_path, monkeypatch):
    _watcher_mod, service, _ = _make_watcher(monkeypatch, tmp_path)
    monkeypatch.setattr(service, "_core", lambda: None)
    await service._tick()
    await service._tick()
    assert service._handle is None
    assert service.diagnostics()["running"] is False
    # the reason is logged once, not every second
    assert service._reported_unavailable is True


@pytest.mark.asyncio
async def test_rescan_flag_invalidates_everything(prompt_server, tmp_path, monkeypatch):
    """`need_rescan` (a backend that may have missed events) must widen the
    invalidation to a full sweep (`type: null`)."""
    _watcher_mod, service, _root = _make_watcher(monkeypatch, tmp_path)

    class RescanCore:
        def __init__(self):
            self.first = True

        def watch_start(self, roots, opts=None):
            return 7

        def watch_poll(self, handle):
            if self.first:
                self.first = False
                return json.dumps({"paths": [], "rescan": True, "degraded": None})
            return json.dumps({"paths": [], "rescan": False, "degraded": None})

        def watch_stop(self, handle):
            return None

    core = RescanCore()  # ONE instance: `_core()` is called on every tick
    monkeypatch.setattr(service, "_core", lambda: core)
    await service._tick()  # arms AND polls in the same tick -> the rescan report
    await service._tick()  # nothing pending -> no second broadcast
    events = [(event, data) for event, data, _sid in prompt_server.sent]
    assert events == [("models_changed", {"type": None, "reason": "fs-watch-rescan"})]


@pytest.mark.asyncio
async def test_type_cooldown_collapses_a_bulk_copy(prompt_server, tmp_path, monkeypatch):
    """A burst of changes for one type broadcasts once per cooldown window."""
    watcher_mod, service, root = _make_watcher(monkeypatch, tmp_path)
    payloads = [
        json.dumps({"paths": [str(root / "a.safetensors")], "rescan": False, "degraded": None}),
        json.dumps({"paths": [str(root / "b.safetensors")], "rescan": False, "degraded": None}),
    ]

    class BurstCore:
        def watch_start(self, roots, opts=None):
            return 9

        def watch_poll(self, handle):
            return payloads.pop(0) if payloads else json.dumps({"paths": [], "rescan": False, "degraded": None})

        def watch_stop(self, handle):
            return None

    monkeypatch.setattr(service, "_core", lambda: BurstCore())
    monkeypatch.setattr(watcher_mod, "TYPE_COOLDOWN", 5.0)
    await service._tick()
    await service._tick()  # a
    await service._tick()  # b (inside the cooldown)
    events = [data for event, data, _sid in prompt_server.sent if event == "models_changed"]
    assert len(events) == 1, events
    assert events[0]["type"] == "checkpoints"


@pytest.mark.asyncio
async def test_arm_and_release_run_off_the_event_loop(tmp_path, monkeypatch):
    """`watch_start` walks the tree and adds one inotify watch per directory, so
    it MUST NOT run on the loop (the Phase-5 audit fixed the same defect class in
    the download resume path). Pinned by recording the executing thread."""
    import threading

    _watcher_mod, service, _root = _make_watcher(monkeypatch, tmp_path)
    threads: list[tuple[str, bool]] = []
    loop_thread = threading.get_ident()

    class ThreadRecordingCore:
        def watch_start(self, roots, opts=None):
            threads.append(("start", threading.get_ident() == loop_thread))
            return 1

        def watch_poll(self, handle):
            # polling stays ON the loop by design (a mutex swap + a small JSON)
            threads.append(("poll", threading.get_ident() == loop_thread))
            return json.dumps({"paths": [], "rescan": False, "degraded": None})

        def watch_stop(self, handle):
            threads.append(("stop", threading.get_ident() == loop_thread))

    monkeypatch.setattr(service, "_core", lambda: ThreadRecordingCore())
    await service._tick()
    await service.stop()

    kinds = dict(threads)
    assert kinds.get("start") is False, "watch_start must run in an executor"
    assert kinds.get("stop") is False, "watch_stop must run in an executor"
    assert kinds.get("poll") is True, "watch_poll is cheap and stays on the loop"


def _native_available() -> bool:
    native = import_ext("native")
    native._module = None
    native._reason = None
    native._attempted = False
    tag = native.platform_tag()
    if tag is None or not (REPO_ROOT / "native" / "native-bin" / tag).is_dir():
        return False
    if not native.load():
        return False
    core = native.core()
    return all(hasattr(core, name) for name in ("watch_start", "watch_poll", "watch_stop"))


def test_mountinfo_body_is_cached_within_the_ttl(monkeypatch):
    """The watcher polls once a second and asks about every root; re-reading
    `/proc/self/mountinfo` per root per tick would be pointless syscall churn."""
    import time as time_mod

    watcher = _watcher_module()
    # a cached body is reused (the sentinel never matches a real mount)
    monkeypatch.setattr(watcher, "_mountinfo_cache", (time_mod.monotonic(), "SENTINEL"))
    assert watcher._linux_network_mount("/tmp") is None
    assert watcher._mountinfo_cache[1] == "SENTINEL", "an expired-free cache must not re-read"
    # an expired cache re-reads the real file
    monkeypatch.setattr(watcher, "_mountinfo_cache", (0.0, "SENTINEL"))
    assert watcher._linux_network_mount("/") is None
    assert watcher._mountinfo_cache[1] != "SENTINEL", "an expired cache must re-read"


def test_type_matcher_resolves_roots_once_and_matches_types_for_path(tmp_path):
    """`type_matcher` is the burst-friendly form of `types_for_path`."""
    watcher = _watcher_module()
    root = tmp_path / "models"
    (root / "loras").mkdir(parents=True)
    base_paths = {"loras": [str(root / "loras")], "checkpoints": [str(root / "loras"), ""]}
    match = watcher.type_matcher(base_paths)
    assert match(str(root / "loras" / "a.safetensors")) == ["loras", "checkpoints"]
    assert match(str(tmp_path / "elsewhere.safetensors")) == []
    assert watcher.types_for_path(str(root / "loras" / "a.safetensors"), base_paths) == [
        "loras",
        "checkpoints",
    ]


@pytest.mark.asyncio
async def test_setting_is_cached_for_the_ttl(tmp_path, monkeypatch):
    """The poll loop runs once a second while the feature is OFF by default, so
    the setting (a `comfy.settings.json` read) must not be re-read every tick."""
    watcher_mod, service, _root = _make_watcher(monkeypatch, tmp_path, enabled=False)
    reads = {"n": 0}

    def counting_read():
        reads["n"] += 1
        return False

    monkeypatch.setattr(watcher_mod, "is_enabled_setting", counting_read)
    monkeypatch.setattr(watcher_mod, "SETTING_TTL", 60.0)
    for _ in range(5):
        await service._tick()
    assert reads["n"] == 1, "five ticks inside the TTL read the setting once"
    assert service.diagnostics()["enabled"] is False

    # expiring the cache makes the next tick re-read (the switch is honoured
    # without a restart)
    service._setting_cache = None
    monkeypatch.setattr(watcher_mod, "is_enabled_setting", lambda: True)
    await service._tick()  # enabled now: it will try to arm (no native -> quiet)
    assert service.diagnostics()["enabled"] is True


@pytest.mark.asyncio
async def test_rescan_broadcast_honours_the_cooldown(prompt_server, tmp_path, monkeypatch):
    """A backend that keeps reporting `need_rescan` must not trigger a full
    library sweep once per second."""
    watcher_mod, service, _root = _make_watcher(monkeypatch, tmp_path)

    class AlwaysRescan:
        def watch_start(self, roots, opts=None):
            return 3

        def watch_poll(self, handle):
            return json.dumps({"paths": [], "rescan": True, "degraded": None})

        def watch_stop(self, handle):
            pass

    monkeypatch.setattr(service, "_core", lambda: AlwaysRescan())
    monkeypatch.setattr(watcher_mod, "TYPE_COOLDOWN", 60.0)
    for _ in range(5):
        await service._tick()
    events = [data for event, data, _sid in prompt_server.sent if event == "models_changed"]
    assert len(events) == 1, events
    assert events[0] == {"type": None, "reason": "fs-watch-rescan"}


@pytest.mark.asyncio
async def test_network_root_skip_is_logged_once(tmp_path, monkeypatch):
    """A permanently network-mounted root is reported once, not once a second."""
    watcher_mod, service, _root = _make_watcher(monkeypatch, tmp_path)
    utils = import_ext("utils")
    nas = tmp_path / "nas"
    nas.mkdir()
    monkeypatch.setattr(utils, "resolve_model_base_paths", lambda: {"loras": [str(nas)]})
    monkeypatch.setattr(watcher_mod, "network_mount_of", lambda path: "nfs on /nas")

    # The root selection is pure Python and must be testable without a built
    # native core, so the tick gets a stand-in that would arm if asked.
    class UnusedCore:
        def watch_start(self, roots, opts=None):
            raise AssertionError("a network-only library must not arm a session")

        def watch_poll(self, handle):
            return "{}"

        def watch_stop(self, handle):
            pass

    monkeypatch.setattr(service, "_core", lambda: UnusedCore())

    logged: list[str] = []
    monkeypatch.setattr(utils, "print_info", lambda msg, *a, **k: logged.append(str(msg)))
    for _ in range(4):
        await service._tick()
    skips = [line for line in logged if "skipping network root" in line]
    assert len(skips) == 1, skips
    assert service._handle is None, "no session is armed for a network-only library"
