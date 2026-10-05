> [!CAUTION]
> **本プロジェクトはまだ開発中であり、現時点では一般の使用は推奨しません。**
> 予期せぬバグが発生する可能性があり、機能を追加している途中のため、
> 中途半端な成果物が含まれている場合があります。インターフェースも今後
> 変わり続ける可能性があります。一方で、フィードバックや Issue の報告は
> 大歓迎です。

<div align="center">

# <img src="https://api.iconify.design/lucide/boxes.svg?color=%236366f1" width="41" height="41" align="middle" alt=""> ComfyUI‑Model‑Manager‑Neo

### 閲覧・ダウンロード・アップロード・ドラッグ＆ドロップ — モデルを、美しく管理。

ComfyUI のモデルマネージャーを **Vue 3 + Tailwind CSS v4 + reka‑ui** で
再構築し、モダンなグラスモフィズム UI へ再設計したフォークです。ZipNN
圧縮エンジンを含むすべてのホットパスを、**プリビルドの純 Rust コア**が
実行します。

![Version](https://img.shields.io/badge/version-0.3.0-6366f1.svg)
![License](https://img.shields.io/badge/License-GPL--3.0--only-blue.svg)
![ComfyUI](https://img.shields.io/badge/ComfyUI-Custom%20Node-8A8B98.svg)
![CI](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/actions/workflows/ci.yml/badge.svg?branch=main)
![Native core](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/actions/workflows/native.yml/badge.svg?branch=main)
![ZipNN](https://img.shields.io/badge/ZipNN-Rust_reimplementation-0ea5e9.svg)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?logo=python&logoColor=white)
![Rust](https://img.shields.io/badge/Rust-1.85%2B_%C2%B7_edition_2024-DEA584.svg?logo=rust&logoColor=black)
![PyO3](https://img.shields.io/badge/PyO3-0.29_%C2%B7_abi3--py312_%2B_abi3t--py315-229988.svg)
![Free-threaded](https://img.shields.io/badge/CPython-3.15%2B_free--threaded_%28abi3t%29-229988.svg?logo=python&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D.svg?logo=vuedotjs&logoColor=white)
![reka-ui](https://img.shields.io/badge/reka--ui-2-16A353.svg?logo=rekaui&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6.svg?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38BDF8.svg?logo=tailwindcss&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8_%C2%B7_Rolldown-646CFF.svg?logo=vite&logoColor=white)
![ESLint](https://img.shields.io/badge/ESLint-10-4B32C3.svg?logo=eslint&logoColor=white)
![Prettier](https://img.shields.io/badge/Prettier-3-F7B93E.svg?logo=prettier&logoColor=black)
![Stylelint](https://img.shields.io/badge/Stylelint-17-263238.svg?logo=stylelint&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-0.16.9-D7FF64.svg?logo=ruff&logoColor=black)
![Node](https://img.shields.io/badge/Node-26-339933.svg?logo=nodedotjs&logoColor=white)
![pnpm](https://img.shields.io/badge/pnpm-12-F69220.svg?logo=pnpm&logoColor=white)
![uv](https://img.shields.io/badge/uv-dev_%26_CI-DE5FE9.svg?logo=uv&logoColor=white)

![Linux x86_64](https://img.shields.io/badge/Linux-x86__64-FCC624.svg?logo=linux&logoColor=black)
![Linux aarch64](https://img.shields.io/badge/Linux-aarch64-FCC624.svg?logo=linux&logoColor=black)
![macOS universal2](https://img.shields.io/badge/macOS-Intel_%2B_Apple_Silicon-000000.svg?logo=apple)
![Windows x64](https://img.shields.io/badge/Windows-x64-0078D6.svg?logo=windows&logoColor=white)

[English](README.md) · **日本語** · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

![Hero overview](demo-assets/hero.webm)

</div>

---

**目次**

- [Why Neo?](#why-neo) · [スクリーンショット](#screenshots) · [インストール](#installation) ·
  [機能](#features)
- [モデル検索とマルチプラットフォーム探索](#search) · [ZipNN 可逆圧縮](#zipnn) ·
  [元版からの変更点](#what-changed) · [削除された機能: バッチスキャン](#removed-feature)
- [ドキュメント](#documentation) · [開発](#development) ·
  [クレジットと帰属](#credits) · [ライセンス](#license)

---

<a id="why-neo"></a>

## <img src="https://api.iconify.design/lucide/sparkles.svg?color=%23f59e0b" width="34" height="34" align="middle" alt=""> Why Neo?

**ComfyUI‑Model‑Manager‑Neo** は、優れた元祖マネージャーを受け継ぎながら、
体験を根底から作り直したものです:

**1. Neo の新機能**

- <img src="https://api.iconify.design/lucide/cpu.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **Rust ネイティブコア** — ライブラリスキャン・ハッシュ・safetensors ヘッダ
  解析・テンソルツリー・フォルダ監視・プレビュー WebP codec・ZipNN エンジン
  全体が、リポジトリ同梱の**プリビルド Rust 拡張**で動きます（4 プラットフォーム ×
  Stable ABI 2 フレーバ: GIL build は abi3 = CPython 3.12 以降、フリースレッド build は
  abi3t = CPython 3.15 以降・PEP 803、各 1 バイナリ）。コア自体は素の
  `import` だけでロードされます — **コア単体にコンパイラも pip パッケージも
  ダウンロードも不要**です（拡張機能の Python ハブ依存 4 点は従来どおり
  初回起動時に自動インストールされます）。純 Python の元実装との実測比較:
  5,000 モデルのスキャンがコールドで約 **7.5 倍**高速（ウォームは 100 ms 未満）、
  5 表記のハッシュを **1 パス**で計算、65,000 テンソルの MoE テンソルツリー構築が
  約 **100 倍**高速、ZipNN 圧縮はモデルの大きさを問わず**ピーク RAM 1 GB 未満**
  （証跡: [`docs/BENCH.md`](docs/BENCH.md)）。
- <img src="https://api.iconify.design/lucide/shield-check.svg?color=%2322c55e" width="19" height="19" align="middle" alt=""> **検証付きでメモリ安全な圧縮** — Rust エンジンは lint で `unsafe` を
  deny しています: フォーマット中核は `unsafe` ゼロ、必要となる唯一の境界
  （読み取り専用のメモリマップ）は SAFETY レビュー済みで文書化されています。
  7 本の継続的ファジングターゲットで強化され、復元のたびに、圧縮時に
  記録した SHA‑256 との照合が走ります。公式 `zipnn` 0.5.4 とのフォーマット互換は
  約束ではなく CI ゲートです — push のたびに双方向でクロス検証されます。
- <img src="https://api.iconify.design/lucide/package-plus.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **ZipNN 可逆圧縮** — safetensors モデルをその場で圧縮/解凍
  （`.znn.safetensors`）、フォルダ単位では密封された `<name>_DeltaZNN` バンドルへ
  バッチ圧縮、ファインチューンはベースモデルとの極小**デルタファイル**へ。
- <img src="https://api.iconify.design/lucide/upload-cloud.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **Hugging Face / ModelScope へアップロード** — ローカルモデルを HF または
  ModelScope のリポジトリへ直接公開（必要ならリポジトリ作成、プライベート指定、
  関連アセット同梱、ライブ進捗表示）。ModelScope はダウンロード・アップロード・
  検索・認証まで、すべて Neo での新規実装です。
- <img src="https://api.iconify.design/lucide/radar.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **マルチハブ検索とハッシュ識別** — 1 つの入力欄から Hugging Face・
  ModelScope・Civitai を並列検索でき、ローカルファイルをハッシュで Civitai
  カタログに逆引きできます。
- <img src="https://api.iconify.design/lucide/list-checks.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **複数選択** — モデル/フォルダカードにチェックを入れて、ワークフローへ
  一括追加、または一括削除。
- <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="19" height="19" align="middle" alt=""> **スター** — 全カードのスタートグル。スター済みは常に先頭へ並びます。
- <img src="https://api.iconify.design/lucide/folder-plus.svg?color=%2322c55e" width="19" height="19" align="middle" alt=""> **フォルダ作成** — フォルダビューの「フォルダを追加」ボタン。
- <img src="https://api.iconify.design/lucide/link.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **直接リンクダウンロード** — 生の `.safetensors` / `.ckpt` / `.gguf` URL を
  貼り付け、保存先フォルダと任意のサブフォルダを選択できます。
- <img src="https://api.iconify.design/lucide/zap.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **`hf_xet` アクセラレーション** — Hugging Face 転送は、利用可能な場合
  チャンク分割・重複排除された Xet プロトコルを使用します。
- <img src="https://api.iconify.design/lucide/languages.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **日本語・繁體中文ロケール** — English・簡体中文に加え、完全な日本語
  バンドルと繁體中文（zh-TW）バンドルを追加。UI は ComfyUI 自身の言語
  設定に追従し、リージョンサブタグ（`ja-JP` 等）は基底部言語へ折りたたまれ、
  Hant 書記系タグ（`zh-Hant`・`zh-Hant-TW` 等）は繁體中文バンドルを
  選択します。

**2. 刷新・強化されたポイント**

- <img src="https://api.iconify.design/lucide/layers.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **グラスモフィズム UI** — 半透明・ぼかし・奥行き対応のインターフェース。
  ComfyUI 自身のライト/ダークパレットに自動で追従します。
- <img src="https://api.iconify.design/lucide/puzzle.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **Reka-UI への全面刷新** — PrimeVue 依存は軽量でヘッドレスな
  **[reka-ui]** プリミティブ + **Tailwind CSS v4** + **[Lucide]** アイコンへ
  置き換わりました（ソースを読んで調整できる shadcn-vue スタイルの
  コンポーネント群）。
- <img src="https://api.iconify.design/lucide/workflow.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **第一級のノードグラフ統合** — モデルをキャンバスへドラッグしてノードを
  生成/入力、embedding をテキストエリアへドラッグ、プレビュー画像に埋め込まれた
  ワークフローの読込。
- <img src="https://api.iconify.design/lucide/monitor-smartphone.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **レスポンシブ** — デスクトップ・モバイル・マルチスクリーン環境を想定した設計。
- <img src="https://api.iconify.design/lucide/wrench.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **現代的なツールチェーン** — Vite 8（Rolldown）、TypeScript 6、ESLint 10
  flat config、Prettier、Stylelint、Ruff、clippy、husky + lint‑staged。
  決定的で lint クリーンなビルド。

> [!NOTE]
> Neo は [`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
> の**フォーク**であり、同じ **GPL‑3.0** ライセンスで配布されます。
> 元のアーキテクチャに関するすべてのクレジットは原著作者に帰します —
> [クレジット](#credits)を参照してください。

---

<a id="screenshots"></a>

## <img src="https://api.iconify.design/lucide/camera.svg?color=%238b5cf6" width="34" height="34" align="middle" alt=""> スクリーンショット

### 1. フラット「モデル」ビュー — 検索・並び替え・グリッドサイズ変更

![Flat models grid](demo-assets/view-flat.avif)

**フラット**レイアウトのマネージャーウィンドウ: ガラス製のモデルカードのグリッド
（プレビュー・種別とサイズのチップ付き）、検索バー、種別/並び替え/カードサイズの
セレクタ。

### 2. フォルダ（エクスプローラ）ビュー — ディレクトリツリーを辿る

![Folder explorer view](demo-assets/view-folders.avif)

**フォルダ**レイアウトの 1 階層目。ブレッドクラムと、ポインターを休ませると
ふわりとフロートするペールターコイズのガラスフォルダカード。

### 3. モデル詳細・編集・Hugging Face アップロード

|                                                                              |                                                                                                        |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| ![Model info](demo-assets/model-info.avif)                                   | ![Edit mode](demo-assets/model-edit.avif)                                                              |
| _モデル情報: プレビュー、基本情報テーブル、Description / Information タブ。_ | _編集モード: 種別ドロップダウン、フォルダピッカーボタン、`folder/name` 接頭辞を受け付けるファイル名。_ |

|                                                                                                |                                                                                                |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| ![Hugging Face upload](demo-assets/hf-upload.avif)                                             | ![Japanese UI](demo-assets/ja-model-info.avif)                                                 |
| _Hugging Face へアップロード、ステップ 3: リポジトリ ID、作成時プライベート指定、保存先パス。_ | _同じウィンドウの**日本語**表示 — UI は English / 中文（簡繁）/ 日本語 の完全バンドルを同梱。_ |

### 4. モデル名検索と safetensors テンソルツリー

|                                                                                                               |                                                                                                              |
| ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| ![マルチプラットフォーム検索](demo-assets/search-columns.avif)                                                | ![テンソルツリー](demo-assets/tensor-tree.avif)                                                              |
| _1 つのクエリで 3 ハブ: Hugging Face / ModelScope / Civitai の列にアバター・ダウンロード数・ディープリンク。_ | _Information タブは safetensors ヘッダを折りたたみ可能なフォルダツリーで描画（Hugging Face ビューア様式）。_ |

10 秒間のツアーは [`demo-assets/hero.webm`](demo-assets/hero.webm) です。

---

<a id="installation"></a>

## <img src="https://api.iconify.design/lucide/rocket.svg?color=%2322c55e" width="34" height="34" align="middle" alt=""> インストール

Neo は ComfyUI のカスタムノードとして動作します。いずれかの方法で導入してください:

**1 · Git クローン（アップデート推奨）**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/rikunarita/ComfyUI-Model-Manager-Neo.git
```

**2 · 手動ダウンロード**

[リポジトリのアーカイブ](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/archive/refs/heads/main.zip)
をダウンロードして `ComfyUI/custom_nodes/` に展開し、フォルダ名が
`ComfyUI-Model-Manager-Neo` であることを確認してください。

**3 · ComfyUI レジストリ（ComfyUI Manager / CLI）**

Neo は ComfyUI レジストリに
[`comfyui-model-manager-neo`](https://registry.comfy.org/publishers/rikunarita7669/nodes/comfyui-model-manager-neo)
として公開されています: [ComfyUI-Manager] で
**“ComfyUI‑Model‑Manager‑Neo”** を検索するか、公式 CLI から
インストールできます:

```bash
comfy node install comfyui-model-manager-neo
```

その後 **ComfyUI を再起動**してください。Python 依存
（`huggingface_hub`・`hf_xet`・`modelscope_hub`・`markdownify`）は初回起動時に
自動インストールされます。Web バンドルは [`web/`](web) に、Rust コアは
[`native/native-bin/`](native/native-bin) にビルド済みで同梱されているため、
拡張機能の_実行_に Node.js もコンパイラも不要です — コアのロードは単なる
`import` です（対応プラットフォームは[エンジンの表](#the-engine)参照）。

マネージャーは、トップバーの **「Model Manager Neo」** ボタン、サイドバー、
`Extensions → Model Manager Neo` メニュー、またはコマンドパレットから開きます。

---

<a id="features"></a>

## <img src="https://api.iconify.design/lucide/list-checks.svg?color=%233b82f6" width="34" height="34" align="middle" alt=""> 機能

<details open>
<summary><b>閲覧と整理</b></summary>

- 2 つのレイアウト: **フラット**グリッド（既定）と**フォルダ**エクスプローラ。
  いつでも切り替え可能。
- リアルタイム検索（`*` ワイルドカードと複数トークンの AND 一致に対応）。
- 並び替え: 名前 / サイズ / 作成日 / 更新日 / **最近使用**
  （モデルを開くかグラフへ追加すると記録されます）。
- カードサイズ調整（プリセット + 完全カスタム寸法）。
- 隠しファイル（`.` 始まり）の表示/非表示を再起動なしで切替。
- 画像**と動画**のプレビュー（フルスクリーンの**ライトボックス**で拡大表示）、
  ホバーでふわりとフロートするペールターコイズのガラスフォルダアートワーク、
  ガラス製のプレビュー欠落フォールバック。
- 種別ルートフォルダカードはその**種別の合計サイズ**を表示
  （軽量な容量ダッシュボード）。記録済み SHA256 がライブラリ内の別ファイルと
  一致するモデルは、詳細ウィンドウに赤い**重複警告**を出します。
- 種別ルートの下へ格納されたモデルカードは、名前の上に**サブディレクトリ**を
  表示します（両レイアウト共通）。
- **スマートコレクション** — フラットビューの現在の検索 + 種別フィルタを
  名前付きのユーザー毎コレクションとして保存し、ワンクリックで再適用。
  保存と適用は 1 つのピルボタンに集約され、フロッピー部分が保存ダイアログ、
  残りが適用/切替メニューを開きます。
- **衛生スキャン** — 孤立プレビュー/ノート・プレビュー欠落モデル・空フォルダを
  探すローカル専用の一斉検査（ネットワーク/ハッシュ計算なし）。
  一括削除はいつもの確認ダイアログ経由です。
- **任意のフォルダ監視** — 既定 OFF のネイティブ監視を有効にすると、他の
  プログラムがモデルを追加/削除したとき、影響を受けた一覧が約 1.5 秒で
  更新されます。

</details>

<details>
<summary><b>ノードグラフ統合</b></summary>

- モデルサムネイルをキャンバスへドラッグして**ローダーノードを追加**。
- 既存ノードへドラッグして**一致する入力へ投入**（曖昧な場合は正確に）。
- **embedding** をテキストエリアへドラッグして `(embedding:name:1.0)` を追記。
- プレビュー画像をグラフへドラッグして**埋め込みワークフローを読込**。
- **追加** / **コピー** ボタンでノード配置、または ComfyUI のクリップボードへ複製。

</details>

<details>
<summary><b>ダウンロード</b></summary>

- **Civitai**・**Hugging Face**・**ModelScope**（`www.modelscope.ai`）・
  **直接ファイル** URL を貼り付け — あるいはモデル**名**を入力すれば
  3 ハブを並列検索します。
- Civitai ミラーホスト `civitai.red` のページ URL は Civitai と完全に同一扱い
  （保存されるモデルページは貼り付けたホストを維持）。
- ページごとの複数ファイル/バージョンを解決して、欲しいものを選択。
- 直接リンクは明示的な種別指定が必須。任意のカスタムサブフォルダも指定可能。
- プレビュー画像は任意 — モデルページが提供する**ギャラリー全体**が保存され、
  ダウンロード時に選択していた画像がカードのメインプレビューになります。
  Markdown 説明も編集可能です。
- **空き容量ガード**: ダイアログは保存先ボリュームの空き容量を表示し、
  宣言サイズが収まらないタスクはバックエンドが拒否します。
- タスクの一時停止 / 再開 / 削除。進捗・速度・サイズはライブ更新。
- Hugging Face ダウンロードは `huggingface_hub`（+ 利用可能なら `hf_xet`）。
- Civitai ダウンロードは完了時に SHA256 検証、ファイル種別に応じた自動振り分け、
  ベースモデル不一致と実行形式ペイロードの警告を備えます。

</details>

<details>
<summary><b>アップロード</b></summary>

- **ローカルファイルから**任意のモデルフォルダへ（Download List に
  進捗付きのライブタスクとして登録）。
- **Hugging Face / ModelScope へ**: ウィザードの最初のステップでプラットフォーム
  を選択。対応するトークンで認証し、リポジトリが存在しなければ作成
  （パブリック/プライベート）、保存先パスを選んでライブ進捗を見守れます。
  ModelScope は常に国際版 `www.modelscope.ai` ドメインと通信します。
- 任意の**関連アセット**スイッチは、`<モデル名>.*` のサイドカー
  （プレビュー画像・Markdown ノート）もモデルと同じリポジトリへアップロード
  します — ノートはリポジトリの `README.md` としてコミットできます。
- 選択した**フォルダ**は一括アップロード（内部の全モデル、サブフォルダ構造を
  維持）できます。

</details>

<details>
<summary><b>モデル情報とメンテナンス</b></summary>

- 読み取り専用の **Information** テーブルに、モデルについて記録されたすべてを
  表示: ノートの YAML front‑matter を解析した作者・ベースモデル・全ハッシュ
  （`AutoV1` … `SHA256_12`）・フォーマットと精度・モデルプラットフォーム・
  モデルページリンク・全プレビュー URL（未知のキーは末尾にそのまま表示）、
  またはノートのないモデルでは safetensors の `__metadata__` ブロック。
- safetensors モデルはさらに**テンソル構成**を折りたたみ可能な
  **フォルダツリー**として表示 — ドット区切りの名前をセグメントごとに
  グループ化し、各階層の数と、テンソルごとの name / dtype / shape を
  Hugging Face ビューア様式で描画します。ツリーは Rust コアが事前グループ化
  するため、65,000 テンソルの MoE ヘッダでも即座に開きます。
- モデルのリネーム・フォルダ/種別間の移動・プレビューとノートを含む
  **完全削除**。未保存の変更がある編集のキャンセルは確認を求めます。
- モデルの隣に保存された Markdown ノートの閲覧・編集・保存。
  Information テーブル自体も明示的な警告の背後で編集できます
  （保存時にノートの front‑matter を書き換えます）。
- プレビュー**ギャラリー**の管理: 並べ替え・削除・ローカル画像の追加・
  メインプレビューの選択（編集モードで青いリングを付けたタイル）。
- **モデルページを開く**ボタンは記録されたソースハブ（Civitai・Hugging Face・
  ModelScope）のロゴを背景に表示し、**ローカルへダウンロード**は保存済み
  ファイルをライブラリ名そのままに添付としてブラウザへストリームします。
- **ハッシュで識別**はローカルファイルを Civitai カタログに逆引きします
  （記録済みハッシュを先に試し、なければ 1 パスでハッシュ計算）。
- すべてモデルを開いたときにオンデマンドで読み込まれます —
  ライブラリ全体のスキャン工程は存在しません。

</details>

<details>
<summary><b>設定と i18n</b></summary>

- **Civitai**・**Hugging Face**・**ModelScope** の API キー。拡張機能隣の
  `private.key` にローカル保存され（`CIVITAI_API_KEY` / `HF_TOKEN` /
  `MODELSCOPE_API_TOKEN` 環境変数がフォールバック）、旧バージョンで ComfyUI
  ユーザー設定に保存されたキーは初回起動時に自動移行されます。
- モデル一覧から除外する種別の指定、隠しファイルの表示/非表示。
- **モデルフォルダの外部変更監視**（既定 OFF。ネットワークマウントは
  自動でスキップ）。
- ZipNN 自動化: N 日以上未使用のモデルの自動圧縮、ダウンロード完了後の
  自動圧縮、prompt 実行中のダウンロード一時停止。
- UI 言語は ComfyUI のロケールに追従 — **English**・**中文**（簡体・繁體）・
  **日本語**の完全バンドルを同梱。リージョンサブタグ（`ja-JP` 等）は基部
  言語へ折りたたまれ、Hant 書記系タグは繁體中文バンドルを選択します。

</details>

---

<a id="search"></a>

## <img src="https://api.iconify.design/lucide/search.svg?color=%2314b8a6" width="34" height="34" align="middle" alt=""> モデル検索とマルチプラットフォーム探索

**ダウンロードタスクを作成**ウィンドウはページ URL 以外も受け付けます:
`https://` で**始まらない**入力はモデル名クエリとして扱われ、
**Hugging Face**（左列）・**ModelScope**（中央）・**Civitai**（右）の
3 プラットフォームを並列検索します。入力中は検索モードと URL モードが
リアルタイムに切り替わり、結果は短いデバウンスで更新され、各列は
検索全体を失敗させることなく自分のエラーを自分で報告します。

- 結果の各行は公開ユーザー/組織の**アバター**（ハブが公開していない場合は
  イニシャルバッジ）と通算ダウンロード数を表示します。
- モデル ID は 2 つのディープリンクに分かれます: **オーナー名**は
  ユーザー/組織ページ、**リポジトリ名**はモデルページを開き、行のそれ以外を
  クリックするとそのモデルがダウンロードエディタへ解決されます。
- 素の **`username/repo-name`** 入力にも対応し、**Enter は常に 1 回で解決**
  します: 結果内の完全一致 → Hugging Face リポジトリとしての裸のリポジトリ ID →
  最初の非空列の先頭行の順。結果がまだ無ければ Enter は即座に名前検索を実行。
- 各列はページングします: 下端までスクロールすると、次のページがあるときだけ
  **「∨ もっと見る」**ボタンが現れます。
- プラットフォームごとの非表示と**並び順**は **設定 → Model Manager Neo →
  検索** で選べます（既定は Hugging Face トレンド・ModelScope いいね・
  Civitai 高評価順）。

Civitai ダウンロードには、公式 CLI が普及させた安全網をマネージャーの
タスクシステムへ適合させたものが追加で備わります:

- **ダウンロード計画（ドライラン）** — 開始前に、解決済みの保存先パス・
  宣言サイズ・公開 SHA256・プラットフォーム API キーの設定有無を提示。
- **SHA256 検証** — 完了した Civitai ダウンロードは公開 SHA256 と照合され、
  不一致はファイルを削除してタスクを失敗させます。
- **レイアウトルーティング** — 同梱 VAE など、自身の種別が別のモデルフォルダに
  対応するファイルは、選択先ではなくそのフォルダへ格納されます。
- **ベースモデル警告** — バージョンのベースモデルが、保存先フォルダの
  ライブラリに記録されたベースモデルと合わない場合に通知します。
- **実行形式警告** — pickle/アーカイブ形式のペイロードはロード時にコードを
  実行し得ます。ダウンロード前にエディタが明示します。
- **ハブアカウント（whoami）** — キーを設定した全プラットフォームについて、
  ダウンロードダイアログが接続中アカウントを表示し、401 失敗時はキーの
  作成場所と再開方法を正確に案内します。

Civitai 由来モデルのプレビューを拡大すると、左に画像・右に解析済みの
**生成メタデータ**（プロンプト、ネガティブプロンプト、サンプラー、ステップ数、
CFG スケール、シード、clip skip、サイズ、ベースモデル、リソース構成）を
示すライトボックスが開きます。

モデル詳細ウィンドウの**ハッシュで識別**は、ローカルファイルがどのモデル
バージョンかを Civitai カタログへ問い合せる逆引きです: Markdown サイドカーに
記録済みのハッシュを先に試し、どれも当たらなければファイルを 1 パスで
ハッシュ計算します（`SHA256` / `AutoV2` / `AutoV1` / `CRC32`、利用可能なら
`BLAKE3` も）。ヒット時は解決されたモデル/バージョンがベースモデル・
トリガーワード・ファイル一覧・公式 CLI と同じ `civitai download` コマンドと
ともに開き、ミスマッチ時は該当なしと報告されます。

---

<a id="zipnn"></a>

## <img src="https://api.iconify.design/lucide/package-plus.svg?color=%230ea5e9" width="34" height="34" align="middle" alt=""> ZipNN 可逆圧縮

大きな `.safetensors` チェックポイントはディスクをすぐに食い尽くします。
Neo はこれらを [ZipNN](https://github.com/zipnn/zipnn) 形式で**その場・可逆**に
圧縮/解凍できます — 公式 ZipNN プロジェクトと同じテンソル認識の方式を、
Neo の**純 Rust コア**が実行し、push のたびに公式 `zipnn` 0.5.4 パッケージと
CI で相互検証するため、ZipNN エコシステム全体と交換可能なままです。

### 1. 仕組み

モデル重みの大半は浮動小数点数で、浮動小数点数の大半は_冗長_です:
行儀の良い重みテンソルの指数バイトは何度も繰り返されます。ZipNN はまさに
そこを突きます。テンソルごとに:

- 値をバイト平面へ**分割**し、符号/指数/仮数のビットを並べ替えて
  類似バイトを集約してから、
- 各平面を FiniteStateEntropy（FSE）codec で **Huffman 符号化**します。

浮動小数でないテンソル（整数インデックス・マスク等）は公式レシピでは
そのまま素通りしますが、**Neo の Rust コアはこれらも圧縮します**
（safetensors の全 dtype を 2 つの相互運用帯で — 下記の
[dtype カバレッジと相互運用マトリクス](#dtype-coverage--the-interoperability-matrix)参照）。
圧縮しても実際には小さくならないテンソルは**そのまま保存**されます。
圧縮された各テンソルは `uint8` ベクトルとして格納され、ファイルは
`znn_compressed_vectors` という 1 つのメタデータエントリに全テンソルの
元の `dtype` と `shape` を記録します。何も近似も削除もされません —
解凍は元ファイルを**ビット単位で**再現します。

圧縮モデルは原本の隣に `<name>.znn.safetensors` として書き出されます —
公式 ZipNN ツール（および `zipnn_safetensors()` パッチ済みローダー）が
期待するまさに同じサフィックスなので、パッチ済み ComfyUI ローダーは
Neo の圧縮モデルを透過的に読み込めます。現実的なチェックポイントは
通常、元のサイズの **60〜80 %** 程度に収まります（ランダム性の強いデータは
あまり縮まず、低エントロピーの重みはもっと縮みます）。

### <a id="dtype-coverage--the-interoperability-matrix"></a>2. dtype カバレッジと相互運用マトリクス

Rust コアは **safetensors 0.8 が定義する全 22 dtype** を 2 つの相互運用帯で
圧縮します。圧縮ファイルの帯はメタデータに記録され
（拡張帯は `znn_neo_extended="1"`）、UI にも表示されます: Information タブの
**Neo Extended** バッジ、dtype 内訳行（`bfloat16×412, uint8×3, …`）、
そして圧縮確認ダイアログの明示的な注記です。

| テンソル dtype                                                                                                                  | ZipNN dtype コード | 公式 ZipNN 0.5.4 ツールの挙動                                                     |
| ------------------------------------------------------------------------------------------------------------------------------- | ------------------ | --------------------------------------------------------------------------------- |
| `F32` `F16` `BF16` `F8_E4M3` `F8_E5M2`                                                                                          | 1–30（上流互換帯） | **Neo のファイルをそのまま解凍可能**                                              |
| `F64` `C64` `I8` `U8` `BOOL` `I16` `U16` `I32` `U32` `I64` `U64` `F8_E4M3FNUZ` `F8_E5M2FNUZ` `F8_E8M0` `F4` `F6_E2M3` `F6_E3M2` | 128–146（Neo 帯）  | **明示的なエラーで拒否** — 静かな破損は起きません（CI で pip 版に対して実証済み） |

知っておく価値のある詳細:

- 公式デコーダは未実装の dtype コードをすべて `ValueError: Unsupported Dtype N`
  で拒否します — Neo 拡張ファイルを上流ツールが誤って解凍することは
  原理的にありません。Neo 内部では他のファイルと同様、SHA‑256 検証付きで
  バイト単位まで復元されます。
- `complex64` は Neo 帯（コード 130）を使います: 公式 0.5.4 デコーダには
  予約コード 9 の分岐が存在せず、Neo 帯のコードとまったく同じように拒否します
  （CI のテストで実証済み）。つまり互換性を保つべき相手がそもそもいません。
- 上位バイトがゼロの整数テンソル（`< 65536` の `int32` インデックス・マスク・
  スケールテーブル等）はさらに**トランケーションモード**を使います:
  すべてゼロのバイト平面はペイロードから丸ごと落とされます — テンソル全体で
  ゼロであることを検証した平面のみを落とすため、構造上可逆です。
- `complex128` と `bcomplex32` は codec 級（コード 129/131）に存在しますが、
  safetensors 表現を持たないため、`.safetensors` ファイルがこれらを運ぶことは
  ありません。

### 3. 使い方

任意の `.safetensors` モデルを開くと、プレビューと情報テーブルの間に
**ZipNN アートワークそのもののボタン**があります — 同梱 SVG は自前の
ガラスプレート（ダークモード変種込み）を描画し、ホバーで浮き上がって明るく
なり、ツールチップとスクリーンリーダーに自分を説明します。押すと:

1. わざと「Danger」スタイルにしていない確認ダイアログが出ます
   （圧縮は可逆で、圧縮ファイルが完全に書き込まれ検証されるまで原本を
   削除しません）。
2. Rust コアがファイルをストリーム処理している間、ボタンは**ライブ進捗バー**に
   置き換わります（メモリマップ・GIL 解放済み — ComfyUI の残りは応答性を
   保ちます）。タスクはいつでもキャンセルできます。
3. 成功すると原本は `<name>.znn.safetensors` へ置き換わります —
   プレビューと Markdown ノートはリネームに追従し、グリッドは自動更新されます。

**圧縮済み**モデルを開くと、同じアートワークが**反転色**で表示され、アクションは
同じ確認を挟んで _解凍_ へ反転し、素の `.safetensors` を復元します。
情報テーブルも変わり、1 行の _ファイルサイズ_ の代わりに
**元のファイルサイズ**・**圧縮後ファイルサイズ**・**元サイズ比**の 3 行に
なります — 圧縮前のサイズは圧縮時にファイルのメタデータへ記録されるため、
この内訳はリネーム後も生き残ります（このキーを書かない公式 ZipNN CLI が
圧縮したファイルは、素の _ファイルサイズ_ 行のままです）。

同じアートワークは**すべてのモデル/フォルダカードの右上**（スタートグルの隣）にも
あります: 1 クリックで、モデルを開かずに、同一の確認ダイアログ経由で圧縮
（または反転表示の解凍）を実行できます。実行中は — 単体・バッチ・デルタの
いずれでも — ボタンは**円形の進捗リング**（バッチはパーセント付き）になります。

### 4. バッチ圧縮（フォルダ単位）

フォルダを選択（「ファイルを選択」）して**ボトムバーの ZipNN アートワークボタン**
を押すか、フォルダカードのコーナーボタンを使うと、フォルダツリー内のすべての
`.safetensors` モデルが圧縮され（プレビューとノートも追従）、
**バンドルフォルダ `<name>_DeltaZNN` へ移動**します。空になった元のフォルダは
消えます。すでにその場で圧縮済みのモデル（単体ボタン・自動圧縮・旧バージョン
由来）は再圧縮されず、そのままバンドルへ移動します — 圧縮済みファイルが
バンドル外に残ることはありません。`*_DeltaZNN` バンドルは密封されています:

- 中に置けるのは ZipNN コンテンツ（`*.znn.*` モデル・`*.znn` デルタファイル）
  のみ（素のモデルのアップロード・ダウンロード・移動は拒否されます）。
- バンドルフォルダと非バンドルフォルダを同時に選択することはできません —
  警告トーストとともにバンドル側の選択が自動解除されます。
- バンドルの ZipNN ボタンは**反転**しており、押すとバンドルを
  **バッチ解凍**して、バンドル名の元になったフォルダへすべてを移し返します
  （空になったバンドルフォルダは削除されます）。
- デルタフォルダ（`<base>_DeltaZNN`、下記参照）もバンドルです:
  反転ボタンは内部の全ファインチューンを一度に復元します。
- モデル種別の**ルートフォルダ**（`checkpoints` 等）はバンドルを
  **自分の内側**（`<root>_DeltaZNN`）に作ります — 種別ルートの兄弟は
  ComfyUI のフォルダマッピングの外へ落ち、ローダーからもマネージャーからも
  見えなくなってしまうためです。方向は自動検出されます: 素のモデルがあれば
  圧縮、バンドルしか無ければ解凍。
- 旧バージョンが作ったバンドル（`<name>_ZNN`）も認識され、元の名前へ
  解凍できます。

複数フォルダはキューとして実行されます: 確認は 1 回、タスクは逐次、
進捗表示も一度に 1 つです。

### 5. デルタ圧縮（ベースに対するファインチューン）

ファインチューンモデルはベースと大部分のバイトを共有しており、ZipNN は
**差分だけ**を保存できます: 素の `.safetensors` モデルをちょうど 2 つ選択して
ボトムバーの **ZipNN デルタ圧縮**を押してください。小さなダイアログで
どちらが**ベース**でどちらが**ファインチューン**かを選びます
（ベースとファインチューンのメタデータが異なっていても構いません）。
結果 — 通常はファインチューンのサイズの数 % — は
**`<base>_DeltaZNN/<ft>_delta_<base>.znn`** へ書き出され、冗長になった
ファインチューンファイルは削除されます。デルタの解凍（反転したカードボタン）は
ファインチューンモデルをベースの隣に**バイト単位まで正確に**復元し、
空になったデルタフォルダを撤去します。復元にはベースモデルが必要で、
デルタにはファインチューン自身の SHA‑256 が記録されるため、
復元はエンドツーエンドで検証されます。

デルタファイルは公式 ZipNN の **streaming コンテナ**形式で書き出されます:
公式 `zipnn` パッケージ（byte デルタモード）がそれをバイト単位まで正確に
復元でき、逆に Neo も公式ツールが生成したデルタ（単一コンテナ形式・
streaming 形式の双方）を復元できます — 双方向とも CI のクロス検証に
含まれています。また `.znn` は ComfyUI の対応モデル拡張子へ登録される
（元版の実験的な `.gguf` と同様）ため、デルタファイルはグリッドに
管理対象のモデルとして表示され、UI から直接復元できます。

### <a id="the-engine"></a>6. エンジン: プリビルドの純 Rust コア

圧縮器は公式 Python パッケージのラッパーではなく、Neo 自前の**純 Rust
エンジン**が形式を実行します: 上流の C 拡張は PyPI に Linux wheel が無く
（`pip install zipnn` はソースからのコンパイルになります）、Neo はその
コンパイルをあなたのマシンから完全に無くしました。フォーマットは Rust へ
移植され（[`native/crates/znn-codec`](native/crates/znn-codec):
フォーマット中核に `unsafe` なし、7 本の継続的ファジングターゲット、
オリジナル C 実装とのバイト同一差分検証の経歴）、リポジトリ同梱の
**プリビルド abi3 / abi3t バイナリ**として出荷されます — プラットフォーム ×
Stable ABI フレーバごとに 1 本、ロードは `import` だけ:

| プラットフォーム                 | 成果物                                          | 要件                                                 |
| -------------------------------- | ----------------------------------------------- | ---------------------------------------------------- |
| Linux x86_64                     | `native-bin/linux-x86_64/mm_core.abi3.so`       | glibc ≥ 2.28（Debian 10 / Ubuntu 20.04+）            |
| Linux aarch64                    | `native-bin/linux-aarch64/mm_core.abi3.so`      | glibc ≥ 2.28                                         |
| macOS（Intel & Apple Silicon）   | `native-bin/macos-universal2/mm_core.abi3.so`   | 1 本の fat binary — Intel 10.12+ / Apple Silicon 11+ |
| Windows x86_64                   | `native-bin/windows-x86_64/mm_core.pyd`         | MSVC ビルド                                          |
| Linux x86_64（フリースレッド）   | `native-bin/linux-x86_64t/mm_core.abi3t.so`     | glibc ≥ 2.28・フリースレッド CPython 3.15+           |
| Linux aarch64（フリースレッド）  | `native-bin/linux-aarch64t/mm_core.abi3t.so`    | glibc ≥ 2.28・フリースレッド CPython 3.15+           |
| macOS（フリースレッド）          | `native-bin/macos-universal2t/mm_core.abi3t.so` | 1 本の fat binary・フリースレッド CPython 3.15+      |
| Windows x86_64（フリースレッド） | `native-bin/windows-x86_64t/mm_core.pyd`        | MSVC ビルド・フリースレッド CPython 3.15+            |

各プラットフォームの 1 バイナリが **CPython 3.12 以降**すべてに対応します
（Stable ABI、`abi3-py312` — CI で 3.12 と 3.14 に対して実証）。
フリースレッド build は **abi3t** の双子（`abi3t-py315`・PEP 803 — CI で
3.15 の GIL/フリースレッド両 build に対して実証）が対応し、ローダーが自動で
選びます（フリースレッド解釈系は通常の abi3 バイナリをロードできず、3.15+ の
GIL build は従来どおり通常バイナリを使います）。サイズは CI の予算ゲートが
1 本 ≤ 5 MB に抑えます（8 本の合計は 40 MB の目安で管理）。linux-x86_64 と
Windows の GIL バイナリは **PGO 最適化済み**です — CI ビルド毎に決定論的
ワークロードから再トレーニングされるプロファイル誘導最適化で、非最適化
ビルドとの CI A/B 計測により初回実行スループット最大 ~10 % 向上
（[BENCH §13](docs/BENCH.md)）。abi3t バイナリは現時点では非 PGO で出荷します。

この移植は信頼性も根本から改善しました: 書き換え作業の過程で、C コアの
デルタ経路にメモリ安全欠陥の一クラスが実証されていました（特定の入力長での
決定的クラッシュ、端数チャンクでの境界外書き込み）。Rust エンジンはこの
欠陥クラスを構造的に排除します — すべての平面分割とチャンク演算は
境界チェック付きで、唯一の `unsafe` 境界（読み取り専用 mmap）も SAFETY
レビュー済みです — そして当時クラッシュした入力は回帰テストとして
固定されています。相互運用は約束ではなく
CI ゲートです: `integration` ワークフローが push のたびに**公式 pip `zipnn` 0.5.4**
と双方向でクロス検証します。ライセンス: フォーマット移植は
ZipNN（MIT）と FiniteStateEntropy（BSD‑2‑Clause）に帰属し、プレビュー WebP
codec は zenwebp（AGPL‑3.0）を使用 — 全文は [`native/NOTICE`](native/NOTICE) に
あります。

バイナリの無いプラットフォーム（その他のアーキテクチャ・32 ビット・特殊な libc）
でも拡張機能はインストールできます: 閲覧・ダウンロード・ハッシュは純 Python
経路へフォールバックし、ZipNN 操作とプレビュー再エンコードは静かに失敗する代わりに
ローダーの正確な理由を報告します。

> [!NOTE]
> 圧縮は mmap でファイルをストリーム処理します — ピーク RAM はモデル全体ではなく
> およそ最大単一テンソル分です（12 GB のチェックポイントでも 1 GB 未満）。
> **可逆かつ検証付き**です: コアは圧縮時に原本の SHA‑256 を記録し、復元時に
> インラインで再照合します（不一致時は圧縮ファイルを保持したまま、復元物を
> 検査用に `.corrupt` として退避）。素の `.safetensors` は
> `.znn.safetensors` が書き込まれ検証された後のアトミック rename でのみ削除され、
> 失敗した実行は部分出力を掃除します。オプトインの **paranoid モード**は、
> 原本削除前に解凍し直して比較まで行います。

---

<a id="what-changed"></a>

## <img src="https://api.iconify.design/lucide/git-compare.svg?color=%23a855f7" width="34" height="34" align="middle" alt=""> 元版からの変更点

この節は GPL‑3.0 ライセンスが求める通り、フォークの差分を明示します。
比較の基準は [`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
**v2.8.5** です。機能は保持・拡張されており、_削除_されたのは 2 つ —
PrimeVue 依存そのものと、バッチスキャン機能です
（[削除された機能: バッチスキャン](#removed-feature)参照）。

### <img src="https://api.iconify.design/lucide/palette.svg?color=%23d946ef" width="26" height="26" align="middle" alt=""> インターフェース

| 領域                     | 元版                                                      | **Neo**                                                                                                                                                                                                                                                                                                            |
| ------------------------ | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| コンポーネントライブラリ | PrimeVue 4                                                | **reka‑ui**（ヘッドレス）+ shadcn‑vue スタイルのラッパー                                                                                                                                                                                                                                                           |
| スタイリング             | Tailwind CSS v3 + PrimeVue テーマ                         | スコープ付き `--mm-*` デザイントークンによる **Tailwind CSS v4**                                                                                                                                                                                                                                                   |
| アイコン                 | PrimeIcons                                                | アイコンマップ経由の **Lucide**（`@lucide/vue`）                                                                                                                                                                                                                                                                   |
| 見た目と操作感           | 標準の PrimeVue サーフェス                                | **グラスモフィズム**（ぼかし・奥行き・マイクロインタラクション）、自動ダークモード                                                                                                                                                                                                                                 |
| ダイアログ               | PrimeVue `Dialog`/`ContextMenu`                           | reka‑ui ダイアログ、ダイアログ毎のサイズ/位置、ドラッグ移動、アンカー付きコンテキストメニュー                                                                                                                                                                                                                      |
| モデル詳細タブ           | Description + Metadata（生の safetensors `__metadata__`） | Description + **Information**: ノートの YAML front‑matter を解析した読み取り専用テーブル（作者・ベースモデル・ハッシュ・フォーマットと精度・モデルプラットフォーム・モデルページリンク・全プレビュー URL・未知のキーはそのまま表示）、フォールバックは生の `__metadata__`、加えて safetensors の**テンソルツリー** |
| ロケール                 | English・中文                                             | English・中文（簡体＋**繁體**）・**日本語**（完全バンドル）                                                                                                                                                                                                                                                        |

### <img src="https://api.iconify.design/lucide/cpu.svg?color=%230ea5e9" width="26" height="26" align="middle" alt=""> バックエンドとエンジン

最深部の変更は UI の下にあります。元版は純 Python（バックエンド 7 モジュール・
HTTP ルート 19 本）ですが、Neo は 16 モジュール・42 ルートへ成長し、
すべてのホットパスをプリビルド Rust 拡張（`native/`、Stable ABI 上の PyO3 —
[エンジンの表](#the-engine)参照）へ移しました。純 Python フォールバックは
「エラーを返すより、限定的な結果でも答える方がよい」箇所だけに残しています:

| 領域                   | 元版                                                                                                                      | **Neo**                                                                                                                                                                                                                                                                                                             |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| モデル一覧             | リクエスト毎の再帰 Python `os.scandir`                                                                                    | Rust 並列 walk + 再起動をまたぐ永続 front‑matter インデックス（5,000 モデルのスキャンがコールドで約 7.5 倍、ウォーム約 100 ms。エントリ単位のゴールデンテスト済み）                                                                                                                                                 |
| モデル詳細ルート       | ヘッダ解析が**イベントループ上**で実行 — 巨大 MoE ヘッダでサーバー全体が停止                                              | executor 経由 + Rust 解析でサーバーは応答性を維持                                                                                                                                                                                                                                                                   |
| ハッシュ               | `hashlib` SHA‑256 ループ 1 本                                                                                             | 5 表記（`SHA256`/`AutoV1`/`AutoV2`/`CRC32`/`BLAKE3`）を**1 パス**のストリーミングで                                                                                                                                                                                                                                 |
| ダウンロード検証       | 完了後のフル再読込                                                                                                        | 書込ループが供給するインラインダイジェスト — 追加 I/O ゼロ — Civitai SHA‑256 ゲートは維持                                                                                                                                                                                                                           |
| safetensors ヘッダ     | `comfy.utils` + `json.loads`                                                                                              | 1 ルートに集約された Rust jiter 解析（metadata + tensors + 事前グループ化された表示ツリー。65k テンソル MoE のツリー構築は約 100 倍高速、wire フォーマットは JS とクロスチェック）                                                                                                                                  |
| ZipNN 圧縮             | —                                                                                                                         | エンジン全体: 圧縮/解凍/フォルダバッチ/ファインチューン デルタ、mmap ストリーミング（どんなモデルでも RAM 1 GB 未満）、SHA‑256 検証付き復元、協調キャンセル API                                                                                                                                                     |
| プレビュー画像         | PIL 再エンコード。アニメは 1 フレーム目に固定化                                                                           | zenwebp（純 Rust）の encode/decode。アニメ GIF/WebP プレビューは**アニメのまま**（フレーム・duration・ループ数・ICC プロファイルを保持）                                                                                                                                                                            |
| ハブ統合               | Civitai と Hugging Face のみ: ページ解決はブロッキング `requests`、ファイルは素の HTTP URL から取得 — ModelScope は非対応 | **Civitai + Hugging Face + ModelScope** — ModelScope はダウンロード元・アップロード先・検索ハブ・認証まで全新規実装。SDK ベースの転送（`huggingface_hub` + `hf_xet`・`modelscope_hub`）、3 ハブ並列の名称検索、`private.key` へのハブ別 API キー（環境変数フォールバック + ComfyUI 設定からの移行）、ハッシュ逆引き |
| ハブ HTTP              | スレッドプールワーカー内のブロッキング `requests`                                                                         | イベントループ上の共有 `aiohttp` セッション 1 本（ストールした CDN が read timeout の 120 秒間ワーカーを専有することはもうありません）                                                                                                                                                                              |
| フォルダ監視           | —                                                                                                                         | 任意のネイティブ `notify` watcher（既定 OFF）: 種別単位で約 1.5 秒の更新、ネットワークマウントはスキップ、inotify 予算枯渇は 30 秒 TTL 更新へフォールバック                                                                                                                                                         |
| ライブラリ衛生         | —                                                                                                                         | 孤立サイドカー/空フォルダの一斉検査と一括削除                                                                                                                                                                                                                                                                       |
| アップロード preflight | —                                                                                                                         | HF/ModelScope アップロードの重複検出ハッシュをネイティブコアで実行（GIL 解放）                                                                                                                                                                                                                                      |
| 配布                   | プリビルドの web バンドルを初回起動時に GitHub Releases からダウンロード                                                  | web バンドルは `web/` に、Rust コアは `native/native-bin/` に同梱 — 初回起動時の取得は Python 依存 4 点のみ                                                                                                                                                                                                         |

元版に対する機能面の追加 — **ModelScope 統合の一式**（ダウンロード元・
アップロード先・検索ハブ・認証）、Hugging Face へのアップロード、
SDK ベースの Hugging Face ダウンロード（`huggingface_hub` + `hf_xet`。
元版は素の resolve URL の取得）、マルチハブ検索、ハッシュ識別、
スマートコレクション、スター、「最近使用」の記録と並び替え、複数選択、
フォルダ作成、直接リンクダウンロード、ブラウザへの「ローカルへダウンロード」、
空き容量ガード、Civitai ダウンロードの安全網、ギャラリープレビュー、
SHA256 重複警告、サブディレクトリ表示と種別ルートの合計サイズ、
フルスクリーンのプレビュー ライトボックス、日本語・繁體中文ロケール —
は[機能](#features)で説明しており、すべて Neo 側の実装です。

### <img src="https://api.iconify.design/lucide/package.svg?color=%23f97316" width="26" height="26" align="middle" alt=""> パッケージ

- **削除:** `primevue`・`@primevue/themes`・`lodash`・`dayjs`・`js-yaml`
  （最後の 1 つは元版でも実使用なし — YAML 処理は `yaml` が担っていました）。
- **追加 / 置換:** `reka-ui`・`@lucide/vue`・`es-toolkit`（← lodash）・
  `date-fns`（← dayjs）・`vue-sonner`（トースト）・
  `class-variance-authority`・`clsx`・`tailwind-merge`。
- **更新:** Vite 5 → **8**（Rolldown）、TypeScript 5 → **6**、Vue i18n 9 →
  **11**、markdown‑it 14 → **15**、`@vueuse/core` 11 → **15**、`yaml` 2.6 →
  **2.9**。
- **Python:** `huggingface_hub` + `hf_xet` + `modelscope_hub` を追加
  （元版の必須は `markdownify` のみ）。旧スレッドプールに代わる asyncio
  タスクプール、ブロッキング `requests` 呼び出しをすべて置き換える共有
  aiohttp クライアント。
- **Rust:** `native/` ワークスペース（`znn-codec` フォーマットコア +
  `mm-core` PyO3 バインディング）を追加し、プリビルド abi3 / abi3t バイナリとして
  同梱 — 拡張機能はコンパイル済み Python パッケージを一切インストール
  しません。ZipNN 圧縮はすべて Neo 側の実装です（フォーク元には同梱されて
  いませんでした）。本フォークの開発期間中に一時的に同梱していた vendored
  ZipNN C ソースと CPython バージョン別 `.so` は、Rust コアへの置き換えと
  ともにすべて撤去済みです。

### <img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%2306b6d4" width="26" height="26" align="middle" alt=""> ツールバー/ボタンの役割

マネージャーヘッダーは明示的なアイコン駆動アクションへ再設計されました:
**フラット ⇄ フォルダレイアウト切替**・**衛生スキャン**・
**隠しファイルの表示/非表示**・**更新**・**ダウンロード一覧**・
**Hugging Face / ModelScope へのアップロード**。

### <img src="https://api.iconify.design/lucide/folder-open.svg?color=%23f59e0b" width="26" height="26" align="middle" alt=""> ガラスアセットパック（フォルダアイコンと NO‑PREVIEW アート）

インターフェースは `assets/` の手作りグラスモフィズム アセットパックを
使用します:

- **フォルダカード**は静止したガラスフォルダを表示し、ホバー中は穏やかな CSS
  フロート（上下動）が再生、離れるとすぐに静止へ戻ります。SVG は SMIL を含まない
  純ベクタファイルで、HTTP 経由 ETag・max‑age 付きで配信され、全カードが単一の
  キャッシュ済コピーを共有します。
- **ブレッドクラム**は各セグメントに小さなフォルダグリフを付けます。
- **プレビューのないモデル**はガラスの NO‑PREVIEW アートワークを使い、
  ベクトル（`image/svg+xml`）のまま配信されるためラスタライズされません。
- **モデルハブのロゴ**（Civitai・Hugging Face・ModelScope）は
  **モデルページを開く**ボタンの背景になり、モデルの出所が一目で分かります。

_数ある色からペールターコイズを選んだのは、これが **Neo** だからです。_

### <img src="https://api.iconify.design/lucide/hammer.svg?color=%2365a30d" width="26" height="26" align="middle" alt=""> ツールチェーン

lint/format パイプラインは、フロントエンドに**ESLint 10 flat config** +
**Prettier** + **Stylelint 17**、Python バックエンドに **Ruff** + **mypy**、
Rust ワークスペースに **clippy `-D warnings`** + **rustfmt** を備えた
慣例的でフル設定の構成で、**dependency‑cruiser**（import グラフゲート）と
[Fallow](https://fallow.tools)（未使用コード・重複解析）が補完します。
品質は 5 層のテストピラミッドで担保されます: Rust 単体テスト、ゴールデン
契約テスト、**cargo‑fuzz** ターゲット（7 表面・週次 3 h/ターゲット予算）、
3 OS でビルド成果物に対して走る pytest スイート全体、そして公式 `zipnn`
クロス検証（[開発](#development)参照）。

---

<a id="removed-feature"></a>

## <img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="34" height="34" align="middle" alt=""> 削除された機能: バッチスキャン

**「モデル情報のバッチスキャン」**機能は削除されました。冗長だったためです:
モデル詳細ウィンドウは、そのモデルの `__metadata__` を safetensors ヘッダから
直接、隣に保存された Markdown ノートとともに読み込み、プレビューのないモデルは
グリッド上で同梱のガラス製 NO‑PREVIEW アートワークが表示されます。
ライブラリ全体を walk して全モデルをハッシュし Civitai へ問い合わせる方式は、
同じ情報へ至るはるかに遅い第二の経路でした — さらにモーダルダイアログ・
グローバルストア・websocket イベント・ディスク上のタスクファイル・専用設定まで、
すべて保守する必要がありました。

スキャンより長生きした 2 つの設定は、今日**モデル一覧**を駆動しています
（どの種別をグリッドへ読み込むか、`.` 始まりファイルを表示するか）。
設定カテゴリは **Model List** です。歴史的な `ModelManager.Scan.*` ID 文字列を
維持しているのは、この ID が ComfyUI がユーザーの値を保存するキーだからです —
改名すると既存インストールの保存値が孤立します。

> [!NOTE]
> **手放したもの:** Civitai からファイルハッシュでプレビューと説明を
> _一括バックフィル_する唯一の手段です。情報を一度も取得していないモデルは、
> プレビュー/ノートを手で設定する（エディタのギャラリーストリップ）か、
> _ダウンロードタスクを作成_で再ダウンロードするまで、プレースホルダー
> プレビューのままです。モデル情報の読み取りは影響を受けません —
> 常にオンデマンドでディスクから来ます — 個別のモデルは詳細ウィンドウの
> ハッシュ逆引きで Civitai カタログに識別を問い合せられます。

---

<a id="documentation"></a>

## <img src="https://api.iconify.design/lucide/book-open.svg?color=%237c3aed" width="34" height="34" align="middle" alt=""> ドキュメント

それぞれ完結したステップバイステップの使い方ガイド:

- [`docs/USAGE.md`](docs/USAGE.md) — English
- [`docs/USAGE.ja.md`](docs/USAGE.ja.md) — 日本語
- [`docs/USAGE.zh-CN.md`](docs/USAGE.zh-CN.md) — 中文（简体）
- [`docs/USAGE.zh-TW.md`](docs/USAGE.zh-TW.md) — 中文（繁體）

インストール、2 つのレイアウト、カード操作とグラフへのドラッグ、モデルエディタ
（フォルダピッカー・フォルダ接頭辞付きファイル名・プレビュー・説明）、
ダウンロードとタスク一覧、ハブアップロード（Hugging Face / ModelScope）の
フェーズと完了メッセージ、ZipNN 圧縮、設定とロケール、
トラブルシューティング表を収録しています。

さらに詳しく:

- [`docs/BENCH.md`](docs/BENCH.md) — この README のすべての性能主張の裏にある
  計測記録。
- [`native/README.md`](native/README.md) — Rust ワークスペース: レイアウト・
  テストピラミッド・ファジング構成・プリビルドバイナリの生成方法。

---

<a id="development"></a>

## <img src="https://api.iconify.design/lucide/terminal.svg?color=%230ea5e9" width="34" height="34" align="middle" alt=""> 開発

Web バンドルの**ビルド**に必要なのは Node.js だけです。ComfyUI 内での実行に
必要なのは Python のみ（Rust コアはプリビルド同梱）。

```bash
corepack enable          # ピン留めされた pnpm バージョンを使用（Node 26）
pnpm install
uv sync --frozen         # Python の開発/テスト環境（.venv）
```

Python の開発/テスト環境（pytest・ruff・mypy・ハブ SDK・torch‑CPU）は
**[uv]** が管理します — `uv sync --frozen` が `pyproject.toml` の
`[dependency-groups]` とコミットされた `uv.lock` から一発で再構築します。
これは開発上の便宜にすぎず、_ランタイム_契約は不変です — ComfyUI は従来通り
初回起動時に自分で `requirements.txt` をインストールします
（2 つのリストはテストで一致を固定しています）。

Rust コアの作業には stable ツールチェーンで十分です — debug ビルドも正当な
`mm_core` です（API ハンドシェークと pytest スイート全体が release と
同一挙動）:

```bash
cd native && cargo build -p mm-core
cp target/debug/libmm_core.so native-bin/linux-x86_64/mm_core.abi3.so   # 自分のプラットフォームのタグ
```

`scripts/build-native.sh --target <tag> --size-gate` が出荷用 release 成果物を
再現します（glibc ≥ 2.28 の床は cargo‑zigbuild、macOS universal2 は
maturin + lipo、Windows は maturin/MSVC）。ワークスペース・テストピラミッド・
ファジング構成は [`native/README.md`](native/README.md) にまとめてあります。

| スクリプト                            | 内容                                                                      |
| ------------------------------------- | ------------------------------------------------------------------------- |
| `pnpm dev`                            | Vite 開発サーバー（ComfyUI ホットリロード用 `web/manager-dev.js` を出力） |
| `pnpm build`                          | `web/` への本番ビルド                                                     |
| `pnpm build:clean`                    | `web/` を削除して再ビルド                                                 |
| `pnpm rebuild`                        | `node_modules/` **と** `web/` を削除し、再インストールして再ビルド        |
| `pnpm typecheck`                      | `vue-tsc --noEmit` 型チェック                                             |
| `pnpm lint` / `pnpm lint:fix`         | ESLint（flat config）                                                     |
| `pnpm lint:css` / `pnpm lint:css:fix` | Stylelint 17（CSS + Vue SFC スタイルブロック、Tailwind v4 対応）          |
| `pnpm deps`                           | dependency-cruiser: import グラフゲート（Node ≥ 22 が必要）               |
| `pnpm deps:graph`                     | モジュールグラフを `dependency_graph.svg` へ書き出し                      |
| `pnpm format` / `pnpm format:check`   | Prettier（Tailwind プラグイン付き）                                       |
| `pnpm py:lint` (`:fix`)               | バックエンドの Ruff lint（`py/`・`__init__.py`・`tests/`・`scripts/`）    |
| `pnpm py:format` (`:check`)           | バックエンドの Ruff format                                                |
| `pnpm py:test`                        | pytest スイート（`mm_core` 未ビルド時は native 系テストを skip）          |
| `python -m mypy`                      | バックエンドの静的型検査（pyproject の `[tool.mypy]`）                    |
| `pnpm rs:fmt` (`:check`) / `rs:lint`  | `native/` の rustfmt / clippy `-D warnings`                               |
| `pnpm rs:test`                        | Rust 単体 + 統合テスト（mm-core は extension-module なしで）              |
| `pnpm rs:build`                       | `mm-core` の release ビルド                                               |
| `pnpm fallow`                         | Fallow フルパイプライン: 未使用コード + 重複 + ヘルス                     |
| `pnpm fallow:dead` (`:type-aware`)    | 未使用ファイル/export/型/依存・循環 — 任意の TS 意味解析パス              |
| `pnpm fallow:dupes`                   | AST クローン検出（`mild` モード、`.fallowrc.json` 参照）                  |
| `pnpm fallow:health`                  | 複雑性ホットスポット・リファクタ対象・0–100 ヘルススコア                  |
| `pnpm fallow:fix:dry` / `fallow:fix`  | 自動クリーンアップのプレビュー / 適用（常にまず dry-run）                 |
| `pnpm fallow:audit`                   | PR 風ゲート: 現在の変更が導入した指摘のみ                                 |

**husky** の `pre-commit` フックがステージされたファイルに **lint-staged**
（フロントエンドは ESLint + Stylelint + Prettier、バックエンドは Ruff）と
`pnpm typecheck` 全体を実行します。

### 1. 品質ゲート

**Fallow**（Rust 製・解析器に AI 不使用）はリポジトリを 1 つの依存グラフとして
読み、未使用ファイル/export/型/依存・循環 import・クローングループ・複雑性の
ホットスポットを報告します。ツリーは**未使用 export ゼロ・重複ゼロ**に保たれ、
CI は ERROR 級の指摘で失敗します。

**ESLint 10** flat config が `typescript-eslint`・`eslint-plugin-vue`・
`eslint-plugin-import-x`・`eslint-plugin-tailwindcss`・
`eslint-config-prettier` を配線し、**Prettier** が整形と Tailwind クラスの
ソート、**Stylelint 17** が `src/style.css` と全 SFC スタイルブロック、
**dependency‑cruiser 18** が `src/` の import グラフ（循環なし・孤立なし・
出荷コードからの devDependency / Node core import なし）をゲートします。

**Ruff**（`pyproject.toml [tool.ruff]`）がバックエンドの lint/format
（target `py312`・行長 120・精選ルールセット）、**mypy** が静的型を検査します。

**CI** は push のたびに上記すべてに加え、フロントエンド計測ゲート
（`scripts/bench/front/k15.mjs`）を実行し、`native` ワークフローが 8
プラットフォーム成果物（abi3 ×4 + abi3t ×4）をビルドし、サイズ予算を強制し、
7 本の fuzz ターゲットをスモークし、abi3 成果物を CPython 3.12 と 3.14 で・
abi3t 成果物を 3.15 の GIL/フリースレッド両 build で import 疎通し、pytest スイート
全体（フリースレッド 3.15t セルを含む）と公式 `zipnn` クロス検証を
Linux・Windows・macOS で実行します。

### 2. プロジェクト構成

```
├─ __init__.py            # ComfyUI エントリ: 依存インストール・ルート登録
├─ py/                    # Python バックエンド（aiohttp ルート・タスク・ハブクライアント）
│  ├─ manager.py          #   モデル CRUD + native 高速化された一覧/衛生
│  ├─ download.py         #   ダウンロードタスク（http + huggingface_hub + modelscope_hub）
│  ├─ upload.py           #   ローカルファイルアップロード（パス検証付き）
│  ├─ upload_hf.py        #   Hugging Face へのアップロード（共有ハブパイプライン）
│  ├─ upload_modelscope.py#   ModelScope へのアップロード
│  ├─ compress.py         #   native ジョブ API を駆動する ZipNN ルート
│  ├─ information.py      #   Civitai/HF/ModelScope ページ解決・プレビュー配信
│  ├─ search.py           #   マルチプラットフォーム モデル名検索 + アバタープロキシ
│  ├─ identify.py         #   Civitai ハッシュ逆引き
│  ├─ native.py           #   プリビルドコア ローダー（プラットフォームタグ・API ハンドシェーク）
│  ├─ http_client.py      #   すべてのハブ往復用の共有 aiohttp セッション
│  ├─ watcher.py          #   任意のライブラリ監視（native notify・既定 OFF）
│  ├─ auth.py · config.py · thread.py · utils.py
├─ native/                # Rust ワークスペース（GPL-3.0・帰属は native/NOTICE）
│  ├─ crates/znn-codec/   #   ZipNN フォーマットコア + scan/hash/header/webp（+ fuzz/）
│  ├─ crates/mm-core/     #   PyO3 abi3 バインディング（mm_core モジュール）
│  └─ native-bin/         #   プラットフォームタグ別のプリビルドバイナリ（main へコミット）
├─ src/                   # Vue 3 フロントエンド
│  ├─ components/         #   アプリコンポーネント + ui/（reka-ui ラッパー）
│  ├─ hooks/              #   store・models・download・zipnn・upload・config 等
│  ├─ utils/ · types/ · locales/
│  ├─ style.css           #   Tailwind v4 エントリ + デザイントークン
│  └─ main.ts             #   ComfyUI 拡張として登録
├─ scripts/               # native ビルド + 公式 zipnn クロス検証 + フロントエンド計測ゲート
├─ tests/                 # pytest スイート: ゴールデン契約・parity・接合部
└─ web/                   # ComfyUI へ配信されるプリビルドバンドル（コミット対象）
```

---

<a id="credits"></a>

## <img src="https://api.iconify.design/lucide/heart-handshake.svg?color=%23ec4899" width="34" height="34" align="middle" alt=""> クレジットと帰属

ComfyUI‑Model‑Manager‑Neo は、**[hayden‑cn](https://github.com/hayden-cn)** 氏の
**[`ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)**
が先に存在したからこそ存在します。このフォークの構造的なアイデアはすべて —
モデルフォルダの抽象化、websocket 進捗プロトコルを備えた再開可能な
ダウンロードタスクシステム、Civitai / Hugging Face のページパーサ、
カードをグラフへドラッグする統合、モデルエディタのフォーム配管、
カードサイズ プリセットのような小さな気配りまで — hayden‑cn 氏の設計です。
Neo が変えたのは外観と依存関係、そして数多くのバグであり、アーキテクチャ
そのものをゼロから発明する必要はありませんでした。このコードベースがなぜ今の形をしているかを理解する最速の道は
今もオリジナルを読むことであり、アーキテクチャへの正直な帰属は
**原著作者のもの**です。

圧縮エンジンは **[ZipNN](https://github.com/zipnn/zipnn)** プロジェクト（MIT）の
フォーマットを実装したものです — Hershcovitch et al.,
_“ZipNN: Lossless Compression for AI Models”_
（[arXiv:2411.05239](https://arxiv.org/abs/2411.05239)）。エントロピー符号は
zstd の huff0/FSE 仕様（RFC 8878）と FiniteStateEntropy（BSD‑2‑Clause）に
従います。ネイティブコアの第三者帰属の全文は
[`native/NOTICE`](native/NOTICE) にあります。

このフォークは **GNU General Public License v3.0** に従って使用・改変された
派生物です。Neo の改変部分（UI 再構築、PrimeVue 除去、Rust ネイティブコア、
ZipNN 圧縮、Hugging Face / ModelScope のハブ統合、マルチハブ検索とハッシュ識別、
パッケージ現代化、ツールチェーン、信頼性とセキュリティの強化、
バッチスキャンの削除、日本語ローカライズ —
[元版からの変更点](#what-changed)に箇条書き）は同じ GPL‑3.0 ライセンスで
提供されます。ライセンスに従い、オリジナルの著作権表示とライセンス全文は
[`LICENSE`](LICENSE) に保存されています。

### <img src="https://api.iconify.design/logos/qwen-icon.svg" width="26" height="26" align="middle" alt=""> Built with Qwen Studio

このフォークの大部分は **[Qwen Studio]** との緊密な協働で作られました:
グラスモフィズム UI への再構築、Rust ネイティブコア、ZipNN 圧縮エンジン、
ハブアップロードフロー、信頼性とセキュリティの強化、そしてデバッグの
多くまでです。

これらの優れたプロジェクトとともに構築: [reka-ui]・[Tailwind CSS]・[Lucide]・
[VueUse]・[es-toolkit]・[vue-sonner]・[huggingface_hub]・[hf_xet]・
[modelscope_hub]・[ZipNN]・[zenwebp]。

---

<a id="license"></a>

## <img src="https://api.iconify.design/lucide/scale.svg?color=%2394a3b8" width="34" height="34" align="middle" alt=""> ライセンス

**GPL‑3.0‑only** — 全文は [`LICENSE`](LICENSE) を参照してください。

Rust ネイティブコア（[`native/`](native/)）は、プレビュー WebP パイプラインのために
**[zenwebp]**（純 Rust WebP codec、**AGPL‑3.0‑only** または Imazen 商用の
デュアルライセンス）を追加でリンクします。Neo は GPL‑3.0‑only であり、zenwebp を
**AGPL‑3.0** 条件で使用します（AGPLv3 §13 は AGPL 成果物と GPLv3 成果物の結合を
明示的に許可しており、AGPL 部分は AGPL のままです）。ComfyUI はネットワーク
サービスではなく**ローカル**アプリケーションのため、AGPL のネットワーク条項は
ここでは実質的に作用せず、配布時のソース入手可能性義務はこの公開リポジトリに
よって満たされています。ネイティブコアの第三者帰属の全文:
[`native/NOTICE`](native/NOTICE)。

<div align="center">

**Neo が時間を節約してくれたなら、リポジトリへのスター <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="19" height="19" align="middle" alt=""> と、
[原作者](https://github.com/hayden-cn/ComfyUI-Model-Manager)への感謝をよろしくお願いします。**

</div>

<!-- Link references -->

[reka-ui]: https://reka-ui.com
[Tailwind CSS]: https://tailwindcss.com
[Lucide]: https://lucide.dev
[VueUse]: https://vueuse.org
[es-toolkit]: https://es-toolkit.dev
[vue-sonner]: https://vue-sonner.vercel.app
[huggingface_hub]: https://github.com/huggingface/huggingface_hub
[hf_xet]: https://github.com/huggingface/xet-core
[modelscope_hub]: https://github.com/modelscope/modelscope_hub
[ZipNN]: https://github.com/zipnn/zipnn
[zenwebp]: https://github.com/imazen/zenwebp
[uv]: https://docs.astral.sh/uv/
[Qwen Studio]: https://chat.qwen.ai/
[ComfyUI-Manager]: https://github.com/ltdrdata/ComfyUI-Manager
