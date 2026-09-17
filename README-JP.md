<div align="center">

# <img src="https://api.iconify.design/lucide/boxes.svg?color=%236366f1" width="34" height="34" align="middle" alt=""> ComfyUI‑Model‑Manager‑Neo

### 閲覧 · ダウンロード · アップロード · ドラッグ&ドロップ — あなたのモデルを、美しく管理。

ComfyUI モデルマネージャーを、モダンなガラスモーフィズムで再構築。
**Vue 3 + Tailwind CSS v4 + reka-ui** を基盤に、ツールチェーンも全面的に刷新しました。

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
リポジトリのQRコードです。ご自身のデバイスにこのリポジトリを瞬時に読み込むことができます。

</div>

---

**目次**

- [なぜ Neo なのか?](#why-neo) · [UI ツアー](#screenshots) · [インストール](#installation) ·
  [機能](#features)
- [ZipNN 無劣化圧縮](#zipnn) · [オリジナルからの変更点](#what-changed) ·
  [削除した機能: バッチスキャン](#removed-feature)
- [ドキュメント](#documentation) · [開発](#development) ·
  [クレジットと帰属表示](#credits) · [ライセンス](#license)

---

<a id="why-neo"></a>

## <img src="https://api.iconify.design/lucide/sparkles.svg?color=%23f59e0b" width="28" height="28" align="middle" alt=""> なぜ Neo なのか?

**ComfyUI‑Model‑Manager‑Neo** は、優れたオリジナルのマネージャーを土台に、
エクスペリエンスを根本から作り直したプロジェクトです:

- <img src="https://api.iconify.design/lucide/layers.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ガラスモーフィズム UI** — 半透明・ブラー・エレベーション(奥行き表現)を備え、ComfyUI 本体のライト/ダークパレットへ自動で追従するインターフェース。
- <img src="https://api.iconify.design/lucide/puzzle.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **PrimeVue 決別** — PrimeVue 依存を丸ごと撤去し、軽量なヘッドレスプリミティブ **[reka-ui]** + **Tailwind CSS v4** + **[Lucide]** アイコンへ置き換え(コンポーネントは shadcn-vue スタイル。中身を読んで自在に調整できます)。
- <img src="https://api.iconify.design/lucide/upload-cloud.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Hugging Face へのアップロード** — ローカルの任意のモデルを HF リポジトリへ直接公開(リポジトリがなければ作成、プライベート指定可、進捗はリアルタイム表示)。*Neo の新機能*。
- <img src="https://api.iconify.design/lucide/package-plus.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ZipNN 無劣化圧縮** — safetensors モデルをインプレースで圧縮/解凍(`.znn.safetensors`)。確認ダイアログと進捗表示を備え、圧縮済みモデルではアイコンが反転します。フォルダー全体を封印済み `<name>_DeltaZNN` バンドルへバッチ圧縮でき、ファインチューンはベースに対する小さな**デルタファイル**まで縮小できます。*Neo の新機能*。
- <img src="https://api.iconify.design/lucide/list-checks.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **マルチセレクト** — カードにチェックを入れ、複数のモデルをワークフローへ一度に追加したり、まとめて削除したりできます。*Neo の新機能*。フォルダーにもチェック可能で、「Add to workflow」は中身を再帰的に展開して追加、「Delete」はフォルダーごと丸ごと削除します。
- <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="16" height="16" align="middle" alt=""> **スター** — すべてのモデルカードとフォルダーカードの右上にスタートグルを搭載(モデル詳細のアクション行とセレクションバーにも配置)。スター付きのアイテムは黄色く塗りつぶされた星で表示され、常に最上位へソートされます。*Neo の新機能*。
- <img src="https://api.iconify.design/lucide/folder-plus.svg?color=%2322c55e" width="16" height="16" align="middle" alt=""> **フォルダー作成** — フォルダービューの「Add Folder」ボタンから、開いているディレクトリ内に任意の名前の(サブ)フォルダーを作成できます。*Neo の新機能*。
- <img src="https://api.iconify.design/lucide/link.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ダイレクトリンクダウンロード** — 生の `.safetensors` / `.ckpt` / `.gguf` URL を貼り付け、対象フォルダーを選択。任意でカスタムサブフォルダーも指定できます。
- <img src="https://api.iconify.design/lucide/zap.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **`hf_xet` アクセラレーション** — Hugging Face の転送には、利用可能な環境でチャンクベース・重複排除の Xet プロトコルを使用します。
- <img src="https://api.iconify.design/lucide/workflow.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ファーストクラスのノードグラフ統合** — モデルをキャンバスへドラッグしてノードを生成・充填し、embedding をテキストエリアへドラッグし、プレビュー画像に埋め込まれたワークフローを読み込めます。
- <img src="https://api.iconify.design/lucide/monitor-smartphone.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **レスポンシブ** — デスクトップ、モバイル、マルチスクリーン構成を想定した設計です。
- <img src="https://api.iconify.design/lucide/wrench.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **モダンなツールチェーン** — Vite 8(Rolldown)、TypeScript 6、ESLint 10 フラットコンフィグ、Prettier、husky + lint-staged。ビルドは決定論的で、lint もクリーンに通ります。

> [!NOTE]
> Neo は [`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
> の**フォーク**であり、同じ **GPL-3.0** ライセンスのもとで配布されます。
> オリジナルのアーキテクチャに対するクレジットは、すべてその作者に帰属します —
> [クレジットと帰属表示](#credits)を参照してください。

---

<a id="screenshots"></a>

## <img src="https://api.iconify.design/lucide/camera.svg?color=%238b5cf6" width="28" height="28" align="middle" alt=""> UI ツアー

> [!NOTE]
> デモ GIF とスクリーンショットは現在準備中です。整い次第、本セクションに掲載します。
> それまでは、各画面の見どころをテキストでお伝えします。

### フラット「Models」ビュー — 検索・ソート・グリッドのリサイズ

**Flat** レイアウトのマネージャーウィンドウです。プレビューとタイプ・サイズのチップを
備えたグラス調のモデルカードがグリッド状に並び、検索バーと
タイプ / ソート / カードサイズの各セレクターが揃っています。

### フォルダー(エクスプローラー)ビュー — ディレクトリツリーをナビゲート

**Folder** レイアウトで1階層潜ったところです。ブレッドクラム(各セグメントに
小さなフォルダーグリフ付き)と、アニメーションするグラス調のフォルダーカードが
表示されます。

### モデル詳細・編集・HuggingFace アップロード

- **モデル情報**: プレビューと基本情報テーブル(**Directory** の末尾に `/` が付く点に注目)、
  そして Description / Information タブ。
- **編集モード**: タイプのドロップダウン、フォルダーピッカーボタン、
  `folder/name` プレフィックスを受け付けるファイル名欄。
- **HuggingFace へのアップロード**(ステップ3): リポジトリ ID、作成時のプライベート指定、
  アップロード先パス。
- **日本語 UI**: 同じウィンドウを**日本語**で表示したところ。
  UI は English / 中文 / 日本語 の完全な言語バンドルを同梱しています。

ウィンドウを開き、フォルダービューへ潜り、フォルダーにホバーして戻り、モデルを開き、
カードをライブのキャンバスへドラッグする — そんな一連の操作感は、
ぜひ実際の ComfyUI 上で確かめてみてください。

---

<a id="installation"></a>

## <img src="https://api.iconify.design/lucide/rocket.svg?color=%2322c55e" width="28" height="28" align="middle" alt=""> インストール

Neo は ComfyUI のカスタムノードとして動作します。以下のいずれかの方法を選んでください:

**1 · Git clone(アップデートしやすく、推奨)**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/rikunarita/ComfyUI-Model-Manager-Neo.git
```

**2 · 手動ダウンロード**

[リポジトリのアーカイブ](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/archive/refs/heads/main.zip)
をダウンロードして `ComfyUI/custom_nodes/` に展開し、
フォルダー名が `ComfyUI-Model-Manager-Neo` になっていることを確認してください。

**3 · ComfyUI Manager**

このフォークがレジストリに登録されていれば、[ComfyUI-Manager] で
**「ComfyUI-Model-Manager-Neo」** を検索してインストールできます。

その後、**ComfyUI を再起動**してください。Python 依存(`huggingface_hub`、`hf_xet`、
`markdownify`)は初回起動時に自動でインストールされます。ビルド済みの Web バンドルは
[`web/`](web) に同梱されているため、拡張を*実行するだけ*なら Node.js は不要です。

起動は、トップバーの **「Model Manager Neo」** ボタン、サイドバー、
または `Extensions → Model Manager Neo` メニューコマンドから行えます。

> [!TIP]
> Neo は活発に開発が進んでいます — 日常利用に耐える品質には達していますが、
> インターフェースは今後も変わり得ます。フィードバックや Issue は大歓迎です。

---

<a id="features"></a>

## <img src="https://api.iconify.design/lucide/list-checks.svg?color=%233b82f6" width="28" height="28" align="middle" alt=""> 機能

<details open>
<summary><b>閲覧と整理</b></summary>

- 2つのレイアウト: **Flat** グリッド(デフォルト表示)と **Folder** エクスプローラー。いつでも切り替え可能です。
- リアルタイム検索(`*` ワイルドカードと、複数トークンの「AND」マッチに対応)。
- 名前・サイズ・作成日・更新日でのソート。
- カードサイズの調整(プリセット + 完全カスタムの寸法指定)。
- 隠しファイル(`.` 始まり)の表示/非表示を、再起動なしでトグル。
- 画像**と動画**のプレビュー。ホバーで開閉アニメーションするグラス調のフォルダーアートワークと、グラス調のプレビュー無しフォールバックも搭載。

</details>

<details>
<summary><b>ノードグラフ統合</b></summary>

- モデルのサムネイルをキャンバスへドラッグすると、**ローダーノードが追加**されます。
- 既存ノードへドラッグすると、**一致する入力を充填**します(候補が曖昧な場合は完全一致が必要)。
- **embedding** をテキストエリアへドラッグすると、`(embedding:name:1.0)` が追記されます。
- プレビュー画像をグラフへドラッグすると、**埋め込みワークフローを読み込み**ます。
- **Add** / **Copy** ボタンで、ノードを配置したり ComfyUI のクリップボードへコピーしたりできます。

</details>

<details>
<summary><b>ダウンロード</b></summary>

- **Civitai**、**Hugging Face**、**ファイル直リンク**の URL を貼り付けて利用します。
- 1つのページから複数のファイル/バージョンを解決し、欲しいものを選択できます。
- ダイレクトリンクは対象タイプの明示的な指定が必須で、任意でカスタムサブフォルダーも指定できます。
- プレビュー画像は任意で取得可能 — モデルページが提供する**ギャラリー全体**を保持し、ダウンロード時に選んだ画像がカードのプライマリプレビューになります — さらに、ダウンロードごとに編集可能な Markdown 説明も保存されます。
- タスクの一時停止 / 再開 / 削除に対応。進捗・速度・サイズはリアルタイムで更新されます。
- Hugging Face からのダウンロードは `huggingface_hub` を使用(利用可能なら `hf_xet` も併用)。

</details>

<details>
<summary><b>アップロード</b></summary>

- **ローカルファイルから**任意のモデルフォルダーへアップロード(Download List に進捗付きのライブタスクとして登録されます)。
- **Hugging Face へ** *(Neo の新機能)*: HF トークンで認証し、リポジトリが存在しなければ作成(公開/非公開を選択)、アップロード先パスを指定して、進捗を見守れます。

</details>

<details>
<summary><b>モデル情報とメンテナンス</b></summary>

- ファイル情報を確認し、読み取り専用の **Information** テーブルでモデルに関する記録のすべてを読めます。ノートの YAML フロントマターをパースした作者、ベースモデル、各種ハッシュ(`AutoV1` … `SHA256_12`)、フォーマットとプレシジョン、モデルプラットフォーム、モデルページへのリンク、全プレビュー URL(未知のキーは末尾にそのまま表示)、あるいはノートのないモデルでは safetensors の `__metadata__` ブロックをそのまま表示します。
- モデルのリネーム、フォルダー/タイプ間の移動、プレビューやノートもろとも**完全削除**。
- モデルの隣に保存された Markdown ノートの閲覧・編集・保存。
- モデルのプレビュー画像の変更や削除 — 保存時に開いていたギャラリーページが、カードのプライマリプレビューになります。
- **モデルページを開く**アクションのボタン背景には、モデルのソースハブ(Civitai または Hugging Face)のロゴが掲げられるため、モデルの出所が一目で分かります。
- モデル情報(safetensors メタデータ、Markdown ノート、プレビュー)は、モデルを開いたときにオンデマンドで読み込まれます — ライブラリ全体をスキャンする別工程は存在しません。

</details>

<details>
<summary><b>設定と i18n</b></summary>

- **Civitai** と **Hugging Face** の API キーは `private.key` にローカル保存されます(`CIVITAI_API_KEY` / `HF_TOKEN` 環境変数へのフォールバック付き)。キーは初回起動時に ComfyUI のユーザー設定から移行されます。
- モデルリストから特定のモデルタイプを除外したり、隠しファイルを含める/除外したりできます。
- UI 言語は ComfyUI のロケールに追従します — **English**、**中文**、**日本語**をフルバンドル。リージョン/文字体系のサブタグ(`ja-JP`、`zh-Hant-TW` など)は基本言語にフォールドされます。

</details>

---

<a id="zipnn"></a>

## <img src="https://api.iconify.design/lucide/package-plus.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> ZipNN 無劣化圧縮

**Neo の目玉機能です。** 大容量の `.safetensors` チェックポイントは、ディスク容量を
あっという間に食い潰します。Neo はそれらを
[ZipNN](https://github.com/zipnn/zipnn) フォーマットにより**インプレースかつ無劣化**で
圧縮・解凍できます。テンソルを認識する方式は公式 ZipNN プロジェクトと同じなので、
生成物はより広い ZipNN エコシステムと互換性を保ちます。

### 仕組み

モデルの重みの大半は浮動小数点数であり、浮動小数点数の大半は*冗長*です。
素性の良い重みテンソルの指数部バイトには、同じ値が何度も繰り返し現れます。
ZipNN が狙うのはまさにこの性質です。各テンソルに対して:

- 値をバイトプレーン単位に**分割**し、符号 / 指数 / 仮数のビットを並べ替えて同種のバイト同士を集約し、
- 各プレーンを FiniteStateEntropy(FSE)コーデックで**ハフマン符号化**します。

浮動小数点数*でない*テンソル(整数インデックス、マスクなど)は無加工のままコピーされ、
圧縮しても実際には小さくならない浮動小数点テンソルは、水増しせずに**そのまま**
残されます。圧縮された各テンソルは `uint8` ベクトルとして格納され、すべてのテンソルの
元の `dtype` と `shape` は、単一の `znn_compressed_vectors` メタデータエントリに
記録されます。近似も間引きも行われません — 解凍すれば元のファイルが
**ビット単位で完全**に再現されます。

圧縮済みモデルは `<name>.znn.safetensors` として元のファイルの隣に書き出されます。
これは公式 ZipNN ツール(`zipnn_safetensors()` でパッチを当てたローダーを含む)が
期待する正確なサフィックスなので、パッチ済みの ComfyUI ローダーは Neo が圧縮した
モデルを透過的に読み込めます。実用的なチェックポイントなら、おおむね元サイズの
**60〜80%** に収まります(ランダム性の高いデータはほとんど圧縮できず、
低エントロピーの重みはそれ以上に小さくなります)。

### 使い方

任意の `.safetensors` モデルを開いてください。プレビューと情報テーブルの間には、
**ZipNN のアートワークそのものがボタン**として鎮座しています。同梱の SVG は
自前のグラスプレート(ダークモード版を含む)を描画し、ホバーで浮き上がって明るくなり、
ツールチップとスクリーンリーダーの両方で役割を説明します。押すと:

1. 確認を求めますが、あえて「Danger」風のスタイルにはしていません(圧縮は可逆であり、圧縮ファイルの書き込みと検証が完全に終わるまで、元ファイルが削除されることは決してないためです);
2. 処理中(CPU プール上でテンソルごとに実行)、ボタンは**ライブ進捗バー**に置き換わり、ComfyUI の他の部分は応答性を保ちます;
3. 成功すると、元ファイルが `<name>.znn.safetensors` に置き換わります — プレビューと Markdown ノートもリネームに追従し、グリッドは自動で再描画されます。

**圧縮済み**のモデルを開くと、同じアートワークの色が**反転**して表示され、
アクションは同じ確認ダイアログを挟んで*解凍*に切り替わり、プレーンな
`.safetensors` を復元します。情報テーブルも変わり、単一の *File Size* 行が
**Original File Size**、**Compressed File Size**、**% of Original Size** の
3行に置き換わります — 圧縮前のサイズは圧縮時にファイルのメタデータへ記録されるため、
リネーム後も内訳は生き残ります(このキーを書き込まない公式 ZipNN CLI で圧縮された
ファイルは、プレーンな *File Size* 行のままです)。

同じアートワークは、**すべてのモデルカードとフォルダーカードの右上**
(スタートグルの隣)にも配置されています。ワンクリックで、モデルを一切開かずに、
同一の確認・進捗動作で圧縮(反転表示の場合は解凍)を実行できます。
シングル・バッチ・デルタのいずれのタスクが実行中であっても、ボタンは
**円形の進捗リング**を表示します。

### バッチ圧縮(フォルダー全体)

ZipNN の公式ツールはパス全体を圧縮できます。Neo はそれをマネージャーに組み込みました。
フォルダーを選択(「Select files」)して**ボトムバーの ZipNN アートワークボタン**を押すか、
フォルダーカードのコーナーボタンを使うと、フォルダーツリー内のすべての
`.safetensors` モデルが圧縮され(プレビューとノートもモデルに追従)、
**バンドルフォルダー `<name>_DeltaZNN`** へ移動されます — 空になった元のフォルダーは
消えます。`*_DeltaZNN` バンドルは封印されています:

- 中に置けるのは ZipNN コンテンツ(`*.znn.*` モデル、`*.znn` デルタファイル)のみ(プレーンなモデルのアップロード・ダウンロード・移動はすべて拒否されます);
- バンドルフォルダーと非バンドルフォルダーの同時選択は不可能 — バンドル側が警告トースト付きで自動的に選択解除されます;
- バンドルの ZipNN ボタンは**反転**表示で、押すとバンドルを**バッチ解凍**し、中身すべてを名前の由来となったフォルダーへ戻します(空になったバンドルフォルダーは削除されます);
- デルタフォルダー(`<base>_DeltaZNN`、後述)もバンドルの一種です。その反転ボタンは、内部のすべてのファインチューンを一括で復元します;
- モデルタイプの**ルートフォルダー**(`checkpoints` など)は、バンドルを**自分自身の内側**(`<root>_DeltaZNN`)に作ります — タイプルートの兄弟ディレクトリに置くと ComfyUI のフォルダーマッピングの外にはみ出し、ローダーからもマネージャーからも姿を消してしまうためです。方向は自動判定され、プレーンなモデルが残っていれば圧縮、バンドルのみになれば解凍を行います;
- 旧バージョンが作ったバンドル(`<name>_ZNN`)も引き続き認識され、元の名前に解凍できます;
- タスクの実行中、ボタンは**円の中にパーセンテージ**を表示する円形リングになります。

複数のフォルダーはキューとして処理されます: 確認は1回、タスクは逐次実行、
進捗状態も常に1つだけです。

### デルタ圧縮(ファインチューンをベースに対して)

ファインチューン済みモデルはベースモデルと大半のバイトを共有しており、ZipNN は
その**差分のみ**を保存できます。プレーンな `.safetensors` モデルを正確に2つ選択し、
ボトムバーの **ZipNN delta compress** を押してください。小さなダイアログで、
選択した2つのうちどちらが**ベース**でどちらが**ファインチューン**かを選べます
(内部ではヘッダー長アライメント付きの公式バイトレベルデルタ API を使用するため、
ベースとファインチューンのメタデータが異なっていても問題ありません)。
結果 — 通常はファインチューンのサイズの数%程度 — は
**`<base>_DeltaZNN/<ft>_delta_<base>.znn`** に書き出され、冗長になった
ファインチューンファイルは削除されます。デルタの解凍(反転表示になったカードボタン)は、
ファインチューン済みモデルを**バイト単位で正確に**ベースの隣へ復元し、
空になったデルタフォルダーを片付けます。復元にはベースモデルが必要であり、
ZipNN はデルタ作成時に両者のバイト長が一致することを検証します。

### 同梱済み。だからそのまま動く

<details>
<summary><b>なぜ以前は苦痛だったのか — そして Neo の解決策</b></summary>

ZipNN の Python 側は些細なものですが、そのコンプレッサーは C 拡張
(`zipnn_core`、FiniteStateEntropy ベース)です。**PyPI には Linux 向けホイールが
一切提供されていません** — macOS-arm64 ホイールとソース tarball のみ — そのため、
素の `pip install zipnn` はソースからのコンパイルを試み、C コンパイラと Python ヘッダー
(`Python.h`)のないマシンでは確実に落ちます。ComfyUI のごく一般的な動かし方ですし、
失敗メッセージは難解です(`error: [Errno 2] No such file or directory:
'x86_64-pc-linux-gnu-gcc'`)。

そこで Neo は、ライブラリ全体を [`third_party/`](third_party/) に**ベンダリング**し、
Linux x86_64(CPython 3.10〜3.13)向けの**ビルド済み `zipnn_core` バイナリ**を
同梱しています。これらのプラットフォームでは、初回の圧縮時に同梱パッケージと
対応するバイナリを `sys.path` に載せるだけ — **コンパイラ不要、pip 不要、
ネットワーク不要、待たされません**。ビルド済みバイナリが一致しない場合
(macOS、Windows、マイナーなアーキテクチャ、最新すぎる CPython)のみ、
同梱の C ソースから**単一の**クリーンビルドへフォールバックします — pip の
インストール戦略を数珠つなぎで試すような真似は決してしません。

ディレクトリ構成、プラットフォーム/glibc のカバー範囲、ライセンス
(ZipNN は MIT、FiniteStateEntropy は BSD-2-Clause OR GPL-2.0)、
バイナリの再ビルドや追加方法については、[`third_party/README.md`](third_party/README.md)
を参照してください。

</details>

> [!NOTE]
> 圧縮にはモデルのテンソルをメモリへ展開する必要があるため、処理は CPU プール上で
> 実行され、上限となるのは VRAM ではなく RAM です。**無劣化かつ可逆**です:
> プレーンな `.safetensors` が削除されるのは、`.znn.safetensors` ファイルの書き込みと
> クローズが完了した後だけであり、失敗した実行は部分的な出力をクリーンアップします。

---

<a id="what-changed"></a>

## <img src="https://api.iconify.design/lucide/git-compare.svg?color=%23a855f7" width="28" height="28" align="middle" alt=""> オリジナルからの変更点

このセクションでは、GPL-3.0 ライセンスの要求に従い、フォークとしての差分を明示します。
機能は維持しつつ拡張されています。*削除*されたのは2つ、PrimeVue 依存そのものと
バッチスキャン機能です — [削除した機能: バッチスキャン](#removed-feature)を参照してください。

### <img src="https://api.iconify.design/lucide/palette.svg?color=%23d946ef" width="22" height="22" align="middle" alt=""> インターフェース

| 領域 | オリジナル | **Neo** |
| --- | --- | --- |
| コンポーネントライブラリ | PrimeVue 4 | **reka-ui**(ヘッドレス)+ shadcn-vue スタイルのラッパー |
| スタイリング | Tailwind CSS v3 + PrimeVue テーマ | スコープ付き `--mm-*` デザイントークンを備えた **Tailwind CSS v4** |
| アイコン | PrimeIcons | アイコンマップ経由の **Lucide**(`@lucide/vue`) |
| ルック&フィール | 標準の PrimeVue サーフェス | **ガラスモーフィズム**(ブラー、エレベーション、マイクロインタラクション)、自動ダークモード |
| ダイアログ | PrimeVue の `Dialog` / `ContextMenu` | reka-ui ダイアログ、ダイアログごとのサイズ/位置、ドラッグ移動、アンカー付きコンテキストメニュー |
| モデル詳細タブ | Description + Metadata(生の safetensors `__metadata__`) | Description + **Information**: ノートの YAML フロントマターをパースする読み取り専用テーブル(作者、ベースモデル、各種ハッシュ、フォーマットとプレシジョン、モデルプラットフォーム、モデルページリンク、全プレビュー URL、未知のキーはそのまま表示)。フォールバックとして生の `__metadata__` |

### <img src="https://api.iconify.design/lucide/package.svg?color=%23f97316" width="22" height="22" align="middle" alt=""> パッケージ

- **削除:** `primevue`、`@primevue/themes`、`lodash`、`dayjs`、`js-yaml`。
- **追加 / 置換:** `reka-ui`、`@lucide/vue`、`es-toolkit`(← lodash)、
  `date-fns`(← dayjs)、`yaml`(← js-yaml)、`valibot`(ランタイムスキーマ検証)、
  `vue-sonner`(トースト)、`class-variance-authority`、`clsx`、
  `tailwind-merge`、`tw-animate-css`。
- **アップグレード:** Vite 5 → **8**(Rolldown)、TypeScript 5 → **6**、Vue i18n 9 →
  **11**、markdown-it 14 → **15**、`@vueuse/core` 11 → **14**。
- **Python:** `huggingface_hub` + `hf_xet` を追加。旧スレッドプールは asyncio タスクプールへ置換。

### <img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%2306b6d4" width="22" height="22" align="middle" alt=""> ツールバー / ボタンの役割

マネージャーのヘッダーは、アイコン主体の明示的なアクションへと再設計されました:
**フラット ⇄ フォルダーのレイアウト切替**、**隠しファイルの表示/非表示**、**更新**、
**ダウンロードリスト**、そして **Hugging Face へのアップロード**。

### <img src="https://api.iconify.design/lucide/folder-open.svg?color=%23f59e0b" width="22" height="22" align="middle" alt=""> グラスアセットパック(フォルダーアイコン & プレビュー無しアート)

インターフェースは、`assets/` にある手作りのガラスモーフィズムアセットパックを利用しています:

- **フォルダーカード**は静止時、`Folder-Icons/close-folder_beside-fit.svg` を表示します。
  カード上にポインターを**1秒以上**留めると `folder-opening-animation.svg`
  (SMIL モーフ: 0.2秒のディレイ + 1.35秒)が再生され、1秒間離れていると
  `folder-closing-animation.svg` が再生された後、カードは静止アイコンに戻ります。
  さっと通り過ぎただけでは、フォルダーが勝手に開閉することはありません。
  SVG はバンドルにインライン化(`?raw` + data URI)されており、各カードが
  独自の SVG ドキュメントを所有します: 追加のリクエストは発生せず、画面に
  多数のカードが並んでも、アートワーク内部のグラデーション id が衝突することは
  決してありません。
- **ブレッドクラム**は各セグメントの先頭に、小さな `close-folder_all-fit.svg` グリフ
  (14px)を付けます — 小さいサイズで最も判読しやすいバリアントです。
- **プレビューのないモデル**は、グラス調の `NOPREVIEW-Icon/NO-PREVIEW.svg` を
  **デフォルト**アートワークとして使用します: モデルリストは
  `GET /model-manager/no-preview.svg` を直接指し(`image/svg+xml` としてそのまま配信され、
  ベクターアートがラスタライズされることは決してありません)、プレビュールート自体には
  **もはやフォールバックチェーンがありません** — 実在するプレビューファイルを配信するか、
  404 を返すだけです。旧来のフラットな `no-preview.png` ラスターは削除されました。
- **モデルハブのロゴ**は `AIModelHub-Logos/`(`civitai-icon.svg`、`hf-icon.svg`)に
  あります: **モデルページを開く**ボタンは、モデルのノート(`website`)に記録された
  プラットフォームのロゴを背景にまとい、詳細のアクション行でもカードのホバーカラムでも
  同様に表示されます。

### <img src="https://api.iconify.design/lucide/hammer.svg?color=%2365a30d" width="22" height="22" align="middle" alt=""> ツールチェーン

Biome は試用ののち**撤去**し、オーソドックスかつフル構成の
**ESLint 10 フラットコンフィグ** + **Prettier** パイプラインに一本化しました
([開発](#development)を参照)。

---

<a id="removed-feature"></a>

## <img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="28" height="28" align="middle" alt=""> 削除した機能: バッチスキャン

**「モデル情報のバッチスキャン」機能は完全に削除されました**。冗長だったからです:
モデルを開けば、まさに今見ているモデルについて、スキャンがかつて一括でバックフィル
していた情報すべてが、オンデマンドで読み込まれます。

- `DialogModelDetail` はマウント直後に `GET /model-manager/model/{type}/{index}/{filename}`
  をリクエストします。これはモデルの `__metadata__`(safetensors ヘッダーから直接読み取り)と、
  ファイルの隣に保存された Markdown ノートを返します。
- プレビューは `GET /model-manager/preview/{type}/{index}/{filename}` が配信し、
  実在するプレビューファイル(`.webp` / `.png` / `.jpg` / 動画、`name.ext` または
  `name.preview.ext` 形式)を解決します。プレビューのないモデルは、モデルリスト内で
  同梱のグラス調 `NO-PREVIEW.svg` の URL をそのまま保持するため、ルートに
  フォールバックチェーンはなく、実在しないものには素直に 404 を返します。

ライブラリ全体を走査してすべてのモデルをハッシュ化し、Civitai にハッシュで問い合わせる
処理は、同じ情報へ至る2つ目の、そしてはるかに遅い経路にすぎませんでした — おまけに
モーダルダイアログ、グローバルストア、2つの websocket イベント、ディスク上の
タスクファイル、専用設定が付随し、そのすべてを保守する必要がありました。
これらはすべて消えました。

**フロントエンド**

- `src/components/DialogScanning.vue` と `src/hooks/scan.ts` を削除。
- `App.vue`: ツールバーの `scanning` ボタン、`openModelScanning()`、`DialogScanning` の
  import を削除。`utils/iconMap.ts`: `mdi mdi-folder-search-outline` のマッピングと
  `FolderSearch` の import を削除。
- `en.json` / `zh.json` からスキャン専用の10個のキー(`batchScanModelInformation`、
  `modelInformationScanning`、`scanModelInformation`、`selectedAllPaths`、
  `scanFullInformation`、`scanMissInformation`、`scanCompleted`、
  `scanCompletedWithErrors`、`setting.scanAll`、`setting.scanMissing`)を削除。

**バックエンド**

- `py/information.py`: `GET` および `POST /model-manager/model-info/scan` ルート、
  `create_scan_model_info_task`、`download_model_info`、`get_scan_model_info_task_list`、
  `get_scan_information_task_filepath`、`SCAN_TASK_ID`、スキャン専用の
  `DownloadThreadPool`(ならびに不要になった `functools` / `thread` の import)を削除。
- `ModelSearcher.search_by_hash` とその3つの実装を削除 — 呼び出し元はスキャンだけでした。
  `_resolve_model_type` は残しています: `search_by_url` が使用するためです。
- `py/utils.py`: `recursive_search_files` と `calculate_sha256`(および `hashlib` の
  import)を削除 — どちらもスキャン専用のものでした。
- `update_scan_information_task` / `complete_scan_information_task` の websocket イベントは
  存在しなくなり、`downloads/scan_information.task` ファイルも書き出されません。

**意図的に残したもの** — 名前に「scan」を含みますが、バッチスキャンとは*無関係*です:

- `ModelManager.Scan.excludeScanTypes` と `ModelManager.Scan.IncludeHiddenFiles` は、
  **モデルリスト**(どのタイプをグリッドに読み込むか、`.` 始まりのファイルを表示するか)と
  ツールバーの隠しファイル表示切替を駆動しています。**この2つの設定 ID 文字列は
  意図的に変更していません**: ID は ComfyUI がユーザーの値を永続化する際のキーであり、
  リネームすれば既存インストールの保存済み設定が黙って孤立してしまうからです。
- ID の*周囲*は、いずれも永続化されないため、すべて「scan」臭を抜きました:
  設定カテゴリーは **Model List**(旧「Scan」)、ラベルは
  **「Exclude model types (separate with commas)」**(旧「Exclude scan types」)、
  i18n キーは `setting.modelList` / `setting.excludeModelTypes`、TypeScript の識別子は
  `configSetting.excludeModelTypes`、`py/config.py` のバックエンド設定グループは
  `model_list`(したがって `manager.py` は現在 `model_list.include_hidden_files` を解決します)。
- `ModelManager.scan_models()` / `os.scandir` — モデル**リスト**を構築します
  (ここでの「scan」は上流と同様、「フォルダーを列挙する」の意味)。意図的にそのままです:
  リネームすれば、削除した機能と無関係なコードまで巻き込むことになります。
- `scan_model_download_task_list()` — **ダウンロードタスク**の一覧取得。理由は同じです。
- `src/style.css` 内の Tailwind の「source scan」という文言 — 無関係。
- `ui/tree`、`ui/progress`、`useModelFolder`、および `selectModelType` /
  `selectSubdirectory` / `selectedSpecialPath` / `noModelsInCurrentPath` の文字列 —
  Upload・Hugging Face Upload ダイアログとモデルエディターで共用。

> [!NOTE]
> **失われたもの:** ファイルハッシュを介して Civitai からプレビューと説明を
> *一括バックフィル*する、唯一の手段です。情報を一度も取得していないモデルは、
> プレビュー/ノートを手動で設定する(モデルエディター → **Preview** →
> *Network* / *Local*)か、プレビュー付きで再ダウンロードする
> (_Create Download Task_ 経由)まで、プレースホルダーのプレビューのままになります。
> モデル情報の*読み取り*には影響ありません — それは常にディスクから、
> オンデマンドで取得されていたためです。

<a id="documentation"></a>

## <img src="https://api.iconify.design/lucide/book-open.svg?color=%237c3aed" width="28" height="28" align="middle" alt=""> ドキュメント

ステップバイステップの使い方ガイド。それぞれ完結しており、単体で読めます:

- [`docs/USAGE-EN.md`](docs/USAGE-EN.md) — English
- [`docs/USAGE-JA.md`](docs/USAGE-JA.md) — 日本語
- [`docs/USAGE-ZN.md`](docs/USAGE-ZN.md) — 中文

インストール、2つのレイアウト、カード操作とグラフへのドラッグ、モデルエディター
(フォルダーピッカー、フォルダープレフィックス付きのファイル名、プレビュー、説明)、
ダウンロードとタスクリスト、HuggingFace アップロードの各フェーズと完了メッセージ、
ZipNN 圧縮、設定とロケール、さらにトラブルシューティング表までを網羅しています。

<a id="development"></a>

## <img src="https://api.iconify.design/lucide/terminal.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> 開発

Web バンドルの**ビルド**にだけ Node.js が必要です。ComfyUI 内で拡張を実行するには、
Python 以外何も要りません。

```bash
corepack enable          # ピン留めされた pnpm バージョンを使用
pnpm install
```

| スクリプト | 用途 |
| --- | --- |
| `pnpm dev` | Vite 開発サーバー(ComfyUI 内でのホットリロード用に `web/manager-dev.js` を書き出す) |
| `pnpm build` | `web/` への本番ビルド |
| `pnpm build:clean` | `web/` を削除してから再ビルド |
| `pnpm rebuild` | `node_modules/` **と** `web/` を削除し、再インストールしてから再ビルド |
| `pnpm typecheck` | `vue-tsc --noEmit` による型チェック |
| `pnpm lint` / `pnpm lint:fix` | ESLint(フラットコンフィグ) |
| `pnpm format` / `pnpm format:check` | Prettier(Tailwind プラグイン付き) |
| `python -m mypy --config-file mypy.ini` | バックエンドの静的型チェック(クリーン) |
| `pnpm fallow` | Fallow フルパイプライン: デッドコード + 重複 + ヘルス |
| `pnpm fallow:dead`(`:type-aware`) | 未使用のファイル/エクスポート/型/依存、循環 — 任意で TS セマンティックパス |
| `pnpm fallow:dupes` | AST クローン検出(`mild` モード、`.fallowrc.json` を参照) |
| `pnpm fallow:health` | 複雑度のホットスポット、リファクタリング対象、0〜100 のヘルススコア |
| `pnpm fallow:fix:dry` / `fallow:fix` | 自動クリーンアップのプレビュー / 適用(常にまずドライラン) |
| `pnpm fallow:audit` | PR スタイルのゲート: 今回の変更で新たに生じた検出のみを報告 |

> [!WARNING]
> `pnpm dev` は `manager-dev.js` を書き出す前に **`web/` ディレクトリを丸ごと削除**します
> (`vite.config.ts` の `dev()` プラグインを参照)。これにより、コミット済みの本番バンドル —
> `web/manager.js` と `web/style-*.css` — がワーキングツリーから消え、`git status` では
> 削除扱いで表示されます。その状態でコミットすると、UI が読み込まれない拡張を
> 配布することになります。コミット前に必ず `pnpm build` を実行し、
> `web/manager.js` が欠けたツリーは決してコミットしないでください。

**husky** の `pre-commit` フックが、ステージされたファイルに対して **lint-staged**
(ESLint `--fix` + Prettier)を実行します。

### Fallow(コードベースインテリジェンス)

[Fallow](https://fallow.tools)(Rust 製、アナライザー内部に AI を使わない)は、
リンターを補完します: リポジトリを単一の依存グラフとして読み取り、未使用の
ファイル/エクスポート/型/依存、循環 import、クローングループ、複雑度のホットスポットを
報告します。`.fallowrc.json` はエントリポイント(`src/main.ts`)を固定し、コミット済みの
`web/` バンドル、ベンダリングされた `third_party/`、docs、assets をグラフから除外し、
private 型のリーク検査と未解決 import 検査を有効化します。ツリーは
**未使用エクスポートゼロ、重複ゼロ**に保たれており、残る唯一の検出は、
`@comfyorg/comfyui-desktop-bridge-types`(`@comfyorg/comfyui-frontend-types` の
推移的な型パッケージ)をピン留めするための、意図的な `pnpm-workspace.yaml` の
オーバーライドです。`pnpm fallow:fix:dry` ですべての自動削除をプレビューしてから、
`pnpm fallow:fix` で適用できます。

### Lint & フォーマット構成

ESLint 10 フラットコンフィグが、`typescript-eslint`、`eslint-plugin-vue`
(`vue-eslint-parser` 経由)、`eslint-plugin-import-x`(エイリアス認識の import 順序付け)、
`eslint-plugin-tailwindcss`(クラスの衛生管理)、`eslint-config-prettier`
(必ず最後に置くこと)を統合します。フォーマットと Tailwind クラスのソートは
Prettier が担当し、`prettier-plugin-tailwindcss` を使用します。

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

## <img src="https://api.iconify.design/lucide/heart-handshake.svg?color=%23ec4899" width="28" height="28" align="middle" alt=""> クレジットと帰属表示

ComfyUI‑Model‑Manager‑Neo が存在できるのは、
**[hayden-cn](https://github.com/hayden-cn)** 氏による
**[`ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)** が
先に存在したからです。このフォークの構造上のアイデアはすべて — モデルフォルダーの
抽象化、websocket 進捗プロトコルを備えた再開可能なダウンロードタスクシステム、
Civitai / HuggingFace のページパーサー、カードをグラフへドラッグする統合、
モデルエディターのフォーム基盤、カードサイズプリセットのような細かなアフォーダンスに
至るまで — hayden-cn 氏の設計です。Neo が変えたのは外装と依存関係、そして数多くの
バグであり、骨格を新たに発明する必要はありませんでした。このコードベースが
*なぜ*このような形をしているのかを理解する最速の方法は、今もオリジナルを読むことであり、
アーキテクチャに対する誠実な帰属表示はただ一つ、**彼らのもの**です。

本フォークは、**GNU General Public License v3.0** に従って使用・改変された派生物です。
Neo での変更(UI の再構築、PrimeVue の除去、Hugging Face アップロード、ZipNN 圧縮、
パッケージの近代化、ツールチェーン、信頼性・セキュリティの強化、バッチスキャンの削除、
日本語ローカライズ)は、同じ GPL-3.0 ライセンスのもとで提供されます。ライセンスに従い、
オリジナルの著作権表示とライセンス全文は [`LICENSE`](LICENSE) に保持されています。

### <img src="https://api.iconify.design/lucide/bot.svg?color=%236366f1" width="22" height="22" align="middle" alt=""> Qwen Studio とともに構築

このフォークの大部分は、**[Qwen Studio]** を使って構築されました。ZipNN 統合 —
ライブラリのベンダリング、ビルド済み `zipnn_core` バイナリの生成、テンソル単位の
圧縮/解凍の移植 — から、ガラスモーフィズム UI の再構築、Hugging Face アップロードフロー、
信頼性・セキュリティの一通りの強化、デバッグの多くに至るまで、すべて Qwen Studio との
密接な協力のもとで開発されました。その丁寧で反復的なエンジニアリングこそが Neo の
堅牢さの大きな理由であり、本プロジェクトはその貢献に感謝します。

このフォークがあなたの役に立ったなら、スターに値するのは上流のリポジトリです:
その肩の上に立つ仕事がなければ、上記の何ひとつ実現しなかったのですから。

以下の優れたプロジェクトのお世話になっています: [reka-ui]、[Tailwind CSS]、[Lucide]、
[VueUse]、[es-toolkit]、[valibot]、[vue-sonner]、[huggingface_hub]、[hf_xet]、
そして [ZipNN]。

---

<a id="license"></a>

## <img src="https://api.iconify.design/lucide/scale.svg?color=%2394a3b8" width="28" height="28" align="middle" alt=""> ライセンス

**GPL-3.0-only** — 全文は [`LICENSE`](LICENSE) を参照してください。

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
