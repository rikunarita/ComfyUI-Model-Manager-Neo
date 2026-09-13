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
