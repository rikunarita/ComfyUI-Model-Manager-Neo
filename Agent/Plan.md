# 開発計画・作業規程（NEO‑PLAN‑2026‑005）

| 項目           | 内容                                                                                                                                                                                                                                 |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 文書番号       | NEO‑PLAN‑2026‑005                                                                                                                                                                                                                    |
| 版数           | 1.0                                                                                                                                                                                                                                  |
| 作成日         | 2026‑11‑05                                                                                                                                                                                                                           |
| 対象リポジトリ | `rikunarita/ComfyUI-Model-Manager-Neo`                                                                                                                                                                                               |
| 対象ブランチ   | `dev`                                                                                                                                                                                                                                |
| 現行バージョン | v0.4.0（`api_version` 6 — 公開作業はユーザ専任）                                                                                                                                                                                     |
| 文書の位置づけ | **living document**。実装計画 NEO‑PLAN‑2026‑001〜004 の完了に伴い、以降の実装を進めやすくするための**作業規程**を定める。履歴・恒久規程の正は [`MEMO.md`](MEMO.md)、計測の一次ソースは [`../docs/BENCH.md`](../docs/BENCH.md) です。 |

> **完了済み計画の所在。** NEO‑PLAN‑2026‑001（Plan.md）・002（Plan‑2.md）・
> 003（Plan‑3.md）・004（Plan‑4.md）は全要件の完了に伴いツリーから削除済みで、
> 原文は git 履歴に完全な形で保存されています（復元 SHA は
> [`MEMO.md`](MEMO.md) 冒頭の「計画文書の保存場所」を参照）。
> 本書はそれらを置き換える**新しい作業規程**であり、実装フェーズの計画ではありません。

## 1. cargo 使用の最適化（開発効率）

### 1.1 原則

| 原則                                                    | 理由                                                                                                                              |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **開発中は `cargo check` を常用する**                   | 型・借用・未使用警告をコード生成なしで最速に検出できる。編集→check のループを最小コストで回す。                                   |
| **`cargo test` は必要なときだけ実行する**               | テストはビルド（リンク）+ 実行のコストが高い。対象を `-p` / テスト名フィルタで絞り、振る舞いを変えた時と push 前に限定する。      |
| **clippy / rustfmt はコード品質を高める場面で活用する** | 日常の check に同乗させ（clippy は型検査と同時に走る）、整形は編集直後と push 前に回す。品質ゲートは `-D warnings`（CI と同一）。 |
| **`cargo build` は最終確認のみ**                        | 配布成果物は `scripts/build-native.sh`（zigbuild / maturin + サイズゲート）が正。手元の `cargo build` は最終確認に限る。          |

### 1.2 コマンド早見表（`cd native` で実行）

| 目的                   | コマンド                                                                                        | 備考                                                                        |
| ---------------------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| 日常の型検査           | `cargo check --workspace --all-targets`                                                         | **常用**。`--all-targets` でテスト・example 側も型検査。                    |
| クレートを絞った型検査 | `cargo check -p znn-codec --all-targets`                                                        | 反復作業はこちらが速い。                                                    |
| 単体 + 統合テスト      | `cargo test -p znn-codec`                                                                       | 必要なときだけ。                                                            |
| 一部のテストだけ       | `cargo test -p znn-codec --lib <モジュール名>` / `cargo test -p znn-codec --test extended_band` | フィルタ実行を優先する。                                                    |
| mm‑core 単体テスト     | `cargo test -p mm-core --no-default-features`                                                   | `extension-module` を外す（libpython をリンクするため。開発ヘッダが必要）。 |
| 整形                   | `cargo fmt --all`（確認は `cargo fmt --all -- --check`）                                        | stable の既定オプションのみ（`rustfmt.toml`）。                             |
| Lint                   | `cargo clippy --workspace --all-targets --all-features -- -D warnings`                          | CI と同一条件。                                                             |
| 最終確認（ローカル）   | `cargo build --release -p mm-core`                                                              | 最終確認時のみ。                                                            |
| 配布成果物             | `scripts/build-native.sh --target <tag> --size-gate`                                            | サイズ予算ゲート込み。                                                      |
| pnpm ラッパー          | `pnpm rs:fmt` / `rs:fmt:check` / `rs:lint` / `rs:test` / `rs:build`                             | `package.json` の既存スクリプト（CI と同じコマンド）。                      |

> ツールチェーン前提: stable（`rustfmt` / `clippy` 同梱）。fuzz のみ nightly の
> 別ワークスペース（`crates/znn-codec/fuzz/`）。
> 詳細（feature 構成・abi3/abi3t・成果物ビルド）は
> [`../native/README.md`](../native/README.md) を参照してください。

### 1.3 `tests/` フォルダによるテスト管理

テストは**到達範囲で 3 層に分けて配置**し、`cargo test` の対象を常に把握できる状態に保ちます。

| 層                   | 配置                                                           | 用途                                                                                                        |
| -------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| 単体（private 可）   | `native/crates/znn-codec/src/*.rs` のインライン `#[cfg(test)]` | モジュール内部の不変条件・境界値。`delta` のみ `src/delta/tests.rs`。                                       |
| **統合（公開 API）** | **`native/crates/znn-codec/tests/`**                           | クレート外から見た端到端の契約（例: `extended_band.rs` = K14 ゲート）。新しい端到端テストはここへ追加する。 |
| 敵対的入力           | `native/crates/znn-codec/fuzz/`（nightly・別ワークスペース）   | libFuzzer ターゲット 7 種。CI: fuzz-smoke（push）+ fuzz-long（週次）。                                      |
| Python               | `tests/`（pytest）                                             | ルート契約・パイプライン・ルート/ws ゴールデン。成果物あり/なしの両方で実行する。                           |

- **新規テストの置き場所**: 公開 API の振る舞い = `tests/`（Rust 統合）、
  内部実装の不変条件 = インライン単体、敵対的入力 = `fuzz/`、Python 側 = `tests/`。
- **`tests/` を増やしたら `cargo test -p <crate> --test <name>` で単独実行**して
  から、push 前に全体を 1 回だけ回します（1.5 参照）。

### 1.4 開発環境ごとの注意（サンドボックスのスペックはセッションで変わる）

サンドボックスのスペックはセッションにより異なります（実測例: **2 vCPU / RAM 1 GiB**
のセッション [MEMO §2.1] と **16 vCPU / RAM 64 GiB** のセッション [2026‑11‑05 第 2]）。
小スペック環境では次を守ってください。

- **並列度**: clippy / test は `CARGO_BUILD_JOBS=1`、release LTO は `1–2`
  （リンク時のメモリ逼迫回避）。
- **長時間ビルドの切り離し**: ツール呼び出しのタイムアウトでプロセスグループごと
  落ちるため、`setsid` で切り離してバックグラウンド実行し、ログをポーリングする。
- **差分ビルド前提**: `native/target/` は削除しない（初回フルビルドが最も高コスト）。
- **`cargo build` の前に `cargo check`**: release LTO は失敗時のやり直しが高くつくため、
  まず check / clippy でエラーを潰す。

### 1.5 push 前チェックリスト（軽い → 重い）

1. `pnpm exec prettier --write <変更した md>` → `pnpm format:check`
2. `cd native && cargo fmt --all -- --check`（整形済みなら即時）
3. `cd native && cargo check --workspace --all-targets`（**必須の常設ゲート**）
4. `cd native && cargo clippy --workspace --all-targets --all-features -- -D warnings`
5. `python -m ruff check` / `ruff format --check` / `mypy`（`pyproject.toml` の設定）
6. `pnpm typecheck` / `pnpm lint` / `pnpm lint:css` / `pnpm deps` /
   `pnpm fallow:dead` / `pnpm fallow:dupes`
7. `pnpm build`（`web/` バンドル再生成。**`web/manager.js` を欠いたツリーは絶対にコミットしない**）
8. `cargo test`（**必要なとき** — 振る舞いの変更・push 前の全体確認）
   ＋ pytest を「native 成果物あり / なし」の両方で実行
9. 最終確認のみ `cargo build` / `scripts/build-native.sh`

## 2. 文書体系（どこに何を書くか）

| 文書                                       | 役割                                                                   |
| ------------------------------------------ | ---------------------------------------------------------------------- |
| **`Agent/Plan.md`（本書）**                | **これからの作業規程**（living）。cargo 使用最適化・文書体系・基準値。 |
| `Agent/MEMO.md`                            | 履歴・恒久規程・技術知見・残件の**正**。セッション毎の記録を追記する。 |
| `Agent/environment-report.md`              | サンドボックス環境の一次実測（再構築手順・環境の癖）。                 |
| `docs/BENCH.md`                            | 計測の一次ソース。**証跡 JSON は再生成しない**規程。                   |
| `README.md` / `README.{ja,zh-CN,zh-TW}.md` | ユーザ向け概要（4 言語で同期）。                                       |
| `docs/USAGE*.md`                           | ユーザ向け手順書（4 言語で同期）。                                     |
| `native/README.md`                         | Rust ワークスペースの詳細（レイアウト・テスト・ビルド・abi3/abi3t）。  |
| `SECURITY.md`                              | 脆弱性報告の手順と CI のセキュリティゲート。                           |

- セッション記録（何をしたか・検証結果・残件）は **MEMO.md に追記**します。
- 本書に記載する恒久ルールを変更する場合は、**MEMO.md §1.2（開発ワークフロー規程）と
  同一コミットで**更新してください（二重管理のドリフト防止）。

## 3. 現状の基準値（2026‑11‑05 時点）

| 項目           | 値                                                                                     |
| -------------- | -------------------------------------------------------------------------------------- |
| バージョン     | v0.4.0（`pyproject` / `package.json` / native workspace / web バンドルで同期）         |
| `api_version`  | 6（4 者同期: `py/native.py` / mm‑core / native.yml / pytest）                          |
| 成果物         | 8 本（abi3 ×4 + abi3t ×4・合計 34.98 MiB）。PGO 適用 = linux‑x86_64 / Windows GIL      |
| テスト         | Rust L1 206 + 統合 4 + mm‑core 5 / pytest 225（2026‑10‑03 実測 — MEMO §6）             |
| fuzz           | 7 ターゲット（週次 日曜 18:00 UTC）・L5 公式 zipnn クロス検証が恒久互換ゲート          |
| ツールチェーン | CI: Node 26.10.0 / pnpm 12.8.1 / ruff 0.17.2 / uv / Python 3.12・3.14・3.15（+ 3.15t） |

> 数値の更新は MEMO §6 と同時に行います（スナップショットの二重管理を避ける）。

## 4. 改訂履歴

| 版数 | 日付       | 変更概要                                                                                 |
| ---- | ---------- | ---------------------------------------------------------------------------------------- |
| 1.0  | 2026‑11‑05 | 初版。ユーザ指示（2026‑11‑05）による cargo 使用最適化・`tests/` 管理・文書体系の規程化。 |
