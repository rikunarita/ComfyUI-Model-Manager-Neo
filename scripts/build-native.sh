#!/usr/bin/env bash
# Build the distributable mm_core native artifacts.
#
#   scripts/build-native.sh --target <tag> [--size-gate] [--pgo <profdata> | --pgo-train]
#
# PGO:
#   --pgo <profdata>  linux targets only: link the SHIPPED artifact against a
#                     pre-merged LLVM profile (instrumented build + training
#                     are orchestrated by the caller — see the pgo-measure job
#                     in .github/workflows/native.yml and scripts/pgo/README.md).
#                     Adds -Cllvm-args=-pgo-warn-missing-function so a stale /
#                     mismatched profile shows up as countable warnings (the
#                     CI asserts their ratio, gate G2).
#   --pgo-train       macOS / Windows only: hand `--pgo` to maturin, which
#                     runs its three-phase flow (instrumented wheel into a
#                     temporary venv -> [tool.maturin] pgo-command training ->
#                     optimized rebuild).
#
# Targets (= native/native-bin/ layout):
#   linux-x86_64      cargo zigbuild x86_64-unknown-linux-gnu.<glibc floor>   -> mm_core.abi3.so
#   linux-aarch64     cargo zigbuild aarch64-unknown-linux-gnu.<glibc floor>  -> mm_core.abi3.so
#   macos-universal2  maturin universal2 (macOS host only: cargo + lipo)      -> mm_core.abi3.so
#   windows-x86_64    maturin MSVC (Windows host only)                        -> mm_core.pyd
#
# abi3t targets (`<tag>t` = the four tags above with
# a `t` suffix: linux-x86_64t / linux-aarch64t / macos-universal2t /
# windows-x86_64t): the free-threaded Stable ABI flavour (PEP 803, pyo3
# `abi3t-py315` via mm-core's `ft` feature). Built NON-PGO with the
# EXCLUSIVE feature set `--no-default-features --features [extension-module,]ft`
# (never together with stable-abi — combining them makes the produced flavour
# host-dependent). Requires a Python >= 3.15 HOST interpreter (PyO3 host >=
# target; CI pins 3.15.0-rc.2 until the 3.15 final lands in the runner
# manifest). Outputs: mm_core.abi3t.so (POSIX) / mm_core.pyd
# (Windows — PEP 803 keeps the plain suffix); loadable by BOTH the
# free-threaded and the GIL build of CPython 3.15+.
#
# Why these routes: Linux crosses pin the glibc floor via
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
#   <tag>t   additionally: Python >= 3.15 on PATH (GIL build is fine — the
#            abi3t flavour is selected by the `ft` Cargo feature, and PyO3
#            only requires host >= target)
#
# The committed repo needs none of this at runtime: py/native.py only reads
# native-bin/ (no compiler, no pip, no network).
set -euo pipefail

GLIBC_FLOOR="${MM_GLIBC_FLOOR:-2.28}" # Debian 10 / Ubuntu 20.04+
SIZE_BUDGET=$((5 * 1024 * 1024))      # <= 5 MB per binary (guideline)

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
PGO_PROFDATA=""
PGO_TRAIN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --size-gate) SIZE_GATE=1; shift ;;
    --pgo) PGO_PROFDATA="$2"; shift 2 ;;
    --pgo-train) PGO_TRAIN=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$TARGET" ]] || { echo "usage: build-native.sh --target <tag> [--size-gate] [--pgo <profdata> | --pgo-train]" >&2; exit 2; }
[[ -z "$PGO_PROFDATA" || "$PGO_TRAIN" -eq 0 ]] || { echo "--pgo and --pgo-train are mutually exclusive" >&2; exit 2; }
# The abi3t (<tag>t) targets build NON-PGO — the LLVM profile runtime is
# unvalidated on free-threaded hosts, and the GIL-side PGO pipeline stays
# exactly as it is.
if [[ -n "$PGO_PROFDATA" ]]; then
  case "$TARGET" in
    linux-x86_64 | linux-aarch64) [[ -f "$PGO_PROFDATA" ]] || { echo "profile not found: $PGO_PROFDATA" >&2; exit 2; } ;;
    *) echo "--pgo <profdata> is linux-GIL-only (macOS/Windows GIL use --pgo-train via maturin; <tag>t targets are non-PGO)" >&2; exit 2 ;;
  esac
fi
if [[ "$PGO_TRAIN" -eq 1 ]]; then
  case "$TARGET" in
    macos-universal2 | windows-x86_64) ;;
    *) echo "--pgo-train is macOS/Windows-GIL-only (linux uses --pgo <profdata>; <tag>t targets are non-PGO)" >&2; exit 2 ;;
  esac
fi

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
  # Per-binary size budget. Callers pass a doubled budget for
  # the macOS universal2 FAT binary (two architecture slices — see
  # build_macos_universal2, which gates each thinned slice at the single-binary
  # budget); every other target is one architecture and uses the default.
  local budget="${2:-$SIZE_BUDGET}"
  [[ -f "$dst" ]] || { echo "artifact missing: $dst" >&2; exit 1; }
  local size sha
  size=$(wc -c < "$dst" | tr -d ' ')
  sha=$("$PYTHON" -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$dst")
  log "artifact: $dst"
  log "size:     $size bytes"
  log "sha256:   $sha"
  if [[ "$SIZE_GATE" -eq 1 ]]; then
    if [[ "$size" -gt "$budget" ]]; then
      echo "SIZE BUDGET EXCEEDED: $size > $budget bytes ($dst)" >&2
      exit 1
    fi
    log "size gate: OK (<= $budget bytes)"
  fi
}

build_linux() {
  local arch="$1" flavour="${2:-abi3}"
  local triple="${arch}-unknown-linux-gnu.${GLIBC_FLOOR}"
  local out_name="mm_core.abi3.so" tag_suffix=""
  local -a feat=()
  if [[ "$flavour" == "ft" ]]; then
    # abi3t (PEP 803) — EXCLUSIVE feature set: never together with stable-abi
    # (host-dependent flavour). Host python must be >= 3.15.
    out_name="mm_core.abi3t.so"
    tag_suffix="t"
    feat=(--no-default-features --features extension-module,ft)
    log "flavour: abi3t (ft feature; non-PGO; host Python >= 3.15 required)"
  fi
  local -a pgo_env=()
  if [[ -n "$PGO_PROFDATA" ]]; then
    log "PGO: -Cprofile-use=$PGO_PROFDATA (+ warn-missing-function for the G2 gate)"
    pgo_env=(env "RUSTFLAGS=-Cprofile-use=$PGO_PROFDATA -Cllvm-args=-pgo-warn-missing-function")
  fi
  # ${feat[*]+...} — bash 3.2 (macOS /bin/bash) treats an EMPTY array as
  # unbound under `set -u`; the +-guard is the same idiom as the invocation
  # below (verified against bash 3.2.57 + 5.2).
  log "cargo zigbuild --release --target $triple -p mm-core ${feat[*]+"${feat[*]}"}"
  (cd "$NATIVE_DIR" && "${pgo_env[@]+"${pgo_env[@]}"}" cargo zigbuild --release --target "$triple" -p mm-core ${feat[@]+"${feat[@]}"})
  local out_dir="$BIN_ROOT/linux-${arch}${tag_suffix}"
  mkdir -p "$out_dir"
  cp "$NATIVE_DIR/target/${arch}-unknown-linux-gnu/release/libmm_core.so" "$out_dir/$out_name"
  finish "$out_dir/$out_name"
}

build_macos_universal2() {
  local flavour="${1:-abi3}"
  [[ "$(uname -s)" == "Darwin" ]] || {
    echo "macos-universal2[t] must be built on macOS (cargo + lipo via maturin; see header)" >&2
    exit 1
  }
  rustup target add aarch64-apple-darwin x86_64-apple-darwin >/dev/null 2>&1 || true
  local out_name="mm_core.abi3.so" tag="macos-universal2"
  local wheel_glob="mm_core-*-cp312-abi3-*universal2.whl" extract_suffix=".abi3.so"
  local -a pgo_flag=() feat=()
  [[ "$PGO_TRAIN" -eq 1 ]] && pgo_flag=(--pgo) && log "PGO: maturin --pgo (pgo-command trains in a temporary venv)"
  if [[ "$flavour" == "ft" ]]; then
    # abi3t (PEP 803), non-PGO. tool.maturin's features already
    # carry pyo3/extension-module, so the CLI only adds `ft` and drops the
    # default (stable-abi) — the two stable-ABI flavours stay exclusive.
    out_name="mm_core.abi3t.so"
    tag="macos-universal2t"
    wheel_glob="mm_core-*-cp315*abi3t*universal2.whl"
    extract_suffix=".abi3t.so"
    feat=(--no-default-features --features ft)
    log "flavour: abi3t (ft feature; non-PGO; host Python >= 3.15 required)"
  fi
  # ${feat[*]+...} — bash 3.2 empty-array guard (see build_linux).
  log "maturin build --release --target universal2-apple-darwin ${feat[*]+"${feat[*]}"}"
  (cd "$NATIVE_DIR" && maturin build --release --target universal2-apple-darwin --out target/wheels ${pgo_flag[@]+"${pgo_flag[@]}"} ${feat[@]+"${feat[@]}"})
  local wheel
  wheel="$(ls -t "$NATIVE_DIR"/target/wheels/$wheel_glob | head -1)"
  local out_dir="$BIN_ROOT/$tag"
  mkdir -p "$out_dir"
  extract_from_wheel "$wheel" "$extract_suffix" "$out_dir/$out_name"
  lipo -info "$out_dir/$out_name" || true
  # universal2 is a FAT binary (x86_64 + arm64). The "<= 5 MB per
  # binary" budget is PER-ARCHITECTURE, so gate each thinned slice at
  # SIZE_BUDGET; the fat file itself is naturally ~2x and is checked against a
  # doubled budget in finish() (the whole native-bin set still has to fit the
  # size-budget CI job's total — the 40 MB guideline).
  if [[ "$SIZE_GATE" -eq 1 ]]; then
    local arch slice ssz
    for arch in x86_64 arm64; do
      slice="$out_dir/.slice-$arch"
      lipo "$out_dir/$out_name" -thin "$arch" -output "$slice" 2>/dev/null || continue
      ssz=$(wc -c < "$slice" | tr -d ' ')
      rm -f "$slice"
      if [[ "$ssz" -gt "$SIZE_BUDGET" ]]; then
        echo "SIZE BUDGET EXCEEDED ($arch slice): $ssz > $SIZE_BUDGET bytes" >&2
        exit 1
      fi
      log "size gate ($arch slice): OK ($ssz <= $SIZE_BUDGET bytes)"
    done
  fi
  finish "$out_dir/$out_name" $((SIZE_BUDGET * 2))
}

build_windows() {
  local flavour="${1:-abi3}"
  local os_name
  os_name="$(uname -s)"
  case "$os_name" in
    CYGWIN*|MINGW*|MSYS*|Windows_NT) ;;
    *) echo "windows-x86_64[t] (MSVC) must be built on Windows (see header)" >&2; exit 1 ;;
  esac
  local tag="windows-x86_64" wheel_glob="mm_core-*-cp312-abi3-win_amd64.whl"
  local -a pgo_flag=() feat=()
  [[ "$PGO_TRAIN" -eq 1 ]] && pgo_flag=(--pgo) && log "PGO: maturin --pgo (pgo-command trains in a temporary venv)"
  if [[ "$flavour" == "ft" ]]; then
    # abi3t (PEP 803), non-PGO. PEP 803 keeps the plain `.pyd`
    # name on Windows — the GIL and t artifacts are separated by their
    # native-bin/<tag> directories, never by filename.
    tag="windows-x86_64t"
    wheel_glob="mm_core-*-cp315*abi3t*win_amd64.whl"
    feat=(--no-default-features --features ft)
    log "flavour: abi3t (ft feature; non-PGO; host Python >= 3.15 required)"
  fi
  # ${feat[*]+...} — bash 3.2 empty-array guard (see build_linux).
  log "maturin build --release (MSVC) ${feat[*]+"${feat[*]}"}"
  (cd "$NATIVE_DIR" && maturin build --release --out target/wheels ${pgo_flag[@]+"${pgo_flag[@]}"} ${feat[@]+"${feat[@]}"})
  local wheel
  wheel="$(ls -t "$NATIVE_DIR"/target/wheels/$wheel_glob | head -1)"
  local out_dir="$BIN_ROOT/$tag"
  mkdir -p "$out_dir"
  # NOTE: mm_core.pyd, NOT mm_core.abi3.pyd — Windows CPython only recognises
  # the plain `.pyd` suffix in EXTENSION_SUFFIXES (PEP 803 keeps the same
  # rule for abi3t).
  extract_from_wheel "$wheel" ".pyd" "$out_dir/mm_core.pyd"
  finish "$out_dir/mm_core.pyd"
}

case "$TARGET" in
  linux-x86_64) build_linux x86_64 ;;
  linux-aarch64) build_linux aarch64 ;;
  linux-x86_64t) build_linux x86_64 ft ;;
  linux-aarch64t) build_linux aarch64 ft ;;
  macos-universal2) build_macos_universal2 ;;
  macos-universal2t) build_macos_universal2 ft ;;
  windows-x86_64) build_windows ;;
  windows-x86_64t) build_windows ft ;;
  *) echo "unknown target tag: $TARGET (linux-x86_64|linux-aarch64|macos-universal2|windows-x86_64, each also with a 't' suffix for the abi3t flavour)" >&2; exit 2 ;;
esac
