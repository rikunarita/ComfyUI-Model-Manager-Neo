#!/usr/bin/env bash
# Full KPI baseline suite (Agent/Plan.md §6.2 Phase 0 -> docs/BENCH.md).
#
# Re-runnable on ANY machine — the Plan's KPI reference hardware is an
# "8C/16T desktop (NVMe)" + a network-storage configuration; the first run
# (2026-09-23) executed in a 2 vCPU / 1 GiB container, which the result
# JSONs record under "env". Numbers in docs/BENCH.md must always be read
# together with that env block.
#
# Usage:
#   FIXTURES=/tmp/mm-bench REAL_MODEL=/path/to/model.safetensors \
#   SIZES_MB="32 96 192" PAIR_MB=32 HASH_MB=256 LIB_MODELS=5000 \
#       ./scripts/bench/run_all.sh
#
# Requirements: python3 with numpy, safetensors, torch (CPU is fine),
# blake3 (optional, adds BLAKE3 to the hash pass), and — for the JSON parser
# bench — a rust toolchain (skipped gracefully when absent).
# No network access is used; REAL_MODEL must be a local file (the 2026-09-23
# run used unsloth/all-MiniLM-L6-v2 model.safetensors from ModelScope).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
FIXTURES="${FIXTURES:-/tmp/mm-bench}"
RESULTS="$HERE/results"
SIZES_MB="${SIZES_MB:-32 96 192}"
PAIR_MB="${PAIR_MB:-32}"
HASH_MB="${HASH_MB:-256}"
LIB_MODELS="${LIB_MODELS:-5000}"
NEO_SYNTH_MB="${NEO_SYNTH_MB:-64}"
REAL_MODEL="${REAL_MODEL:-}"

read -r -a SIZES <<< "$SIZES_MB"
MAX_MB="${SIZES[-1]}"

mkdir -p "$FIXTURES/raw" "$RESULTS"

echo "== fixtures =="
python3 "$HERE/gen_synthetic.py" \
  --moe-header "$FIXTURES/moe-header.safetensors" --header-mb 8 \
  --raw-dtype bf16 f32 f16 fp8e4m3 --raw-size-mb "$MAX_MB" --out-dir "$FIXTURES/raw" >/dev/null
python3 "$HERE/gen_synthetic.py" --library "$FIXTURES/library" --library-models "$LIB_MODELS" >/dev/null
python3 "$HERE/gen_synthetic.py" --pair "$FIXTURES/pair-base-${PAIR_MB}mb.safetensors" \
  "$FIXTURES/pair-ft-${PAIR_MB}mb.safetensors" --pair-size-mb "$PAIR_MB" >/dev/null
echo "fixtures ready in $FIXTURES"

MODEL_ARGS=()
if [[ -n "$REAL_MODEL" && -f "$REAL_MODEL" ]]; then
  MODEL_ARGS=(--model "$REAL_MODEL")
else
  echo "note: REAL_MODEL not set/missing — e2e runs on the synthetic model only"
fi

echo "== bench_zipnn (K1/K2/K3/K5/K13) =="
python3 "$HERE/bench_zipnn.py" --fixtures "$FIXTURES" \
  --sizes-mb "${SIZES[@]}" --neo-synthetic-mb "$NEO_SYNTH_MB" \
  "${MODEL_ARGS[@]}" --json-out "$RESULTS/zipnn.json"

echo "== bench_native_e2e (Phase 2 K1/K2/K3/K13 — native vs legacy, same session) =="
if [[ -f "$REPO_ROOT/native/native-bin/linux-x86_64/mm_core.abi3.so" ]] \
  || [[ -f "$REPO_ROOT/native/native-bin/macos-universal2/mm_core.abi3.so" ]] \
  || [[ -f "$REPO_ROOT/native/native-bin/windows-x86_64/mm_core.pyd" ]]; then
  python3 "$HERE/bench_native_e2e.py" --fixtures "$FIXTURES" \
    --size-mb "$NEO_SYNTH_MB" --rounds 3 \
    "${MODEL_ARGS[@]}" \
    --json-out "$RESULTS/native_e2e.json"
else
  echo "native binary not built — skipping bench_native_e2e (scripts/build-native.sh)"
fi

echo "== bench_delta (K4 + K5 production-path reachability) =="
python3 "$HERE/bench_delta.py" --fixtures "$FIXTURES" --pair-mb "$PAIR_MB" \
  --json-out "$RESULTS/delta.json"

echo "== bench_scan (K9/K10) =="
python3 "$HERE/bench_scan.py" --library "$FIXTURES/library" --repeat 3 \
  --json-out "$RESULTS/scan.json"

echo "== bench_header (K11/K12) =="
python3 "$HERE/bench_header.py" --model "$FIXTURES/moe-header.safetensors" --repeat 7 \
  --json-out "$RESULTS/header.json"

echo "== bench_hash (K7/K8) =="
python3 "$HERE/bench_hash.py" --fixtures "$FIXTURES" --size-mb "$HASH_MB" \
  --json-out "$RESULTS/hash.json"

echo "== json-bench (parser decision) =="
if command -v cargo >/dev/null 2>&1; then
  (cd "$REPO_ROOT/native" && cargo build --release -p json-bench)
  "$REPO_ROOT/native/target/release/json-bench" "$FIXTURES/moe-header.safetensors.json" \
    | tee "$RESULTS/json-bench.txt"
else
  echo "cargo not available — skipping json-bench"
fi

echo "== done: results in $RESULTS =="
