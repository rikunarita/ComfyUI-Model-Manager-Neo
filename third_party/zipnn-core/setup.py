"""Build script for the vendored ``zipnn_core`` C extension.

This is a self-contained copy of the ZipNN core extension
(https://github.com/zipnn/zipnn, version 0.5.4) with the FiniteStateEntropy
sources vendored in-tree, so the build never needs ``git submodule update`` or
network access. It is used ONLY as the fallback for platforms without a
prebuilt binary in ``third_party/zipnn-core-bin/`` (see ``py/compress.py``):

    pip install --no-build-isolation --no-deps third_party/zipnn-core

The Python-side ``zipnn`` package is vendored separately under
``third_party/zipnn/`` and is not (re)installed here.
"""

import sys

from setuptools import Extension, setup

# Source list mirrors the upstream setup.py exactly (csrc + the FiniteStateEntropy
# objects the core links against). Paths are relative to this file's directory.
_FSE = "include/FiniteStateEntropy/lib"
_SOURCES = [
    "csrc/zipnn_core_module.c",
    "csrc/zipnn_core.c",
    "csrc/data_manipulation_dtype16.c",
    "csrc/data_manipulation_dtype32.c",
    f"{_FSE}/fse_compress.c",
    f"{_FSE}/fse_decompress.c",
    f"{_FSE}/huf_compress.c",
    f"{_FSE}/huf_decompress.c",
    f"{_FSE}/entropy_common.c",
    f"{_FSE}/hist.c",
]

# Optimization is nice-to-have; the flags must not break non-GCC/Clang compilers
# (MSVC on Windows rejects `-O3`). gcc >= 14 / clang >= 16 turn a few historical
# C patterns in the 0.5.4 sources into hard errors, so those specific diagnostics
# are relaxed here too - real errors stay loud.
_EXTRA_COMPILE_ARGS = []
if sys.platform != "win32":
    _EXTRA_COMPILE_ARGS = [
        "-O3",
        "-Wno-implicit-function-declaration",
        "-Wno-incompatible-pointer-types",
        "-Wno-int-conversion",
    ]

zipnn_core_extension = Extension(
    "zipnn_core",
    sources=_SOURCES,
    include_dirs=[f"{_FSE}/", "csrc/"],
    extra_compile_args=_EXTRA_COMPILE_ARGS,
)

setup(
    name="zipnn-core",
    version="0.5.4",
    description="Vendored ZipNN core C extension (zipnn_core)",
    ext_modules=[zipnn_core_extension],
    zip_safe=False,
)
