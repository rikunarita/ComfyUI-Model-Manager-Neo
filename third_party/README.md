# `third_party/` — vendored ZipNN

This directory vendors the **[ZipNN](https://github.com/zipnn/zipnn)** lossless
compression library (version **0.5.4**) so the extension's ZipNN feature works
out of the box, with **no `pip install`, no network access and — on the common
platforms — no C compiler**.

PyPI ships no Linux wheels for `zipnn` (only a macOS‑arm64 wheel plus an sdist
that compiles a C extension), so a plain `pip install zipnn` forces a source
build that fails on any host without a C compiler and the Python headers. To
avoid that entirely, the whole library is bundled here.

## Layout

```
third_party/
├─ zipnn/                     # the ZipNN 0.5.4 pure-Python package (importable as `zipnn`)
│  ├─ __init__.py  zipnn.py  util_header.py  util_patch.py
│  └─ util_safetensors.py  util_torch.py
├─ zipnn-core-bin/            # PREBUILT `zipnn_core` C-extension binaries
│  └─ linux-x86_64/
│     ├─ zipnn_core.cpython-310-x86_64-linux-gnu.so
│     ├─ zipnn_core.cpython-311-x86_64-linux-gnu.so
│     ├─ zipnn_core.cpython-312-x86_64-linux-gnu.so
│     └─ zipnn_core.cpython-313-x86_64-linux-gnu.so
├─ zipnn-core/                # C sources, used ONLY to build on platforms with
│  ├─ csrc/                   #   no prebuilt binary (macOS / Windows / other arch)
│  ├─ include/FiniteStateEntropy/lib/
│  ├─ setup.py  pyproject.toml
├─ LICENSE-zipnn.txt                   # ZipNN — MIT
└─ LICENSE-FiniteStateEntropy.txt      # FiniteStateEntropy — BSD-2-Clause OR GPL-2.0
```

## How it is used (see `py/compress.py`)

`ensure_zipnn()` puts `third_party/` and `third_party/zipnn-core-bin/<platform>/`
on `sys.path`. Python's import machinery then loads the `zipnn_core.cpython-3XX`
binary that matches the running interpreter, and `import zipnn` resolves to the
vendored package. That is the whole "install" on Linux x86_64 — nothing is
compiled or downloaded.

Only when no prebuilt binary matches the platform/Python (macOS, Windows, an
uncommon architecture, or a brand-new CPython) does `ensure_zipnn()` fall back to
a **single** clean build from `zipnn-core/`:

```bash
pip install --no-build-isolation --no-deps third_party/zipnn-core
```

There is no cascade of pip strategies and nothing is fetched from PyPI — the
sources are right here. That build needs a C compiler and the Python headers.

The only runtime dependencies of the vendored package are `numpy`, `safetensors`
and `torch`, all of which ComfyUI already provides.

## Prebuilt binary compatibility

The Linux binaries are built against the CPython limited-set of stable C-API
symbols and link only `libc.so.6`; they require **glibc ≥ 2.34** (Debian 12+,
Ubuntu 22.04+, RHEL 9+, Fedora 34+, Arch, Gentoo). On an older glibc the
prebuilt core will not load and `ensure_zipnn()` transparently falls back to the
source build.

## Rebuilding / adding prebuilt binaries

To (re)build the `zipnn_core` binaries for Linux x86_64 (run on a glibc‑2.34+
host with the matching Python headers, one per Python version):

```bash
cd third_party/zipnn-core
gcc -O3 -fPIC -shared \
    -Iinclude/FiniteStateEntropy/lib/ -Icsrc/ -I<python-include-dir> \
    csrc/zipnn_core_module.c csrc/zipnn_core.c \
    csrc/data_manipulation_dtype16.c csrc/data_manipulation_dtype32.c \
    include/FiniteStateEntropy/lib/{fse_compress,fse_decompress,huf_compress,huf_decompress,entropy_common,hist}.c \
    -o ../zipnn-core-bin/linux-x86_64/zipnn_core.cpython-3XX-x86_64-linux-gnu.so \
    -lpthread
strip --strip-unneeded ../zipnn-core-bin/linux-x86_64/zipnn_core.cpython-3XX-x86_64-linux-gnu.so
```

Binaries for other platforms (e.g. `macos-arm64/`, `windows-x86_64/`) can be
added the same way; until then those platforms use the source build.

## Licenses & attribution

- **ZipNN** (© IBM and the ZipNN contributors) is licensed under the **MIT**
  License — see [`LICENSE-zipnn.txt`](LICENSE-zipnn.txt). Upstream:
  https://github.com/zipnn/zipnn
- **FiniteStateEntropy** (© Yann Collet / Facebook) is dual-licensed under the
  **BSD-2-Clause** license and the **GPL-2.0**; it is used here under the
  permissive BSD terms — see
  [`LICENSE-FiniteStateEntropy.txt`](LICENSE-FiniteStateEntropy.txt). Upstream:
  https://github.com/Cyan4973/FiniteStateEntropy

Both licenses are compatible with this project's GPL‑3.0. The sources are
vendored verbatim from ZipNN 0.5.4 (the `zipnn-core/setup.py` build script is a
local adaptation that points at the in-tree FiniteStateEntropy copy instead of a
git submodule).
