# Offline ZipNN wheels (optional)

PyPI ships **no Linux wheels** for `zipnn` — `pip install zipnn` compiles its C
extension from the sdist, which needs a C compiler and the Python headers.
On air-gapped or toolchain-less hosts, drop a prebuilt wheel here:

```
assets/zipnn-wheels/zipnn-0.5.4-cp311-cp311-linux_x86_64.whl
```

The on-demand installer prefers wheels in this directory over PyPI (newest
filename wins). Build one on a similar machine with:

```bash
pip wheel zipnn --no-deps -w assets/zipnn-wheels/
```

Wheels themselves are git-ignored (`*.whl`); only this README is tracked.

Before reaching for a wheel, note the installer also self-heals one very common
failure on its own: when the compiler CPython recorded at build time (e.g.
Gentoo's `x86_64-pc-linux-gnu-gcc`) is not installed but *some* usable
`cc`/`gcc`/`clang` exists (even outside a stripped-down `PATH`), every build
attempt runs with `CC` pointed at the substitute. Check the ComfyUI console for
a `note: the compiler this Python expects (...) was not found; building with
CC=...` line to see whether that happened.
