# `scripts/pgo/` — PGO トレーニング / 計測ドライバ（NEO‑PLAN‑2026‑002）

`mm_core`（Rust ネイティブコア）の **PGO（プロファイル誘導最適化）** 用
ワークロードドライバです。設計と段階計画は [`Agent/Plan-2.md`](../../Agent/Plan-2.md)、
運営記録は [`Agent/MEMO.md`](../../Agent/MEMO.md) を参照してください。

## `train.py` — 3 モード

| モード        | 用途                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| （既定）train | 計装ビルド（`-Cprofile-generate`）された `mm_core` を決定論的合成フィクスチャで全 API 表面にわたり駆動し、`.profraw` を生成する                                                                                                                                                                                                                                                                                                                                                        |
| `--bench-one` | 1 ワークロードのタイム計測（`--measure` のサブプロセス。単独実行も可）                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `--measure`   | A/B スループット計測: 2 つのコア（`--a` = baseline、`--b` = PGO）を交互にサブプロセス実行（steal ゲート + 再計測 = BENCH 準拠）。**判定統計は側別中央値**（min = 最悪窓 / best = 干渉ゼロ上限は参考並記）— min 判定は round 0 冷間効果と短時間窓の二峰分散で 2 run 連続のアーティファクトを生んだため run #109 以降は中央値（run #107/#108 の教訓・BENCH §13.1/§13.6）。JSON には **ラウンド別生サンプル（`roundsA`/`roundsB`）**と 3 統計（`ratio`/`ratioMed`/`ratioBest`）が含まれる |

**依存は stdlib + `mm_core` + `tests/harness`（字节級 safetensors ライタ）のみ** —
pip 依存ゼロなので、maturin `--pgo` の一時 venv でも任意のランナーでもそのまま
動きます。全フィクスチャはシード固定（ネットワーク・時刻・乱数非依存）で、
プロファイル形状がビルド毎に再現されます。

### トレーニングがカバーするホットパス

圧縮/解凍ジョブ往復（bf16 low-entropy + random / f32 / f16 / fp8、SHA‑256
往復検証付き）・paranoid モード・デルタ圧縮/解凍（sidecar 検証込み）・
scan_models 冷/暖（永続インデックス）・scan_hygiene・walk_models・
move_with_sidecars・hash_file 5 表記・インクリメンタル hasher・
safetensors_header + tensor_tree（MoE 形 1,200 テンソル ×20）・
WebP 静止 + アニメの encode/decode ×10。

**重み付け（run #107 の G1 実測後に改訂）**: PGO の重みは実行カウントに
比例するため、codec 秒級に対して 2 パスしかなかった scan 系を
冷×5（毎回インデックス削除 = 本番の初回スキャン経路）+ 暖×20
（インデックスヒット = リフレッシュ経路）、hygiene/walk を ×5 へ
増量した（Plan‑2 R7 緩和）。

### 環境変数（サイズノブ）

| 変数            | 既定 | 内容                             |
| --------------- | ---- | -------------------------------- |
| `TRAIN_MB`      | 32   | 圧縮フィクスチャのサイズ MB      |
| `TRAIN_MODELS`  | 800  | スキャン合成ライブラリのモデル数 |
| `TRAIN_HASH_MB` | 128  | ハッシュ対象ファイルのサイズ MB  |
| `TRAIN_ROUNDS`  | 2    | 圧縮/解凍の反復回数              |

### 使い方（ローカル）

```bash
# 1. 計装ビルド（ホストネイティブ。--target で build script を計装から除外）
cd native
RUSTFLAGS="-Cprofile-generate=/tmp/pgo-prof" \
  cargo build --release -p mm-core --target x86_64-unknown-linux-gnu
mkdir -p /tmp/pgo-inst
cp target/x86_64-unknown-linux-gnu/release/libmm_core.so /tmp/pgo-inst/mm_core.abi3.so

# 2. トレーニング（profraw 生成）
cd ..
LLVM_PROFILE_FILE="/tmp/pgo-prof/default_%m.profraw" \
  python3 scripts/pgo/train.py --lib-dir /tmp/pgo-inst

# 3. マージ（llvm-profdata は rustup component add llvm-tools-preview）
LLVM_BIN="$(rustc --print sysroot)/lib/rustlib/x86_64-unknown-linux-gnu/bin"
"$LLVM_BIN/llvm-profdata" merge -o /tmp/pgo-prof/merged.profdata /tmp/pgo-prof

# 4. 出荷ビルド（zigbuild 経路。G2 = scripts/pgo/g2_check.py の 4 条件 —
#    missing 比率 < 50 % + Total count > 0 + 関数数/znn_codec プローブ）
scripts/build-native.sh --target linux-x86_64 --size-gate --pgo /tmp/pgo-prof/merged.profdata

# 5. 効果計測（A/B 交互・steal ゲート・側別中央値判定 — min/best 並記）
python3 scripts/pgo/train.py --measure \
  --a <baseline の mm_core があるディレクトリ> \
  --b native/native-bin/linux-x86_64 \
  --rounds 5 --json-out /tmp/pgo-measure.json
```

CI では **出荷ビルド自体が PGO 化されています**（`native-build-linux` の
三段階 + `--pgo-train` の Windows。macOS universal2 は計装 fat dylib の
終了時 SIGSEGV 実証により非 PGO〔Plan‑2 §4.4 判断 (c)〕、linux-aarch64 は
クロスコンパイルのため対象外〔§4.5〕）。
プロファイルの no-op 化は **`g2_check.py`（恒久 G2 ゲート）**が毎ビルドで
機械検出します（しきい値は run #106 の実測で再校正 — fat-LTO + PGO
インライナの良性乖離 13.81 % は通過、真の no-op ~100 % は失敗。
判定根拠は同スクリプトの docstring）。A/B 効果レポートは
**`pgo-measure`** ジョブ（workflow_dispatch または HEAD コミットメッセージの
`[pgo-measure]` マーカーで起動）が上記 1–5 を一括実行し、G1（compress /
decompress +3 %）を job summary へ出力します。

## プロファイルの方針

- **ビルド毎生成・コミットしない** — ソースとの版本ズレ（ドリフト）と
  リポジトリ肥大を構造的にゼロにする（Plan‑2 §4.6）。
- **同一 arch / OS のプロファイルのみ使用** — linux-aarch64 はクロス
  コンパイルかつ ARM ランナーが無いため PGO 対象外（x86_64 プロファイルの
  流用は禁止。Plan‑2 §4.5）。
- macOS / Windows は maturin の `--pgo`（`native/pyproject.toml` の
  `pgo-command` がこの train.py を呼ぶ）でランナー内で完結する。
