"""Standalone smoke test for py/native.py against the built mm_core binary.

Run from the repo root (after `scripts/build-native.sh --target <host tag>`):

    python3 tests/_smoke_native.py

Also exercised properly (with isolation) in tests/test_phase0_native_loader.py.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import stubs

stubs.install()

os.environ.pop("MM_NATIVE", None)

from harness import REPO_ROOT, import_ext

native = import_ext("native")
config = import_ext("config")
assert config.extension_uri == str(REPO_ROOT), config.extension_uri

print("tag:", native.platform_tag())
ok = native.load()
print("load():", ok)
print("diagnostics:", native.diagnostics())
if not ok:
    print(f"SKIP-equivalent FAILURE: native core unavailable: {native.reason()}", file=sys.stderr)
    print("(build it first: scripts/build-native.sh --target <tag>)", file=sys.stderr)
    sys.exit(1)
core = native.core()
assert core is not None
print("api_version:", core.api_version())
print("core_version:", native.core_version())
assert core.api_version() == native.MIN_API_VERSION

os.environ["MM_NATIVE"] = "0"
import importlib

native = importlib.reload(native)
assert native.load() is False
assert "MM_NATIVE=0" in (native.reason() or ""), native.reason()
print("MM_NATIVE=0 path OK:", native.reason())
print("SMOKE OK")
