"""Root pytest guard — keep the ComfyUI entry point out of test collection.

This repository IS a ComfyUI extension: the `__init__.py` at the root is the
runtime entry point (it pip-installs requirements, downloads the web
distribution and registers aiohttp routes via relative `.py` imports). It is
NOT a Python package for testing.

pytest >= 8 collects every directory containing an `__init__.py` as a
`Package` node and IMPORTS that `__init__.py` during setup — which would
execute the extension entry point (and die on `from .py import ...`: pytest
imports it as a top-level module named `__init__`, so the relative import has
no parent package).

The primary defence is `tests/pytest.ini`, which moves rootdir/confcutdir to
`tests/` so the repository root never enters the collector chain (use
`python -m pytest tests`). This conftest is the fallback for invocations whose
rootdir IS the repository root (e.g. a bare `python -m pytest`): the ancestor
Package node for the root is created through a hook proxy that excludes this
conftest (it is keyed by the directory's PARENT), but node-level hooks like
`pytest_collectstart` do see it — so the root Package's `setup()` (the only
step that imports `__init__.py`) is neutralised here, per node, leaving
collection otherwise untouched.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def pytest_collectstart(collector) -> None:
    if type(collector).__name__ == "Package" and Path(collector.path).resolve() == _ROOT:
        # Treat the repository root as a plain Dir: no __init__.py import,
        # no setup_module/teardown_module discovery (there is none to run).
        collector.setup = lambda: None  # type: ignore[method-assign]
