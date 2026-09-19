<div align="center">

# <img src="https://api.iconify.design/lucide/boxes.svg?color=%236366f1" width="34" height="34" align="middle" alt=""> ComfyUI‑Model‑Manager‑Neo

### 閲覧 · ダウンロード · アップロード · ドラッグ&ドロップ — モデルを、美しく管理。

ComfyUI のモデルマネージャーを、ガラスモーフィズムの UI とモダンなツールチェーンで
再構築したフォークです。**Vue 3 + Tailwind CSS v4 + reka‑ui** を基盤にしています。

![License](https://img.shields.io/badge/License-GPL--3.0--only-blue.svg)
![ComfyUI](https://img.shields.io/badge/ComfyUI-Custom%20Node-8A8B98.svg)
![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D.svg?logo=vuedotjs&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38BDF8.svg?logo=tailwindcss&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6.svg?logo=typescript&logoColor=white)
![ESLint](https://img.shields.io/badge/ESLint-10-4B32C3.svg?logo=eslint&logoColor=white)
![Prettier](https://img.shields.io/badge/Prettier-3-F7B93E.svg?logo=prettier&logoColor=black)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

</div>

<div align="center">
<p align="center">
  <img src="QR_663267.svg" width="150">
</p>
リポジトリの QR コードです。読み取ると、お手元のデバイスでこのリポジトリを直接開けます。

</div>

---

**目次**

- [なぜ Neo なのか](#why-neo) · [UI ツアー](#screenshots) · [インストール](#installation) ·
  [機能](#features)
- [ZipNN 無劣化圧縮](#zipnn) · [オリジナルからの変更点](#what-changed) ·
  [削除した機能: バッチスキャン](#removed-feature)
- [ドキュメント](#documentation) · [開発](#development) ·
  [クレジットと帰属](#credits) · [ライセンス](#license)

---

<a id="why-neo"></a>

## <img src="https://api.iconify.design/lucide/sparkles.svg?color=%23f59e0b" width="28" height="28" align="middle" alt=""> なぜ Neo なのか

**ComfyUI‑Model‑Manager‑Neo** は、オリジナルのモデルマネージャーの設計を活かしつつ、
見た目・依存関係・機能のすべてを今の ComfyUI に合わせて作り直したものです。

- <img src="https://api.iconify.design/lucide/layers.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ガラスモーフィズム UI** — 半透明・ブラー・奥行き表現を備え、ComfyUI 本体の
  ライト/ダークパレットに自動で追従します。
- <img src="https://api.iconify.design/lucide/puzzle.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **PrimeVue 非依存** — PrimeVue を含まず、ヘッドレスな **[reka-ui]** プリミティブ +
  **Tailwind CSS v4** + **[Lucide]** アイコンで構成しています(コンポーネントは
  shadcn-vue スタイルで、中身を読んで調整できます)。
- <img src="https://api.iconify.design/lucide/upload-cloud.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Hugging Face / ModelScope へのアップロード** — ローカルのモデルを HF リポジトリ
  または ModelScope のモデルリポジトリへ直接公開できます(リポジトリがなければ作成、
  非公開指定可、進捗はリアルタイム表示)。
- <img src="https://api.iconify.design/lucide/package-plus.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ZipNN 無劣化圧縮** — safetensors モデルをインプレースで圧縮・解凍
  (`.znn.safetensors`)。確認ダイアログと進捗表示を備え、圧縮済みモデルではアイコンが
  反転します。フォルダー単位の一括圧縮、ベースモデルに対する**デルタ圧縮**にも
  対応しています。
- <img src="https://api.iconify.design/lucide/list-checks.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **マルチセレクト** — カードにチェックを入れて、複数のモデルをワークフローへ
  一度に追加したり、まとめて削除したりできます。フォルダーも選択でき、
  「Add to workflow」は中身を再帰的に展開、「Delete」はフォルダーごと削除します。
- <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="16" height="16" align="middle" alt=""> **スター** — すべてのモデルカードとフォルダーカードの右上にスタートグルがあります
  (モデル詳細のアクション行とセレクションバーにも配置)。スター付きの項目は
  塗りつぶしの黄色い星で表示され、常に先頭へソートされます。
- <img src="https://api.iconify.design/lucide/folder-plus.svg?color=%2322c55e" width="16" height="16" align="middle" alt=""> **フォルダー作成** — フォルダービューの「Add Folder」ボタンから、開いている
  ディレクトリ内に任意の名前の(サブ)フォルダーを作成できます。
- <img src="https://api.iconify.design/lucide/link.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ダイレクトリンクダウンロード** — 生の `.safetensors` / `.ckpt` / `.gguf` URL を
  貼り付け、対象フォルダー(任意でサブフォルダーも)を指定できます。
- <img src="https://api.iconify.design/lucide/zap.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **`hf_xet` アクセラレーション** — Hugging Face からの転送は、利用可能な環境では
  チャンク転送・重複排除を行う Xet プロトコルを使います。
- <img src="https://api.iconify.design/lucide/workflow.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ノードグラフ統合** — モデルをキャンバスへドラッグしてノードの生成・入力の充填、
  embedding をテキストエリアへ追記、プレビュー画像に埋め込まれたワークフローの
  読み込みができます。
- <img src="https://api.iconify.design/lucide/monitor-smartphone.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **レスポンシブ** — デスクトップ・モバイル・マルチスクリーン構成を想定した設計です。
- <img src="https://api.iconify.design/lucide/wrench.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **モダンなツールチェーン** — Vite 8 (Rolldown)、TypeScript 6、ESLint 10 フラット
  コンフィグ、Prettier、husky + lint‑staged。ビルドは決定論的で、lint もクリーンです。

> [!NOTE]
> Neo は [`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
> のフォークであり、同じ **GPL‑3.0** ライセンスのもとで配布されます。
> オリジナルのアーキテクチャに対するクレジットは、すべてその作者に帰属します
> ([クレジットと帰属](#credits)を参照)。

---

<a id="screenshots"></a>

## <img src="https://api.iconify.design/lucide/camera.svg?color=%238b5cf6" width="28" height="28" align="middle" alt=""> UI ツアー

> [!NOTE]
> デモ GIF とスクリーンショットは準備中です。整い次第このセクションへ掲載します。
> それまでは、各画面の見どころをテキストでご案内します。

### フラット「Models」ビュー — 検索・ソート・グリッドのリサイズ

**Flat** レイアウトのマネージャーウィンドウです。プレビューとタイプ・サイズのチップを
備えたガラス調のモデルカードがグリッド状に並び、検索バーと
タイプ / ソート / カードサイズの各セレクターが揃っています。

### フォルダー(エクスプローラー)ビュー — ディレクトリツリーのナビゲート

**Folder** レイアウトで 1 階層潜った画面です。ブレッドクラム(各セグメントに小さな
フォルダーグリフ付き)と、アニメーションするガラス調のフォルダーカードを表示します。

### モデル詳細・編集・Hugging Face アップロード

- **モデル情報**: プレビューと基本情報テーブル(**Directory** の末尾に `/` が付きます)、
  そして Description / Information タブ。
- **編集モード**: タイプのドロップダウン、フォルダーピッカーボタン、
  `folder/name` プレフィックスを受け付けるファイル名欄。
- **Hugging Face へのアップロード**(ステップ 3): リポジトリ ID、作成時のプライベート
  指定、アップロード先パス。
- **日本語 UI**: 同じウィンドウを日本語で表示した画面。UI は
  English / 中文 / 日本語 の完全な言語バンドルを同梱しています。

ウィンドウを開き、フォルダービューへ潜り、フォルダーにホバーして戻り、モデルを開き、
カードをキャンバスへドラッグする — そんな一連の操作感は、ぜひ実際の ComfyUI 上で
確かめてみてください。

---

<a id="installation"></a>

## <img src="https://api.iconify.design/lucide/rocket.svg?color=%2322c55e" width="28" height="28" align="middle" alt=""> インストール

Neo は ComfyUI のカスタムノードとして動作します。いずれかの方法を選んでください。

**1 · Git clone(アップデートしやすい推奨方法)**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/rikunarita/ComfyUI-Model-Manager-Neo.git
```

**2 · 手動ダウンロード**

[リポジトリのアーカイブ](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/archive/refs/heads/main.zip)
をダウンロードして `ComfyUI/custom_nodes/` に展開し、フォルダー名が
`ComfyUI-Model-Manager-Neo` になっていることを確認してください。

**3 · ComfyUI Manager**

このフォークがレジストリに登録されている場合、[ComfyUI-Manager] で
**「ComfyUI‑Model‑Manager‑Neo」** を検索してインストールできます。

その後、**ComfyUI を再起動**してください。Python 依存(`huggingface_hub`、`hf_xet`、
`markdownify`)は初回起動時に自動でインストールされます。ビルド済みの Web バンドルは
[`web/`](web) に同梱されているため、拡張を*実行するだけ*なら Node.js は不要です。

起動は、トップバーの **「Model Manager Neo」** ボタン、サイドバー、または
`Extensions → Model Manager Neo` メニューコマンドから行えます。

> [!TIP]
> Neo は開発が進行中のプロジェクトです。日常利用に耐える品質を目指していますが、
> インターフェースは今後も変わり得ます。フィードバックや Issue は歓迎します。

---

<a id="features"></a>

## <img src="https://api.iconify.design/lucide/list-checks.svg?color=%233b82f6" width="28" height="28" align="middle" alt=""> 機能

<details open>
<summary><b>閲覧と整理</b></summary>

- 2 つのレイアウト: **Flat** グリッド(既定)と **Folder** エクスプローラー。いつでも切り替えられます。
- リアルタイム検索(`*` ワイルドカードと、複数トークンの AND マッチに対応)。
- 名前・サイズ・作成日・更新日・**最近使用**(モデルを開くかグラフへ追加すると記録)でのソート。
- カードサイズの調整(プリセット + 完全カスタムの寸法指定)。
- 隠しファイル(`.` 始まり)の表示/非表示を、再起動なしで切り替え。
- 画像**と動画**のプレビュー。ホバーで開閉アニメーションするガラス調のフォルダー
  アートワークと、ガラス調のプレビュー無しアートワークを用意。
- タイプルートのフォルダーカードは、その**タイプの合計サイズ**を表示します。また、
  記録済み SHA256 がライブラリ内の別ファイルと一致するモデルは、詳細ウィンドウに
  赤い**重複警告**を出します。
- **スマートコレクション** — フラットビューの現在の検索 + タイプフィルタを、名前付きの
  コレクションとしてユーザー単位で保存し、ワンクリックで再適用できます。保存ボタンは
  コレクションセレクタの前の余白に配置されています(普段は減光、ホバーで明るくなります)。
- **衛生スキャン** — ローカルのみ(ネットワーク・ハッシュ計算なし)で、孤立した
  プレビュー/ノート、プレビューのないモデル、空フォルダーを一覧化し、確認ダイアログ
  経由で一括削除できます。

</details>

<details>
<summary><b>ノードグラフ統合</b></summary>

- モデルのサムネイルをキャンバスへドラッグすると、**ローダーノードを追加**します。
- 既存ノードへドラッグすると、**一致する入力を充填**します(候補が曖昧な場合は完全一致が必要)。
- **embedding** をテキストエリアへドラッグすると、`(embedding:name:1.0)` を追記します。
- プレビュー画像をグラフへドラッグすると、**埋め込みワークフローを読み込み**ます。
- **Add** / **Copy** ボタンで、ノードの配置や ComfyUI クリップボードへのコピーができます。

</details>

<details>
<summary><b>ダウンロード</b></summary>

- **Civitai**・**Hugging Face**・**ModelScope**(`www.modelscope.ai`)・**直接ファイルリンク**
  の URL を貼り付けて利用できます。
- 1 つのページから複数のファイル/バージョンを解決し、欲しいものを選択できます。
- ダイレクトリンクは対象タイプの明示的な指定が必須で、任意でカスタムサブフォルダーも指定できます。
- プレビュー画像は任意で取得でき、モデルページが提供する**ギャラリー全体**を保持します。
  ダウンロード時に選択していた画像がカードのプライマリプレビューになり、ダウンロード
  ごとの Markdown 説明も編集・保存できます。
- **空き容量ガード**: ダウンロードダイアログが保存先ボリュームの空き容量を表示し、
  サイズが収まらないタスクはバックエンドが拒否します。
- タスクの一時停止 / 再開 / 削除に対応。進捗・速度・サイズはリアルタイムで更新されます。
- Hugging Face からのダウンロードは `huggingface_hub` を使用します(利用可能なら `hf_xet` も併用)。

</details>

<details>
<summary><b>アップロード</b></summary>

- **ローカルファイルから**任意のモデルフォルダーへアップロードできます
  (Download List に進捗付きのライブタスクとして登録されます)。
- **Hugging Face / ModelScope へ**: ウィザードの最初のステップでプラットフォームを
  選択。対応するトークンで認証し、リポジトリが存在しなければ作成(公開/非公開を
  選択)、アップロード先パスを指定して進捗を確認できます。ModelScope は常に国際
  ドメイン `www.modelscope.ai` へ接続し、そのロゴは他のハブと同じく「モデルページを
  開く」ボタンの背景になります。オプションの**関連アセット**スイッチは、
  `<モデル名>.*` のサイドカー(プレビュー画像・Markdown ノート)もモデルの隣へ
  アップロードします(ノートは既定でリポジトリの `README.md` としてコミット)。
  選択した**フォルダー**は、フォルダービューのセレクションバーから一括アップロード
  できます(内部の全モデル、サブフォルダー構造も保持)。

</details>

<details>
<summary><b>モデル情報とメンテナンス</b></summary>

- 読み取り専用の **Information** テーブルで、モデルに記録された情報をすべて読めます。
  ノートの YAML フロントマターを、作者・ベースモデル・各種ハッシュ(`AutoV1` …
  `SHA256_12`)・フォーマットとプレシジョン・モデルプラットフォーム・モデルページへの
  リンク・全プレビュー URL へ展開し(解析できないキーは末尾にそのまま表示)、ノートの
  ないモデルは safetensors の `__metadata__` ブロックをそのまま表示します。
- モデルのリネーム、フォルダー/タイプ間の移動、プレビューやノートを含めた**完全削除**。
- モデルの隣に保存された Markdown ノートの閲覧・編集・保存。Information テーブル自体も、
  警告付きで編集できます(保存時にノートのフロントマターを書き換えます)。
- プレビュー画像の変更・削除 — 保存時に開いていたギャラリーページが、カードの
  プライマリプレビューになります。編集モードのギャラリーグリッド末尾の点線タイル
  から、ローカル画像を追加できます。
- **モデルページを開く**アクションのボタン背景には、モデルの出所(Civitai /
  Hugging Face)のロゴが表示されます。
- safetensors モデルは、ヘッダーから解析した**テンソル構成**を畳み込み可能な
  **フォルダーツリー**(ドット区切りのテンソル名を階層化、階層ごとのフォルダーアイコン、
  既定は畳んだ状態、テンソル名 / dtype / 形状を表示)として Information タブに表示します。
- モデル情報(safetensors メタデータ・テンソル構成・Markdown ノート・プレビュー)は、
  モデルを開いたときにオンデマンドで読み込まれます。ライブラリ全体をスキャンする
  別工程はありません。

</details>

<details>
<summary><b>設定と i18n</b></summary>

- **Civitai**・**Hugging Face**・**ModelScope** の API キーを `private.key` にローカル保存
  (`CIVITAI_API_KEY` / `HF_TOKEN` / `MODELSCOPE_API_TOKEN` 環境変数へのフォールバック付き)。
  キーは初回起動時に ComfyUI ユーザー設定から移行されます。
- モデルリストから特定のモデルタイプを除外、隠しファイルの含める/除外を設定できます。
- ZipNN の自動化: 未使用 N 日のモデルを自動圧縮、ダウンロード完了後に自動圧縮、
  prompt 実行中はダウンロードを一時停止。
- UI 言語は ComfyUI のロケールに追従します — **English**・**中文**・**日本語** をフル
  バンドル。リージョン/文字体系のサブタグ(`ja-JP`、`zh-Hant-TW` など)は基本言語へ
  畳まれます。

</details>

---

<a id="zipnn"></a>

## <img src="https://api.iconify.design/lucide/package-plus.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> ZipNN 無劣化圧縮

大容量の `.safetensors` チェックポイントはディスク容量を大きく消費します。Neo は
それらを [ZipNN](https://github.com/zipnn/zipnn) フォーマットにより**インプレースかつ
無劣化**で圧縮・解凍できます。テンソルを認識する方式は公式 ZipNN プロジェクトと
同じなので、生成物はより広い ZipNN エコシステムと互換性を保ちます。

### 仕組み

モデルの重みの大半は浮動小数点数であり、浮動小数点数の大半は*冗長*です。
素性の良い重みテンソルの指数部バイトには、同じ値が何度も繰り返し現れます。
ZipNN が狙うのはまさにこの性質です。各テンソルに対して:

- 値をバイトプレーン単位に**分割**し、符号 / 指数 / 仮数のビットを並べ替えて
  同種のバイト同士を集約し、
- 各プレーンを FiniteStateEntropy(FSE)コーデックで**ハフマン符号化**します。

浮動小数点数*でない*テンソル(整数インデックス、マスクなど)は無加工のままコピーされ、
圧縮しても実際には小さくならない浮動小数点テンソルは、水増しせずに**そのまま**
残されます。圧縮された各テンソルは `uint8` ベクトルとして格納され、すべてのテンソルの
元の `dtype` と `shape` は、単一の `znn_compressed_vectors` メタデータエントリに記録
されます。近似も間引きも行われず、解凍すれば元のファイルが**ビット単位で完全**に
再現されます。

圧縮済みモデルは `<name>.znn.safetensors` として元のファイルの隣に書き出されます。
これは公式 ZipNN ツール(`zipnn_safetensors()` でパッチを当てたローダーを含む)が
期待するサフィックスそのものなので、パッチ済みの ComfyUI ローダーは Neo が圧縮した
モデルを透過的に読み込めます。実用的なチェックポイントなら、おおむね元サイズの
**60〜80%** に収まります(ランダム性の高いデータはほとんど圧縮できず、低エントロピーの
重みはそれ以上に小さくなります)。

### 使い方

任意の `.safetensors` モデルを開いてください。プレビューと情報テーブルの間に、
**ZipNN のアートワークそのもののボタン**があります。同梱の SVG は自前のグラスプレート
(ダークモード版を含む)を描画し、ホバーで浮き上がって明るくなり、ツールチップと
スクリーンリーダーの両方で役割を説明します。押すと:

1. 確認を求めます(あえて「Danger」風のスタイルにはしていません。圧縮は可逆であり、
   圧縮ファイルの書き込みと検証が完全に終わるまで元ファイルは削除されないためです);
2. 処理中(CPU プール上でテンソルごとに実行)、ボタンは**ライブ進捗バー**に置き換わり、
   ComfyUI の他の部分は応答性を保ちます;
3. 成功すると、元ファイルが `<name>.znn.safetensors` に置き換わります。プレビューと
   Markdown ノートもリネームに追従し、グリッドは自動で再描画されます。

**圧縮済み**のモデルを開くと、同じアートワークの色が**反転**して表示され、アクションは
同じ確認ダイアログを挟んで*解凍*に切り替わり、プレーンな `.safetensors` を復元します。
情報テーブルも変わり、単一の _File Size_ 行が **Original File Size**・**Compressed File
Size**・**% of Original Size** の 3 行に置き換わります(圧縮前のサイズは圧縮時にファイルの
メタデータへ記録されるため、リネーム後も内訳は残ります。このキーを書き込まない公式
ZipNN CLI で圧縮されたファイルは、プレーンな _File Size_ 行のままです)。

同じアートワークは、**すべてのモデルカードとフォルダーカードの右上**(スタートグルの隣)
にも配置されています。ワンクリックで、モデルを開かずに同一の確認・進捗動作で圧縮
(反転表示の場合は解凍)を実行できます。シングル・バッチ・デルタのいずれのタスクが
実行中であっても、ボタンは**円形の進捗リング**を表示します。

### バッチ圧縮(フォルダー全体)

ZipNN の公式ツールはパス全体を圧縮でき、Neo はそれをマネージャーに組み込んでいます。
フォルダーを選択(「Select files」)して**ボトムバーの ZipNN アートワークボタン**を押すか、
フォルダーカードのコーナーボタンを使うと、フォルダーツリー内のすべての
`.safetensors` モデルが圧縮され(プレビューとノートもモデルに追従)、**バンドルフォルダー
`<name>_DeltaZNN`** へ移動されます(空になった元のフォルダーは消えます)。
`*_DeltaZNN` バンドルは封印されています:

- 中に置けるのは ZipNN コンテンツ(`*.znn.*` モデル、`*.znn` デルタファイル)のみで、
  プレーンなモデルのアップロード・ダウンロード・移動はすべて拒否されます;
- バンドルフォルダーと非バンドルフォルダーの同時選択はできず、バンドル側が警告
  トースト付きで自動的に選択解除されます;
- バンドルの ZipNN ボタンは**反転**表示で、押すとバンドルを**バッチ解凍**し、中身すべてを
  名前の由来となったフォルダーへ戻します(空になったバンドルフォルダーは削除されます);
- デルタフォルダー(`<base>_DeltaZNN`、後述)もバンドルの一種で、その反転ボタンは内部の
  すべてのファインチューンを一括で復元します;
- モデルタイプの**ルートフォルダー**(`checkpoints` など)は、バンドルを**自分自身の内側**
  (`<root>_DeltaZNN`)に作ります(タイプールの兄弟ディレクトリに置くと ComfyUI の
  フォルダーマッピングの外にはみ出し、ローダーからもマネージャーからも見えなくなる
  ためです)。方向は自動判定され、プレーンなモデルが残っていれば圧縮、バンドルのみに
  なれば解凍を行います;
- 旧バージョンが作ったバンドル(`<name>_ZNN`)も引き続き認識され、元の名前に解凍できます;
- タスクの実行中、ボタンは**円の中にパーセンテージ**を表示する円形リングになります。

複数のフォルダーはキューとして処理されます(確認は 1 回、タスクは逐次実行、進捗状態も
常に 1 つだけです)。

### デルタ圧縮(ファインチューンをベースに対して)

ファインチューン済みモデルはベースモデルと大半のバイトを共有しており、ZipNN はその
**差分のみ**を保存できます。プレーンな `.safetensors` モデルを正確に 2 つ選択し、
ボトムバーの **ZipNN delta compress** を押してください。小さなダイアログで、選択した
2 つのうちどちらが**ベース**でどちらが**ファインチューン**かを選べます(内部では
ヘッダー長アライメント付きの公式バイトレベルデルタ API を使用するため、ベースと
ファインチューンのメタデータが異なっていても問題ありません)。結果 — 通常は
ファインチューンのサイズの数%程度 — は **`<base>_DeltaZNN/<ft>_delta_<base>.znn`** に
書き出され、冗長になったファインチューンファイルは削除されます。デルタの解凍
(反転表示になったカードボタン)は、ファインチューン済みモデルを**バイト単位で正確に**
ベースの隣へ復元し、空になったデルタフォルダーを片付けます。復元にはベースモデルが
必要であり、ZipNN はデルタ作成時に両者のバイト長が一致することを検証します。

### 同梱されているため、そのまま動きます

<details>
<summary><b>ZipNN を同梱している理由</b></summary>

ZipNN の Python 側は単純ですが、そのコンプレッサーは C 拡張(`zipnn_core`、
FiniteStateEntropy ベース)です。**PyPI には Linux 向けホイールが提供されていません**
(macOS-arm64 ホイールとソース tarball のみ)。そのため素の `pip install zipnn` は
ソースからのコンパイルを試み、C コンパイラと Python ヘッダー(`Python.h`)のない
マシンでは失敗します(ComfyUI の一般的な動かし方であり、失敗メッセージも難解です:
`error: [Errno 2] No such file or directory: 'x86_64-pc-linux-gnu-gcc'`)。

そこで Neo は、ライブラリ全体を [`third_party/`](third_party/) に**ベンダリング**し、
Linux x86_64(CPython 3.10〜3.14)向けの**ビルド済み `zipnn_core` バイナリ**を同梱して
います。これらのプラットフォームでは、初回の圧縮時に同梱パッケージと対応するバイナリを
`sys.path` に載せるだけで動作します(コンパイラ不要、pip 不要、ネットワーク不要、
待ち時間なし)。ビルド済みバイナリが一致しない場合(macOS、Windows、マイナーな
アーキテクチャ、最新すぎる CPython)のみ、同梱の C ソースから**一度だけ**クリーンビルド
へフォールバックします。

ディレクトリ構成、プラットフォーム/glibc のカバー範囲、ライセンス(ZipNN は MIT、
FiniteStateEntropy は BSD-2-Clause OR GPL-2.0)、バイナリの再ビルドや追加方法については、
[`third_party/README.md`](third_party/README.md)を参照してください。

</details>

> [!NOTE]
> 圧縮にはモデルのテンソルをメモリへ展開する必要があるため、処理は CPU プール上で
> 実行され、上限となるのは VRAM ではなく RAM です。**無劣化かつ可逆**です:
> プレーンな `.safetensors` が削除されるのは、`.znn.safetensors` ファイルの書き込みと
> クローズが完了した後だけであり、失敗した実行は部分的な出力をクリーンアップします。

---

<a id="what-changed"></a>

## <img src="https://api.iconify.design/lucide/git-compare.svg?color=%23a855f7" width="28" height="28" align="middle" alt=""> オリジナルからの変更点

このセクションでは、GPL‑3.0 ライセンスの要求に従い、フォークとしての差分を明示します。
機能は維持しつつ拡張しています。*削除*したものは 2 つ — PrimeVue 依存そのものと、
バッチスキャン機能です([削除した機能: バッチスキャン](#removed-feature)を参照)。

### <img src="https://api.iconify.design/lucide/palette.svg?color=%23d946ef" width="22" height="22" align="middle" alt=""> インターフェース

| 領域                     | オリジナル                                              | **Neo**                                                                                                                                                                                                                                                                                    |
| ------------------------ | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| コンポーネントライブラリ | PrimeVue 4                                              | **reka-ui**(ヘッドレス)+ shadcn-vue スタイルのラッパー                                                                                                                                                                                                                                     |
| スタイリング             | Tailwind CSS v3 + PrimeVue テーマ                       | スコープ付き `--mm-*` デザイントークンを備えた **Tailwind CSS v4**                                                                                                                                                                                                                         |
| アイコン                 | PrimeIcons                                              | アイコンマップ経由の **Lucide**(`@lucide/vue`)                                                                                                                                                                                                                                             |
| ルック&フィール          | 標準の PrimeVue サーフェス                              | **ガラスモーフィズム**(ブラー、エレベーション、マイクロインタラクション)、自動ダークモード                                                                                                                                                                                                 |
| ダイアログ               | PrimeVue の `Dialog` / `ContextMenu`                    | reka-ui ダイアログ、ダイアログごとのサイズ/位置、ドラッグ移動、アンカー付きコンテキストメニュー                                                                                                                                                                                            |
| モデル詳細タブ           | Description + Metadata(生の safetensors `__metadata__`) | Description + **Information**: ノートの YAML フロントマターをパースする読み取り専用テーブル(作者、ベースモデル、各種ハッシュ、フォーマットとプレシジョン、モデルプラットフォーム、モデルページリンク、全プレビュー URL、未知のキーはそのまま表示)。フォールバックとして生の `__metadata__` |

### <img src="https://api.iconify.design/lucide/package.svg?color=%23f97316" width="22" height="22" align="middle" alt=""> パッケージ

- **削除:** `primevue`、`@primevue/themes`、`lodash`、`dayjs`、`js-yaml`。
- **追加 / 置換:** `reka-ui`、`@lucide/vue`、`es-toolkit`(← lodash)、
  `date-fns`(← dayjs)、`yaml`(← js-yaml)、`valibot`(ランタイムスキーマ検証)、
  `vue-sonner`(トースト)、`class-variance-authority`、`clsx`、
  `tailwind-merge`、`tw-animate-css`。
- **アップグレード:** Vite 5 → **8**(Rolldown)、TypeScript 5 → **6**、Vue i18n 9 →
  **11**、markdown-it 14 → **15**、`@vueuse/core` 11 → **14**。
- **Python:** `huggingface_hub` + `hf_xet` を追加。旧スレッドプールは asyncio の
  タスクプールへ置換しました。

### <img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%2306b6d4" width="22" height="22" align="middle" alt=""> ツールバー / ボタンの役割

マネージャーのヘッダーは、アイコン主体の明示的なアクションへ再設計しました:
**フラット ⇄ フォルダーのレイアウト切替**、**隠しファイルの表示/非表示**、**更新**、
**ダウンロードリスト**、そして **Hugging Face へのアップロード**。

### <img src="https://api.iconify.design/lucide/folder-open.svg?color=%23f59e0b" width="22" height="22" align="middle" alt=""> グラスアセットパック(フォルダーアイコン & プレビュー無しアート)

インターフェースは、`assets/` にある手作りのガラスモーフィズムアセットパックを
利用しています:

- **フォルダーカード**は静止時 `Folder-Icons/close-folder_beside-fit.svg` を表示します。
  カード上にポインターを**1 秒以上**留めると `folder-opening-animation.svg`
  (SMIL モーフ: 0.2 秒のディレイ + 1.35 秒)が再生され、1 秒間離れていると
  `folder-closing-animation.svg` が再生された後、カードは静止アイコンに戻ります。
  さっと通り過ぎただけでは、フォルダーが開閉することはありません。SVG はバンドルに
  インライン化(`?raw` + data URI)されており、各カードが独自の SVG ドキュメントを
  所有するため、追加のリクエストは発生せず、多数のカードが並んでもアートワーク内部の
  グラデーション id が衝突しません。
- **ブレッドクラム**は各セグメントの先頭に、小さな `close-folder_all-fit.svg` グリフ
  (14 px)を付けます(小さいサイズで最も判読しやすいバリアントです)。
- **プレビューのないモデル**は、ガラス調の `NOPREVIEW-Icon/NO-PREVIEW.svg` を
  **既定**のアートワークとして使用します。モデルリストは
  `GET /model-manager/no-preview.svg` を直接指し(`image/svg+xml` としてそのまま配信
  され、ベクターアートがラスタライズされることはありません)、プレビュールートは実在する
  プレビューファイルを配信するか 404 を返すだけです。
- **モデルハブのロゴ**は `AIModelHub-Logos/`(`civitai-icon.svg`、`hf-icon.svg`)に
  あります。**モデルページを開く**ボタンは、モデルのノート(`website`)に記録された
  プラットフォームのロゴを背景に、詳細のアクション行でもカードのホバーカラムでも
  同様に表示されます。

### <img src="https://api.iconify.design/lucide/hammer.svg?color=%2365a30d" width="22" height="22" align="middle" alt=""> ツールチェーン

lint / フォーマットは、オーソドックスかつフル構成の **ESLint 10 フラットコンフィグ** +
**Prettier** パイプラインで行い、デッドコードと重複の解析には
[Fallow](https://fallow.tools) を併用しています([開発](#development)を参照)。

---

<a id="removed-feature"></a>

## <img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="28" height="28" align="middle" alt=""> 削除した機能: バッチスキャン

**「モデル情報のバッチスキャン」機能は完全に削除しました**。冗長だったためです:
モデル詳細ウィンドウは、開いたモデルの `__metadata__`(safetensors ヘッダーから直接
読み取り)と、ファイルの隣に保存された Markdown ノートをオンデマンドで要求し、
プレビュールートは実在するプレビューファイルを解決します(プレビューのないモデルは、
モデルリストの時点で同梱のガラス調 `NO-PREVIEW.svg` の URL を保持しています)。

ライブラリ全体を走査してすべてのモデルをハッシュ化し、Civitai にハッシュで問い合わせる
処理は、同じ情報へ至る 2 つ目の、そしてはるかに遅い経路にすぎませんでした。おまけに
モーダルダイアログ、グローバルストア、websocket イベント、ディスク上のタスクファイル、
専用設定が付随し、そのすべてを保守する必要がありました。これらはフロントエンド・
バックエンドともどもすべて削除しています(スキャンダイアログとスキャンフック、スキャン
ルートとタスク管理、ハッシュ検索、スキャン専用だった再帰走査 / sha256 ヘルパー)。

スキャン時代に由来する 2 つの設定 ID — `ModelManager.Scan.excludeScanTypes` と
`ModelManager.Scan.IncludeHiddenFiles` — は、**ID 文字列を意図的にそのまま**にしています:
これらは現在**モデルリスト**(どのタイプをグリッドへ読み込むか、`.` 始まりのファイルを
表示するか)を駆動しており、ID は ComfyUI がユーザーの値を永続化するキーであるため、
リネームすると既存インストールの保存済み設定が黙って孤立してしまうからです。ID の周囲は
新しい役割に合わせて改名しました(設定カテゴリーは **Model List**、ラベルは
**「Exclude model types (separate with commas)」**)。ほかに「scan」を名前に含む識別子
(フォルダーを列挙する `scan_models()`、ダウンロードタスクを一覧する
`scan_model_download_task_list()`)は、無関係な動作に対する上流の命名であるため
そのまま残しています。

> [!NOTE]
> **失われるもの:** ファイルハッシュを介して Civitai からプレビューと説明を
> *一括バックフィル*する唯一の手段です。情報を一度も取得していないモデルは、
> プレビュー/ノートを手動で設定する(モデルエディター → **Preview** →
> _Network_ / _Local_)か、プレビュー付きで再ダウンロードする(_Create Download Task_
> 経由)まで、プレースホルダーのプレビューのままになります。モデル情報の*読み取り*には
> 影響ありません(それは常にディスクから、オンデマンドで取得されていたためです)。

<a id="documentation"></a>

## <img src="https://api.iconify.design/lucide/book-open.svg?color=%237c3aed" width="28" height="28" align="middle" alt=""> ドキュメント

ステップバイステップの使い方ガイドです。それぞれ完結しており、単体で読めます:

- [`docs/USAGE-EN.md`](docs/USAGE-EN.md) — English
- [`docs/USAGE-JA.md`](docs/USAGE-JA.md) — 日本語
- [`docs/USAGE-ZN.md`](docs/USAGE-ZN.md) — 中文

インストール、2 つのレイアウト、カード操作とグラフへのドラッグ、モデルエディター
(フォルダーピッカー、フォルダープレフィックス付きのファイル名、プレビュー、説明)、
ダウンロードとタスクリスト、Hugging Face アップロードの各フェーズと完了メッセージ、
ZipNN 圧縮、設定とロケール、さらにトラブルシューティング表までを網羅しています。

<a id="development"></a>

## <img src="https://api.iconify.design/lucide/terminal.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> 開発

Web バンドルの**ビルド**にだけ Node.js が必要です。ComfyUI 内で拡張を実行するには、
Python 以外何も要りません。

```bash
corepack enable          # ピン留めされた pnpm バージョンを使用
pnpm install
```

| スクリプト                              | 用途                                                                                |
| --------------------------------------- | ----------------------------------------------------------------------------------- |
| `pnpm dev`                              | Vite 開発サーバー(ComfyUI 内でのホットリロード用に `web/manager-dev.js` を書き出す) |
| `pnpm build`                            | `web/` への本番ビルド                                                               |
| `pnpm build:clean`                      | `web/` を削除してから再ビルド                                                       |
| `pnpm rebuild`                          | `node_modules/` **と** `web/` を削除し、再インストールしてから再ビルド              |
| `pnpm typecheck`                        | `vue-tsc --noEmit` による型チェック                                                 |
| `pnpm lint` / `pnpm lint:fix`           | ESLint(フラットコンフィグ)                                                          |
| `pnpm format` / `pnpm format:check`     | Prettier(Tailwind プラグイン付き)                                                   |
| `python -m mypy --config-file mypy.ini` | バックエンドの静的型チェック                                                        |
| `pnpm fallow`                           | Fallow フルパイプライン: デッドコード + 重複 + ヘルス                               |
| `pnpm fallow:dead`(`:type-aware`)       | 未使用のファイル/エクスポート/型/依存、循環(任意で TS セマンティックパス)           |
| `pnpm fallow:dupes`                     | AST クローン検出(`mild` モード、`.fallowrc.json` を参照)                            |
| `pnpm fallow:health`                    | 複雑度のホットスポット、リファクタリング対象、0〜100 のヘルススコア                 |
| `pnpm fallow:fix:dry` / `fallow:fix`    | 自動クリーンアップのプレビュー / 適用(常にまずドライラン)                           |
| `pnpm fallow:audit`                     | PR スタイルのゲート: 今回の変更で新たに生じた検出のみを報告                         |

> [!WARNING]
> `pnpm dev` は `manager-dev.js` を書き出す前に **`web/` ディレクトリを丸ごと削除**します
> (`vite.config.ts` の `dev()` プラグインを参照)。これにより、コミット済みの本番バンドル
> (`web/manager.js` と `web/style-*.css`)がワーキングツリーから消え、`git status` では
> 削除扱いで表示されます。その状態でコミットすると、UI が読み込まれない拡張を配布する
> ことになります。コミット前に必ず `pnpm build` を実行し、`web/manager.js` が欠けたツリーは
> コミットしないでください。

**husky** の `pre-commit` フックが、ステージされたファイルに対して **lint-staged**
(ESLint `--fix` + Prettier)を実行します。

### Fallow(コードベース解析)

[Fallow](https://fallow.tools)(Rust 製)はリンターを補完します: リポジトリを単一の依存
グラフとして読み取り、未使用のファイル/エクスポート/型/依存、循環 import、クローン
グループ、複雑度のホットスポットを報告します。`.fallowrc.json` はエントリポイント
(`src/main.ts`)を固定し、コミット済みの `web/` バンドル、ベンダリングされた
`third_party/`、docs、assets をグラフから除外したうえで、private 型のリーク検査と
未解決 import 検査を有効化しています。

### Lint & フォーマット構成

ESLint 10 フラットコンフィグが、`typescript-eslint`、`eslint-plugin-vue`
(`vue-eslint-parser` 経由)、`eslint-plugin-import-x`(エイリアス認識の import 順序付け)、
`eslint-plugin-tailwindcss`(クラスの衛生管理)、`eslint-config-prettier`(必ず最後に置く)
を統合します。フォーマットと Tailwind クラスのソートは Prettier が担当し、
`prettier-plugin-tailwindcss` を使用します。

### プロジェクト構成

```
├─ __init__.py            # ComfyUI エントリーポイント: 依存のインストール、ルートの登録
├─ py/                    # Python バックエンド(aiohttp ルート、HF/Civitai、タスク)
│  ├─ manager.py          #   モデルの CRUD + フォルダー一覧
│  ├─ download.py         #   ダウンロードタスク(http + huggingface_hub)
│  ├─ upload.py           #   ローカルファイルのアップロード(パス検証付き)
│  ├─ upload_hf.py        #   Hugging Face へのアップロード
│  ├─ compress.py         #   ZipNN 圧縮 / 解凍(ベンダリング済みコア)
│  ├─ information.py      #   URL による Civitai/HF 検索、プレビューの配信
│  ├─ auth.py · config.py · thread.py · utils.py
├─ third_party/           # ベンダリング済み ZipNN(Python パッケージ + ビルド済み zipnn_core + C ソース)
├─ src/                   # Vue 3 フロントエンド
│  ├─ components/         #   アプリコンポーネント + ui/(reka-ui ラッパー)
│  ├─ hooks/              #   store、models、download、config、dialog、…
│  ├─ utils/ · types/ · locales/
│  ├─ style.css           #   Tailwind v4 エントリー + デザイントークン
│  └─ main.ts             #   ComfyUI 拡張の登録
└─ web/                   # ComfyUI へ配信されるビルド済みバンドル(コミット対象)
```

---

<a id="credits"></a>

## <img src="https://api.iconify.design/lucide/heart-handshake.svg?color=%23ec4899" width="28" height="28" align="middle" alt=""> クレジットと帰属

ComfyUI‑Model‑Manager‑Neo が存在できるのは、
**[hayden-cn](https://github.com/hayden-cn)** 氏による
**[`ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)** が
先に存在したからです。このフォークの構造上のアイデアはすべて — モデルフォルダーの
抽象化、websocket 進捗プロトコルを備えた再開可能なダウンロードタスクシステム、
Civitai / Hugging Face のページパーサー、カードをグラフへドラッグする統合、モデル
エディターのフォーム基盤、カードサイズプリセットのような細かなアフォーダンスに
至るまで — hayden-cn 氏の設計です。Neo が変えたのは外装と依存関係、そして数多くの
バグです。このコードベースが*なぜ*このような形をしているのかを理解する最速の方法は、
今もオリジナルを読むことであり、アーキテクチャに対する帰属はただ一つ、**原著者の
もの**です。

本フォークは、**GNU General Public License v3.0** に従って使用・改変された派生物です。
Neo での変更(UI の再構築、PrimeVue の除去、Hugging Face / ModelScope アップロード、
ZipNN 圧縮、パッケージの近代化、ツールチェーン、信頼性とセキュリティの強化、
バッチスキャンの削除、日本語ローカライズ)は、同じ GPL‑3.0 ライセンスのもとで提供
されます。ライセンスに従い、オリジナルの著作権表示とライセンス全文は
[`LICENSE`](LICENSE) に保持されています。

### <img src="https://api.iconify.design/lucide/bot.svg?color=%236366f1" width="22" height="22" align="middle" alt=""> Qwen Studio とともに構築

このフォークの大部分は、**[Qwen Studio]** を使って構築されました。ZipNN 統合
(ライブラリのベンダリング、ビルド済み `zipnn_core` バイナリの生成、テンソル単位の
圧縮/解凍の移植)から、ガラスモーフィズム UI の再構築、Hugging Face アップロード
フロー、信頼性とセキュリティの強化、デバッグの多くに至るまで、すべて Qwen Studio との
密接な協力のもとで開発されました。

このフォークがあなたの役に立ったなら、スターに値するのは上流のリポジトリです。
その肩の上に立つ仕事がなければ、上記の何ひとつ実現しなかったのですから。

以下の優れたプロジェクトのお世話になっています: [reka-ui]、[Tailwind CSS]、[Lucide]、
[VueUse]、[es-toolkit]、[valibot]、[vue-sonner]、[huggingface_hub]、[hf_xet]、
そして [ZipNN]。

---

<a id="license"></a>

## <img src="https://api.iconify.design/lucide/scale.svg?color=%2394a3b8" width="28" height="28" align="middle" alt=""> ライセンス

**GPL‑3.0‑only** — 全文は [`LICENSE`](LICENSE) を参照してください。

<div align="center">

**Neo があなたの時間を節約できたなら、リポジトリへのスター <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="16" height="16" align="middle" alt=""> と、[オリジナルの作者](https://github.com/hayden-cn/ComfyUI-Model-Manager)への感謝をご検討ください。**

</div>

<!-- リンク参照 -->

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
