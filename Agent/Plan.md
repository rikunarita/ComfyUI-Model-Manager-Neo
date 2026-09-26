# ComfyUI‑Model‑Manager‑Neo 大幅刷新計画書

## ― Rust ネイティブコア化と ZipNN 完全置き換え ―

| 項目           | 内容                                                                                                                                                                                                                                                                                                                                                                            |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 文書番号       | NEO‑PLAN‑2026‑001                                                                                                                                                                                                                                                                                                                                                               |
| 版数           | 2.0                                                                                                                                                                                                                                                                                                                                                                             |
| 作成日         | 2026‑09‑22                                                                                                                                                                                                                                                                                                                                                                      |
| 対象リポジトリ | `rikunarita/ComfyUI-Model-Manager-Neo`                                                                                                                                                                                                                                                                                                                                          |
| 対象ブランチ   | `dev`                                                                                                                                                                                                                                                                                                                                                                           |
| 現行バージョン | v0.2.0（α3）                                                                                                                                                                                                                                                                                                                                                                    |
| 目標バージョン | v0.3.0                                                                                                                                                                                                                                                                                                                                                                          |
| 状態           | **Phase 0 完了・Phase 1 完了（2026‑09‑25、fuzz 15 h バジェット消化 — run 36148521214 全 5 ターゲット緑）・Phase 2 実装完了（2026‑09‑24、L4/L5 緑・K1/K6/K13 達成、K2/K3 は参照機再計測待ち — BENCH §7）・Phase 3 実装完了（2026‑09‑25、K4/K5 達成・L5 セクション D 緑・SEGFAULT クラス解消実証 — BENCH §8。2026‑09‑26 に独立監査で全ゲート再検証 + GIL 解放修正 — MEMO 同日）** |

### 版数履歴

| 版数 | 日付       | 変更概要                                                                                                                                                                                                                                                                     |
| ---- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.0  | 2026‑09‑22 | 初版。コードベース精読・技術調査・基本計画の策定                                                                                                                                                                                                                             |
| 2.0  | 2026‑09‑22 | 全面改訂。(1) C コアのメモリ欠陥を実機実証し重大度評価を追加、(2) データ完全性保証設計を新設、(3) 追加最適化 8 件を精査・反映、(4) mold / rustfmt / clippy をツールチェーン標準に採用、(5) crate 最新版の再検証（jiter・bincode 3 等）、(6) 事業計画書レベルの構成へ全面再編 |

### 進捗マーク凡例

| マーク  | 意味   |
| ------- | ------ |
| `- [x]` | 完了   |
| `- [/]` | 進行中 |
| `- [ ]` | 未着手 |

---

## エグゼクティブサマリー

本計画は、ComfyUI 用モデルマネージャー拡張「ComfyUI‑Model‑Manager‑Neo」の
中核処理を **Rust ネイティブコア（`mm_core`）へ移行**し、以下 4 点を実現するものである。

1. **信頼性の抜本改善（最優先）**
   現行の vendored ZipNN C コア（上流 0.5.4 と同一）に対し、本計画策定過程で
   **再現性のある SEGFAULT とヒープオーバーフロー（未定義動作）を実機実証した**
   （付録 C）。デルタ圧縮では特定のファイル長において ComfyUI プロセス全体が
   異常終了する。Rust への置き換えにより、この種のメモリ安全欠陥を
   **構造的に消滅**させ、さらに SHA‑256 による端到端の完全性検証を新たに導入する
   （現行には検証機構が一切存在しない）。
2. **メモリ効率の劇的改善（ゼロコピー化）**
   mmap とストリーミング処理により、圧縮時のピークメモリを
   「モデルサイズの約 2 倍」から **O(チャンク×スレッド数)（数百 MB 以下）** へ、
   デルタ圧縮を「約 4–5 倍」から **1 GB 未満**へ削減する。
   大容量モデルでの OOM・スワップを解消する。
3. **処理速度の改善**
   ZipNN 圧縮 ≥1.5 倍・解凍 ≥2 倍、ライブラリスキャン ≤2 秒（5,000 モデル・冷間）、
   safetensors ヘッダー解析 ≤40 ms（8 MB MoE ヘッダー）等を目標とする（§2.2 KPI 表）。
4. **配布・対応プラットフォームの拡充**
   CPython バージョン別 C 拡張 ×6 本（Linux x86_64 のみ）を、
   **abi3 単一バイナリ ×4 プラットフォーム**（Linux x86_64/aarch64・Windows x64・
   macOS universal2）へ置換する。Windows / macOS はコンパイラ不要の正式対応となる。

dtype 対応は現行 5 種（f32/f16/bf16/fp8×2）から **safetensors 0.8 / PyTorch 2.14 の
全 dtype（22 種以上）**へ拡張する。公式 ZipNN エコシステムとの相互運用性は
双方向クロス検証により CI で機械的に保証する。

実施は **Phase 0〜7 の 8 段階**（§6）で進め、各フェーズに定量の完了条件と
ロールバック手段を設ける。既存 C プリビルドは移行期の差分テスト
（ゴールデン検証）に活用したうえで最終フェーズで撤去する。

**主要数値サマリー**

| 指標                                 | 現行                         | 目標                           |
| ------------------------------------ | ---------------------------- | ------------------------------ |
| 圧縮ピークメモリ（12 GB モデル）     | 約 24 GB 超                  | **1 GB 未満**                  |
| デルタ圧縮ピークメモリ（12 GB ペア） | 約 50 GB 級                  | **1 GB 未満**                  |
| メモリ安全欠陥                       | SEGFAULT・UB を実証（付録C） | **構造的にゼロ**               |
| データ完全性検証                     | なし                         | **SHA‑256 端到端検証**         |
| スキャン（5,000 モデル・冷間）       | 5–20 秒                      | **2 秒以下**                   |
| 対応プラットフォーム                 | Linux x86_64（プリビルド）   | **4 プラットフォーム**         |
| CPython カバレッジ                   | 3.10–3.15（版別 .so ×6）     | **3.10 以降すべて（abi3 ×1）** |

---

## 目次

- [1. 背景と現状評価](#1-背景と現状評価)
- [2. 刷新方針](#2-刷新方針)
- [3. 技術選定](#3-技術選定)
- [4. システム設計](#4-システム設計)
- [5. 品質保証計画](#5-品質保証計画)
- [6. 実施計画](#6-実施計画)
- [7. リスク管理](#7-リスク管理)
- [8. ライセンスとコンプライアンス](#8-ライセンスとコンプライアンス)
- [9. 進捗サマリー](#9-進捗サマリー)
- [付録 A: 技術調査記録](#付録-a-技術調査記録)
- [付録 B: ZipNN バイトフォーマット仕様](#付録-b-zipnn-バイトフォーマット仕様)
- [付録 C: C コア欠陥の再現手順と実証結果](#付録-c-c-コア欠陥の再現手順と実証結果)
- [付録 D: 用語集](#付録-d-用語集)

---

# 1. 背景と現状評価

## 1.1 対象システムの概要

Neo は `hayden-cn/ComfyUI-Model-Manager` を全面刷新したフォーク
（GPL‑3.0‑only）であり、次の 3 層で構成される。

| 層             | 技術                                       | 規模                                                    |
| -------------- | ------------------------------------------ | ------------------------------------------------------- |
| フロントエンド | Vue 3.5 + Tailwind v4 + reka‑ui + Vite 8   | `src/` 約 5,000 行（hooks）+ 44 コンポーネント          |
| バックエンド   | Python（aiohttp ルート、asyncio タスク）   | `py/` 13 モジュール・約 7,300 行                        |
| 圧縮コア       | vendored ZipNN 0.5.4（Python 層 + C 拡張） | `third_party/` 約 4,000 行（C 含む）+ プリビルド .so ×6 |

主要機能は、モデルの閲覧・検索（HF/ModelScope/Civitai）・ダウンロード・
アップロード・メタデータ編集、および **ZipNN 可逆圧縮**
（単体・フォルダ一括・デルタ）である。

## 1.2 現行アーキテクチャの評価

### 1.2.1 良好な点（維持すべき資産）

- asyncio + 専用実行プール（IO 8 スレッド / CPU n÷2）の分離設計。
- WebSocket による進捗配信プロトコル（`update_zipnn_progress` /
  `zipnn_complete` / `update_download_task`）。
- フロントエンドの行単位仮想スクロール（`ResponseScroll.vue`）。
- 安全配慮（パス内包検査、`.tmp` + rename の原子入替、
  バンドルフォルダ不変条件 `*_DeltaZNN`）。
- 既存依存はすべて最新版近傍（§1.4 の監査結果）。

### 1.2.2 課題一覧（定量評価）

重要度順。**【重大】**は本計画の直接の引き金となった実証済みの欠陥である。

| #   | 重要度   | 領域   | 課題                                                                                                                                          | 該当箇所                                                                                        |
| --- | -------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 1   | **重大** | 信頼性 | C コアが `total % 256KB ∈ {1,2,3}` の入力で **SEGFAULT**（NULL 参照）。デルタ圧縮で到達可能 → ComfyUI プロセス全体が死亡                      | `handle_split_mode_220` 主ループ（付録 C）                                                      |
| 2   | **重大** | 信頼性 | 端数チャンクで **1–3 バイトのヒープオーバーフロー書き込み + 最大 3 バイトの境界外読み取り**（UB）。デルタ圧縮の約 75% が該当                  | 同上 + `split_bytearray_dtype16`                                                                |
| 3   | **重大** | 信頼性 | 圧縮前後の**完全性検証が皆無**。破損しても検知手段がない                                                                                      | `py/compress.py` 全般                                                                           |
| 4   | 高       | メモリ | 圧縮のピーク RAM ≈ モデルサイズ ×2 超（全テンソルを RAM dict に保持 + clone + bytearray コピー）                                              | `py/compress.py` L648–736                                                                       |
| 5   | 高       | メモリ | デルタ圧縮のピーク RAM ≈ ファイルサイズ ×4–5（両ファイル全文 `f.read()` + パディング + XOR コピー）                                           | `py/compress.py` L1043–1200                                                                     |
| 6   | 高       | 応答性 | `GET /model-manager/model/...`（モデル詳細）が **イベントループ上で同期実行**。MoE の巨大ヘッダー解析中、サーバー全体（WebSocket 含む）が停止 | `py/manager.py` L135–160（executor 未使用。scan/hygiene/update は修正済みだが本ルートのみ残存） |
| 7   | 中       | 保守   | vendored ZipNN のインストール層約 470 行（pip ビルド・コンパイラ探索・sys.path 注入）。CPython 新版ごとの .so 追加ビルド運用                  | `py/compress.py` L160–628                                                                       |
| 8   | 中       | 配布   | Windows / macOS にプリビルドなし（C コンパイラ必須のソースビルドにフォールバック）                                                            | `third_party/zipnn-core-bin/`                                                                   |
| 9   | 中       | 性能   | スキャンが GIL 下の ThreadPool(4) + 毎回全面走査。キャッシュはプロセス内のみで再起動消失                                                      | `py/manager.py` L329–465                                                                        |
| 10  | 中       | 性能   | safetensors ヘッダー解析が Python `json.loads`（8 MB MoE ヘッダーで数百 ms）。しかも課題 6 と連動                                             | `py/utils.py` L324–368                                                                          |
| 11  | 中       | 性能   | ダウンロード完了後に検証用フル再読込（10 GB で +30–60 秒）。ダウンロードチャンク 8 KB で Python ループ負荷สูง                                 | `py/download.py` L129–138, L529, L680                                                           |
| 12  | 低       | 性能   | 検索フィルタがモデル 1 件ごとに正規表現を再構築。ソートが `localeCompare`（国際化照合の低速パス）×4 箇所                                      | `DialogManager.vue` L176–177 ほか                                                               |
| 13  | 低       | 性能   | `models` ストアが深いリアクティブ（数千オブジェクトの Proxy 化）。`<img>` に `decoding="async"` 未指定                                        | `src/hooks/model.ts` L114, `ResponseImage.vue`                                                  |
| 14  | 低       | 機能   | 外部ツールで追加されたモデルの反映が 30 秒 TTL の再取得頼み（ファイル監視なし）                                                               | `src/hooks/model.ts` L136                                                                       |

## 1.3 ZipNN vendored スタックの構成（置き換え対象）

```
third_party/
├─ zipnn/                       # ZipNN 0.5.4 Python 層（MIT）: zipnn.py 1,643 行
├─ zipnn-core/                  # C ソース: zipnn_core.c 1,157 行、
│                               #   data_manipulation_dtype16.c 238 行、同 dtype32.c 474 行、
│                               #   FiniteStateEntropy（huf_compress/huf_decompress/fse_*/entropy_common/hist）
├─ zipnn-core-bin/linux-x86_64/ # プリビルド .so ×6（CPython 3.10–3.15、計 620 KB）
└─ LICENSE-*                    # ZipNN = MIT、FiniteStateEntropy = BSD-2-Clause OR GPL-2.0
```

調査で確認した重要事実:

- 上流 `zipnn/zipnn` の最新版は **0.5.4（2026‑04‑11）**であり、同梱版と同一世代。
  C ソースのファイルサイズは上流と完全一致（`data_manipulation_dtype32.c`
  14,573 B、`zipnn_core.c` 41,661 B）→ **課題 1・2 の欠陥は上流にも存在する**。
  （上流への issue 報告を推奨アクションとして §6 Phase 1 に記載）
- 上流の C コアは dtype16/dtype32 のみ。**f64・整数・complex の実装は
  上流に存在しない** → dtype 拡張（§4.6）は Neo が先行実装する。
- 上流 0.5.3 で FP8、0.5.4 でゼロコピー返却とリーク修正が入っており、
  同梱ソースはこれらの修正を含む。

## 1.4 既存依存の最新性監査（2026‑09‑22 確認）

| 依存                  | リポジトリの指定                                          | PyPI 最新 | 判定                    |
| --------------------- | --------------------------------------------------------- | --------- | ----------------------- |
| huggingface_hub       | `>=1.32.0`                                                | 1.32.0    | **最新**                |
| hf_xet                | `>=1.5.2,<2.0.0`                                          | 1.6.0     | 範囲内（最新可）        |
| modelscope_hub        | `>=0.4.3`                                                 | 0.4.5     | 範囲内（最新可）        |
| markdownify           | `>=0.14.0`                                                | 1.2.3     | 範囲内（最新可）        |
| safetensors（Python） | ComfyUI 同梱                                              | 0.8.0     | Rust crate 0.8.0 と同版 |
| フロントエンド        | Vue 3.5 / Vite 8 / TypeScript 6 / ESLint 10 / Tailwind v4 | —         | **すべて現行最新系**    |

結論: 既存の Python / フロントエンド依存は更新済みであり、
本計画での追加更新は不要（Rust 側の選定は §3）。

---

# 2. 刷新方針

## 2.1 基本方針

1. **安全性最優先**: メモリ安全欠陥の実証（付録 C）を踏まえ、
   データの完全性を最優先課題とする。圧縮・解凍の全経路に
   検証を織り込む（§4.4）。
2. **段階的移行**: 8 フェーズの段階進行。各フェーズに定量の完了条件と
   ロールバック手段（環境変数スイッチ `MM_NATIVE`）を設け、
   移行期は新旧両経路を CI で並行検証する。
3. **互換性の機械的保証**: ファイルフォーマット（`.znn.safetensors`・
   デルタ `.znn`）・HTTP ルート・WebSocket イベントは現行と完全互換を維持し、
   公式 ZipNN とのクロス検証を CI ゲート化する。
4. **ゼロコピー原則**: 大容量データは Python 境界を跨がせない。
   パスを渡し、Rust 内部で mmap/ストリーム処理する（§4.3）。
5. **配布の単純化**: コンパイル不要・ネットワーク不要・
   CPython バージョン非依存（abi3）。

## 2.2 定量目標（KPI）

すべて Phase 0 で記録する実測ベースラインに対する目標。
検証環境は「8C/16T デスクトップ（NVMe）」と「ネットワークストレージ」の 2 構成。
**KPI 未達のフェーズは完了としない。**

| #   | 指標                                  | 現行（見込み実測）           | 目標                                      |
| --- | ------------------------------------- | ---------------------------- | ----------------------------------------- |
| K1  | 圧縮ピーク RAM（12 GB bf16 モデル）   | 24 GB 超                     | **< 1 GB**                                |
| K2  | 圧縮スループット                      | ベースライン計測値           | **≥ 1.5 倍**                              |
| K3  | 解凍スループット                      | 同上                         | **≥ 2 倍**                                |
| K4  | デルタ圧縮ピーク RAM（12 GB ペア）    | 50 GB 級                     | **< 1 GB**                                |
| K5  | C コア既知欠陥（SEGFAULT/UB）         | 再現（付録 C）               | **全ケースでエラーまたは正常動作**        |
| K6  | データ完全性検証                      | なし                         | **圧縮後・解凍後の SHA‑256 端到端検証**   |
| K7  | ダウンロード検証の追加 I/O            | フル再読込（+30–60 s/10 GB） | **ゼロ**（インライン検証）                |
| K8  | ハッシュ 5 種 1 パス（10 GB）         | 60–90 秒                     | **≤ 15 秒**                               |
| K9  | スキャン 5,000 モデル（冷間・NVMe）   | 5–20 秒                      | **≤ 2 秒**                                |
| K10 | スキャン（暖間・差分）                | 全面再走査                   | **≤ 100 ms**                              |
| K11 | MoE ヘッダー解析（8 MB）              | 200–400 ms                   | **≤ 40 ms**                               |
| K12 | モデル詳細ルートのイベントループ阻塞  | 解析時間分ブロック           | **ゼロ**（executor + Rust 化）            |
| K13 | 起動時 ZipNN 可用性                   | プリビルド or C ビルド       | **import のみ（< 50 ms・全 OS）**         |
| K14 | 対応 dtype 数                         | 5 種                         | **safetensors 0.8 全 22 種 + torch 拡張** |
| K15 | 検索 keystroke → 描画（5,000 モデル） | 計測して記録                 | **≤ 16 ms（P95）**                        |
| K16 | プリビルドバイナリ                    | Linux x86_64 のみ・版別 ×6   | **4 プラットフォーム・abi3 ×1**           |

## 2.3 適用範囲

**対象（In scope）**

- ZipNN 圧縮/解凍/デルタ/バッチの実処理（C → Rust）
- ライブラリスキャン・衛生スキャン・永続インデックス
- safetensors ヘッダー解析（メタデータ・テンソルツリー）
- ハッシュ計算（SHA256/AutoV1/AutoV2/CRC32/BLAKE3）とダウンロード検証
- モデル詳細ルートの非阻塞化ほか §1.2.2 の課題 6・11〜14
- プリビルドバイナリ配布基盤（native-bin/）と CI

**対象外（Out of scope）— 理由付き**

| 対象外項目                           | 理由                                                                                     |
| ------------------------------------ | ---------------------------------------------------------------------------------------- |
| ネットワーク層の Rust 化             | `hf_xet` は既に Rust。ボトルネックはネットワークであり投資対効果が低くリスクが高い       |
| UI フレームワーク変更                | Vue 3 + reka‑ui は現行最新系で刷新済み                                                   |
| GGUF / CKPT(pickle) の圧縮           | 容器が異なる。GGUF は量子化済みで需要が薄い（将来候補として記録のみ）                    |
| 非可逆圧縮・GPU 圧縮                 | 可逆性の保証（本計画の最優先事項）と競合                                                 |
| プレビューの WebP エンコード Rust 化 | 純 Rust のロッシー WebP エンコーダが不在（§3.8）。PIL 経路はメモ化済みで実測上の問題なし |
| `zipnn` PyPI への依存復活            | vendoring も pip も行わない（配布方針 §2.1‑5）                                           |

## 2.4 設計原則

1. Rust コードは `unsafe` を最小化し、clippy を `-D warnings` でゲート化（§3.4）。
2. 長時間処理はすべて GIL 解放 + 協調キャンセル + アトミック進捗。
3. ファイル変更は「一時ファイル → fsync → rename（+ ディレクトリ fsync）」。
   原本の削除は検証成功後のみ。
4. フォーマットは公式 ZipNN 0.5.4 と双方向互換。Neo 拡張は
   専用コード帯とメタデータマーカーで明示的に分離（§4.6）。
5. インデックス等の派生データは常に再構築可能に設計し、破損時は自動再生成。
6. 既存の HTTP ルート・WebSocket イベント名・ペイロード形状は不変
   （フロントエンド無改修での切り替えを可能にする）。

---

# 3. 技術選定

> 本章のバージョン・日付はすべて 2026‑09‑22 に一次ソース
> （crates.io API / docs.rs / PyPI / GitHub / 公式ドキュメント）で確認した。
> 詳細な出典一覧は付録 A。

## 3.1 選定結果サマリー

| 領域                  | 採用                                                  | バージョン             | 不採用とした主要候補                                                                                    |
| --------------------- | ----------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------- |
| Python バインディング | **PyO3**（abi3）                                      | 0.29.2                 | uniffi / cffi+cbindgen / Cython / rust-cpython                                                          |
| ビルド・配布          | **maturin** + cargo-zigbuild                          | 1.15.0 / 0.23.4        | cibuildwheel+wheel 配布（clone 配布哲学に不適合）                                                       |
| リンカー              | **mold**（Linux）                                     | 2.42.1                 | rust-lld（Rust 1.90+ 既定。mold を明示採用する指示に基づく）                                            |
| フォーマッタ          | **rustfmt**                                           | Rust 1.98.1 同梱       | —（指示に基づく採用）                                                                                   |
| Linter                | **clippy**（`-D warnings`）                           | Rust 1.98.1 同梱       | —（指示に基づく採用）                                                                                   |
| 並列化                | **rayon**（専用プール）                               | 1.12.0                 | std::thread 手動管理 / tokio（CPU バウンドに不向き）                                                    |
| エントロピー符号      | **自社ポート `znn-codec`**                            | —                      | huff0 crate（2018 年死蔵）/ ruzstd（huff0 非公開）/ zstd C バインディング（C 依存残存）                 |
| safetensors I/O       | 読取: **memmap2 + 自前パーサ**、書込: **自前 Writer** | memmap2 0.9.11         | safetensors crate の serialize（キーをソートするため byte‑exact 復元に不適合）                          |
| JSON                  | **jiter**（第一候補）                                 | 0.17.0                 | simd-json 0.18.1（in‑place 変換を要し read‑only mmap と相性が悪い。Phase 0 で両者ベンチし確定）         |
| ハッシュ              | **sha2 / blake3 / crc32fast**                         | 0.11.0 / 1.8.7 / 1.5.2 | OpenSSL バインディング（C 依存）                                                                        |
| 並列ディレクトリ走査  | **ignore**（第一候補）                                | 0.4.33                 | jwalk 0.9.0（「Use dua-core instead」表記で事実上 maintenance）/ dua-core 4.1.0（Phase 5 でベンチ比較） |
| インデックス永続化    | **bincode** スナップショット（下記の注記参照）        | 2.0.1                  | rusqlite（SQLite = C のビルド混入）/ postcard 1.1.3（代替候補）                                         |
| ファイル監視（任意）  | **notify + notify-debouncer-full**                    | 8.2.0 / 0.7.0          | Python watchdog（GIL 下ポーリング）                                                                     |
| f16/bf16              | **half**                                              | 2.7.1                  | —                                                                                                       |
| YAML                  | **yaml-rust2**                                        | 0.13.0                 | serde_yaml（**deprecated 確認済み**）/ serde_yml（同）                                                  |

> 〔Phase 0 実装注記 2026‑09‑23・bincode〕 crates.io の `max_stable_version`
> は 3.0.0 だが、同リリースは **コンパイル不能なプレースホルダ**（lib.rs 全体が
> `compile_error!("https://xkcd.com/2347/")`、依存ゼロ — 依存混淆攻撃対策の
> スクワットガード。一次ソース: static.crates.io 配信の .crate 実展開で確認）。
> 実体の安定版は **2.0.1**（2025‑03‑10）。Phase 5 のインデックス実装は
> 2.0.1 を既定とし、postcard 1.1.3 を代替候補として再評価する。

## 3.2 Python バインディング: PyO3 0.29.2

2026‑09 時点で PyO3 に代わる成熟した選択肢は存在しないことを確認した
（累計 DL 2.56 億、2026‑08‑05 リリースの 0.29.2 が最新、Rust ≥1.83 要求、
現行 stable Rust 1.98.1 を満たす）。

- **abi3**: `abi3-py310` 〜 `abi3-py315`、自由スレッド向け `abi3t-py315` を
  サポート。本計画は **abi3-py310** を採用し、1 バイナリで CPython 3.10
  以降を将来にわたりカバーする（リポジトリの `requires-python >= 3.10` と整合）。
- **制約事項（確認済み）**: `PyBuffer`（buffer プロトコル）は Limited API では
  Py3.11+ 限定。本設計は大容量バッファを境界で渡さないため影響なし（§4.3）。
  `PyBytes` / `PyByteArray` / 文字列 / 数値は Limited API で利用可。
- `pyo3-async-runtimes` 0.29.0（asyncio ブリッジ）は存在するが、
  既存の `run_in_executor` 方式で十分であり**第 1 版では採用しない**。

## 3.3 ビルド・配布: maturin + abi3 + cargo-zigbuild

- maturin 1.15.0（2026‑08‑27）。`maturin generate-ci github` で
  GH Actions ワークフローを生成、`maturin-action` でクロスビルド。
- Linux は **cargo-zigbuild 0.23.4** で glibc 2.28 ターゲット
  （Debian 10 / Ubuntu 20.04 以降）。現行 C プリビルドの要件
  （glibc ≥ 2.34）より広いカバレッジ。
- macOS は x86_64 + aarch64 をビルドし `lipo` で universal2 化。
  Windows は `x86_64-pc-windows-msvc`（`.pyd`）。
- パニック戦略は **`panic = "unwind"` 固定**（PyO3 が境界でパニックを捕捉し
  Python 例外化する。`abort` は ComfyUI プロセスを殺すため禁止）。
- サイズ予算: `opt-level`・`lto = "fat"`・`codegen-units = 1`・`strip` で
  **1 バイナリ ≤ 4 MB**、5 ファイル合計 ≤ 20 MB（Phase 0 で実測検証）。

## 3.4 ツールチェーン標準: mold / rustfmt / clippy（採用確定）

### 3.4.1 mold リンカー（v2.42.1、2026‑09‑11 リリース）

- **適用範囲**: Linux（ELF）のローカル開発ビルドと CI の native-test ジョブ。
  macOS（Mach‑O）と Windows（MSVC PE）は mold の対象外のため
  プラットフォーム既定リンカーを使用する（macOS: ld‑prime、Windows: link.exe）。
  なお Rust 1.90 以降、x86_64‑linux の既定は rust-lld であり、mold は
  それに対するさらなるリンク高速化として機能する。
- **設定**（リポジトリに `native/.cargo/config.toml` としてコミット）:

  ```toml
  # Linux ネイティブビルドのみ mold を使用する。
  # クロスビルド（zig 経由）では zig 側リンカー（LLD）が使用され、本設定は影響しない。
  [target.x86_64-unknown-linux-gnu]
  linker = "clang"
  rustflags = ["-C", "link-arg=-fuse-ld=mold"]

  [target.aarch64-unknown-linux-gnu]
  linker = "clang"
  rustflags = ["-C", "link-arg=-fuse-ld=mold"]
  ```

- **導入方法**: 開発環境・CI ともに `apt-get install mold`（Ubuntu 24.04 系）
  または公式リリースの事前ビルドバイナリを使用。clang が利用できない環境では
  `-C link-arg=-B<mold>/lib/mold` 方式にフォールバック（手順を
  `native/README.md` に記載）。
- maturin は内部で cargo を呼び出すため、上記設定はそのまま適用される。

### 3.4.2 rustfmt / clippy

- **rustfmt**: `native/rustfmt.toml` をコミット（edition 2024、
  その他は既定 + 安定オプションのみ。〔Phase 0 実装注記 2026‑09‑23〕
  `imports_granularity` / `group_imports` は Rust 1.98 時点でも **nightly 専用**
  のため不採用（stable の `cargo fmt --check` を正とする）。newline_style は
  Auto のまま `.gitattributes` の `*.rs text eol=lf` で LF を保証する —
  Windows ランナーの core.autocrlf による CRLF checkout が fmt ゲートを
  破壊するため（CI 実走で確認・修正済み）。
  `pnpm rs:fmt` / `pnpm rs:fmt:check` を package.json に追加
  （既存の `pnpm py:lint` 等と同じ命名作法）。
- **clippy**: `native/clippy.toml` に MSRV を設定。〔Phase 0 実装注記
  2026‑09‑23〕 PyO3 の MSRV は 1.83 だが edition 2024 が rustc ≥1.85 を
  要求するため、実効床は **`msrv = "1.85"`**（clippy.toml に理由付きで明記。
  低い値を二重指定すると clippy が不一致警告を出すため）。
  ワークスペースルートで `cargo clippy --all-targets --all-features -- -D warnings`
  を CI ゲート化。加えて crate 属性で `clippy::pedantic` を warn、
  選別した項目のみ deny（過度な警告による開発摩擦を避けるため allow リストを
  `native/crates/*/src/lib.rs` に明記）。
- `unsafe` は `unsafe_op_in_unsafe_fn` ほか unsafe 系 lint を deny とし、
  使用箇所は `// SAFETY:` コメントを必須とする（レビュー規則）。
- husky pre-commit には組み込まない（Rust ビルド時間のため）。CI で担保する。

## 3.5 並列化: rayon 1.12.0

- テンソル間・チャンク間・走査・ハッシュのデータ並列に使用。
- **ComfyUI プロセスとの共存**: グローバルプールを使わず
  `rayon::ThreadPoolBuilder` による専用プールを `pool.install()` で使用。
  既定スレッド数は上流 ZipNN と同じ `min(論理コア, 16)`、設定で変更可。
  「プロンプト実行中はスレッド数を半減する」オプションを新設
  （既存の『プロンプト実行中はダウンロードを停止』設定と同型の配慮）。
- ネスト並列（テンソル×チャンク）は rayon の分割統治に委ね、
  小テンソル・大テンソルの双方でコアを埋める。

## 3.6 圧縮コア: 純 Rust 自社ポート（`znn-codec`）

crates.io 全件調査の結果、ZipNN が要求する**生 huff0 ブロック**
（FiniteStateEntropy の `HUF_compress`/`HUF_decompress` 等価）を
提供する成熟 crate は存在しない:

| crate                            | 状態（2026‑09‑22 確認）                                    | 判定                     |
| -------------------------------- | ---------------------------------------------------------- | ------------------------ |
| `huff0` 0.1.0                    | 2018 年最終更新・DL 1,852                                  | 死蔵                     |
| `huffman-coding` 0.1.2           | 2017 年                                                    | 死蔵                     |
| `ruzstd` 0.9.0                   | 純 Rust zstd（RFC 8878）。huff0/FSE は非公開内部モジュール | 参照実装として活用       |
| `libzstd-bitexact-rs` 0.157      | 2026‑06 初版・BSD‑3・DL 918。C とビット完全一致志向        | 若すぎる。差分検証の参照 |
| `zstd` 0.14 / `zstd-safe` 8      | C バインディング（`HUF_*` 非公開）                         | C 依存が残るため不採用   |
| `oxiarc-zstd` / `zstdx` / `zrip` | 2026 年の新生純 Rust zstd。huff0 単体 API なし             | 監視                     |

よって **`znn-codec` crate を自社実装**する:

- 仕様準拠先: RFC 8878 §4.2（Huffman_Tree_Description、4X1/4X2 ストリーム）。
- 実装参照: 同梱 FiniteStateEntropy C ソース
  （**BSD‑2‑Clause OR GPL‑2.0** → BSD‑2 経路で GPL‑3.0‑only 配布に適合。§8）
  および `zipnn_core.c` のチャンク/レイアウト意味論（§4.5、付録 B）。
- 主要定数（同梱 `huf.h` で確認）: `HUF_BLOCKSIZE_MAX = 128 KB`、
  `HUF_TABLELOG_MAX = 12`、`HUF_TABLELOG_DEFAULT = 11`。
- 正当性の担保: 撤去前の C プリビルド .so をゴールデン生成器とした
  **双方向差分テスト + cargo-fuzz**（§5.1、付録 C の再現ケースを
  回帰テストに固定化）。

## 3.7 データ処理 crate（確定バージョン表）

| 用途               | crate                                    | バージョン                                               | 備考                                                                                           |
| ------------------ | ---------------------------------------- | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| safetensors 読取   | `memmap2` + 自前ヘッダーパーサ           | 0.9.11                                                   | ゼロコピー。32 MB ヘッダー上限ガード維持                                                       |
| JSON               | `jiter`（第一候補）/ `simd-json`（比較） | 0.17.0 / 0.18.1                                          | jiter は非破壊解析で read‑only mmap に直接適用可。Phase 0 で 8 MB MoE ヘッダーによりベンチ確定 |
| スキャン結果直列化 | `serde` + `serde_json`                   | 1.0.151                                                  | —                                                                                              |
| ハッシュ           | `sha2` / `blake3` / `crc32fast`          | 0.11.0 / 1.8.7 / 1.5.2                                   | blake3 は `rayon`・`mmap` フィーチャ使用（並列ツリーハッシュ）。sha2 は SHA‑NI 実行時検出      |
| 並列 walk          | `ignore`（第一候補）/ `dua-core`（比較） | 0.4.33 / 4.1.0                                           | Phase 5 でベンチ比較                                                                           |
| インデックス       | `bincode`（+ `blake3` チェックサム）     | 2.0.1（§3.1 注記: 3.0.0 はコンパイル不能プレースホルダ） | 純 Rust・原子入替スナップショット。SQLite（C）は不採用                                         |
| f16/bf16           | `half`                                   | 2.7.1                                                    | —                                                                                              |
| バイト cast        | `bytemuck`                               | 1.25.2                                                   | 平面分割の安全な reinterpret                                                                   |
| 監視（任意機能）   | `notify` + `notify-debouncer-full`       | 8.2.0 / 0.7.0                                            | デバウンスは公式クレートに委譲                                                                 |
| YAML               | `yaml-rust2`                             | 0.13.0                                                   | front‑matter 部分集合。serde_yaml 系は deprecated のため不使用                                 |
| 一時ファイル       | `tempfile`                               | 3.x                                                      | 原子入替                                                                                       |
| PyO3 拡張          | `pyo3`（abi3-py310, extension-module）   | 0.29.2                                                   | —                                                                                              |

## 3.8 周辺領域の選定結論（Rust 化しない判断を含む）

- **プレビュー WebP**: 純 Rust の**ロッシー** WebP エンコーダは成熟 crate が
  存在しないことを確認（`image` 0.25.10 の WebP は LOSSLESS のみ、
  `webp` 0.3.1 は libwebp の C バインディング、`webp-encode` は不在）。
  現行 PIL 経路は (mtime_ns, size) メモ化済みで実測上の問題がないため
  **PIL 維持**とする。将来の差し替えに備え `_encode_preview` の
  分離構造は維持する。
- **ネットワーク**: aiohttp / huggingface_hub / hf_xet / modelscope_hub を維持。
  ただし `search.py` / `information.py` / `identify.py` の
  **ブロッキング `requests.get`（executor 経由）は aiohttp へ統一**する
  （スレッドホップの除去・タイムアウト/プロキシ設定の一元化。§4.8‑B2）。

---

# 4. システム設計

## 4.1 全体アーキテクチャ

```
┌─────────────────────────── ComfyUI プロセス ───────────────────────────┐
│  フロントエンド（Vue 3、変更は Phase 6 のみ）                          │
│      ▲ HTTP / WebSocket（イベント名・ペイロード形状は現行互換）        │
│  Python バックエンド（py/、薄いアダプタ層へ縮退）                      │
│   ├─ compress.py   ルート・タスク台帳・ws 配信（実処理は mm_core へ）  │
│   ├─ manager.py    ルート（scan/info は mm_core へ）                   │
│   ├─ download.py   タスク管理（検証ハッシュのみ mm_core へ）           │
│   ├─ identify.py   逆引きフロー（ハッシュ計算は mm_core へ）           │
│   └─ native.py     ローダー: native-bin/<tag> → import mm_core         │
│      ▲ PyO3（abi3、GIL 解放、パス/JSON/アトミックのみ境界通過）        │
│  Rust ネイティブコア native/crates/                                    │
│   ├─ mm-core     PyO3 拡張（ジョブ管理・進捗・キャンセル・監視）      │
│   └─ znn-codec   純 Rust ZipNN（ヘッダー/平面/huff0・FSE/delta/        │
│                  safetensors I/O/スキャン/ハッシュ、Python 非依存）    │
└────────────────────────────────────────────────────────────────────────┘
         ▲ 移行期のみ: MM_NATIVE=0 で third_party 旧経路にフォールバック
```

## 4.2 ネイティブコア `mm-core`

### 4.2.1 ワークスペース構成

```
native/
├─ Cargo.toml                    # [workspace] resolver = "2"
├─ .cargo/config.toml            # mold 設定（§3.4.1）
├─ rustfmt.toml  clippy.toml     # §3.4.2
├─ crates/
│  ├─ znn-codec/                 # 純 Rust ZipNN コーデック（Python 非依存）
│  │  ├─ src/
│  │  │  ├─ header.rs            # ZN ヘッダー 32B + packed shape（付録 B.1）
│  │  │  ├─ reorder.rs           # 符号/指数ビット並べ替え（f64/f32/bf16）
│  │  │  ├─ planes.rs            # N 平面分割/結合（N=1,2,4,8）+ 安全な端数処理
│  │  │  ├─ huf/                 # huff0（compress.rs / decompress.rs / fse.rs）
│  │  │  ├─ codec.rs             # zipnn_core 等価レイヤー（チャンク並列・閾値）
│  │  │  ├─ safetensors_io.rs    # mmap 読取・キー順保持 Writer・原子入替
│  │  │  ├─ dtype.rs             # dtype ↔ 符号コード ↔ 平面方式の対応表
│  │  │  ├─ delta.rs             # ストリーミング XOR デルタ
│  │  │  ├─ scan.rs              # 並列 walk + front‑matter + インデックス
│  │  │  └─ hash.rs              # 多アルゴリズム 1 パスハッシュ
│  │  ├─ tests/                  # 単体・差分・回帰（付録 C のケースを含む）
│  │  └─ fuzz/                   # cargo-fuzz ターゲット
│  ├─ mm-core/                   # PyO3 拡張（モジュール名 `mm_core`、abi3）
│  └─ znn-cli/                   # 検証用 CLI（配布しない）
└─ native-bin/                   # リポジトリ同梱プリビルド（third_party 代替）
   ├─ linux-x86_64/mm_core.abi3.so
   ├─ linux-aarch64/mm_core.abi3.so
   ├─ windows-x86_64/mm_core.pyd      # ← .abi3.pyd ではない（下記の注記）
   └─ macos-universal2/mm_core.abi3.so
```

> 〔Phase 0 実装注記 2026‑09‑23〕 **Windows 成果物名は `mm_core.pyd`**:
> Windows CPython の `importlib.machinery.EXTENSION_SUFFIXES` は `['.pyd']`
> のみで、Linux/macOS で有効な `.abi3.pyd` 名は import されない（実機検証）。
> `scripts/build-native.sh` と `native/native-bin/README.md` はこの名前で
> 確定済み。abi3 であること自体は wheel タグ（`cp310-abi3`）と
> CPython 3.10/3.13 での import 疎通 CI（native.yml `abi3-import`）が担保する。

### 4.2.2 Python API 表面

```python
# 可用性・版数
mm_core.api_version() -> int
mm_core.core_version() -> str                    # "x.y.z+commit"

# ZipNN（パス入出力。GIL 解放。非同期ジョブ）
mm_core.zipnn_compress(src, dst, opts) -> JobHandle
mm_core.zipnn_decompress(src, dst, opts) -> JobHandle
mm_core.zipnn_delta_compress(base, ft, out, opts) -> JobHandle
mm_core.zipnn_delta_decompress(base, delta, out, meta, opts) -> JobHandle
mm_core.zipnn_inspect(path) -> str               # 統計 JSON（現行 stats 互換）

# ジョブ制御（ポーリング方式 — GIL 再取得コールバックを使わない）
mm_core.job_progress(handle) -> (done, total, phase)
mm_core.job_cancel(handle) -> bool
mm_core.job_result(handle) -> str                # 完了統計 JSON
mm_core.job_error(handle) -> str | None

# スキャン・インデックス・ヘッダー
mm_core.scan_models(roots, opts) -> str          # 現行 data と同一形状の JSON
mm_core.index_open(path) -> IndexHandle
mm_core.index_refresh(handle, roots) -> str      # 差分スキャン JSON
mm_core.safetensors_header(path) -> str
mm_core.safetensors_tensor_tree(path) -> str     # 表示用グループ化（任意）

# ハッシュ
mm_core.hash_file(path, algos, opts) -> str      # 1 パス・並列・結果 JSON
mm_core.hasher_new(algos) -> HasherHandle        # インライン検証用（§4.8‑B1）
mm_core.hasher_update(handle, chunk: bytes)      # PyBytes は &[u8] としてゼロコピー借用
mm_core.hasher_finalize(handle) -> str           # 結果 JSON

# ユーティリティ
mm_core.walk_models(root, opts) -> str
mm_core.move_with_sidecars(src, dst) -> None
mm_core.watch_roots(roots) -> WatchHandle        # notify（任意機能）
```

**設計不変条件**: (1) 大容量データはパスで渡し境界を跨がせない、
(2) 長時間 API は `py.allow_threads()` で GIL 解放（PyO3 0.29 での API 名は
`py.detach()` — 同期プリミティブ `walk_models` / `move_with_sidecars` も
含む。2026‑09‑26 監査で全同期 API の準拠を固定）、
(3) パニックは PyO3 境界で捕捉し Python 例外化（`panic = "abort"` 禁止）、
(4) キャンセルはチャンク境界で `AtomicBool` 検査 + `.tmp` 削除。

### 4.2.3 Python 側の再編

- `py/native.py`（新規・約 60 行）: プラットフォーム判定 →
  `native-bin/<tag>` を `sys.path` へ → import → バージョン検証。
  不在時は `available=False` + 理由を返すだけ（**コンパイル・pip・
  ネットワーク不要**）。現行 `ensure_zipnn` L160–628 を置換。
- `py/compress.py`: ルート・タスク台帳・ws 配信
  （イベント名 `update_zipnn_progress` / `zipnn_complete`、phase
  `prepare/tensors/delta/done`、stats キー `originalBytes/compressedBytes/
tensors/compressedTensors` を維持）を残し、実処理をポーリングループへ。
  バンドル（`*_DeltaZNN`）のディレクトリ意味論は既存ロジックを維持。
- `py/manager.py` / `py/utils.py` / `py/identify.py` / `py/download.py`:
  該当関数を `mm_core` 呼び出しへ置換（JSON 形状は現行互換）。
- 移行期は `MM_NATIVE=0/1/auto` で新旧経路を切替（Phase 7 で旧経路撤去）。

## 4.3 ゼロコピー設計

**原則: モデルのバイト列は Python 境界を一切跨がせない。**

| 経路         | 現行                                     | 刷新後                                         |
| ------------ | ---------------------------------------- | ---------------------------------------------- |
| 圧縮入力     | `safe_open` → torch テンソル → `clone()` | `Mmap`（読取専用）→ `&[u8]` 直参照             |
| ヘッダー     | Python `json.loads`                      | jiter が mmap バイトを非破壊・借用解析         |
| 圧縮出力     | RAM dict → `save_file`                   | 並列圧縮 → RAM/スポイル → `BufWriter` 逐次書込 |
| デルタ       | `f.read()` ×2 + パディング + XOR コピー  | 両側 mmap + ストリーミング XOR（追加コピー 0） |
| スキャン結果 | Python dict 群                           | Rust で JSON 1 文字列 → Python は 1 回 loads   |
| 進捗         | `run_coroutine_threadsafe`（GIL 再取得） | AtomicU64 を Python 側 10 Hz ポーリング        |

これにより OS ページキャッシュが唯一のコピーとなり、
ピーク RSS は O(チャンク × スレッド数) に収束する（KPI K1/K4）。

> 〔Phase 2 実装注記 2026‑09‑24・圧縮出力の「RAM/spoil」〕実装は
> **単一書き込みパス**を採用した: ヘッダー領域をworst‑case長（ソース
> ヘッダーからエントリごとに桁数上限を構成 — 固定スラックではない）で
> 予約してペイロードをストリームし、全テンソル確定後に seek‑back で確定
> ヘッダー JSON をパッチする（予約残は JSON 空白として正当なスペース —
> レガシーのデルタ パディングと同一技法）。スポイル方式（ペイロードを
> 一時ファイルへ書いてから組立て = 3 倍 I/O）は実測見積りで K2 を確実に
> 割るため不採用。上限超過は原理的に起きないが防御的フォールバック
> （再書き込み）も実装・テスト済み。詳細と実測: BENCH §7.3‑1。
> なお現行 C コアの「入力を in‑place で破壊する」挙動
> （Python 側 `tensor.clone()` の原因）は、Rust では
> **変換を出力側バッファで行う**ことで消滅する。

## 4.4 データ完全性保証設計（本計画の最重要項目）

### 4.4.1 現行 C コアで実証された欠陥（要約。詳細と再現手順は付録 C）

リポジトリ同梱のプリビルド `zipnn_core.cpython-311-x86_64-linux-gnu.so`
（Python 3.11.2 実機）に対する検証結果:

| 事象                       | 条件                                         | 結果                                                   |
| -------------------------- | -------------------------------------------- | ------------------------------------------------------ |
| **SEGFAULT（決定論的）**   | `total % 262144 ∈ {1, 2, 3}`（dtype32 経路） | 100% クラッシュ（NULL プレーンへの書込）               |
| ヒープオーバーフロー（UB） | 最終チャンク長 `% 4 ≠ 0`                     | 1–3 バイトの超過書込 + 最大 3 バイトの境界外読取       |
| dtype16 の奇数長（UB）     | `len % 2 == 1`                               | 境界外読取 + 超過書込（Neo 使用経路では到達しない）    |
| データ往復の正しさ         | クラッシュしない全ケース                     | **すべて一致**（生チャンク・huff0 チャンク双方で確認） |

Neo への影響評価:

- **単体圧縮（テンソル経路）は安全**: f32/f16/bf16/fp8 テンソルのバイト長は
  要素サイズの倍数であり、SEGFAULT 条件（最終チャンク 1–3 バイト）に
  到達しない。実運用で圧縮が日常動作している事実と整合する。
- **デルタ圧縮は危険**: パディング後のファイル長は任意のため、
  (a) `total % 256KB ∈ {1,2,3}` で **ComfyUI プロセスが SEGFAULT**
  （確率 ≈ 3/262144 / 回。稀だが致命的。Python 例外化されず
  サーバー全体が死亡する）、(b) `total % 4 ≠ 0`（約 75%）で
  ヒープオーバーフロー UB が常時発生（glibc のアロケーションスラックに
  吸収され通常は無症状だが、長時間稼働プロセスでの蓄積リスクは未定義）。
- **完全性検証の不在**: 上記に限らず、圧縮・解凍のいずれにも
  事後検証が存在せず、万一の破損を検知する手段がない。

### 4.4.2 Rust による構造的排除

- 平面分割/結合は**スライス境界チェック付き**で実装し、端数
  （チャンク長 1–8 バイトを含む全ケース）を明示的に処理する。
  付録 C の全クラッシュケースを**回帰テストとして固定化**し、
  「エラーまたは正常動作」であって「クラッシュ・UB ではない」ことを
  CI で保証する（KPI K5）。
- 解凍器は**敵対的入力前提**で設計する（ヘッダー値・cumSizes・
  chunkTypes の全検証、整数オーバーフロー検査、割り当て上限、
  fuzz でパニック・OOM しないことを確認）。ComfyUI は第三者の
  モデルファイルを読み込むため、悪意ある `.znn` に対する堅牢性は
  セキュリティ要件である。

### 4.4.3 端到端の検証パイプライン（新設）

```
圧縮時:
  1. 原本ファイル全体の SHA‑256 を圧縮パスと並行して算出
     （mmap ページは圧縮で既に温まっており追加コストは数秒/10GB）
  2. 圧縮出力を書込み → 構造検証（ヘッダー・チャンク表・全長整合）
  3. メタデータに記録:
       znn_neo_original_bytes（現行互換）
       znn_neo_src_sha256   = 原本ファイル SHA‑256（新設）
       znn_neo_extended     = "1"（Neo 拡張 dtype を含む場合のみ）
  4. paranoid モード（設定、既定 OFF）: 出力を即解凍し原本と
     SHA‑256 比較してから原本を削除
  5. 検証成功後のみ原本削除（現行の順序保証を維持・強化）

解凍時:
  1. 復元ファイルを tmp に書込
  2. znn_neo_src_sha256 があれば復元結果の SHA‑256 と比較（既定 ON。
     SHA‑NI により数秒/10GB）
  3. 一致 → rename で確定、圧縮ファイルを削除
     不一致 → **圧縮ファイルを削除せず**、エラーを UI に報告し
     復元物を診断用 `.corrupt` サフィックスで退避
  4. キーなし（公式 CLI 由来ファイル等）→ 検証スキップの旨をログ
```

> 〔Phase 2 実装注記 2026‑09‑24〕(a) **`znn_neo_exact` キーの新設**:
> 原本ヘッダーが正準形（参照 Writer とバイト同一に再構築可能）でない
> ファイルでは byte‑exact 復元が原理的に不可能なため、圧縮時に正準性を
> 判定して記録する。解凍時の sha 不一致は exact=1 のみ「破損扱い
> （圧縮ファイル保持 + `.corrupt` 退避 + UI エラー）」、exact=0 は
> §4.7.4 の最低保証（構造検証: テンソルデータ + メタデータ等価）へ
> ダウングレード — §4.4.3 の一律エラーをそのまま実装すると非正準原本が
> 永久に解凍不能になるため、両節の意図を両立させた。(b)
> **`znn_neo_src_meta_absent` キーの新設**: 原本の `__metadata__` が
> 「無い」と「空マップ」の区別を記録（参照 Writer は None=キー省略、
> 空マップ=`{}` — バイトが違う）。レガシー解凍側も尊重する。
> (c) 検証ハッシュは解凍時に**インライン**（書込バイトがハッシャを
> 通過 — 追加 I/O ゼロ）。並列ハッシャは 2 vCPU 実測で逆効果 + RSS 増
> のため不採用（BENCH §7.3 末尾の注記）。

デルタも同様: `.neo-delta.json` に fine‑tune 原本の SHA‑256 を記録し、
復元時に検証する（サイドカーは Neo 専有のため互換性影響なし）。

**効果**: 「圧縮前と解凍後が完全に一致すること」が、
実装の正しさへの信頼から**毎回機械的に検証される事実**へ変わる。
現行 C コアに見つかった欠陥（§4.4.1）は、この検証が存在すれば
すべて検知できたものである。

### 4.4.4 原子性とクラッシュ耐性

- 全書込: 同一ディレクトリの tempfile → flush → **fsync（ファイル + 親
  ディレクトリ）** → rename。停電時の「0 バイトファイル」を防止
  （現行 Python 実装は fsync なし → 改善点）。
- 原本削除は常に検証・rename 成功後（§4.4.3）。
- 起動時に残存 `.tmp` / `.corrupt` を一覧し、設定に従い掃除。
- ENOSPC（ディスク満杯）: 書込失敗時に tmp を削除し原本を保持、
  事前の空き容量チェック（ダウンロード側の Free‑space guard と同型）を
  圧縮開始時にも追加。

## 4.5 ZipNN コーデック移植仕様（要約）

C ソース読解により確定した移植仕様（完全版は付録 B）:

1. **ビット並べ替え（可逆全単射）**
   - f32: u32 単位で `sign=(u>>8)&0x800000; exp=(u<<1)&0xFF000000;
man=u&0x7FFFFF; u'=exp|sign|man`（`data_manipulation_dtype32.c` L39–50）。
   - bf16: u32=2 要素パックで `sign=(u>>8)&0x800080;
exp=(u<<1)&0xFF00FF00; man=u&0x7F007F`（`data_manipulation_dtype16.c`
     L10–21）。**bf16 のみ**適用（f16 は bits_mode=0）。
2. **平面分割**: 4 平面（bytes_mode=220）/ 2 平面（10）/ 1 平面（FP8。
   C の「変更なしコピー」を Rust では**コピーなし**に改善）。
   端数は C の in‑bounds レイアウトと**バイト同一**になるよう実装
   （C のオーバーフロー書込は論理ペイロードに含まれないため、
   clean 実装で両方向互換が成立する — 付録 C.4 の分析）。
3. **チャンク処理**: 既定 256 KB（FP8 は ≤128 KB = `HUF_BLOCKSIZE_MAX`）。
   平面ごとに `HUF_compress` 相当 → 閾値 `comp < uncomp × 0.95` で
   type=1（huff0）/ type=0（生）。`check_th_after_percent` の早期打切りは
   C 側で無効化されている（L594–596）ため、Rust でもパラメータ互換のみ維持。
4. **出力レイアウト**: `[ZN ヘッダー 32B + packed shape] +
[chunkTypes: numBuf×numChunks] + [cumSizes: numBuf×numChunks×u64] +
[平面別連結データ]`（64 ビット専用 = C と同一制約を明記）。
5. **huff0**: RFC 8878 §4.2.1 準拠（重みテーブル直書き/FSE 両対応、
   4X1/4X2、tableLog ≤ 12）。エンコードはビット完全一致を要求しない
   （仕様互換で公式デコーダが復号可能）。デコードは公式 C エンコーダ
   出力の 100% 受理を要件とする。
6. **デルタ**: 1 MB ストリーミングチャンクごとに `XOR(ft, base)` →
   byte 形式（bytearray_dtype=float32 → 4 平面 + bit_reorder=1）で圧縮。
   ヘッダー等長化パディングと `.neo-delta.json` は現行セマンティクス維持
   （エラーメッセージ文言まで互換 — UI がそのまま表示するため）。

## 4.6 dtype 対応の大幅拡張

### 4.6.1 対象（2026‑09 確認: safetensors 0.8 Dtype 全 22 種 + PyTorch 2.14）

safetensors 0.8: `BOOL, F4, F6_E2M3, F6_E3M2, U8, I8, F8_E5M2, F8_E4M3,
F8_E8M0, F8_E4M3FNUZ, F8_E5M2FNUZ, I16, U16, F16, BF16, I32, U32, F32,
C64, F64, I64, U64`。
PyTorch 2.14 追加: `bcomplex32`、complex32/128、float8_e8m0fnu、
float4_e2m1fn_x2、uint16/32/64、シェル dtype（uint1–7、float6_*_pe）。

### 4.6.2 符号方式

| dtype 群                             | 平面数 | ビット並べ替え               | 備考                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ------------------------------------ | ------ | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F32 / C64（=2×f32）                  | 4      | f32 方式                     | C64 は u32 単位処理で同一変換が成立                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| BF16 / bcomplex32（=2×bf16）         | 2      | dtype16 方式                 | 現行どおり                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| F16                                  | 2      | なし                         | 現行どおり                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| F8_E4M3 / E5M2 / E4M3FNUZ / E5M2FNUZ | 1      | なし                         | 現行 FP8 経路を FNUZ へ拡張                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| F8_E8M0                              | 1      | なし                         | 値が 2 のべき乗の指数のみ → 極めて高い圧縮率                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **F64 / complex128（=2×f64）**       | **8**  | **f64 方式**                 | f32 方式の一般化: `sign=(u>>11)&0x0010_0000_0000_0000; exp=(u<<1)&0xFFE0_0000_0000_0000; man=u&0x000F_FFFF_FFFF_FFFF; u'=exp\|sign\|man` → レイアウト [exp11 bits 63..53][sign bit 52][man52 bits 51..0]。**【2026‑09‑23 訂正（Phase 1 実装が証明）】** 旧式（`>>12`/`0x0008…`/`0x0007…` = sign を bit 51 へ、man を 51 bit に切詰め）は**全単射でない**: mantissa bit 51 を落とし bit 52 を死なせるため任意 u64 の約 50 % が往復に失敗（実測 100,045/200,000、例 1.5→1.0）。訂正版は f32 パターン [exp][sign][man] の 11/1/52 への忠実な一般化で、`reorder.rs` の proptest（any::<u64> 往復 + 衝突なし）が恒久的に固定する。逆変換: `sign=(u<<11)&0x8000…; exp=(u>>1)&0x7FF0…; man=u&0x000F…` |
| **I8 / U8 / BOOL**                   | 1      | なし                         | BOOL は {0,1} → huff0 で約 1/8                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **I16 / U16**                        | 2      | なし（+任意トランケート）    | C 実装済みのモード 8/1 を正式化                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **I32 / U32**                        | 4      | なし（+トランケート 41/9/1） | ゼロバイト統計で自動選択                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **I64 / U64**                        | 8      | なし                         | 上位バイトのゼロ偏りで高圧縮                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **F4 / F6_E2M3 / F6_E3M2**           | 1      | なし                         | 不透明バイトとして huff0                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| GGUF 量子化型                        | —      | —                            | 対象外（§2.3）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

### 4.6.3 コード割り当てと相互運用マトリクス

ヘッダー[15] の dtype コードは 2 帯域で管理する:

- **上流互換帯（1–30）**: 上流実装済み dtype のみ、上流と同一コード・
  同一方式で書込 → **公式 zipnn 0.5.4 デコーダで解凍可能**。
  FLOAT32/FLOAT=1/2、FLOAT16/HALF=4/5、BFLOAT16=6、
  FLOAT8_E4M3FN=29、FLOAT8_E5M2=30。
- **Neo 拡張帯（128–255）**: 上流 enum（現在 1–30）と十分離した
  Neo 専用領域。F64=128、COMPLEX128=129、COMPLEX64=130※、
  BCOMPLEX32=131、I8/U8=132/133、BOOL=134、I16/U16=135/136、
  I32/U32=137/138、I64/U64=139/140、F8_E4M3FNUZ/E5M2FNUZ=141/142、
  F8_E8M0=143、F4/F6_E2M3/F6_E3M2=144/145/146。
  ※COMPLEX64 は公式デコーダがコード 9 + 220/1 方式を汎用処理で
  読める可能性があり、Phase 4 の実証テストで互換帯(9)/Neo 帯(130)を
  確定する（推測で決めない）。
- **失敗モードの安全性**: 公式 zipnn は未知コードを明示エラーで拒否する
  （静かな破損は起きない）。Neo 拡張帯を含むファイルには
  `znn_neo_extended="1"` を記録し、UI に
  「公式 ZipNN ツールでは解凍不可」バッジを表示する（i18n: en/ja/zh）。
- `znn_compressed_vectors` の dtype 文字列は現行同様 torch 表記
  （`"float64"` 等）を記録。Neo 解凍器は torch 非依存で
  safetensors dtype 名（`"F64"` 等）へ変換する表を持つ。

### 4.6.4 UI 反映

- Information タブに「圧縮方式」行（dtype 内訳集計 `bf16×412, uint8×3…`。
  ヘッダー解析は Rust 化済みのため追加コストほぼゼロ）。
- Neo 拡張形式バッジ + ツールチップ、圧縮確認ダイアログに
  「公式互換で圧縮 / Neo 拡張形式になります」の明示。

## 4.7 スキャン・更新・表示・保存の刷新

### 4.7.1 スキャン（Rust 並列 walk + 永続インデックス）

```
1. 並列 walk（ignore::WalkBuilder 第一候補。hidden フィルタは opts）
2. rayon でエントリ並列処理:
   - 拡張子フィルタ（supported_pt_extensions は Python から受領 —
     ComfyUI 本体の定義を唯一の真実として維持）
   - プレビュー解決（ディレクトリ名集合へのゼロ stat 照合。
     現行 previews_in_names と同一の 20 スロット規則を移植）
   - .md front‑matter 先頭 4 KB パース（modelPage/website/hashes.SHA256/baseModel）
   - stat（size/ctime/mtime）
3. 永続インデックス（bincode スナップショット + blake3 チェックサム、
   拡張データ dir、原子入替）: (path, mtime_ns, size) → パース済み 4 値。
   ComfyUI 再起動後も有効（現行 _SITE_CACHE のプロセス内限界を解消）。
   破損・不一致時は自動全再構築（常に派生データ）
4. serde_json で 1 文字列に直列化（現行 data 形状を厳密維持:
   type/subFolder/isFolder/basename/extension/pathIndex/sizeBytes/preview/
   modelPage/modelPlatform/modelSha256/modelBase/createdAt/updatedAt）
```

- **安定順序**: walk 結果をパスでソートしてから直列化し、
  「一覧順が更新間で揺れない」現行契約（manager.py L455–459 の意図）を維持。
- 衛生スキャン（orphan サイドカー・空フォルダ）も同一 walk 基盤で Rust 化。

### 4.7.2 更新伝播

1. **イベント駆動無効化**: ダウンロード完了・リネーム・削除・ZipNN 完了・
   アップロード登録時に `models_changed {type, reason}` を ws 配信 →
   フロントは該当 type のみ再取得（30 秒 TTL revalidate はフォールバック維持）。
2. **外部変更検出（任意機能）**: `watch_roots`（notify +
   notify-debouncer-full、500 ms デバウンス）。ネットワークストレージでは
   自動無効化し定期ポーリングへフォールバック。設定で OFF 可。
3. **差分ペイロード（ストレッチ）**: インデックス世代番号による
   `?since=<gen>` 差分取得。

### 4.7.3 表示

- **ヘッダー解析**: `safetensors_header`（jiter）が 8 MB MoE ヘッダーを
  ≤40 ms で解析（K11）。`get_model_tensors` の出力形状は互換維持。
- **テンソルツリー事前グループ化（任意）**: Rust で折りたたみ木を構築し
  フロント（`modelInformation.ts`）の再計算を削減。
- **モデル詳細ルートの非阻塞化**: 課題 6（§1.2.2）の修正 —
  `get_model_info` を executor 経由へ（Rust 化と合わせて K12 達成）。
- フロントエンド最適化は計測駆動で Phase 6 実施（§4.8‑C）。

### 4.7.4 保存

- 原子性の統一（§4.4.4）、front‑matter 書込の正規化
  （キー順安定・引用規則固定の Rust ヘルパ — 編集のたびの diff 揺れ防止）。
- **byte‑exact 復元**: 自前 Writer がキー順を保持するため、標準ツール由来
  ファイルでは復元ファイルが原本とバイト一致する（`znn_neo_src_sha256` で
  毎回検証）。特殊 writer 由来で一致しない場合の最低保証は
  「テンソルデータ + メタデータ値の等価」。

## 4.8 追加最適化一覧（本次精査で新規特定）

Rust 化と独立に実施可能な項目を含む。重要度順。

### A. バックエンド（Python 側の即時改善 — Quick Win）

| #   | 項目                       | 内容                                                                                                                             | 効果                                                                      | 実施フェーズ     |
| --- | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ---------------- |
| A1  | モデル詳細ルートの非阻塞化 | `py/manager.py` L135–160 の `get_model_info` 同期呼び出しを `run_in_executor` へ（scan/hygiene/update と同じ修正パターンを適用） | サーバー全体のフリーズ解消（K12 の前半）。**Rust 化を待たず即時実施可能** | Phase 0 と並行可 |
| A2  | ダウンロードチャンク拡大   | `iter_chunked(8192)`（L680）→ 512 KB–1 MB（10 GB で Python ループ 130 万回 → 1 万回）                                            | CPU 減・イベントループ余裕。インラインハッシュの前提                      | Phase 5          |
| A3  | ブロッキング HTTP の統一   | `search.py`/`information.py`/`identify.py` の `requests.get`（executor 経由）を共有 aiohttp セッションへ                         | スレッドホップ除去・タイムアウト一元化・IO プール枯渇リスク低減           | Phase 5（任意）  |

### B. ネイティブコアに統合（Rust 化と同時）

| #   | 項目                    | 内容                                                                                                                                                           | 効果                    |
| --- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| B1  | インラインハッシュ検証  | ダウンロード書込ループから `hasher_update` へチャンク供給。完了時フル再読込（`_sha256_of`）を削除。一時停止/再開はハッシャー状態（64 B 級）を `.task` に保存   | K7（追加 I/O ゼロ）、K8 |
| B2  | 多アルゴリズム 1 パス化 | SHA256 + AutoV1 窓（offset 0x100000 の 64 KiB）+ CRC32 + BLAKE3（rayon 並列）を 1 読取で同時計算。Civitai 表記（大文字 hex・CRC32 バイト反転）の golden テスト | identify の高速化       |
| B3  | 永続インデックス        | §4.7.1‑3                                                                                                                                                       | K9/K10                  |
| B4  | ヘッダー解析内製化      | `comfy.utils.safetensors_header` 依存を撤去し ComfyUI 本体 API 変更に耐性                                                                                      | K11 + 保守性            |

### C. フロントエンド（Phase 6、計測駆動）

| #   | 項目                      | 内容                                                                                                                              | 効果                                                |
| --- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| C1  | 正規表現ホイスティング    | `DialogManager.vue` L176–177 の `tokens.map(buildRegex)` をフィルタループ外へ                                                     | keystroke ごとに O(モデル数) 回の正規表現構築を排除 |
| C2  | ソートの照合キー化        | `localeCompare` ×4 箇所（DialogManager/model.ts/DialogExplorer×2）を共有 `Intl.Collator` インスタンス（または事前小文字化キー）へ | 大規模一覧のソート高速化                            |
| C3  | 浅いリアクティブ化        | `models` ストアを `shallowRef` + イミュータブル差し替えへ（星/選択は別ストアのため影響なし — 棚卸しリスト先行）                   | 数千モデルの Proxy コスト除去                       |
| C4  | 画像デコード非同期化      | `ResponseImage.vue` の `<img>` に `decoding="async"`（仮想スクロール済みのため `loading="lazy"` は不要）                          | スクロールジャンク低減                              |
| C5  | performance mark 計測基盤 | 5,000 モデル合成データでの計測を常設                                                                                              | K15 の継続検証                                      |

---

# 5. 品質保証計画

## 5.1 テスト戦略（5 層）

| 層              | 内容                                                                                                                                                                                                                                                                                  | 合格基準                               |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| L1: Rust 単体   | ビット並べ替えの全単射性（proptest）、平面分割/結合の往復（端数 len%4 ∈ {0,1,2,3}・チャンク長 1–8 を網羅）、huff0 往復（空・1B・全同一・ランダム・128KB 境界・tableLog 1–12・重みテーブル両経路）、ヘッダー codec                                                                     | 全 green + カバレッジ目標（分岐 ≥90%） |
| L2: 差分テスト  | 同梱 C プリビルド .so をゴールデン生成器とし、**Rust 圧縮→C 解凍** / **C 圧縮→Rust 解凍**を ≥10,000 ランダムケース + 実テンソルで検証。**付録 C の全クラッシュケースは「Rust がエラーまたは正常動作」することを回帰テストに固定**                                                     | 原本一致 100%、クラッシュ 0            |
| L3: ファジング  | cargo-fuzz（libFuzzer）: `huf_decompress` / ZN ヘッダー / safetensors ヘッダー / 敵対的 .znn 入力                                                                                                                                                                                     | ≥8 時間でパニック・OOM・ハング 0       |
| L4: Python 統合 | pytest: ルート/ws 契約（イベント名・phase・stats キーを golden JSON 固定）、`MM_NATIVE=0/1` 両経路、実モデルコーパス（sd1.5‑fp16 / sdxl‑fp16 / flux‑fp8 / LLM‑bf16 / VAE‑f32 / MoE 巨大ヘッダー / complex64 音声 / f64 合成）で圧縮→解凍→**原本 SHA‑256 一致** + 圧縮率 C 版 ±1% 以内 | 全 green                               |
| L5: 相互運用    | 公式 zipnn 0.5.4（pip、CI のみ）とのクロス検証: Neo(Rust) 圧縮 → 公式解凍（互換帯 dtype）、公式圧縮（HF `zipnn/gpt2-ZipNN` 等）→ Neo 解凍                                                                                                                                             | 両方向 100%                            |

## 5.2 ベンチマーク

- Phase 0 で全 KPI のベースラインを `docs/BENCH.md` に記録。
- criterion（Rust マイクロベンチ）+ `scripts/bench`（端到端）。
- 各フェーズ完了判定で §2.2 KPI 表と機械的に照合。

## 5.3 CI/CD

| ジョブ                | ランナー                 | 内容                                                                         |
| --------------------- | ------------------------ | ---------------------------------------------------------------------------- |
| ci（既存）            | ubuntu                   | lint/typecheck/build/mypy/ruff（維持）                                       |
| native-test           | ubuntu / windows / macos | `cargo fmt --check`、`cargo clippy -D warnings`、`cargo test`、fuzz スモーク |
| native-cross          | ubuntu（zig）            | linux x86_64/aarch64（glibc ≥2.28）ビルド + サイズ予算ゲート（≤4 MB/本）     |
| native-diff（移行期） | ubuntu                   | L2 差分テスト（C プリビルド使用）                                            |
| integration           | ubuntu / windows / macos | L4/L5（pytest + 公式 zipnn クロス検証）                                      |

- mold は native-test（ubuntu）とローカル開発で使用（§3.4.1）。
  クロスビルド（zig）は zig 側 LLD のため mold 対象外。
- 成果物は PR では検証のみ。`main`/リリースタグで `native-bin/` 更新
  コミットを自動生成（既存 web/ バンドル運用と同型）。

## 5.4 移行期の安全装置とロールバック

- `MM_NATIVE=0/1/auto`（既定 auto）で新旧経路を切替。Phase 2–6 は
  両経路を CI で並行走行。
- **paranoid モード**（圧縮後即解凍検証、§4.4.3）を設定で提供。
- third_party 撤去は「L5 クロス検証 CI が 2 リリースサイクル連続 green」を
  ゲート条件とする（Phase 7）。
- 各フェーズのロールバック単位 = そのフェーズの切替フラグ 1 本
  （旧経路が生きている限り、単一コミット revert で復帰可能）。

---

# 6. 実施計画

## 6.1 フェーズ総覧

| Phase | 名称                                | 主成果物                         | 完了条件（要約）                                     |
| ----- | ----------------------------------- | -------------------------------- | ---------------------------------------------------- |
| 0     | 基盤準備                            | ワークスペース・CI・ベンチ基盤   | 全ターゲットで abi3 ビルド疎通、KPI ベースライン記録 |
| 1     | znn-codec フォーマット中核          | ヘッダー/平面/huff0・FSE/codec   | L1–L3 green、C 版との圧縮率差 ±0.5%・速度同等以上    |
| 2     | safetensors 圧縮/解凍 + 接続        | mm-core API、compress.py 切替    | L4 green、K1–K3/K6 達成、UI QA                       |
| 3     | デルタ + バッチ                     | delta.rs、バッチプリミティブ     | K4/K5 達成、現行と同一挙動 QA                        |
| 4     | dtype 大幅拡張                      | 8 平面/f64/整数/MX 系、UI バッジ | 全拡張 dtype 往復 green、L5 退行なし                 |
| 5     | スキャン/インデックス/ハッシュ/更新 | scan.rs、hash.rs、models_changed | K7–K11 達成、UI 退行なし                             |
| 6     | フロントエンド表示最適化            | C1–C5                            | K15 計測実証                                         |
| 7     | third_party 撤去・配布仕上げ        | native-bin 単一経路、v0.3.0      | 全新規 clone で全 OS 動作                            |

## 6.2 フェーズ詳細

### Phase 0 — 基盤準備

- [x] KPI 全項目のベースライン計測・`docs/BENCH.md` 記録
      （圧縮/解凍/デルタ/スキャン/ヘッダー/ハッシュ。実モデル + 合成）
- [x] **Quick Win A1**: `get_model_info` の executor 化（Rust 化に先行、単独 PR。
      回帰テスト `tests/test_phase0_a1_model_info_route.py` — mm-io 実行と
      ループ生存を機械的に検証）
- [x] `native/` cargo ワークスペース雛形（edition 2024、resolver 2）
- [x] **mold 導入**: `native/.cargo/config.toml`（§3.4.1）+ CI への
      mold インストールステップ + ローカル導入手順の文書化
- [x] **rustfmt/clippy 導入**: `rustfmt.toml` / `clippy.toml` /
      crate 属性（pedantic=warn、unsafe lint=deny）+ `pnpm rs:fmt` /
      `pnpm rs:lint` スクリプト + CI ゲート（`-D warnings`）
- [x] maturin + abi3-py310 ビルド疎通（hello world を 5 ターゲットで）+
      サイズ予算の実測
- [x] JSON パーサ確定: jiter 0.17 vs simd-json 0.18 を 8 MB MoE ヘッダーで
      マイクロベンチ（非破壊借用解析の要件込み）
- [x] `py/native.py` ローダー雛形 + `MM_NATIVE` スイッチ
      （ハンドシェイク検証テスト `tests/test_phase0_native_loader.py`。
      不一致モジュールを sys.modules に残さない後始末を含む）
- [x] 完了条件: 全ターゲットで abi3 ビルド成功、import 疎通、
      clippy/fmt gate green、サイズ ≤4 MB/本、ベースライン記録完了
      （達成証跡: native.yml @ 81854f5 全ジョブ緑 = 5 ターゲットビルド +
      CPython 3.10/3.11/3.13 import 疎通 + サイズ計 1.55 MiB、
      docs/BENCH.md = K1–K16 ベースライン + JSON パーサ選定）

### Phase 1 — znn-codec フォーマット中核

- [x] ZN ヘッダー codec（32B + packed shape 往復。付録 B.1）— `header.rs`、
      敵対的入力検証 + L3 zn_header ターゲットで固定
- [x] ビット並べ替え f32/bf16（proptest 全単射）+ **f64 新方式**（§4.6.2）—
      `reorder.rs`。**f64 式は全単射でなかったため訂正**（§4.6.3 表の訂正注記、
      proptest any::<u64> が恒久固定）
- [x] 平面分割/結合 N=1,2,4（**チャンク長 1–8 を含む端数網羅。
      C in‑bounds レイアウトとバイト一致**。付録 C クラッシュケースの回帰化）—
      `planes.rs`（0..=72 網羅 + チャンク境界 + 付録 C 長 + proptest + L2 で
      C ゴールデンとバイト照合）
- [x] huff0 デコーダ（RFC 8878。4X1/4X2・重みテーブル両経路・敵対的入力検証）—
      `huf/decode.rs`（X2 デコードは 4X1/4X2 両_variant_の同一ビットストリームを
      解釈。重み FSE/直接両経路、RLE・stored 特殊形、全破損系を Err 化）
- [x] huff0 エンコーダ（tableLog 選択戦略込み）— `huf/encode.rs` + `huf/tree.rs`。
      optimalTableLog/HUF_sort/setMaxHeight/canonical 代入/重み FSE 選択/逆順
      ビットライタまで C 逐条移植 → **出力バイト C と完全同一**（L2 9,880/9,880）
- [x] FSE 重みテーブル符号化/復号 — `fse.rs`（normalizeCount+M2/writeNCount/
      buildCTable/双状態ライタ/readNCount/buildDTable/双状態デコード）
- [x] `codec.rs`: チャンク並列（rayon 専用プール）・閾値 0.95・
      出力レイアウト（chunkTypes/cumSizes、C とバイト同一構造）—
      ヘッダー [24:32] resBufSize 書込み・最終チャンク decompLen 式・
      C が検証しない敵対的ペイロードの全検証（単調性/span/type/生スライス長/
      出力キャップ）込み
- [x] L2 差分テスト基盤（C .so をゴールデン生成器に、≥10,000 ケース）—
      `scripts/l2/golden_diff.py`。**フル 10,500 ケース GATE PASS**
      （バイト一致 9,880/9,880、相互解凍両方向全通過、付録 C クラス
      495/495 安全処理、C の UB 形状は fork 隔離でゴールデン化）。
      CI: native.yml `native-diff`（quick）+ fuzz-long.yml `l2-full`（週次）
- [x] L3 cargo-fuzz ターゲット 3 種 — huf_decompress / zn_header /
      codec_decompress（シードコーパス 69 件コミット、クラッシュ回帰シード含む）。
      ローカルスモーク ~60 万実行パニック 0、**実バグ 3 件を検出・修正**
      （byte13 正規形・cumSizes usize 溢れ・orig_len+chunk-1 溢れ）。
      CI: native.yml `fuzz-smoke`（60s×3）+ fuzz-long.yml（週次 3h×3 = 9h ≥ 8h）
- [x] （推奨）上流 zipnn への欠陥報告 issue 起票（付録 C の再現手順添付）—
      **ユーザ判断（2026‑09‑23）: 起票せず、Neo 実装内でバグが完全修正
      されていればよい**。担保: Neo は設計上 OOB 不可能（unsafe ゼロ・全経路
      bounds-checked）+ 付録 C 全長回帰（L1/L2 495/495/L3 ASan ~60 万実行）
  - ファズ検出オーバーフロー 2 件修正済み。証跡整理 = docs/BENCH.md §6.4
    （起票文案は `docs/upstream/zipnn-core-defect-report.md` に参考保管）
- [x] 完了条件: L1–L3 green（L1 69 テスト緑・L2 フル 10,500 ケース GATE PASS・
      L3 スモーク緑。fuzz ≥8 h は 〔2026‑09‑24 訂正（Phase 2 セッション、
      GitHub API で実証）〕admin 権限 PAT でも workflow_dispatch が **404** —
      fuzz-long.yml が default branch（main）に存在せず workflow 未登録 —
      だったため **dev→main マージ（PR）で登録を有効化**して消化した。
      〔2026‑09‑25 追記（GitHub API で実証）〕初回ディスパッチ run 36088280583
      （head 3b3a3af、3h×5）完走: **l2‑full / st_parse / codec_decompress /
      huf_decompress / zn_header = SUCCESS（3 h クラッシュゼロ）**、
      blob_decompress = FAILED（libFuzzer rss_limit 2048MB 到達。live heap
      ~25MB で**コード非欠陥**）。修正 4cce777（thread_local 再利用バッファ +
      ASan チューニング + rss_limit 4096）の run 36114455354 も
      **blob_decompress のみ再度 OOM（4097MB、~35.5 B/exec の線形保持）** —
      〔2026‑09‑25 続セッションで真因特定〕前回の「アロケータのページ保持」
      診断は誤りで、実因は**ハーネスの threads=1 が default_threads()(=4) と
      異なるため `with_threads` が exec ごとに新規 rayon プールを生成破棄
      （OS スレッド 1 本/exec の churn → ランタイム/サニタイザ メタデータが
      プロセス生存中累積）**だった（傍証: threads=0 の codec_decompress は
      両 run 緑）。修正 de1a153（明示スレッド数のプールをキャッシュ +
      上限ガード、ローカル A/B: 定常窓 ~44→~9 B/exec）で再ディスパッチした
      **run 36148521214（head de1a153、3h×5）が全 5 ターゲット SUCCESS** —
      blob_decompress は **189,822,394 execs / 3 h 完走、最終 peak RSS
      164 MB（limit 4096 MB の 1/25）、クラッシュ 0、exec/s 17,574
      （run 2 比 +63 % — churn はスループット税でもあった）**。l2‑full も緑。
      ≥8 h バジェット = 5 ターゲット × 3 h = 15 h で消化完了）、
      f32/bf16/f16/fp8 で C 版比 圧縮率差 ±0.5% 以内
      （**Δ0.0000 % = バイト同一で達成。ユーザ要件「67 % を下回らない」も
      bf16 実測 0.6623 で構造的に保証 — BENCH §6.3**）・速度同等以上
      （**8/8 指標 ×1.09–1.81 で達成** — virtual-raw 平面最適化により
      bf16/f16 圧縮 ×0.72–0.84 → ×1.18–1.45 に反転。同一 steal ゲート
      プロトコルの連続 2 実行で安定。**unsafe 不使用**（ユーザ指示）。
      変動注記: BENCH §6.2）、clippy/fmt green（**達成**）

### Phase 2 — safetensors 圧縮/解凍パイプライン + バックエンド接続

- [x] `safetensors_io.rs`: mmap 読取・キー順保持 Writer・
      原子入替（fsync + 親ディレクトリ fsync）・ENOSPC 処理 —
      参照実装 safetensors 0.8.0（Rust）の一次ソース精読で
      **バイト同一の正準シリアライズ**を実装（`__metadata__` 先頭・
      compact JSON・8B 整列スペースパディング・検証規則の逐条ミラー）。
      mmap は crate 唯一の unsafe 境界（SAFETY レビュー済み、§3.4.2 の
      「意識的・レビュー付き導入」条項 — native/README 参照）。
      副次発見: 参照実装はメタデータを **HashMap 順（プロセスごとに
      ランダム）**で書くため、レガシー往復の byte‑exact は複数キー時に
      偶然依存だった — Neo の順序保持 Writer がこの潜伏バグを解消
      （BENCH §7.3‑4）
- [x] 圧縮パイプライン（§4.3 + §4.4.3 の完全性検証:
      `znn_neo_src_sha256`/`znn_neo_exact`/`znn_neo_src_meta_absent` 記録、
      原本 sha は圧縮と並行スレッドで算出）— 「RAM/spoil」は
      **単一書き込みパス（H_max ヘッダー予約 + seek‑back パッチ）**で
      実装（§4.3 の実装注記 + BENCH §7.3‑1、フォールバック再書き込み
      テスト済み）。ピーク RAM = O(最大テンソル)（実測: 64 MB モデルで
      限界 +75 MiB = 1.2× vs レガシー 2.6×）
- [x] 解凍パイプライン（検証 ON 既定 = インライン SHA‑256、追加 I/O ゼロ。
      不一致時は圧縮ファイルを削除せず `.corrupt` 退避 + UI エラー。
      exact=0 のみ §4.7.4 の構造検証へダウングレード — §4.4.3 実装注記 (a)。
      敵対的 `.znn` 対策: 割り当てキャップ（整合的な嘘 original_len を
      Err 化 — OOM abort 防止）、checked offset 累積、fuzz ターゲット
      `st_parse`/`blob_decompress` 追加）
- [x] paranoid モード（圧縮後即解凍検証 — rename 前に実施。内部デコードは
      ジョブ進捗を駆動しない〔done>total バグを実測で発見し修正、
      BENCH §7.3‑7〕。`MM_ZNN_PARANOID` 環境変数 +
      `ModelManager.ZipNN.Paranoid` 設定キー、既定 OFF）
- [x] `mm_core` PyO3 API（api_version **2**: `zipnn_compress`/
      `zipnn_decompress` → handle、`job_progress`（10 Hz ポーリング契約）/
      `job_cancel`/`job_result`/`job_error`。ジョブスレッドは GIL 非接触 +
      `catch_unwind`（パニック → ジョブエラー）。**完了の権威シグナルは
      outcome レコード**（phase との間の競合窓を実測で発見し構造的に
      消滅 — BENCH §7.3‑6）。ローダー `py/native.py` は API 範囲 [2,2]
      （v1 バイナリは AttributeError 前に明確な reason で拒否））
- [x] `py/compress.py` 単体圧縮/解凍ルートの切替
      （`MM_NATIVE=0/1/auto`。ws イベント・stats 形状の golden 互換テスト:
      両経路で**同一ゴールデン**（イベント名・キー集合・phase 語彙・
      monotone 進捗・stats キー）を機械検証。batch/delta ルートは
      Phase 3 までレガシーのまま。クロスパス互換: native 圧縮 →
      レガシー解凍（byte‑exact）/ レガシー圧縮 → native 解凍（意味同一）/
      **両圧縮器のテンソル保存バイト・infos 文字列・stats 完全一致**
      （test_blob_parity）。レガシー解凍側も Neo キー 6 種を strip +
      meta_absent 尊重へ更新。キャンセルルート
      `POST /model-manager/zipnn/cancel` 新設（レガシージョブは
      明示的にキャンセル不可と応答））
- [x] 起動時 `.tmp`/`.corrupt` クリーンアップ（`__init__.py` →
      io_executor でバックグラウンド実行。`.tmp` は**15 分以上前**のもの
      のみ削除（外部ツールの実行中ダウンロードを絶対に触らない年齢
      ガード + ZipNN 名前形のみ）、`.corrupt` は削除せず一覧を
      ログ報告（診断物の自動削除はデータ破壊リスクのため））
- [x] L4 コーパステスト — Plan 列挙の 8 クラス（sd15‑fp16/sdxl‑fp16/
      flux‑fp8/LLM‑bf16/VAE‑f32/MoE 巨大ヘッダ 600 テンソル/complex64 音声/
      f64 合成）+ unicode テンソル名の合成スタンドイン（1 GiB RAM 制約は
      Phase 0 と同じ手法 — 実モデル再実行は `run_all.sh` +
      `bench_native_e2e.py --model` で可能）。全クラス × 圧縮→解凍→
      **原本 SHA‑256 一致** + 圧縮率: C 版比は**バイト同一**（L2 の系譜、
      test_blob_parity が生産経路で再証明）。pytest 43 green +
      Rust L1 98 green
- [/] 完了条件: **L4/L5（互換帯）green** ✓（L5 = pip 版公式 zipnn 0.5.4
  実ビルドとの相互検証 `scripts/l5/official_cross.py` GATE PASS:
  Neo 圧縮→公式解凍 / 公式圧縮→Neo 解凍 / ブロブ字节同一 7/7。
  CI: integration ジョブ 3 OS + ubuntu フルマトリクス）、
  **K1 ✓**（限界 1.2×/0.8× vs レガシー 2.6×/1.7× — サイズ非依存設計
  → 12 GB 換算 <1 GB）・**K6 ✓**（端到端検証実装 + 全経路テスト）・
  **K13 ✓**（import 6 ms/44 MiB 不変を再確認）、**K2/K3 は
  参照機再計測待ち**（この SHA‑NI なし 2 vCPU 機では検証ハッシュが
  壁の ~85 % — sha2 soft ~156 MB/s 実測。検証 OFF なら解凍 ×1.18・
  圧縮 ×1.5–2.0（同一セッション比）。SHA‑NI + NVMe 外挿は
  K2 ×1.3–2.0 / K3 ×1.2–2.1 の**境界** — BENCH §7.1 の通り正直に
  記録し、参照機での `run_all.sh` 再計測を完了条件に残す）、
  手動 QA: 圧縮/解凍/進捗/キャンセルは自動化済み（ルート + ジョブ
  レベル、ws ゴールデン）。ディスク満杯（ENOSPC メッセージ経路 +
  tmp 自動削除は実装・単体検証、実容量注入は参照機 QA 手順書へ）と
  実 ComfyUI UI での QA はユーザ側手順として USAGE 更新時（Phase 7）
  に統合。UI 契約自体はゴールデンテストで機械的に固定済み

### Phase 3 — デルタ圧縮 + バッチプリミティブ

- [x] `delta.rs`: 両側 mmap + ストリーミング XOR + 1 MB チャンク
      ZN byte 形式（K4: ピーク RAM < 1 GB）— 出力は**公式 streaming
      コンテナ連鎖**（header[13]=148・[24:32]=コンテナサイズ —
      zipnn.py の streaming 形式そのもの。公式解凍側が 100 % 受理する
      ことを L5‑D1 で実証）。限界 RSS 実測 2.09×/1.69× だが内訳は
      **回収可能な mmap clean ページがほぼ全て**で、匿名域は
      O(1 MiB チャンク)（0.5 MiB 級ペアで限界 +3–4 MiB がスケーリング
      非依存の証左 — BENCH §8.1。legacy 5.43×/5.72× は匿名コピー）
- [x] ヘッダー等長化パディング + `.neo-delta.json` 互換
      （SHA‑256 記録を追加 = `ftSha256`（ft 原本ダイジェスト、圧縮と
      並行スレッドで算出）。復元時インライン検証（追加 I/O ゼロ）+
      不一致はデルタ保持 + `.corrupt` 退避。サイドカーはエンジンが
      原子コミット（delta 本体 → sidecar の順、失敗時はジョブ失敗 =
      ft 無傷）。エラーメッセージ文言互換維持 — data‑size 不一致 /
      length mismatch / 非デルタの 3 文言を逐語でゴールデンテスト化。
      **相互運用の一次ソース発見**: 公式デルタ文件的 method バイトは
      0–4 いずれでもあり得る（API 既定 AUTO=0・CLI 既定 HUFFMAN だが
      float32 byte コンテナは method によらず常に Huffman ペイロード・
      公式解凍は byte7 を読まない — upstream スクリプト取得 + pip 0.5.4
      実機で確認）→ デルタ復号のみ method ゲートを外す
      `decode_delta`（テンソル経路は B.1 の厳格ゲート維持。BENCH §8.3））
- [x] **付録 C の SEGFAULT ケース（total%256KB ∈ {1,2,3}）を
      デルタ端到端テストに固定化**（Rust 版が正常完了することを確認 —
      三層固定: L1 e2e（1 MiB streaming 境界跨ぎ 3 MiB+2 含む）+
      生産ルート pytest（ws 契約ごと）+ ベンチ証跡
      `k5AllSurvivedByteExact: true`。全ケース byte‑exact 往復）
- [x] `py/compress.py` デルタルート切替（`MM_NATIVE=0/1/auto`。ws 契約
      prepare/delta/done・`kind:"delta"`・stats キー
      originalBytes/compressedBytes は**両経路同一ゴールデン**。
      デルタタスクは cancel ルートでキャンセル可能に（handle 登録）、
      paranoid モード対応（rename 前の再デコード検証）。失敗時
      クリーンアップは「committed‑but‑sidecar‑less のみ dst 削除」=
      Phase 2 の教訓（並行ジョブ tmp 保護）を継承）
- [x] バッチプリミティブ（`walk_models` / `move_with_sidecars`）—
      バンドル意味論（`*_DeltaZNN`・type‑root 内包・legacy `_ZNN`）は
      Python 現行ロジックを維持（プリミティブは Python 現行関数との
      **ゴールデン parity テスト**付き: 3 walker × hidden/symlink/bundle
      網羅、20 スロット プレビュー + .md/.txt 規則。walk は ignore
      crate 並列 = os.walk 意味論の忠実移植、sorted 安定順）。
      バッチルートは native ジョブ（同期ポーリング、per‑file handle 登録で
      キャンセル可）+ Rust walk/sidecar move へ切替（MM_NATIVE 準拠）。
      フォルダバッチ往復（ツリー byte‑exact 復元）・デルタ入りバッチ・
      **両エンジン同一ツリー parity** をテスト化。同期プリミティブは
      `py.detach()` で walk/rename の全行程を GIL フリー実行（§4.2.2
      不変条件 2 — 2026‑09‑26 の独立監査で修正・A/B 実証:
      `test_walk_models_releases_the_gil` が GIL 解放を機械的に固定）
- [x] 完了条件: K4/K5 達成（BENCH §8: 限界 ÷2.6/÷3.4 + 匿名域
      サイズ非依存、SEGFAULT クラス 3/3 生存 + byte‑exact）、
      デルタ往復 byte‑exact（検証付き — verified=sha256 3/3 ラウンド +
      クロスパス双方向 + legacy 単一コンテナ復元）、
      フォルダバッチ圧縮/解凍の現行同一挙動 QA（自動 parity/ゴールデン
      済み — 実 ComfyUI UI での手動 QA は Phase 2 の残件と同様に
      USAGE 改訂（Phase 7）へ統合。UI 契約はゴールデンテストで機械固定）

### Phase 4 — dtype 大幅拡張（Neo 拡張帯）

- [ ] 8 平面分割/結合（N=8）+ f64 並べ替えの往復実証
- [ ] F64 / COMPLEX128 / BCOMPLEX32
- [ ] C64: 公式デコーダ可読性の実証 → 互換帯(9)/Neo 帯(130) 確定
- [ ] 整数系 I8/U8/I16/U16/I32/U32/I64/U64 + BOOL
      （トランケートモード 1/9/41/8 の正式実装 + ゼロ統計自動選択）
- [ ] FNUZ 系 FP8 / F8_E8M0 / F4 / F6_E2M3 / F6_E3M2
- [ ] `znn_neo_extended` マーカー + 公式 zipnn での失敗モード検証
      （明示エラーになることを確認）
- [ ] UI: dtype 内訳表示・Neo 拡張バッジ・確認文（i18n en/ja/zh）
- [ ] ドキュメント: 相互運用マトリクスを README / USAGE へ
- [ ] 完了条件: 全拡張 dtype 往復 green（K14）、L5 退行なし

### Phase 5 — スキャン/インデックス/ハッシュ/更新伝播

- [ ] `scan_models` Rust 化（並列 walk 実装を ignore vs dua-core で
      ベンチ確定）+ 現行 JSON 形状 golden テスト
- [ ] 永続インデックス（bincode + blake3 チェックサム、自動再構築）
- [ ] `scan_hygiene` Rust 化
- [ ] `safetensors_header` / `safetensors_tensor_tree` +
      `py/utils.py` の `get_model_metadata` / `get_model_tensors` 切替（B4）
- [ ] `hash_file` / `hasher_*`（B1/B2）+ `py/identify.py` 切替
      （Civitai 表記 golden テスト）
- [ ] Quick Win A2（ダウンロードチャンク拡大）+ インライン検証接続、
      `_sha256_of` フル再読込パス削除（K7）
- [ ] Quick Win A3（requests → aiohttp 統一、任意）
- [ ] `models_changed` ws 無効化 + フロント部分再取得
- [ ] （任意）`watch_roots` + 設定スイッチ
- [ ] 完了条件: K7–K11 達成、5,000 モデル合成ライブラリで QA、
      既存 UI 退行なし

### Phase 6 — フロントエンド表示最適化（計測駆動）

- [ ] C5 performance mark 計測基盤
- [ ] C1 正規表現ホイスティング
- [ ] C2 Intl.Collator 化（4 箇所）
- [ ] C3 shallowRef 化（影響棚卸し → 移行 → 計測）
- [ ] C4 `decoding="async"`
- [ ] テンソルツリー Rust 事前グループ化接続（MoE 実モデルで計測）
- [ ] 完了条件: K15 達成（検索 keystroke→描画 ≤16 ms P95、
      初回グリッド描画 ≤1 s、5,000 モデル）

### Phase 7 — third_party 撤去・配布仕上げ・リリース

- [ ] ゲート確認: L5 クロス検証 CI が 2 リリースサイクル連続 green
- [ ] `py/compress.py` 旧経路（ensure_zipnn L160–628 ほか）全削除
- [ ] `third_party/` 削除（LICENSE は `native/NOTICE` へ継承）
- [ ] `MM_NATIVE` スイッチ撤去（単一経路化）
- [ ] README / README‑JP / USAGE×3 の全面改訂
      （ZipNN 節を「純 Rust 実装」へ、対応 OS 表・相互運用マトリクス追加）
- [ ] pyproject / requirements 整理、`native-bin/README.md` 整備
- [ ] バイナリサイズ最終最適化（≤4 MB/本）
- [ ] （ストレッチ）自由スレッド Python 向け abi3t ビルド実験
- [ ] リリース v0.3.0（version.yaml / package.json / pyproject 同期）
- [ ] 完了条件: 全新規 clone（Linux/Windows/macOS）で
      コンパイラ・pip・ネットワークなしに ZipNN 機能が動作（K16）

## 6.3 進捗管理規程

- 着手時 `- [/]`、完了時 `- [x]`。§9 のマスターチェックリストと
  §6.2 の詳細チェックリストを**同一コミットで**更新する。
- 各フェーズは完了条件の充足を確認してから次へ進む（保守的進行）。
- KPI 未達・テスト red の状態でフェーズを閉じない。

---

# 7. リスク管理

| #   | リスク                                       | 確率 | 影響 | 緩和策                                                                                                                                                                      | 対応フェーズ |
| --- | -------------------------------------------- | ---- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| R1  | huff0 ポートのビットレベルバグ（静かな破損） | 中   | 大   | L2 差分テスト + L3 fuzz + `znn_neo_src_sha256` 端到端検証（破損は**検知される**）。third_party は Phase 7 まで保持                                                          | 1–7          |
| R2  | 公式 zipnn との非互換（エコシステム分断）    | 低   | 大   | 互換帯は L5 を CI ゲート化。拡張帯はマーキング + UI 明示 + 明示エラー（静かな破損なし）                                                                                     | 1,4          |
| R3  | abi3 バイナリの環境非互換（古い glibc 等）   | 中   | 中   | zigbuild glibc 2.28（現行 C の 2.34 要件より広い）、CI に旧環境スモーク、失敗時は明確なエラー表示                                                                           | 0,7          |
| R4  | Windows の mmap/ロック競合（AV・OneDrive）   | 中   | 中   | 読取専用共有 mmap、書込は tempfile+rename、Windows QA チェックリスト                                                                                                        | 2            |
| R5  | rayon が ComfyUI 推論と CPU 競合             | 中   | 中   | 専用プール + `min(cpu,16)` 既定 + 実行中スレッド半減オプション                                                                                                              | 2            |
| R6  | リポジトリ肥大（native-bin ≤20 MB）          | 中   | 小   | サイズ予算 CI ゲート。超過時は GitHub Releases 配信へ切替（ローダーに取得経路を設計時内蔵）                                                                                 | 0,7          |
| R7  | 永続インデックスの破損/陳腐化                | 低   | 小   | チェックサム + 世代番号。不一致時は自動全再構築（常に派生データ）                                                                                                           | 5            |
| R8  | shallowRef 移行による UI 退行                | 中   | 中   | 影響棚卸し先行・段階移行・計測比較。問題時は対象ストアのみロールバック                                                                                                      | 6            |
| R9  | PyO3/maturin の破壊的変更                    | 低   | 小   | Cargo.lock 同梱でピン留め、更新は専用 PR                                                                                                                                    | 全           |
| R10 | 上流 zipnn の将来フォーマット変更            | 低   | 中   | ヘッダーのバージョンバイト厳密検査、上流リリース監視の CI 定期ジョブ化                                                                                                      | 1,7          |
| R11 | f64 8 平面方式の圧縮率が期待未満             | 中   | 小   | 方式のモジュール化。目標は「破損せず現行（パススルー）以上」。測定後にトランケート等で改善                                                                                  | 4            |
| R12 | 既存デルタファイル（C 版生成）の復旧不能     | 低   | 大   | C 版の往復は非クラッシュケースで全て正しいことを実証済み（付録 C.3）。Rust 解凍器は C 出力を 100% 受理（L2/L5）。万一の不一致ファイルは `.corrupt` 退避で原本（base）を保持 | 3            |
| R13 | free-threaded Python 普及時の abi3 非対応    | 低   | 小   | PyO3 `abi3t-py315` 対応済み。需要確認後に追加ビルド（ストレッチ）                                                                                                           | 7            |

---

# 8. ライセンスとコンプライアンス

- 本リポジトリ: **GPL‑3.0‑only**（維持）。新規 Rust コードも GPL‑3.0‑only。
- `znn-codec/src/huf/` の FSE 由来部分: FiniteStateEntropy は
  **BSD‑2‑Clause OR GPL‑2.0** のデュアルライセンス →
  **BSD‑2 経路を選択**（GPL‑2.0‑only と GPL‑3.0‑only は非互換のため）。
  各ファイルに原典著作権表示 + SPDX + 変更履歴を付す。
- アルゴリズム/フォーマット参照: ZipNN（MIT）— `native/NOTICE` に帰属表示
  （現行 `third_party/LICENSE-zipnn.txt` から継承）。
- 論文: Hershcovitch et al., "ZipNN: Lossless Compression for AI Models"
  (arXiv:2411.05239) を README Credits に追記。
- 採用 crate（PyO3/rayon = MIT OR Apache‑2.0 ほか）はすべて
  GPL‑3.0 配布と両立（Apache‑2.0 は GPL‑3 互換）。
- 上流 zipnn の欠陥（付録 C）は**責任ある開示**として issue 報告を推奨
  （Phase 1 のタスクに組み込み済み）。

---

# 9. 進捗サマリー

> GitHub 上でチェックボックスとして追跡可能。詳細は §6.2。
> 更新時は本節と §6.2 を同一コミットで同期すること。

- [x] **調査・計画策定** — コードベース精読（README 全文 / py・src・third_party /
      C ソース読解）、技術調査（PyO3・maturin・mold・rayon・huff0 実装状況・
      safetensors 0.8・PyTorch 2.14 dtype・依存最新性監査）、
      **C コア欠陥の実機実証（付録 C）**、本計画書 v2.0 の策定
- [x] **Phase 0** — 基盤準備（ベンチ基盤・mold/rustfmt/clippy・abi3 疎通・Quick Win A1）
      完了 2026‑09‑23（`docs/BENCH.md`・`native/`・`py/native.py`・native.yml 全緑）
- [x] **Phase 1** — znn-codec フォーマット中核（ヘッダー/平面/huff0・FSE + L2/L3）
      **完了 2026‑09‑25**（実装・全性能ゲートは 2026‑09‑23）: L1 69 テスト緑・
      L2 フル 10,500 ケース GATE PASS（圧縮出力 C とバイト同一 9,880/9,880 =
      圧縮率恒等一致・付録 C クラス 495/495 安全処理）・L3 スモーク緑
      （実バグ 3 件検出→修正）・速度 **8/8 指標 ×1.09–1.81 で C 超え**
      （unsafe ゼロ）・clippy/fmt 緑・CI 全緑（native-diff / fuzz-smoke 新設）。
      fuzz ≥8h の初回実行: run 36088280583 で 4/5 緑 → blob_decompress の
      rss OOM（run 36114455354 でも再発）の**真因 = ハーネス threads=1 の
      per‑exec rayon プール churn**（ASan メタデータ ~35 B/exec 累積 —
      「アロケータのページ保持」の初診は誤り）を特定し、プール キャッシュ化
      （de1a153）で **run 36148521214 全 5 ターゲット 3h SUCCESS**
      （blob_decompress 1.9 億 execs・peak RSS 164 MB・クラッシュ 0）+
      l2‑full 緑 = 15 h バジェット消化（詳細は §6.2 完了条件・MEMO 同日）
- [/] **Phase 2** — safetensors 圧縮/解凍 + 完全性検証パイプライン + バックエンド接続
  **実装・自動 QA 完了 2026‑09‑24**: Rust パイプライン（mmap 単一
  書き込みパス・ピーク RAM O(最大テンソル)・SHA‑256 端到端検証・
  `.corrupt` 退避・paranoid・協調キャンセル）+ mm_core ジョブ API
  （api_version 2）+ ルート切替（ws/stats ゴールデン両経路一致）+
  起動時クリーンアップ。L4 pytest 43 緑・L1 98 緑・L5 公式 zipnn 0.5.4
  クロス検証 GATE PASS・L2 再実行 PASS・L3 5 ターゲット化。K1/K6/K13
  達成、**K2/K3 は参照機（NVMe + SHA‑NI）再計測待ち**（この 2 vCPU /
  SHA‑NI なし機では検証ハッシュ律速で ×0.46/×0.24 — 内訳実測と外挿は
  BENCH §7.1）。残るは参照機計測と実 UI 手動 QA のみ
- [x] **Phase 3** — デルタ（SEGFAULT 解消実証込み）+ バッチプリミティブ
      **実装・自動 QA 完了 2026‑09‑25**: 公式 streaming 形式（公式 zipnn
      0.5.4 と双方向クロス検証 — L5 セクション D 緑）+ ftSha256 端到端検証 +
      legacy 単一コンテナ復元 + エラー文言逐語互換 + バッチプリミティブ
      （walk_models / move_with_sidecars・Python 現行とのゴールデン parity）。
      **K4 達成**（限界 ÷2.6/÷3.4 — 匿名域 O(チャンク) のサイズ非依存、
      12 GB 換算 <1 GB）・**K5 達成**（付録 C SEGFAULT クラス 3/3 が生産
      ルートで生存 + byte‑exact — 三層テスト固定）。L1 132 緑・pytest 59 緑・
      L2 quick 再 PASS・L3 6 ターゲット化（delta_decompress 追加、スモーク
      122 k execs クラッシュ 0）・api_version 3（ローダー exact レンジ同期）。
      実 UI 手動 QA は Phase 2 残件と併せ Phase 7 で統合（BENCH §8）。
      **2026‑09‑26 独立監査で再検証**（dev の force‑push 巻き戻しから
      12 コミットを SHA 回収・マージ復元したツリーに対して）: L1 132 /
      pytest 60 / L2 quick 1,121 / L5 D 節 / K4・K5 再計測が全て一致し、
      `walk_models`/`move_with_sidecars` の GIL 解放不備（§4.2.2 不変条件 2）を
      修正 + 回帰テスト化（MEMO 同日）。**同日の最終バグチェック（第 2 独立
      セッション）で `delta_decompress` の verify スイッチ match 腕逆転を発見・
      修正**（`verify=false` + ftSha256 記録ありが「internal error」で失敗する
      潜在 API 欠陥 — 本番ルートは verify 既定 true のため無影響。pipeline.rs の
      `src_sha` ゲートと同型化 + 両腕の回帰テストで固定、L1 133。A/B 実証:
      修正前で FAIL・修正後 PASS）し、全ゲートを再検証して緑（clippy
      `-D warnings` / L1 133 debug+release / mm‑core 5 / pytest 60 /
      L2 quick 1,121 / L5 PASS / `.so` 2,375,264 B + GLIBC_2.28 検証 —
      MEMO 同日第 2 セッション）
- [ ] **Phase 4** — dtype 大幅拡張（Neo 拡張帯 + 相互運用マトリクス）
- [ ] **Phase 5** — スキャン/永続インデックス/ハッシュ/更新伝播（Quick Win A2/A3）
- [ ] **Phase 6** — フロントエンド表示最適化（C1–C5、計測駆動）
- [ ] **Phase 7** — third_party 撤去・配布仕上げ・v0.3.0 リリース

---

# 付録 A: 技術調査記録

> 確認日: すべて 2026‑09‑22。出典: crates.io API / docs.rs / PyPI JSON API /
> GitHub API / 公式ドキュメント（一次情報のみ）。

## A.1 Rust エコシステム

| crate                  | バージョン                  | 確認した事実                                                                                                                                                                                                   |
| ---------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pyo3                   | 0.29.2                      | 2026‑08‑05 リリース、DL 2.56 億、abi3-py310..py315、abi3t-py315、Rust ≥1.83、buffer モジュールは Limited API で Py3.11+                                                                                        |
| maturin                | 1.15.0                      | 2026‑08‑27。maturin-action / `generate-ci github`                                                                                                                                                              |
| mold                   | 2.42.1                      | 2026‑09‑11 リリース（rui314/mold releases/latest）                                                                                                                                                             |
| Rust stable            | 1.98.1                      | channel-rust-stable（2026‑09‑03）。1.90 以降 x86_64-linux 既定リンカーは rust-lld                                                                                                                              |
| rayon                  | 1.12.0                      | 2026‑04‑14                                                                                                                                                                                                     |
| cargo-zigbuild         | 0.23.4                      | 2026‑09‑02                                                                                                                                                                                                     |
| safetensors            | 0.8.0                       | 2026‑06‑09。Dtype 22 種（F4/F6_E2M3/F6_E3M2/F8_E8M0/FNUZ×2/C64/U16/U32/U64 含む）。`serialize` はキーソート（→ 自前 Writer 採用の根拠）、`serialize_to_file` は tempfile+rename+BufWriter 1MB、macOS F_NOCACHE |
| jiter                  | 0.17.0                      | 2026‑09‑12、DL 2,288 万（pydantic 系の高速 JSON）                                                                                                                                                              |
| simd-json              | 0.18.1                      | 2026‑08‑23（in‑place = 可変バッファ要件）                                                                                                                                                                      |
| serde_json             | 1.0.151                     | 2026‑07‑20                                                                                                                                                                                                     |
| blake3                 | 1.8.7                       | features: rayon / mmap / pure / avx512 / neon / traits-preview                                                                                                                                                 |
| sha2                   | 0.11.0                      | 2026‑03‑25、DL 9.65 億                                                                                                                                                                                         |
| crc32fast              | 1.5.2                       | 2026‑09‑12（SIMD）                                                                                                                                                                                             |
| memmap2                | 0.9.11                      | 2026‑06‑22                                                                                                                                                                                                     |
| ignore                 | 0.4.33                      | 2026‑08‑04、DL 1.76 億（ripgrep の並列 walker）                                                                                                                                                                |
| jwalk                  | 0.9.0                       | description が「Use `dua-core` instead」= 事実上 maintenance                                                                                                                                                   |
| dua-core               | 4.1.0                       | 2026‑09‑12（jwalk 後継）                                                                                                                                                                                       |
| walkdir                | 2.5.0                       | 直列 walk（比較用）                                                                                                                                                                                            |
| notify                 | 8.2.0                       | 2026‑08‑30                                                                                                                                                                                                     |
| notify-debouncer-full  | 0.7.0                       | 2026‑05‑02                                                                                                                                                                                                     |
| bincode                | 3.0.0 → **2.0.1 採用**      | 3.0.0（2025‑12‑16）はコンパイル不能プレースホルダ（xkcd 2347 スクワットガード）と Phase 0 で一次確認 → 実体安定版 2.0.1（2025‑03‑10）を採用                                                                    |
| postcard               | 1.1.3                       | 2025‑07‑24（bincode の代替候補）                                                                                                                                                                               |
| rusqlite               | 0.40.2                      | 確認のみ — SQLite(C) 混入のため**不採用**                                                                                                                                                                      |
| numpy                  | 0.29.0                      | PyO3 0.29 対応（本計画では不使用）                                                                                                                                                                             |
| half                   | 2.7.1                       | f16/bf16                                                                                                                                                                                                       |
| bytemuck               | 1.25.2                      | 2026‑07‑19                                                                                                                                                                                                     |
| pyo3-async-runtimes    | 0.29.0                      | 2026‑08‑28（第 1 版不使用）                                                                                                                                                                                    |
| ruzstd                 | 0.9.0                       | 2026‑07‑26。デコーダ完全/エンコーダ部分（level 1 相当）。huff0/FSE は非公開                                                                                                                                    |
| libzstd-bitexact-rs    | 0.157.0                     | 2026‑06‑15 初版、BSD‑3、DL 918、1.3 万行（参照用途のみ）                                                                                                                                                       |
| zstd / zstd-safe       | 0.14.0 / 8.0.0              | C バインディング（HUF_* 非公開 → 不採用）                                                                                                                                                                      |
| yaml-rust2             | 0.13.0                      | 2026‑09‑11（保守中）                                                                                                                                                                                           |
| serde_yaml             | 0.9.34+deprecated           | 2024‑03 最終。**deprecated**。serde_yml 0.0.13 も deprecated                                                                                                                                                   |
| image                  | 0.25.10                     | WebP エンコードは LOSSLESS のみ                                                                                                                                                                                |
| webp                   | 0.3.1                       | libwebp C バインディング（不採用）                                                                                                                                                                             |
| huff0 / huffman-coding | 0.1.0 (2018) / 0.1.2 (2017) | 死蔵 → 自社ポート決定                                                                                                                                                                                          |

## A.2 ZipNN / PyTorch / 既存依存

- 上流 `zipnn/zipnn`: **0.5.4（2026‑04‑11）が最新**（GitHub main の最終タグ
  「version 0.5.4」）。csrc は dtype16/dtype32 のみ。0.5.3=FP8、
  0.5.4=ゼロコピー返却 + リーク修正（README Change Log）。
  同梱 C ソースは上流とファイルサイズ完全一致（欠陥も共通 → 付録 C）。
- FSE 定数: `HUF_BLOCKSIZE_MAX=128*1024`、`HUF_TABLELOG_MAX=12`、
  `HUF_TABLELOG_DEFAULT=11`（同梱 huf.h L72/L117/L118）。
- PyTorch 2.14（stable docs、2026‑05‑08 作成/06‑15 更新）: float8_e4m3fn/
  e5m2/e4m3fnuz/e5m2fnuz/e8m0fnu、float4_e2m1fn_x2、bcomplex32、
  complex32/64/128、uint16/32/64、シェル dtype（uint1–7、float6_*_pe）。
- PyPI（2026‑09‑22）: huggingface_hub 1.32.0 / hf_xet 1.6.0 /
  modelscope_hub 0.4.5 / markdownify 1.2.3 / safetensors 0.8.0 /
  blake3 1.0.9 — いずれも現行指定の範囲内または最新（§1.4）。
- 公式スクリプト `zipnn_compress_safetensors.py`（上流 main）を精読し、
  Neo 移植（`py/compress.py`）が同一セマンティクス
  （clone → compress → 非圧縮判定 → uint8 ベクトル化 →
  `znn_compressed_vectors`）であることを確認済み。
- google/granary は 404（存在せず）→ PyO3 対抗馬の不在を確認。

---

# 付録 B: ZipNN バイトフォーマット仕様

## B.1 ZN ヘッダー（32 バイト。`zipnn.py` L355–440）

| offset                                                   | サイズ | 内容                                                                                    |
| -------------------------------------------------------- | ------ | --------------------------------------------------------------------------------------- |
| 0–1                                                      | 2      | magic `"ZN"`                                                                            |
| 2–4                                                      | 3      | version major/minor/tiny（0.5.4）                                                       |
| 5                                                        | 1      | byte_reorder（220=4 平面 / 10=2 平面・1 平面 / truncate 系 1,9,41,8）                   |
| 6                                                        | 1      | bit_reorder（1=符号/指数並べ替えあり）                                                  |
| 7                                                        | 1      | method（1=HUFFMAN のみ必須。他は明示エラー）                                            |
| 8                                                        | 1      | input_format（1=BYTE / 2=TORCH / 3=NUMPY）                                              |
| 9                                                        | 1      | delta_compressed_type（0/1=byte/2=file）                                                |
| 10–12                                                    | 3      | lossy 系（常に 0。非ゼロはエラー）                                                      |
| 13                                                       | 1      | streaming（MSB）+ log2(streaming_chunk)                                                 |
| 14                                                       | 1      | log2(compression_chunk)（既定 18 = 256 KB）                                             |
| 15                                                       | 1      | dtype コード（§4.6.3）                                                                  |
| 16–23                                                    | 8      | original_len（u64 LE）                                                                  |
| 24–31                                                    | 8      | comp_len+32（BYTE 単一グループ経路のみ書込。zipnn_core 経路では 0。解凍側は参照しない） |
| 32–                                                      | 可変   | packed shape（TORCH/NUMPY のみ。dim 数 + 各 dim                                         |
| （1/2/4/8 バイト幅プレフィックス、`zipnn_pack_shape`）） |

## B.2 ペイロード（zipnn_core 出力レイアウト）

```
[chunkTypes : numBuf × numChunks × u8]      # 0=生, 1=huff0
[cumSizes   : numBuf × numChunks × u64 LE]  # 平面ごとの累積サイズ
[data       : 平面0 全チャンク | 平面1 … | …]
```

- チャンク i・平面 b のペイロード =
  `data[bufOffset[b] + cumSizes[b][i-1] .. bufOffset[b] + cumSizes[b][i]]`
  （`cumSizes[b][-1] = 0`）。
- type=1 の実体 = RFC 8878 §4.2.1 の huff0 ブロック
  （Huffman_Tree_Description + jump table(4X) + ビットストリーム）。
- **64 ビット専用**（cumSizes が size_t=8B 前提。C と同一制約）。

## B.3 Neo 上位層（safetensors ラッパー）

- 圧縮テンソルは dtype=U8 の 1‑D ベクトル。
- `__metadata__` キー:
  - `znn_compressed_vectors` = `{"<name>": {"dtype": "bfloat16", "shape": "[1, 2]"}}`
    （公式 `METADATA_KEY` と同一形式）
  - `znn_neo_original_bytes` = 圧縮前ファイルサイズ（現行互換）
  - `znn_neo_src_sha256` = 原本ファイル SHA‑256（**新設**、§4.4.3）
  - `znn_neo_extended` = `"1"`（Neo 拡張 dtype を含む場合のみ）
- ファイル名: `<base>.znn.safetensors`（公式と同一）。
- デルタ: `<base>_DeltaZNN/<ft>_delta_<base>.znn` +
  `….znn.neo-delta.json`（`{"basePad": n, "ftPad": m, "ftSha256": "…"}` ←
  3 番目のキーを新設）。

---

# 付録 C: C コア欠陥の再現手順と実証結果

## C.1 検証環境

- リポジトリ同梱 `third_party/zipnn-core-bin/linux-x86_64/
zipnn_core.cpython-311-x86_64-linux-gnu.so`
- Python 3.11.2（Linux x86_64）、`zipnn_core` を直接 import
  （`zipnn_core(header, data, num_buf, bits_mode, bytes_mode, is_review,
chunk, threshold, check_th, threads)` /
  `combine_dtype(payload, num_buf, bits_mode, bytes_mode, chunk, orig_len,
threads)`）
- 入力バッファは `bytearray` で渡す（C コアは reorder で**入力を
  in‑place 破壊する**ため。Neo Python 層が `tensor.clone()` する理由と同一）。

## C.2 再現手順（最小ケース）

```python
import sys; sys.path.insert(0, "third_party/zipnn-core-bin/linux-x86_64")
import zipnn_core, os
H = b"ZN" + bytes(30)
for L in (262144 + 1, 262144 + 2, 262144 + 3):   # ← 各実行で SEGFAULT
    data = bytearray(os.urandom(L))
    comp = zipnn_core.zipnn_core(H, data, 4, 1, 220, 0, 262144, 0.95, 10, 1)
```

## C.3 実測結果（2026‑09‑22、サブプロセス分離・全 30+ ケース）

| 入力長（dtype32 経路: num_buf=4, bits=1, bytes_mode=220）                     | 結果                                                        |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------- |
| 64–67、1,000,000–1,000,003、262,148–262,152（%4=0–3 含む・最終チャンク ≥4 B） | **往復一致 OK**                                             |
| 262,144（チャンク境界ちょうど）                                               | OK                                                          |
| **262,145 / 262,146 / 262,147**（最終チャンク 1/2/3 B）                       | **SEGFAULT（exit 139、100% 再現）**                         |
| **524,289 / 524,290 / 524,291**（2 チャンク目境界 +1/2/3 B）                  | **SEGFAULT**                                                |
| ランダム（非圧縮チャンク）・低エントロピー（huff0 チャンク）の別              | 結果に差なし                                                |
| dtype16 経路（num_buf=2, bytes_mode=10）: 262,144 / 262,146 / 1,000,002       | OK                                                          |
| dtype16 奇数長（65 / 262,145。Neo 使用経路では到達しない）                    | OK（ただしソース解析上、境界外読取 + 超過書込の UB を確認） |

## C.4 原因解析（C ソースの読解による）

`handle_split_mode_220`（`data_manipulation_dtype32.c` L78–133）:

1. **SEGFAULT（NULL 参照）**: 最終チャンク長 < 4 のとき
   `bufLens` の一部が 0 → `allocate_4chunk_buffs` が該当プレーンを
   **NULL** のまま返し、主ループ
   `for (i=0; i<total_len; i+=4) { *dst1++=…; *dst2++=…; *dst3++=…; *dst4++=…; }`
   が NULL プレーンへ無条件書込 → SIGSEGV。
2. **ヒープオーバーフロー + 境界外読取**: 最終チャンク長 % 4 ≠ 0 のとき、
   主ループの最終反復が `src[total_len .. total_len+2]` を読み
   （境界外読取）、サイズ不足のプレーンへ超過書込。加えて switch の
   フォールスルーと後続 if ブロックが**論理レイアウト外の位置へ
   追加書込**（1–3 バイトのヒープオーバーフロー）。
   glibc のアロケーションスラックに吸収され通常は無症状だが、
   未定義動作であり長時間稼働プロセスでの蓄積リスクは評価不能。
3. **データの正しさ**: 超過書込バイトは `combine_buffers_dtype32` が
   読み取らない（in‑bounds のみ読む）ため、**クラッシュしない全ケースで
   往復データは正しい**（C.3 の実測と一致）。したがって Rust 移植は
   「clean deinterleave + 安全な端数処理」で **in‑bounds レイアウトが
   C とバイト同一**となり、双方向フォーマット互換が成立する。

## C.5 Neo への影響評価

| 経路           | 到達可能性 | 影響                                                                                                                                                                                           |
| -------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 単体圧縮/解凍  | なし       | テンソル長は要素サイズの倍数（f32: %4=0、bf16/f16: %2=0、fp8: 1 平面）で SEGFAULT 条件に到達しない。UB オーバーフローも f32 の %4=0 により発生しない                                           |
| **デルタ圧縮** | **あり**   | パディング後ファイル長は任意。(a) `%256KB ∈ {1,2,3}` → **ComfyUI プロセス SEGFAULT**（確率 ≈1.1×10⁻⁵/回、稀だが致命的・Python 例外化されない）、(b) `%4 ≠ 0`（≈75%）→ 毎回の UB オーバーフロー |
| デルタ解凍     | 低         | (a) のファイルは圧縮時に生成されないため通常は到達しないが、悪意ある細工ファイルで同種の UB に到達し得る → Rust 解凍器の敵対的入力硬化（§4.4.2）で対処                                         |

なお本欠陥は上流 zipnn 0.5.4 にも存在する（C ソースのファイルサイズが
上流と完全一致）。Phase 1 で上流へ責任ある開示（issue 報告）を行う。

---

# 付録 D: 用語集

| 用語            | 意味                                                                             |
| --------------- | -------------------------------------------------------------------------------- |
| abi3            | CPython Stable ABI。1 バイナリが指定版以降の全 CPython で動作する仕組み          |
| huff0           | zstd 系の Huffman ブロック形式（RFC 8878 §4.2）。ZipNN のペイロード符号          |
| FSE             | FiniteStateEntropy（tANS）。huff0 の重みテーブル符号化に使用                     |
| 平面分割        | 値のバイト位置ごとに分離して類似バイトを集約する ZipNN の前処理（byte grouping） |
| ビット並べ替え  | 浮動小数の符号ビットを指数部隣接位置へ移す可逆全単射変換（圧縮率向上）           |
| ゼロコピー      | データの複製なしにバッファ参照のみで処理すること。本計画では mmap 中心設計       |
| GIL             | CPython のグローバルインタプリタロック。Rust 長時間処理中は解放する              |
| mmap            | ファイルを仮想アドレス空間へ写像する I/O（memmap2 crate）                        |
| byte‑exact 復元 | 解凍結果が原本とバイト単位で一致すること（SHA‑256 で毎回検証）                   |
| 差分テスト      | C 実装と Rust 実装の出力・復号結果を突き合わせる検証手法                         |
| Quick Win       | Rust 化を待たず Python/TS 側だけで実施できる即時改善                             |
| KPI             | §2.2 の定量目標。フェーズ完了判定に使用                                          |

---

_本計画書は 2026‑09‑22 の一次情報調査と実機検証に基づく。
実装フェーズ着手前に依存 crate の破壊的変更有無を再確認し、
Cargo.lock でピン留めすること。_
