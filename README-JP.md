<div align="center">

# <img src="https://api.iconify.design/lucide/boxes.svg?color=%236366f1" width="34" height="34" align="middle" alt=""> ComfyUI‑Model‑Manager‑Neo

### 閲覧・ダウンロード・アップロード・ドラッグ＆ドロップ — モデルを、美しく管理。

ComfyUI のモデルマネージャを **Vue 3 + Tailwind CSS v4 + reka‑ui** の上に
グラスモフィズムで再構築したフォークです。ツールチェーンも完全に現代化しています。

![License](https://img.shields.io/badge/License-GPL--3.0--only-blue.svg)
![ComfyUI](https://img.shields.io/badge/ComfyUI-Custom%20Node-8A8B98.svg)
![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D.svg?logo=vuedotjs&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38BDF8.svg?logo=tailwindcss&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6.svg?logo=typescript&logoColor=white)
![ESLint](https://img.shields.io/badge/ESLint-10-4B32C3.svg?logo=eslint&logoColor=white)
![Prettier](https://img.shields.io/badge/Prettier-3-F7B93E.svg?logo=prettier&logoColor=black)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

<!--
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  スクリーンショット                                                       │
  │  下記で参照している画像は `docs/screenshots/` に同梱されています。          │
  │  ファイルごとのマニフェストと、実働 ComfyUI からの撮り直し手順は           │
  │  docs/screenshots/README.md を参照してください。                          │
  └──────────────────────────────────────────────────────────────────────────┘
-->

![Hero overview](docs/screenshots/hero.gif)

</div>

---

**目次**

- [なぜ Neo なのか](#why-neo) · [スクリーンショット](#screenshots) ·
  [インストール](#installation) · [機能](#features)
- [ZipNN 可逆圧縮](#zipnn) · [オリジナルからの変更点](#what-changed) ·
  [削除した機能: バッチスキャン](#removed-feature)
- [ドキュメント](#documentation) · [開発](#development) ·
  [クレジットと帰属](#credits) · [ライセンス](#license)

---

<a id="why-neo"></a>

## <img src="https://api.iconify.design/lucide/sparkles.svg?color=%23f59e0b" width="28" height="28" align="middle" alt=""> なぜ Neo なのか

**ComfyUI‑Model‑Manager‑Neo** は優れたオリジナルのマネージャを引き継ぎつつ、
体験そのものを根本から作り直しました:

- <img src="https://api.iconify.design/lucide/layers.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **グラスモフィズム UI** — 半透明・ぼかし・奥行を意識したインターフェース。
  ComfyUI 本体のライト/ダークパレットに自動で追従します。
- <img src="https://api.iconify.design/lucide/puzzle.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **PrimeVue 不使用** — PrimeVue 依存をまるごと取り除き、軽量でヘッドレスな
  **[reka-ui]** プリミティブ + **Tailwind CSS v4** + **[Lucide]** アイコンへ置換
  （読み書き・調整しやすい shadcn‑vue スタイルのコンポーネント）。
- <img src="https://api.iconify.design/lucide/upload-cloud.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Hugging Face へアップロード** — ローカルモデルをそのまま HF リポジトリへ
  公開（必要ならリポジトリ作成、非公開オプション、ライブ進捗）— _Neo の新機能_。
- <img src="https://api.iconify.design/lucide/package-plus.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ZipNN 可逆圧縮** — safetensors モデルをその場で圧縮/解凍
  (`.znn.safetensors`)。確認ダイアログ・進捗表示・圧縮済みモデルでのアイコン反転付き。
  フォルダ単位では封印された `<name>_ZNN` バンドルへバッチ圧縮でき、ファインチューン
  モデルはベースに対する極小の**デルタファイル**に縮みます — _Neo の新機能_。
- <img src="https://api.iconify.design/lucide/list-checks.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **複数選択** — カードにチェックして、複数モデルのワークフロー投入や一括削除を
  一度に — _Neo の新機能_。フォルダもチェック可能で、「ワークフローに追加」は中身を
  再帰的に展開し、「削除」はフォルダごと削除します。
- <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="16" height="16" align="middle" alt=""> **スター** — すべてのモデル/フォルダカードの右上にスタートグル（モデル詳細の
  アクション列・選択バーにも）。スター付きは塗りつぶしの黄色いスターで表示され、
  常に先頭へ並びます — _Neo の新機能_。
- <img src="https://api.iconify.design/lucide/folder-plus.svg?color=%2322c55e" width="16" height="16" align="middle" alt=""> **フォルダ作成** — フォルダビューの「フォルダを追加」ボタンから、開いている
  ディレクトリの中に任意の名前の(サブ)フォルダを作成 — _Neo の新機能_。
- <img src="https://api.iconify.design/lucide/link.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **直接リンクダウンロード** — 生の `.safetensors`/`.ckpt`/`.gguf` URL を貼り付け、
  送り先フォルダと任意のカスタムサブフォルダを指定。
- <img src="https://api.iconify.design/lucide/zap.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **`hf_xet` 高速化** — Hugging Face 転送は、利用可能な場合チャンク分割・重複排除される
  Xet プロトコルを使用。
- <img src="https://api.iconify.design/lucide/workflow.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **第一級のノードグラフ連携** — モデルをキャンバスへドラッグしてノード生成・入力投入、
  embedding をテキストエリアへ、プレビュー画像に埋め込まれたワークフローの読込。
- <img src="https://api.iconify.design/lucide/monitor-smartphone.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **レスポンシブ** — デスクトップ・モバイル・マルチスクリーン構成を考慮した設計。
- <img src="https://api.iconify.design/lucide/wrench.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **モダンなツールチェーン** — Vite 8 (Rolldown)、TypeScript 6、ESLint 10 flat
  config、Prettier、husky + lint‑staged。決定的で lint クリーンなビルド。

> [!NOTE]
> Neo は [`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
> の**フォーク**であり、同じ **GPL‑3.0** ライセンスで配布されます。オリジナルの
> アーキテクチャに関するすべての功績は原作者に帰属します — [クレジット](#credits)参照。

---

<a id="screenshots"></a>

## <img src="https://api.iconify.design/lucide/camera.svg?color=%238b5cf6" width="28" height="28" align="middle" alt=""> スクリーンショット

> [!TIP]
> 以下の画像は**プレースホルダー**です。`docs/screenshots/` のチェックリストに
> 挙げたファイルを用意すれば自動的に表示されます。この拡張機能を入れた実働の
> ComfyUI から撮影してください（ダークテーマ推奨、統一感のため幅 ~1600 px）。

### フラット「モデル」ビュー — 検索・ソート・グリッドサイズ変更

![Flat models grid](docs/screenshots/view-flat.png)

**フラット**レイアウトのマネージャウィンドウ: プレビュー・種別/サイズチップ付きの
ガラス製モデルカードのグリッド、検索バー、種別/ソート/カードサイズのセレクタ。

### フォルダ（エクスプローラ）ビュー — ディレクトリツリーを辿る

![Folder explorer view](docs/screenshots/view-folders.png)

**フォルダ**レイアウトの1階層目。ブレッドクラム（各階層に小さなフォルダグリフ）と、
アニメーションするガラス製フォルダカードを表示。

### モデル詳細・編集・HuggingFace アップロード

|                                                                                                   |                                                                                                      |
| ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| ![Model info](docs/screenshots/model-info.png)                                                    | ![Edit mode](docs/screenshots/model-edit.png)                                                        |
| _モデル情報: プレビュー、基本情報テーブル（**Directory** の末尾 `/` に注目）、Description タブ。_ | _編集モード: 種別ドロップダウン、フォルダピッカーボタン、`folder/name` 接頭を受け付けるファイル名。_ |

|                                                                                    |                                                                                    |
| ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| ![HuggingFace upload](docs/screenshots/hf-upload.png)                              | ![Japanese UI](docs/screenshots/ja-model-info.png)                                 |
| _HuggingFace アップロード、ステップ3: リポジトリ ID、作成時に非公開、送り先パス。_ | _同じウィンドウの**日本語**表示 — UI は英語 / 中文 / 日本語の完全バンドルを出荷。_ |

10秒ツアー（開く → フォルダビュー → フォルダにホバー → 戻る → モデルを開く）は
[`docs/screenshots/hero.gif`](docs/screenshots/hero.gif)。カードを実キャンバスへ
ドラッグする様子は実働の ComfyUI ウィンドウからの撮影が最適です —
[`docs/screenshots/README.md`](docs/screenshots/README.md) 参照。

---

<a id="installation"></a>

## <img src="https://api.iconify.design/lucide/rocket.svg?color=%2322c55e" width="28" height="28" align="middle" alt=""> インストール

Neo は ComfyUI のカスタムノードとして動作します。いずれかの方法を選んでください:

**1 · Git clone（アップデート推奨）**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/rikunarita/ComfyUI-Model-Manager-Neo.git
```

**2 · 手動ダウンロード**

[リポジトリのアーカイブ](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/archive/refs/heads/main.zip)
をダウンロードし、`ComfyUI/custom_nodes/` に展開して、フォルダ名が
`ComfyUI-Model-Manager-Neo` であることを確認します。

**3 · ComfyUI Manager**

フォークがレジストリに掲載されていれば、[ComfyUI-Manager] で
**“ComfyUI‑Model‑Manager‑Neo”** を検索してインストールできます。

その後 **ComfyUI を再起動**してください。Python 依存（`huggingface_hub`、`hf_xet`、
`markdownify`）は初回起動時に自動インストールされます。ビルド済みの web バンドルは
[`web/`](web) に同梱されるため、拡張機能を**動かす**のに Node.js は不要です。

トップバーの **“Model Manager Neo”** ボタン、サイドバー、または
`Extensions → Model Manager Neo` メニューコマンドから開きます。

> [!TIP]
> Neo は活発に開発中です — 実用的で日常利用に耐えますが、インターフェースは
> まだ進化しうる点にご注意ください。フィードバックや Issue を歓迎します。

---

<a id="features"></a>

## <img src="https://api.iconify.design/lucide/list-checks.svg?color=%233b82f6" width="28" height="28" align="middle" alt=""> 機能

<details open>
<summary><b>閲覧と整理</b></summary>

- 2つのレイアウト: **フラット**グリッド（既定）と**フォルダ**エクスプローラ。
  いつでも切り替え可能。
- リアルタイム検索（`*` ワイルドカードと複数トークンの“AND”マッチに対応）。
- 名前・サイズ・作成日時・更新日時でのソート。
- カードサイズ調整（プリセット + 完全カスタム寸法）。
- 隠しファイル（`.` 始まり）の表示/非表示を再起動なしで切り替え。
- 画像**と動画**のプレビュー、ホバーで開閉するガラス製フォルダアートワーク、
  ガラス製のノープレビュー代替表示。

</details>

<details>
<summary><b>ノードグラフ連携</b></summary>

- モデルサムネイルをキャンバスへドラッグして**ローダーノードを追加**。
- 既存ノードへドラッグして**一致する入力へ投入**（曖昧なときは正確に一致）。
- **embedding** をテキストエリアへドラッグして `(embedding:name:1.0)` を追記。
- プレビュー画像をグラフへドラッグして**埋め込みワークフローを読込**。
- **追加** / **コピー** ボタンでノード配置または ComfyUI クリップボードへコピー。

</details>

<details>
<summary><b>ダウンロード</b></summary>

- **Civitai**・**Hugging Face**・**直接ファイル** URL を貼り付け。
- ページごとの複数ファイル/バージョンを解決して欲しいものを選択。
- 直接リンクは明示的な送り先種別が必要（任意のカスタムサブフォルダ対応）。
- ダウンロードごとに任意のプレビュー画像と編集可能な Markdown 説明。
- タスクの一時停止 / 再開 / 削除。進捗・速度・サイズはライブ更新。
- Hugging Face ダウンロードは `huggingface_hub`（利用可能なら `hf_xet` も）。

</details>

<details>
<summary><b>アップロード</b></summary>

- **ローカルファイルから**任意のモデルフォルダへ（Download List に進捗付きの
  ライブタスクとして登録）。
- **Hugging Face へ** _(Neo の新機能)_: HF トークンで認証、リポジトリが無ければ
  作成（公開/非公開）、送り先パスを選択、進捗を確認。

</details>

<details>
<summary><b>モデル情報とメンテナンス</b></summary>

- ファイル情報と safetensors メタデータの確認。
- 名前変更、フォルダ/種別間の移動、プレビューとノートごと**完全削除**。
- モデルの横に置かれた Markdown ノートの閲覧・編集・保存。
- プレビュー画像の変更・削除。
- モデル情報（safetensors メタデータ、Markdown ノート、プレビュー）はモデルを
  開いたときに要求ベースで読み込み — ライブラリ全体の走査ステップは存在しません。

</details>

<details>
<summary><b>設定と i18n</b></summary>

- **Civitai** と **Hugging Face** の API キーはローカルの `private.key` に保存
  （`CIVITAI_API_KEY` / `HF_TOKEN` 環境変数フォールバック付き）。初回実行時に
  ComfyUI ユーザー設定から移行されます。
- モデル一覧から種別を除外。隠しファイルの含む/除く。
- UI 言語は ComfyUI のロケールに追従 — **English**・**中文**・**日本語**を完全同梱。
  地域/文字サブタグ（`ja-JP`、`zh-Hant-TW` など）は基底言語へfold。

</details>

---

<a id="zipnn"></a>

## <img src="https://api.iconify.design/lucide/package-plus.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> ZipNN 可逆圧縮

**Neo の目玉機能。** 大容量の `.safetensors` チェックポイントはディスクをすぐに
圧迫します。Neo は [ZipNN](https://github.com/zipnn/zipnn) 形式 — 公式 ZipNN
プロジェクトと同じテンサル対応方式 — を使い、これらを**その場で・可逆的に**
圧縮/解凍できます。そのため圧縮結果は ZipNN エコシステム全体と互換のままです。

### 仕組み

モデル重みのほとんどは浮動小数点数であり、そして浮動小数点数のほとんどは
_冗長_です: 挙動の良好な重みテンサルでは指数部のバイトが何度も繰り返されます。
ZipNN はまさにそこを突きます。テンサルごとに:

- 値をバイトプレーンへ**分割**し、符号/指数/仮数のビットを並び替えて同種の
  バイトを集め、
- 各プレーンを FiniteStateEntropy (FSE) コーデックで **Huffman 符号化**します。

浮動小数点でないテンサル（整数インデックス、マスクなど）は無傷でそのまま
コピーされ、圧縮しても実際には小さくならない浮動小数点テンサルは水増しせず
**そのまま残されます**。圧縮された各テンサルは `uint8` ベクタとして格納され、
ファイルはそれぞれの元の `dtype` と `shape` を単一の `znn_compressed_vectors`
メタデータ項目に記録します。何も近似せず何も捨てません — 解凍は元ファイルを
**ビット単位で**復元します。

圧縮モデルは元の横に `<name>.znn.safetensors` として書き出されます — これは
公式 ZipNN の公式ツール群（および `zipnn_safetensors()` パッチ済みローダー）が期待する
正確な接尾辞なので、パッチ済み ComfyUI ローダーは Neo の圧縮モデルを透過的に
読めます。実在のチェックポイントは通常**元の 60〜80 %** 程度に収まります
（ランダム寄りデータはあまり縮みません。低エントロピーの重みはもっと縮みます）。

### 使い方

任意の `.safetensors` モデルを開きます。プレビューと情報テーブルの間の隙間に
**ZipNN アートワークそのもののボタン**があります — 同梱 SVG は自前のガラス盤
（ダークモード版含む）を描き、ホバーで浮き上がって明るくなり、ツールチップと
スクリーンリーダーに自分を説明します。押すと:

1. 意図的に“Danger”スタイルに**しない**確認ダイアログが出ます（圧縮は可逆で、
   圧縮ファイルが完全に書き込まれ検証されるまで元を削除しません）。
2. 作業が CPU プールで（テンサルごとに）走る間、ボタンは**ライブ進捗バー**に
   置き換わり、ComfyUI の他部分は応答性のままです。
3. 成功すると元ファイルが `<name>.znn.safetensors` へ置き換わります — プレビューと
   Markdown ノートもリネームに追従し、グリッドは自動更新されます。

**圧縮済み**モデルを開くと、同じアートワークが**色反転**した状態で現れ、アクションは
_解凍_ に反転。同じ確認を経てプレーンな `.safetensors` を復元します。情報テーブルも
変わり、1行の _ファイルサイズ_ が **元のファイルサイズ**・**圧縮後のファイルサイズ**・
**圧縮前サイズ比** に置き換わります — 圧縮前のサイズは圧縮時にファイルのメタデータへ
記録されるため、リネーム後も内訳が残ります（このキーを書かない公式 ZipNN CLI で
圧縮されたファイルは、そのまま通常の _ファイルサイズ_ 行を表示します）。

同じアートワークは**すべてのモデルカードとフォルダカードの右上隅**（スタートグルの
隣）にもあります: 1クリックで（圧縮済みなら反転したまま解凍）モデルを開かずに
同一の確認・進捗挙動で圧縮/解凍できます。単発・バッチ・デルタを問わず、タスク実行中
はボタンが**円形プログレスリング**になります。

### バッチ圧縮（フォルダ単位）

ZipNN 公式ツールはパス全体の圧縮に対応しています。Neo はそれをマネージャへ
組み込みました。フォルダを選択（「ファイルを選択」）して**下部バーの ZipNN
アートワークボタン**を押すか、フォルダカードのコーナーボタンを使うと、フォルダ
ツリー内のすべての `.safetensors` モデルが圧縮され（プレビューとノートも各モデルに
追従）、その後フォルダは **`<name>_ZNN`** へリネームされます。`*_ZNN` フォルダは
封印されたバンドルです:

- 内部に置けるモデルは `*.znn.*` のみ（プレーンモデルのアップロード・ダウンロード・
  移動は拒否されます）。
- `*_ZNN` フォルダと非 `*_ZNN` フォルダの同時選択は不可 — バンドル側が警告トーストと
  ともに自動で選択解除されます。
- `*_ZNN` フォルダでバッチボタンを押すと**解凍**され、元の名前へ戻ります。

複数フォルダはキューで処理されます: 確認は1回、タスクは逐次、進捗状態は一度に1つ。

### デルタ圧縮（ベースに対するファインチューン）

ファインチューン済みモデルはベースと大半のバイトを共有します。ZipNN はその
**差分だけ**を保存できます: プレーンな `.safetensors` モデルをちょうど2つ選択して
下部バーの **ZipNN デルタ圧縮** を押します。小さなダイアログで、選択のどちらが
**ベース** でどちらが**ファインチューン**かを選べます（内部では公式のファイルレベル
API（バイトレベルデルタ＋ヘッダ長整合）を使用）。結果 — 通常はファインチューン
サイズのわずか数% — は **`<base>_DeltaZNN/<ft>_delta_<base>.znn`** へ書き出され、
冗長なファインチューンファイルは削除されます。デルタの解凍（カードボタン、反転表示）
はファインチューン済みモデルをベースの隣へ**バイト完全一致**で復元し、空になった
デルタフォルダを片付けます。復元にはベースモデルが必要で、ZipNN はデルタ作成時に
両者のバイト長が同一であることを検証します。

### 同梱だから、そのまま動く

<details>
<summary><b>なぜ以前は辛かったのか — そして Neo の解決策</b></summary>

ZipNN の Python 側は trivial ですが、圧縮器は C 拡張です（`zipnn_core`、
FiniteStateEntropy 製）。**PyPI には Linux wheel がありません** — macOS-arm64 の
wheel とソース tarball だけで、素の `pip install zipnn` はソースからコンパイルされ、
C コンパイラと Python ヘッダー（`Python.h`）の無いマシンでは必ず死にます。それは
ComfyUI の非常に一般的な運用形態であり、失敗は難解です（`error: [Errno 2] No such
file or directory: 'x86_64-pc-linux-gnu-gcc'`）。

そこで Neo はライブラリ全体を [`third_party/`](third_party/) に**ベンダー同梱**し、
Linux x86_64（CPython 3.10〜3.13）向けの**ビルド済み `zipnn_core` バイナリ**を
同梱しました。これらのプラットフォームでは、初回の圧縮は同梱パッケージと該当
バイナリを `sys.path` へ載せるだけ — **コンパイラも pip もネットワークも待ち時間も
不要**です。ビルド済みバイナリが一致しない場合（macOS、Windows、珍しい
アーキテクチャ、非常に新しい CPython）のみ、同梱 C ソースからの**単一**のクリーン
ビルドへフォールバックします — pip 戦略のカスケードは決して行いません。

配置、プラットフォーム/glibc 対応範囲、ライセンス（ZipNN は MIT、
FiniteStateEntropy は BSD-2-Clause OR GPL-2.0）、バイナリの再ビルド・追加手順は
[`third_party/README.md`](third_party/README.md) を参照してください。

</details>

> [!NOTE]
> 圧縮はモデルのテンサルをメモリ上に必要とするため CPU プールで実行され、VRAM では
> なく RAM に制約されます。**完全に可逆**です: プレーンな `.safetensors`
> が削除されるのは `.znn.safetensors` が書き込まれ閉じられた後だけで、失敗した実行は
> 途中出力を片付けます。

---

<a id="what-changed"></a>

## <img src="https://api.iconify.design/lucide/git-compare.svg?color=%23a855f7" width="28" height="28" align="middle" alt=""> オリジナルからの変更点

この節は GPL‑3.0 ライセンスが求めるとおり、フォークの差異を明示します。機能は
保存・拡張されています。_削除_ されたのは2つ: PrimeVue 依存そのものと、バッチスキャン
機能 — [削除した機能: バッチスキャン](#removed-feature)参照。

### <img src="https://api.iconify.design/lucide/palette.svg?color=%23d946ef" width="22" height="22" align="middle" alt=""> インターフェース

| 領域             | オリジナル                        | **Neo**                                                                                 |
| ---------------- | --------------------------------- | --------------------------------------------------------------------------------------- |
| コンポーネント庫 | PrimeVue 4                        | **reka‑ui**（ヘッドレス）+ shadcn‑vue スタイルのラッパー                                |
| スタイリング     | Tailwind CSS v3 + PrimeVue テーマ | スコープ付き `--mm-*` デザイントークンの **Tailwind CSS v4**                            |
| アイコン         | PrimeIcons                        | アイコンマップ経由の **Lucide**（`@lucide/vue`）                                        |
| 見た目と操作感   | 標準的な PrimeVue サーフェス      | **グラスモフィズム**（ぼかし・奥行・マイクロインタラクション）、自動ダーク              |
| ダイアログ       | PrimeVue `Dialog`/`ContextMenu`   | reka‑ui ダイアログ、ダイアログごとのサイズ/位置、ドラッグ移動、固定コンテキストメニュー |

### <img src="https://api.iconify.design/lucide/package.svg?color=%23f97316" width="22" height="22" align="middle" alt=""> パッケージ

- **削除:** `primevue`、`@primevue/themes`、`lodash`、`dayjs`、`js-yaml`。
- **追加/置換:** `reka-ui`、`@lucide/vue`、`es-toolkit`（← lodash）、
  `date-fns`（← dayjs）、`yaml`（← js-yaml）、`valibot`（ランタイムスキーマ検証）、
  `vue-sonner`（トースト）、`class-variance-authority`、`clsx`、
  `tailwind-merge`、`tw-animate-css`。
- **アップグレード:** Vite 5 → **8** (Rolldown)、TypeScript 5 → **6**、Vue i18n 9 →
  **11**、markdown‑it 14 → **15**、`@vueuse/core` 11 → **14**。
- **Python:** `huggingface_hub` + `hf_xet` を追加。旧スレッドプールを asyncio タスク
  プールへ置換。

### <img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%2306b6d4" width="22" height="22" align="middle" alt=""> ツールバー / ボタンの役割

マネージャヘッダーは明示的でアイコン主導のアクションへ再設計しました:
**フラット ⇄ フォルダ レイアウト切替**、**隠しファイル表示/非表示**、**更新**、
**ダウンロード一覧**、**Hugging Face へアップロード**。

### <img src="https://api.iconify.design/lucide/folder-open.svg?color=%23f59e0b" width="22" height="22" align="middle" alt=""> ガラスアセットパック（フォルダアイコン & ノープレビューアート）

インターフェースは `assets/` の手作りグラスモフィズムアセットパックを活用します:

- **フォルダカード** は静止時 `Folder-Icons/close-folder_beside-fit.svg` を表示。
  カードにポインタを**1秒以上**置くと `folder-opening-animation.svg` が再生
  （SMIL モーフ: 0.2 s 遅延 + 1.35 s）。1秒離れ続けると
  `folder-closing-animation.svg` が再生され、その後カードは静止アイコンへ戻ります。
  通り過ぎただけではフォルダはばたつきません。SVG はバンドルへインライン化
  （`?raw` + data URI）されるため、各カードは自前の SVG ドキュメントを持ちます:
  追加リクエストは無く、アートワーク内の gradient id が画面上の多数のカード間で
  衝突することも決してありません。
- **ブレッドクラム** は各セグメントの先頭に小さな `close-folder_all-fit.svg`
  グリフを付けます — 小さいサイズで最も読みやすい変種です。
- **プレビューの無いモデル** はガラス製 `NOPREVIEW-Icon/NO-PREVIEW.svg` を
  **既定**のアートワークとして使用: モデル一覧は
  `GET /model-manager/no-preview.svg` を直接指します（`image/svg+xml` でそのまま
  配信され、ベクターアートはラスタ化されません）。プレビュールート自体にはもはや
  **フォールバック連鎖がありません** — 実在するプレビューファイルを提供するか、
  存在しないものには 404 で答えます — そして旧いフラットな `no-preview.png`
  ラスタは消えました。

### <img src="https://api.iconify.design/lucide/hammer.svg?color=%2365a30d" width="22" height="22" align="middle" alt=""> ツールチェーン

Biome は試用の後**削除**され、慣習的で完全に構成された **ESLint 10 flat config** +
**Prettier** パイプラインへ置き換わりました（[開発](#development)参照）。

---

<a id="removed-feature"></a>

## <img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="28" height="28" align="middle" alt=""> 削除した機能: バッチスキャン

**「モデル情報バッチスキャン」** 機能は**完全に削除**されました。冗長だったためです:
モデルを開けば、スキャンが一括補完していたすべてを、要求ベースで・まさに今見てる
モデルについて読み込むからです。

- `DialogModelDetail` はマウント直後に
  `GET /model-manager/model/{type}/{index}/{filename}` を要求します。これはモデルの
  `__metadata__`（safetensors ヘッダーから直接読込）とファイル横の Markdown ノートを
  返します。
- プレビューは `GET /model-manager/preview/{type}/{index}/{filename}` が配信し、
  実在するプレビューファイル（`.webp` / `.png` / `.jpg` / 動画、`name.ext` または
  `name.preview.ext`）を解決します。無いモデルはモデル一覧内で同梱のガラス製
  `NO-PREVIEW.svg` URL をそのまま持つため、ルートにフォールバック連鎖は無く、
  存在しないものには素の 404 で答えます。

ライブラリ全体を走査して全モデルをハッシュ化し Civitai へハッシュ問い合わせする
方式は、同じ情報へ至る第二の、ずっと遅い経路でした — それに加えてモーダル
ダイアログ、グローバルストア、2つの websocket イベント、ディスク上のタスク
ファイル、専用設定までメンテ対象でした。すべて撤去しました。

**フロントエンド**

- `src/components/DialogScanning.vue` と `src/hooks/scan.ts` を削除。
- `App.vue`: `scanning` ツールバーボタン、`openModelScanning()`、`DialogScanning`
  import を削除。`utils/iconMap.ts`: `mdi mdi-folder-search-outline` マッピングと
  その `FolderSearch` import を削除。
- `en.json` / `zh.json` / `ja.json` からスキャン専用の10キーを削除
  （`batchScanModelInformation`、`modelInformationScanning`、`scanModelInformation`、
  `selectedAllPaths`、`scanFullInformation`、`scanMissInformation`、
  `scanCompleted`、`scanCompletedWithErrors`、`setting.scanAll`、
  `setting.scanMissing`）。

**バックエンド**

- `py/information.py`: `GET` と `POST /model-manager/model-info/scan` ルート、
  `create_scan_model_info_task`、`download_model_info`、
  `get_scan_model_info_task_list`、`get_scan_information_task_filepath`、
  `SCAN_TASK_ID`、スキャン専用の `DownloadThreadPool`（および不要になった
  `functools` / `thread` import）を削除。
- `ModelSearcher.search_by_hash` とその3実装を削除 — スキャンが唯一の呼び出し元
  でした。`_resolve_model_type` は残します: `search_by_url` が使用します。
- `py/utils.py`: `recursive_search_files` と `calculate_sha256`（および `hashlib`
  import）を削除 — どちらもスキャン専用でした。
- `update_scan_information_task` / `complete_scan_information_task` websocket イベントは
  存在せず、`downloads/scan_information.task` ファイルも書かれません。

**意図的に残したもの** — “scan” と付きますがバッチスキャンの一部では_ありません_:

- `ModelManager.Scan.excludeScanTypes` と `ModelManager.Scan.IncludeHiddenFiles` は
  **モデル一覧**（グリッドへ読み込む種別、`.` 始まりファイルの表示）とツールバーの
  隠しファイル表示/非表示トグルを司ります。**この2つの設定 ID 文字列は意図的に
  不変更**: ID は ComfyUI がユーザー値を永続化するキーなので、改名すると既存
  インストールの保存設定が静かに孤立します。
- これら ID の_周囲_はすべて de‑scan 済みです。どれも永続化されないため: 設定
  カテゴリは現在 **Model List**（旧 “Scan”）、ラベルは
  **“Exclude model types (separate with commas)”**（旧 “Exclude scan types”）、i18n キーは
  `setting.modelList` / `setting.excludeModelTypes`、TypeScript 識別子は
  `configSetting.excludeModelTypes`、`py/config.py` のバックエンド設定グループは
  `model_list`（よって `manager.py` は `model_list.include_hidden_files` を解決）。
- `ModelManager.scan_models()` / `os.scandir` — モデル**一覧**を構築します（ここの
  “scan” は上流同様「フォルダを列挙する」の意）。意図的にそのまま: 改名は削除
  機能と無関係なコードを無為に churn させます。
- `scan_model_download_task_list()` — **ダウンロードタスク**の一覧。同じ理由。
- `src/style.css` の Tailwind “source scan” 表現 — 無関係。
- `ui/tree`、`ui/progress`、`useModelFolder`、`selectModelType` /
  `selectSubdirectory` / `selectedSpecialPath` / `noModelsInCurrentPath` 文字列 —
  Upload / Hugging Face Upload ダイアログとモデルエディタが共有。

> [!NOTE]
> **これで失うもの:** Civitai からハッシュでプレビューと説明を_一括補完_する唯一の
> 手段。情報を一度も取得していないモデルは、プレビュー/ノートを手で設定するか
> （モデルエディタ → **Preview** → _Network_ / _Local_）、プレビュー付きの
> _Create Download Task_ で再ダウンロードするまで、プレースホルダープレビューのままです。
> モデル情報の読み取りは影響を受けません — あれは常にディスクから要求ベースでした。

<a id="documentation"></a>

## <img src="https://api.iconify.design/lucide/book-open.svg?color=%237c3aed" width="28" height="28" align="middle" alt=""> ドキュメント

手順付きの利用ガイド。それぞれ完結・自己完結です:

- [`docs/USAGE-EN.md`](docs/USAGE-EN.md) — English
- [`docs/USAGE-JA.md`](docs/USAGE-JA.md) — 日本語
- [`docs/USAGE-ZN.md`](docs/USAGE-ZN.md) — 中文

インストール、両レイアウト、カード操作とグラフへのドラッグ、モデルエディタ
（フォルダピッカー、フォルダ接頭名、プレビュー、説明）、ダウンロードとタスク一覧、
HuggingFace アップロードの各フェーズと完了メッセージ、ZipNN 圧縮、設定とロケール、
トラブルシューティング表までを扱います。埋め込みスクリーンショットは
[`docs/screenshots/`](docs/screenshots/) に、ファイルごとのマニフェストは
[`docs/screenshots/README.md`](docs/screenshots/README.md) にあります。

<a id="development"></a>

## <img src="https://api.iconify.design/lucide/terminal.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> 開発

web バンドルの**ビルド**にのみ Node.js が必要。ComfyUI 内での実行は Python だけです。

```bash
corepack enable          # ピン留めされた pnpm バージョンを使用
pnpm install
```

| スクリプト                              | 用途                                                                    |
| --------------------------------------- | ----------------------------------------------------------------------- |
| `pnpm dev`                              | Vite dev サーバ（ComfyUI ホットリロード用 `web/manager-dev.js` を書く） |
| `pnpm build`                            | `web/` へのプロダクションビルド                                         |
| `pnpm build:clean`                      | `web/` を削除してから再ビルド                                           |
| `pnpm rebuild`                          | `node_modules/` と `web/` を削除、再インストール、再ビルド              |
| `pnpm typecheck`                        | `vue-tsc --noEmit` 型チェック                                           |
| `pnpm lint` / `pnpm lint:fix`           | ESLint（flat config）                                                   |
| `pnpm format` / `pnpm format:check`     | Prettier（Tailwind プラグイン込み）                                     |
| `python -m mypy --config-file mypy.ini` | バックエンド静的型、クリーン                                            |

> [!WARNING]
> `pnpm dev` は `manager-dev.js` を書く前に **`web/` ディレクトリ全体を削除**します
> （`vite.config.ts` の `dev()` プラグイン参照）。つまりコミット済みのプロダクション
> バンドル — `web/manager.js` と `web/style-*.css` — が作業ツリーから消え、
> `git status` に削除として表示されます。その状態でコミットすると UI が読み込めない
> 拡張機能を出荷してしまいます。コミット前は必ず `pnpm build` を実行し、
> `web/manager.js` の無いツリーを決してコミットしないでください。

**husky** の `pre-commit` フックがステージ済みファイルに **lint-staged**
（ESLint `--fix` + Prettier）を実行します。

### Lint & format スタック

ESLint 10 flat config が `typescript-eslint`、`eslint-plugin-vue`
（`vue-eslint-parser` 経由）、`eslint-plugin-import-x`（alias 対応の import 順序）、
`eslint-plugin-tailwindcss`（クラス衛生）、`eslint-config-prettier`（必ず最後）を
連結。Prettier は書式と Tailwind クラス並べ替えを `prettier-plugin-tailwindcss` で
担当します。

### プロジェクト構成

```
├─ __init__.py            # ComfyUI エントリ: 依存導入・ルート登録
├─ py/                    # Python バックエンド（aiohttp ルート、HF/Civitai、タスク）
│  ├─ manager.py          #   モデル CRUD + フォルダ一覧 + フォルダ作成
│  ├─ download.py         #   ダウンロードタスク（http + huggingface_hub）
│  ├─ upload.py           #   ローカルファイルアップロード（パス検証済み）
│  ├─ upload_hf.py        #   Hugging Face へアップロード
│  ├─ compress.py         #   ZipNN 圧縮/解凍/バッチ/デルタ（ベンダーコア使用）
│  ├─ information.py      #   Civitai/HF を URL 検索、プレビュー配信
│  ├─ auth.py · config.py · thread.py · utils.py
├─ third_party/           # ベンダー ZipNN（Python pkg + ビルド済み zipnn_core + C ソース）
├─ src/                   # Vue 3 フロントエンド
│  ├─ components/         #   アプリ部品 + ui/（reka-ui ラッパー）
│  ├─ hooks/              #   store, models, download, config, dialog, stars, zipnn …
│  ├─ utils/ · types/ · locales/
│  ├─ style.css           #   Tailwind v4 エントリ + デザイントークン
│  └─ main.ts             #   ComfyUI 拡張の登録
└─ web/                   # ComfyUI へ配信するビルド済みバンドル（コミット済み）
```

---

<a id="credits"></a>

## <img src="https://api.iconify.design/lucide/heart-handshake.svg?color=%23ec4899" width="28" height="28" align="middle" alt=""> クレジットと帰属

ComfyUI‑Model‑Manager‑Neo が存在するのは、
**[hayden‑cn](https://github.com/hayden-cn)** による
**[`ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)** が
先に存在したからです。このフォークの構造的アイデアのすべて — モデルフォルダの
抽象化、websocket 進捗プロトコルを持つ再開可能ダウンロードタスク機構、Civitai /
HuggingFace ページパーサ、カードをグラフへドラッグする連携、モデルエディタの
フォーム配管、カードサイズプリセットのような小さな配慮まで — は hayden‑cn の
設計です。Neo は皮膚と依存とたくさんのバグを変えただけ。躯体を発明する必要は
ありませんでした。オリジナルを読むことが、_なぜ_ このコードベースがこのような
形なのかを理解する最速の方法であり、アーキテクチャに対する誠実な帰属は:
**彼らのもの** です。

このフォークは **GNU General Public License v3.0** に従って使用・改変された派生物です。
Neo の改変（UI 再構築、PrimeVue 除去、Hugging Face アップロード、ZipNN 圧縮、
パッケージ現代化、ツールチェーン、信頼性とセキュリティの強化、バッチスキャン除去、
日本語ローカライズ）は同じ GPL‑3.0 ライセンスで提供されます。ライセンスに従い、
オリジナルの著作権表示とライセンス全文を [`LICENSE`](LICENSE) に保存しています。

### <img src="https://api.iconify.design/lucide/bot.svg?color=%236366f1" width="22" height="22" align="middle" alt=""> Built with Qwen Studio

このフォークの大部分は **[Qwen Studio]** とともに作られました。ZipNN 統合 —
ライブラリのベンダー同梱、ビルド済み `zipnn_core` バイナリの生成、テンサルごとの
圧縮/解凍の移植 — 、グラスモフィズム UI の再構築、Hugging Face アップロードフロー、
信頼性とセキュリティの各パス、そしてデバッグの多くが Qwen Studio との密接な
協働で開発されました。その慎重で反復的なエンジニアリングこそが Neo の頑健さの
大きな理由であり、このプロジェクトはその貢献に感謝します。

このフォークが役に立ったなら、スターは上流リポジトリへ: 上記すべてを可能にしたのは
その肩の上に立つ作業です。

素晴らしいプロジェクトとともに作られました: [reka-ui]、[Tailwind CSS]、[Lucide]、
[VueUse]、[es-toolkit]、[valibot]、[vue-sonner]、[huggingface_hub]、[hf_xet]、
そして [ZipNN]。

---

<a id="license"></a>

## <img src="https://api.iconify.design/lucide/scale.svg?color=%2394a3b8" width="28" height="28" align="middle" alt=""> ライセンス

**GPL‑3.0‑only** — 全文は [`LICENSE`](LICENSE) を参照。

<div align="center">

**Neo があなたの時間を節約したら、リポジトリにスターを <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="16" height="16" align="middle" alt=""> そして
[原作者](https://github.com/hayden-cn/ComfyUI-Model-Manager) への感謝を。**

</div>

<!-- Link references -->

[reka-ui]: https://reka-ui.com
[Tailwind CSS]: https://tailwindcss.com
[Lucide]: https://lucide.dev
[VueUse]: https://vueuse.org
[es-toolkit]: https://es-toolkit.dev
[valibot]: https://valibot.dev
[vue-sonner]: https://vue-sonner.vercel.app
[huggingface_hub]: https://github.com/huggingface/huggingface_hub
[hf_xet]: https://github.com/huggingface/xet-core
[ZipNN]: https://github.com/zipnn/zipnn
[Qwen Studio]: https://chat.qwen.ai/
[ComfyUI-Manager]: https://github.com/ltdrdata/ComfyUI-Manager
