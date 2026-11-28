# `scripts/bench/` — 計測証跡アーカイブ + フロントエンド計測器（CI ゲート）

刷新計画の KPI 計測に使われた Python ハーネス
（`bench_*.py`・`gen_synthetic.py`・`common.py`・`run_all.sh`）と golden differential（旧 `scripts/l2` 系）は、計画の完了に伴いツリーから削除されました。
原文は git 履歴から復元できます。このディレクトリに残るのは次の 2 つです。

## `results/` — コミットされた計測証跡（再生成しない）

[`docs/BENCH.md`](../../docs/BENCH.md) が数値を逐語引用する一次ソースの
JSON 一式です。各 JSON の `env` ブロックに計測環境（CPU・RAM・スレッド数）が
記録されています。**再生成せず、決定的な欄のみ外科的に追記する**のが規程です。

- `zipnn.json` / `delta.json` / `c_defects.json` / `scan.json` / `header.json` /
  `hash.json` / `json-bench.txt` — 初回計測 ベースライン（2026-09-23）
- `native_e2e.json` / `native_delta.json` — safetensors パイプライン/3 の native vs legacy 比較
- `dtypes.json` / `scan_models.json` / `hashing.json` / `safetensors_header.json` — 拡張帯 dtype・スキャン/ハッシュの受入メトリクス証跡
- `front_render.json` — フロントエンド表示最適化の計測（`front/render-bench.mjs` の出力）
- `golden_diff.json` / `golden_speed.json` — 移行期 golden differential ゲート（フル 10,500 ケース
  GATE PASS・圧縮出力 C バイト同一 9,880/9,880）の証跡。旧 `scripts/l2 differential/results/`
  から移設

## `front/` — フロントエンド計測器（現役・CI ゲート）

[`front/render-bench.mjs`](front/render-bench.mjs)（詳細は [`front/README.md`](front/README.md)）は
`src/utils` の実コードを tsc でコンパイルし、合成ライブラリ上で before/after を
同一実行内に計測するヘッドレス計測器です。ゲートは同一実行内比率なので
ランナー非依存です。

- `ci.yml` が毎 push で実行（`node scripts/bench/front/render-bench.mjs`）
- `native.yml` の integration（ubuntu）が `--cross-check` 付きで実行し、
  Rust テンソルツリー符号 == TypeScript フォールバック エンコーダを
  実ビルド成果物 against で検証（`front/cross_check.py` 経由）

## 関連する現役ゲート（このディレクトリ外）

- `scripts/cross_validation/official_cross.py` — official interoperability gate 相互運用ゲート。公式 pip `zipnn` 0.5.4 との
  双方向クロス検証（`native.yml` integration・ubuntu セルが毎 push 実行）
- `scripts/build-native.sh` — 配布用プリビルド成果物のビルド（`native.yml`）
- `scripts/verify_native_binary.py` — 成果物の arch / glibc 下限 / libpython
  非依存の検査（純 Python・手動 QA 用）
