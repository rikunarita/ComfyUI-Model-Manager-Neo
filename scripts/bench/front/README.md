# `scripts/bench/front/` — フロントエンド K15 計測器（Phase 6 / Plan §4.8‑C5）

Plan §2.2 の **K15**（検索 keystroke → 描画 ≤ 16 ms P95 / 初回グリッド描画 ≤ 1 s、
5,000 モデル）と、Phase 6 の C1–C5・テンソルツリー Rust 事前グループ化を
**ヘッドレスで継続計測**するための計測器です。結果は
[`docs/BENCH.md`](../../../docs/BENCH.md) §11 に記録され、
`scripts/bench/results/phase6_front.json` が証跡としてコミットされます。

## 設計原則（`scripts/bench/` 本体と同じ）

- **実コードを計測する**: リポジトリ同梱の `typescript`（`node_modules/.bin/tsc`）で
  `src/utils/modelFilter.ts` / `src/utils/tensorTree.ts` / `src/utils/perf.ts` を
  コンパイルし、**ブラウザが実行するのと同じモジュール**を import して駆動する。
  計測用に書き換えた複製は計測しない。
- **before 側は逐語コピー**: Phase 6 以前の `DialogManager.vue` の `list` computed
  （`naiveBuildRows`）と `ModelInformation.vue` の `tensorTree` computed
  （`legacyTensorTree`）を計測器内にインライン化してある。どちらも
  「同じ行を描画すること」を毎回検証してから計測する
  （`rowsAreIdentical` ゲート — 加速のために表示が変わっていないことの証明）。
- **ゲートは同一実行内の比率**: 共有 CI ランナーの絶対値は信頼できないため、
  `passed` は before/after の比率と parity のみで決まる。絶対値（K15 の 16 ms
  予算を含む）は `env` ブロック付きで記録し、判定は Plan §2.2 の参照機で行う。
- **ネットワーク不使用・決定論的**: 合成ライブラリはシード固定
  （5,050 エントリ = 5,000 モデル + 50 フォルダ）、MoE ヘッダは
  DeepSeek‑V3 形の命名で 84 layers × 256 experts = 65,268 テンソル。

## 実行

```bash
pnpm install --frozen-lockfile     # tsc が必要（node_modules/typescript）
node scripts/bench/front/k15.mjs   # → scripts/bench/results/phase6_front.json

# Rust 符号 == TypeScript フォールバック エンコーダの同一性まで検証するには
# python3 とビルド済み mm_core（scripts/build-native.sh）が必要:
node scripts/bench/front/k15.mjs --cross-check

# CI セル相当の縮小実行（native.yml integration と同一パラメータ）:
MMNEO_TSC=/path/to/node_modules/typescript/bin/tsc \
  node scripts/bench/front/k15.mjs --cross-check \
  --models 1500 --keystrokes 40 --moe-layers 12 --moe-experts 8 \
  --json-out /tmp/phase6_front_crosscheck.json
```

| オプション                       | 既定                                      | 意味                                                                |
| -------------------------------- | ----------------------------------------- | ------------------------------------------------------------------- |
| `--models`                       | 5000                                      | 合成ライブラリのモデル数（+1 % のフォルダ エントリ）                |
| `--keystrokes`                   | 200                                       | keystroke 相当のクエリ数（P95/P99 の母数）                          |
| `--columns`                      | 6                                         | グリッド列数（`chunk` の行幅）                                      |
| `--moe-layers` / `--moe-experts` | 84 / 256                                  | MoE ヘッダの形（65,268 テンソル）                                   |
| `--cross-check`                  | off                                       | `cross_check.py` 経由で Rust の実ビルド成果物と JS エンコーダを比較 |
| `--json-out`                     | `scripts/bench/results/phase6_front.json` | 証跡 JSON の出力先                                                  |
| `MMNEO_TSC`（環境変数）          | `node_modules/typescript/bin/tsc`         | tsc のパス（pnpm ストア外の CI セル用）                             |

終了コードは **ゲート判定**（0 = PASS）。CI（`ci.yml` の
`Frontend K15 bench (C5)`、`native.yml` integration の
`Tensor-tree wire cross-check`）が push ごとに実行します。

## 計測項目

| 出力キー                                     | 内容                                                                      |
| -------------------------------------------- | ------------------------------------------------------------------------- |
| `grid.keystrokeNaive`                        | Phase 6 以前のフィルタ+ソート+chunk（トークン正規表現をモデル毎に再構築） |
| `grid.keystrokeHoisted`                      | **出荷経路**（C1 ホイスティング + 共有 comparator）                       |
| `grid.keystrokeHoistedLocaleSort`            | C1 のみ（comparator をインライン化して C2 の効果を分離）                  |
| `grid.initialRender*`                        | クエリ無しの初回グリッド行構築                                            |
| `grid.numeric*` / `grid.default*`            | **C2 の根拠**: `{numeric:true}` 付き / 既定 の各 comparator 実装比較      |
| `tensorTree.legacyFold`                      | Phase 6 以前のブラウザ内 fold（87,195 ノードを materialize + 全 sort）    |
| `tensorTree.indexCreate` / `renderCollapsed` | Rust payload → 遅延インデックス → 折りたたみ行描画                        |
| `tensorTree.fallbackPath`                    | legacy backend 時の JS エンコーダ経路                                     |
| `tensorTree.parity` / `crossCheck`           | 構造 parity と Rust↔JS の wire 同一性                                     |
| `gates`                                      | 上記から導出した合否（`passed` が CI の判定）                             |

ブラウザ実機での paint 脚（K15 の残り半分 = DOM 反映とフレーム）は
`src/utils/perf.ts` が担当します。設定 **UI → パフォーマンスマーク**（既定 OFF）
またはコンソールで `__mmNeoPerf.enable()` を実行し、`__mmNeoPerf.summary()` で
`mm.grid.queryToPaint` / `mm.grid.keystrokeToPaint` / `mm.grid.initialRender` /
`mm.info.tensorTree` / `mm.info.tensorRows` の P50/P95/P99 を読みます。
