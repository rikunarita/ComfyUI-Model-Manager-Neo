#!/usr/bin/env bash
# Build the distributable mm_core native artifacts (Agent/Plan.md §3.3, §4.2.1).
#
#   scripts/build-native.sh --target <tag> [--size-gate]
#
# Targets (= native/native-bin/ layout):
#   linux-x86_64      cargo zigbuild x86_64-unknown-linux-gnu.<glibc floor>   -> mm_core.abi3.so
#   linux-aarch64     cargo zigbuild aarch64-unknown-linux-gnu.<glibc floor>  -> mm_core.abi3.so
#   macos-universal2  maturin universal2 (macOS host only: cargo + lipo)      -> mm_core.abi3.so
#   windows-x86_64    maturin MSVC (Windows host only)                        -> mm_core.pyd
#
# Why these routes (Plan §3.3): Linux crosses pin the glibc floor via
# cargo-zigbuild (wider coverage than the legacy C prebuilds' glibc >= 2.34);
# macOS/Windows are built ON their OS with maturin — cross-linking a PyO3
# extension for Apple targets from Linux does not work with zig: pyo3-build-config
# emits `-undefined dynamic_lookup` (and rustc the exported-symbols list) as
# argument shapes zig cc mistranslates (verified 2026-09-23 with zig 0.15/0.16).
#
# Host requirements:
#   linux    rustup stable, pip: cargo-zigbuild + ziglang (+ maturin for wheels)
#   macos    rustup stable (+ both darwin targets), pip: maturin, Xcode CLT (lipo)
#   windows  rustup stable (MSVC toolchain), pip: maturin, bash (git-bash)
#
# The committed repo needs none of this at runtime: py/native.py only reads
# native-bin/ (no compiler, no pip, no network).
set -euo pipefail

GLIBC_FLOOR="${MM_GLIBC_FLOOR:-2.28}" # Plan §3.3: Debian 10 / Ubuntu 20.04+
SIZE_BUDGET=$((4 * 1024 * 1024))      # Plan §3.3/R6: <= 4 MB per binary

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Windows (git-bash) runners may only provide `python`, not `python3`.
PYTHON="$(command -v python3 || command -v python)"
[[ -n "$PYTHON" ]] || { echo "python3/python is required" >&2; exit 1; }
NATIVE_DIR="$REPO_ROOT/native"
BIN_ROOT="$NATIVE_DIR/native-bin"

# Stamp the artifact with the exact commit it is built from (mm-core's
# build.rs picks MM_CORE_COMMIT up and re-runs when it changes — a bare
# `git rev-parse` inside build.rs would go stale on warm incremental builds,
# because new commits on the same branch do not touch .git/HEAD).
MM_CORE_COMMIT="${MM_CORE_COMMIT:-$(git -C "$REPO_ROOT" rev-parse --short=9 HEAD 2>/dev/null || echo dev)}"
export MM_CORE_COMMIT

TARGET=""
SIZE_GATE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --size-gate) SIZE_GATE=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$TARGET" ]] || { echo "usage: build-native.sh --target <tag> [--size-gate]" >&2; exit 2; }

log() { printf '== %s\n' "$*"; }

# Extract the extension module out of a maturin wheel (zip) without unzip(1):
# python3 is a hard dependency of this project anyway.
extract_from_wheel() {
  local wheel="$1" suffix="$2" dst="$3"
  "$PYTHON" - "$wheel" "$suffix" "$dst" <<'PY'
import sys, zipfile
wheel, suffix, dst = sys.argv[1], sys.argv[2], sys.argv[3]
with zipfile.ZipFile(wheel) as zf:
    names = [n for n in zf.namelist() if n.endswith(suffix) and "/" in n]
    if len(names) != 1:
        sys.exit(f"expected exactly one *{suffix} in {wheel}, found: {names}")
    with zf.open(names[0]) as src, open(dst, "wb") as out:
        out.write(src.read())
print(f"extracted {names[0]} -> {dst}")
PY
}

finish() {
  local dst="$1"
  [[ -f "$dst" ]] || { echo "artifact missing: $dst" >&2; exit 1; }
  local size sha
  size=$(wc -c < "$dst" | tr -d ' ')
  sha=$("$PYTHON" -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$dst")
  log "artifact: $dst"
  log "size:     $size bytes"
  log "sha256:   $sha"
  if [[ "$SIZE_GATE" -eq 1 ]]; then
    if [[ "$size" -gt "$SIZE_BUDGET" ]]; then
      echo "SIZE BUDGET EXCEEDED: $size > $SIZE_BUDGET bytes ($dst)" >&2
      exit 1
    fi
    log "size gate: OK (<= $SIZE_BUDGET bytes)"
  fi
}

build_linux() {
  local arch="$1"
  local triple="${arch}-unknown-linux-gnu.${GLIBC_FLOOR}"
  log "cargo zigbuild --release --target $triple -p mm-core"
  (cd "$NATIVE_DIR" && cargo zigbuild --release --target "$triple" -p mm-core)
  local out_dir="$BIN_ROOT/linux-${arch}"
  mkdir -p "$out_dir"
  cp "$NATIVE_DIR/target/${arch}-unknown-linux-gnu/release/libmm_core.so" "$out_dir/mm_core.abi3.so"
  finish "$out_dir/mm_core.abi3.so"
}

build_macos_universal2() {
  [[ "$(uname -s)" == "Darwin" ]] || {
    echo "macos-universal2 must be built on macOS (cargo + lipo via maturin; see header)" >&2
    exit 1
  }
  rustup target add aarch64-apple-darwin x86_64-apple-darwin >/dev/null 2>&1 || true
  log "maturin build --release --target universal2-apple-darwin"
  (cd "$NATIVE_DIR" && maturin build --release --target universal2-apple-darwin --out target/wheels)
  local wheel
  wheel="$(ls -t "$NATIVE_DIR"/target/wheels/mm_core-*-cp310-abi3-*universal2.whl | head -1)"
  local out_dir="$BIN_ROOT/macos-universal2"
  mkdir -p "$out_dir"
  extract_from_wheel "$wheel" ".abi3.so" "$out_dir/mm_core.abi3.so"
  lipo -info "$out_dir/mm_core.abi3.so" || true
  finish "$out_dir/mm_core.abi3.so"
}

build_windows() {
  local os_name
  os_name="$(uname -s)"
  case "$os_name" in
    CYGWIN*|MINGW*|MSYS*|Windows_NT) ;;
    *) echo "windows-x86_64 (MSVC) must be built on Windows (see header)" >&2; exit 1 ;;
  esac
  log "maturin build --release (MSVC)"
  (cd "$NATIVE_DIR" && maturin build --release --out target/wheels)
  local wheel
  wheel="$(ls -t "$NATIVE_DIR"/target/wheels/mm_core-*-cp310-abi3-win_amd64.whl | head -1)"
  local out_dir="$BIN_ROOT/windows-x86_64"
  mkdir -p "$out_dir"
  # NOTE: mm_core.pyd, NOT mm_core.abi3.pyd — Windows CPython only recognises
  # the plain `.pyd` suffix in EXTENSION_SUFFIXES (Plan §4.2.1 adjusted).
  extract_from_wheel "$wheel" ".pyd" "$out_dir/mm_core.pyd"
  finish "$out_dir/mm_core.pyd"
}

case "$TARGET" in
  linux-x86_64) build_linux x86_64 ;;
  linux-aarch64) build_linux aarch64 ;;
  macos-universal2) build_macos_universal2 ;;
  windows-x86_64) build_windows ;;
  *) echo "unknown target tag: $TARGET (linux-x86_64|linux-aarch64|macos-universal2|windows-x86_64)" >&2; exit 2 ;;
esac
