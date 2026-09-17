<div align="center">
<img src="https://api.iconify.design/lucide/boxes.svg?color=%236366f1" width="34" height="34" align="middle" alt=""> ComfyUI‑Model‑Manager‑Neo
閲覧・ダウンロード・アップロード・ドラッグ＆ドロップ — あなたのモデルを、美しく管理します。
ComfyUI 標準のモデルマネージャーを、Vue 3 + Tailwind CSS v4 + reka‑ui という
完全にモダンなツールチェーンの上で再構築した、グラスモーフィズム UI 版の再解釈です。
https://img.shields.io/badge/License-GPL--3.0--only-blue.svg
https://img.shields.io/badge/ComfyUI-Custom%20Node-8A8B98.svg
https://img.shields.io/badge/Vue-3.5-4FC08D.svg?logo=vuedotjs&logoColor=white
https://img.shields.io/badge/Tailwind_CSS-v4-38BDF8.svg?logo=tailwindcss&logoColor=white
https://img.shields.io/badge/TypeScript-6-3178C6.svg?logo=typescript&logoColor=white
https://img.shields.io/badge/ESLint-10-4B32C3.svg?logo=eslint&logoColor=white
https://img.shields.io/badge/Prettier-3-F7B93E.svg?logo=prettier&logoColor=black
https://img.shields.io/badge/PRs-welcome-brightgreen.svg
注記： 本プロジェクトのスクリーンショットおよびデモ GIF は現在準備中のため、本 README では割愛しています。
</div>

## 目次

[Neo である理由](#why-neo) ・ [インストール](#installation) ・ [機能一覧](#features)
[ZipNN 可逆圧縮](#zipnn) ・ [オリジナルからの変更点](#what-changed) ・
[削除された機能：バッチスキャン](#removed-feature)
[ドキュメント](#documentation) ・ [開発](#development) ・
[クレジットと帰属表示](#credits) ・ [ライセンス](#license)

<a id="why-neo"></a>
<img src="https://api.iconify.design/lucide/sparkles.svg?color=%23f59e0b" width="28" height="28" align="middle" alt=""> Neo である理由

ComfyUI‑Model‑Manager‑Neo は、優れたオリジナルのマネージャーを土台に、
体験そのものをゼロから再構築したものです。

<img src="https://api.iconify.design/lucide/layers.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> グラスモーフィズム UI — 半透明でブラー処理された、エレベーション（階層感）を意識したインターフェースが、ComfyUI 本体のライト／ダークパレットに自動追従します。

<img src="https://api.iconify.design/lucide/puzzle.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> PrimeVue 完全脱却 — PrimeVue への依存を全面的に排除し、軽量かつヘッドレスな [reka-ui](https://reka-ui.com) プリミティブ、Tailwind CSS v4、[Lucide](https://lucide.dev) アイコンで置き換えました（shadcn‑vue 流のコンポーネント設計であり、コードを読んで自在に調整できます）。

<img src="https://api.iconify.design/lucide/upload-cloud.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> Hugging Face への直接アップロード — ローカルのモデルをそのまま HF リポジトリへ公開可能です（リポジトリの自動作成、非公開オプション、リアルタイム進捗表示付き）。**Neo での新機能です。**

<img src="https://api.iconify.design/lucide/package-plus.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> ZipNN 可逆圧縮 — safetensors モデルをその場で可逆圧縮／展開します（`.znn.safetensors`）。確認ダイアログと進捗表示、圧縮済みモデルには反転アイコンが表示されます。フォルダー単位のバッチ圧縮では封印済みの `<name>_DeltaZNN` バンドルにまとめられ、ファインチューンモデルはベースモデルとの差分のみを保持する極小のデルタファイルに圧縮されます。**Neo での新機能です。**

<img src="https://api.iconify.design/lucide/list-checks.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> マルチセレクト — カードにチェックを入れて複数モデルを一括でワークフローに追加、または一括削除できます。**Neo での新機能です。** フォルダーもチェック対象であり、「ワークフローに追加」は再帰的に展開され、「削除」はフォルダーごと丸ごと削除します。

<img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="16" height="16" align="middle" alt=""> スター機能 — すべてのモデルカードおよびフォルダーカードの右上にスタートグルを配置しました（モデル詳細のアクション行、選択バーにも同様に配置しています）。スター付きの項目は黄色く塗りつぶされた星印が表示され、常にソート上位に固定されます。**Neo での新機能です。**

<img src="https://api.iconify.design/lucide/folder-plus.svg?color=%2322c55e" width="16" height="16" align="middle" alt=""> フォルダー作成 — フォルダービューに「フォルダーを追加」ボタンを実装し、開いているディレクトリ内に任意の名前のフォルダー（サブフォルダーを含む）を作成できます。**Neo での新機能です。**

<img src="https://api.iconify.design/lucide/link.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> 直接リンクによるダウンロード — `.safetensors` / `.ckpt` / `.gguf` の URL を直接貼り付け、格納先フォルダーを選択し、任意でカスタムサブフォルダーを指定できます。

<img src="https://api.iconify.design/lucide/zap.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> `hf_xet` による高速化 — Hugging Face との通信では、利用可能な場合にチャンク分割・重複排除方式の Xet プロトコルを使用します。

<img src="https://api.iconify.design/lucide/workflow.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> ノードグラフとの一級統合 — モデルをキャンバスにドラッグしてノードを生成・充填、埋め込み（embedding）をテキストエリアにドラッグ、プレビュー画像に埋め込まれたワークフローを読み込む、といった操作に対応しています。

<img src="https://api.iconify.design/lucide/monitor-smartphone.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> レスポンシブ対応 — デスクトップ、モバイル、マルチディスプレイ環境を想定した設計です。

<img src="https://api.iconify.design/lucide/wrench.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> モダンなツールチェーン — Vite 8（Rolldown）、TypeScript 6、ESLint 10 のフラット設定、Prettier、husky + lint‑stagedを採用しています。ビルドは決定論的かつ lint エラーゼロを維持しています。

> [!NOTE]
> Neo は `[hayden-cn/ComfyUI-Model-Manager](https://github.com/hayden-cn/ComfyUI-Model-Manager)` のフォークであり、
> 同一の GPL‑3.0 ライセンスの下で配布されています。オリジナルのアーキテクチャに関するすべてのクレジットは
> その作者に帰属します。詳細は[クレジット](#credits)を参照してください。

<a id="installation"></a>
<img src="https://api.iconify.design/lucide/rocket.svg?color=%2322c55e" width="28" height="28" align="middle" alt=""> インストール

Neo は ComfyUI のカスタムノードとして動作します。以下のいずれかの方法でインストールしてください。

### 1. Git clone（アップデートを見込む場合の推奨方法）

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/rikunarita/ComfyUI-Model-Manager-Neo.git
```

### 2. 手動ダウンロード

[リポジトリのアーカイブ](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/archive/refs/heads/main.zip)
をダウンロードし、`ComfyUI/custom_nodes/` 内に展開してください。フォルダー名が
`ComfyUI-Model-Manager-Neo` になっていることを必ず確認してください。

### 3. ComfyUI Manager 経由

本フォークがレジストリに登録されている場合、[ComfyUI-Manager](https://github.com/ltdrdata/ComfyUI-Manager) 内で
「ComfyUI‑Model‑Manager‑Neo」を検索し、そこからインストールしてください。

インストール後は ComfyUI を再起動してください。Python の依存パッケージ（`huggingface_hub`、`hf_xet`、
`markdownify`）は初回起動時に自動でインストールされます。ビルド済みの Web バンドルは
`[web/](web)` に同梱されているため、拡張機能を実行するだけであれば Node.js は不要です。

トップバーの「Model Manager Neo」ボタン、サイドバー、または
`Extensions → Model Manager Neo` メニューコマンドから起動できます。

> [!TIP]
> Neo は現在も活発に開発が進行中です。日常的に実用可能な水準には達していますが、
> インターフェースは今後も変化しうる点にご留意ください。フィードバックおよび Issue の報告を歓迎します。

<a id="features"></a>
<img src="https://api.iconify.design/lucide/list-checks.svg?color=%233b82f6" width="28" height="28" align="middle" alt=""> 機能一覧

<details open>
<summary><b>閲覧と整理</b></summary>

-   フラットグリッド（デフォルトビュー）とフォルダーエクスプローラーの 2 レイアウトを、いつでも切り替え可能です。
-   リアルタイム検索（`*` ワイルドカードおよび複数トークンの「AND」マッチングに対応）をサポートしています。
-   名前・サイズ・作成日・更新日でのソートが可能です。
-   カードサイズの調整（プリセットおよび完全カスタム寸法）に対応しています。
-   再起動不要で隠しファイル（`.` から始まるファイル）の表示切り替えが可能です。
-   画像および動画のプレビュー、ホバー時の開閉アニメーション付きグラス調フォルダーアートワーク、
    プレビュー未設定時のグラス調フォールバック表示を提供します。
</details>

<details>
<summary><b>ノードグラフ統合</b></summary>

-   モデルのサムネイルをキャンバスへドラッグしてローダーノードを追加できます。
-   既存ノードへドラッグして対応する入力に充填できます（曖昧な場合は厳密一致を優先します）。
-   embedding をテキストエリアへドラッグして `(embedding:name:1.0)` を追記できます。
-   プレビュー画像をグラフへドラッグして埋め込まれたワークフローを読み込めます。
-   ノードの配置、または ComfyUI のクリップボードへのコピーを行う「追加 / コピー」ボタンを搭載しています。
</details>

<details>
<summary><b>ダウンロード</b></summary>

-   Civitai、Hugging Face、または直接ファイルの URL を貼り付け可能です。
-   1 ページに複数のファイル／バージョンが存在する場合は、これを解決してユーザーが選択できます。
-   直接リンクの場合は対象タイプの明示的な指定が必要です（任意でカスタムサブフォルダーを指定可）。
-   プレビュー画像は任意設定です。モデルページが提供するギャラリー全体が保持され、
    ダウンロード時に選択した画像がそのままカードの主要プレビューとなります。ダウンロードごとに
    編集可能な Markdown 説明文も付与されます。
-   タスクの一時停止／再開／削除に対応しています。進捗、速度、サイズはリアルタイムで更新されます。
-   Hugging Face からのダウンロードには `huggingface_hub`（利用可能な場合は `hf_xet` を併用）を使用します。
</details>

<details>
<summary><b>アップロード</b></summary>

-   ローカルファイルから任意のモデルフォルダーへアップロードできます（ダウンロードリスト上に進捗付きの
    ライブタスクとして登録されます）。
-   Hugging Face へ（Neo での新機能）：HF トークンによる認証を行い、存在しなければリポジトリを
    自動作成（公開／非公開の選択可）、格納先パスを選択し、進捗をリアルタイムで確認できます。
</details>

<details>
<summary><b>モデル情報と保守</b></summary>

-   ファイル情報を確認し、モデルに関する記録内容のすべてを読み取り専用の「情報（Information）」テーブルで閲覧できます。
-   ノートの YAML フロントマターを解析した作者名、ベースモデル、あらゆるハッシュ値（`AutoV1` … `SHA256_12`）、
    フォーマットおよび精度、モデルのプラットフォーム、モデルページへのリンク、すべてのプレビュー URL
    （未知のキーは末尾にそのまま表示）、あるいは対応する情報を持たないモデルについては safetensors の
    `__metadata__` ブロックをそのまま表示します。
-   モデルの名称変更、フォルダー／タイプ間の移動、プレビューとノートを含めた完全な削除が可能です。
-   モデルに付随する Markdown ノートの読み込み、編集、保存ができます。
-   モデルのプレビュー画像の変更・削除が可能です。保存時に開いていたギャラリーページがそのままカードの
    主要プレビューとなります。
-   **「モデルページを開く」** アクションは、モデルの取得元（Civitai または Hugging Face）のロゴを
    ボタンの背景として表示するため、モデルの出所が一目で判別できます。
-   モデル情報（safetensors メタデータ、Markdown ノート、プレビュー）はモデルを開いた際に
    オンデマンドで読み込まれます。ライブラリ全体を対象とした事前スキャン処理は存在しません。
</details>

<details>
<summary><b>設定と多言語対応（i18n）</b></summary>

-   Civitai および Hugging Face の API キーはローカルの `private.key` に保存されます
    （`CIVITAI_API_KEY` / `HF_TOKEN` の環境変数によるフォールバックにも対応）。初回起動時に
    ComfyUI のユーザー設定からキーが自動移行されます。
-   モデルの一覧からタイプごとの除外設定、隠しファイルの表示／非表示設定が可能です。
-   UI 言語は ComfyUI 本体のロケールに追従します。英語、中文、日本語をフルサポートで同梱しています。
-   地域／文字体系のサブタグ（`ja-JP`、`zh-Hant-TW` など）はベース言語へ自動的に折りたたまれます。
</details>

<a id="zipnn"></a>
<img src="https://api.iconify.design/lucide/package-plus.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> ZipNN 可逆圧縮

Neo の目玉機能です。大容量の `.safetensors` チェックポイントは、ディスク容量を急速に圧迫します。
Neo は [ZipNN](https://github.com/zipnn/zipnn) 方式を用いて、これらをその場で可逆圧縮・展開できます。
これは公式の ZipNN プロジェクトが採用しているものと同一のテンソル対応方式であり、
結果として生成されるファイルは ZipNN エコシステム全体との互換性を保ちます。

### 仕組み

モデルの重みの大部分は浮動小数点数であり、浮動小数点数の大部分は冗長です。すなわち、
挙動の良いウェイトテンソルの指数部バイトは、繰り返し出現する傾向があります。ZipNN はまさにこの性質を
利用します。各テンソルに対して以下を行います。

1.  値をバイトプレーンへ分割し、符号／指数／仮数のビットを並べ替えて、同種のバイトが
    まとまるように再配置します。
2.  各プレーンを FiniteStateEntropy（FSE）コーデックでハフマン符号化します。

浮動小数点でないテンソル（整数のインデックス、マスクなど）はそのまま変更せずコピーされ、
圧縮後のサイズがかえって大きくなる浮動小数点テンソルは、無理にパディングされることなくそのまま維持
されます。圧縮された各テンソルは `uint8` のベクトルとして格納され、元の `dtype` と `shape` は
すべて単一の `znn_compressed_vectors` メタデータエントリに記録されます。近似や欠落は一切発生せず、
展開処理は元のファイルをビット単位で完全に再現します。

圧縮後のモデルは、元のファイルと同じ場所に `<name>.znn.safetensors` として書き出されます。
これは公式の ZipNN ツール群（および `zipnn_safetensors()` でパッチが当てられたローダー）が
期待する拡張子そのものであるため、パッチ適用済みの ComfyUI ローダーは Neo で圧縮されたモデルを
透過的に読み込むことができます。実際のチェックポイントでは、おおむね元のサイズの 60〜80% 程度に
収まることが多いようです（ランダム性の高いデータは圧縮率が低く、低エントロピーの重みはより高い圧縮率を得ます）。

### 使い方

任意の `.safetensors` モデルを開いてください。プレビューと情報テーブルの間にある領域に、
ZipNN のアートワーク自体がボタンとして配置されています。同梱の SVG がガラス板そのものを
描画し（ダークモード用のバリアントを含む）、ホバー時に浮き上がって明るくなり、ツールチップと
スクリーンリーダー向けの説明も備えています。このボタンを押すと、以下の流れになります。

1.  意図的に「危険」表示ではないスタイルの確認ダイアログが表示されます（圧縮は可逆処理であり、
    圧縮ファイルの書き込みと検証が完全に完了するまで、元のファイルが削除されることはありません）。
2.  ボタンがリアルタイムの進捗バーに置き換わり、処理は CPU プール上でテンソル単位で実行される
    ため、ComfyUI 本体の応答性は損なわれません。
3.  成功すると、元のファイルが `<name>.znn.safetensors` に置き換わります。プレビューと Markdown
    ノートもリネームに追従し、グリッド表示も自動的に更新されます。

**圧縮済み**のモデルを開くと、同じアートワークが**色反転**した状態で表示され、アクションは
展開（decompress）に切り替わります。確認手順は同一で、実行すると通常の `.safetensors` に復元されます。

情報テーブルの表示も変化します。単一の「File Size」行が、「元のファイルサイズ」、「圧縮後の
ファイルサイズ」、「元サイズに対する割合（%）」の 3 行に置き換わります。圧縮前のサイズは圧縮時に
ファイルのメタデータへ記録されるため、リネーム後もこの内訳表示は維持されます（このキーを書き込まない
公式 ZipNN CLI で圧縮されたファイルについては、通常の「File Size」行がそのまま表示されます）。

同じアートワークは、すべてのモデルカードおよびフォルダーカードの右上隅（スタートグルの隣）にも
配置されています。ワンクリックで圧縮（あるいは反転していれば展開）が実行され、確認および進捗表示の
挙動は同一ですが、モデルを開く必要はありません。単体・バッチ・デルタのいずれかのタスクが実行中の間、
このボタンには円形の進捗リングが表示されます。

### バッチ圧縮（フォルダー単位）

ZipNN の公式ツールはパス全体を対象とした圧縮に対応しており、Neo はこれをマネージャーに統合しています。
フォルダーを選択（「ファイルを選択」）し、下部バーの ZipNN アートワークボタンを押す
（あるいはフォルダーカードのコーナーボタンを使用する）と、フォルダーツリー内のすべての
`.safetensors` モデルが圧縮され（プレビューとノートは対応するモデルに追従する）、
バンドルフォルダー `<name>_DeltaZNN` へ移動します。元のフォルダーは空になった時点で消滅します。

`*_DeltaZNN` バンドルは封印された領域であり、以下の制約が課されます。

-   バンドル内に配置できるのは ZipNN 由来のコンテンツ（`*.znn.*` モデル、`*.znn` デルタファイル）
    のみです（通常モデルのアップロード、ダウンロード、バンドルへの移動はすべて拒否されます）。
-   バンドルフォルダーと非バンドルフォルダーを同時に選択することはできません。バンドル側は
    警告トーストとともに自動的に選択解除されます。
-   バンドルの ZipNN ボタンは反転表示されており、押下するとバッチ展開が実行され、
    すべてが元の名前のフォルダーへ復元されます（空になったバンドルフォルダーは削除されます）。

デルタフォルダー（`<base>_DeltaZNN`、後述）もバンドルの一種であり、その反転ボタンは
内部のファインチューンモデルをすべて一括で復元します。

モデルタイプのルートフォルダー（`checkpoints` など）については、そのバンドルは
自分自身の内部に生成されます（`<root>_DeltaZNN`）。ルートフォルダーの兄弟フォルダーとして
生成すると ComfyUI のフォルダーマッピングの対象外となり、ローダーおよびマネージャーの双方から
見えなくなってしまうためです。処理方向は自動判定されます。通常モデルが存在すれば圧縮、
バンドルのみが残っていれば展開という具合です。

旧バージョンで作成されたバンドル（`<name>_ZNN`）も引き続き認識され、元の名前へ正しく展開されます。
タスク実行中はボタンが円形のリングとなり、パーセンテージが円の内側に表示されます。
複数フォルダーの処理はキューとして実行されます。確認は 1 回のみ、タスクは順次実行され、
進捗表示は常に 1 件ずつ表示されます。

### デルタ圧縮（ベースモデルに対するファインチューンの差分圧縮）

ファインチューン済みモデルは、そのベースモデルとバイト列の大部分を共有しています。ZipNN はこの
差分のみを保存できます。ちょうど 2 つの通常の `.safetensors` モデルを選択し、下部バーの
「ZipNN デルタ圧縮」を押してください。小さなダイアログが表示され、選択したモデルのうちどちらが
ベースでどちらがファインチューンかを指定します（公式のバイトレベルのデルタ API を
ヘッダー長のアライメント調整とともに内部で使用しているため、ベースとファインチューンで
異なるメタデータを保持していても問題ありません）。結果として生成されるファイル
（多くの場合、ファインチューンモデルの数パーセント程度のサイズに収まります）は
`<base>_DeltaZNN/<ft>_delta_<base>.znn` として書き出され、冗長となったファインチューン側の
ファイルは削除されます。デルタファイルの展開（カードボタンの反転操作）を実行すると、
ファインチューン済みモデルがベースモデルの隣にバイト完全一致の状態で復元され、
空になったデルタフォルダーは自動的に削除されます。復元にはベースモデルが必須であり、
ZipNN はデルタ作成時に双方のバイト長が一致していることを検証します。

### 同梱によって「そのまま動く」

<details>
<summary><b>従来これが厄介だった理由 — そして Neo による解決</b></summary>

ZipNN の Python 側の実装自体は単純ですが、その圧縮処理は C 拡張モジュール
（`zipnn_core`、FiniteStateEntropy をベースに構築）に依存しています。PyPI には Linux 向けの
wheel が一切提供されておらず、macOS-arm64 向けの wheel とソース tarball のみが存在する
状態のため、単純な `pip install zipnn` はソースからのビルドを試み、C コンパイラおよび
Python ヘッダー（`Python.h`）を持たない環境では失敗します。これは ComfyUI の実行環境としては
極めてありふれた状況であり、しかもエラーメッセージは分かりにくいものでした
（`error: [Errno 2] No such file or directory: 'x86_64-pc-linux-gnu-gcc'`）。

そこで Neo は、ライブラリ全体を `[third_party/](third_party/)` 配下に同梱（ベンダリング）し、
Linux x86_64（CPython 3.10〜3.13）向けのビルド済み `zipnn_core` バイナリを提供しています。
これらの環境では、初回の圧縮処理時に同梱パッケージと該当するバイナリを `sys.path` に配置する
だけで済み、コンパイラ不要、pip 不要、ネットワーク通信不要、待ち時間なしで利用できます。

ビルド済みバイナリが一致しない環境（macOS、Windows、一般的でないアーキテクチャ、
あるいは最新の CPython）に限り、同梱の C ソースから単発のクリーンビルドにフォールバックします
（複数の pip 戦略を連鎖的に試すような処理は一切行いません）。

レイアウト、対応プラットフォーム／glibc の範囲、ライセンス（ZipNN は MIT、
FiniteStateEntropy は BSD-2-Clause OR GPL-2.0）、およびバイナリの再ビルド・追加方法については
`[third_party/README.md](third_party/README.md)` を参照してください。
</details>

> [!NOTE]
> 圧縮処理にはモデルのテンソルをメモリ上に展開する必要があるため、CPU プール上で実行され、
> VRAM ではなく RAM の制約を受けます。処理は可逆かつ安全です。通常の `.safetensors` は
> `.znn.safetensors` ファイルの書き込みとクローズが完了した後にのみ削除され、処理が失敗した
> 場合は部分的な出力が自動的にクリーンアップされます。

<a id="what-changed"></a>
<img src="https://api.iconify.design/lucide/git-compare.svg?color=%23a855f7" width="28" height="28" align="middle" alt=""> オリジナルからの変更点

本セクションは、GPL‑3.0 ライセンスの要求に従い、本フォークにおける相違点を明示するものです。
機能は維持された上でさらに拡張されています。削除されたのは 2 点のみです。PrimeVue への依存
そのものと、バッチスキャン機能です。詳細は[削除された機能：バッチスキャン](#removed-feature)
を参照してください。

<img src="https://api.iconify.design/lucide/palette.svg?color=%23d946ef" width="22" height="22" align="middle" alt=""> インターフェース

| 領域                 | オリジナル                                         | Neo                                                                                                                              |
| -------------------- | -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| コンポーネントライブラリ | PrimeVue 4                                         | reka‑ui（ヘッドレス）+ shadcn‑vue スタイルのラッパー                                                                              |
| スタイリング           | Tailwind CSS v3 + PrimeVue テーマ                  | スコープ付き `--mm-*` デザイントークンを用いた Tailwind CSS v4                                                                     |
| アイコン               | PrimeIcons                                         | アイコンマップを介した Lucide（`@lucide/vue`）                                                                                    |
| 見た目                 | 標準的な PrimeVue サーフェス                       | グラスモーフィズム（ブラー、階層感、マイクロインタラクション）、自動ダークモード対応                                               |
| ダイアログ             | PrimeVue の `Dialog` / `ContextMenu`               | reka‑ui ダイアログ。ダイアログごとのサイズ／位置指定、ドラッグ移動、アンカー付きコンテキストメニューに対応                         |
| モデル詳細タブ         | Description + Metadata（生の safetensors `__metadata__`） | Description + Information：ノートの YAML フロントマター（作者、ベースモデル、各種ハッシュ、フォーマットおよび精度、モデルのプラットフォーム、モデルページへのリンク、すべてのプレビュー URL、未知のキーはそのまま表示）を解析した読み取り専用テーブル。フォールバックとして生の `__metadata__` も表示可能 |

<img src="https://api.iconify.design/lucide/package.svg?color=%23f97316" width="22" height="22" align="middle" alt=""> パッケージ

-   **削除：** `primevue`、`@primevue/themes`、`lodash`、`dayjs`、`js-yaml`。
-   **追加／置換：** `reka-ui`、`@lucide/vue`、`es-toolkit`（← lodash）、
    `date-fns`（← dayjs）、`yaml`（← js-yaml）、`valibot`（ランタイムのスキーマ検証）、
    `vue-sonner`（トースト通知）、`class-variance-authority`、`clsx`、
    `tailwind-merge`、`tw-animate-css`。
-   **アップグレード：** Vite 5 → 8（Rolldown）、TypeScript 5 → 6、Vue i18n 9 →
    11、markdown‑it 14 → 15、`@vueuse/core` 11 → 14。
-   **Python：** `huggingface_hub` + `hf_xet` を追加。従来のスレッドプールを asyncio ベースの
    タスクプールへ置換しました。

<img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%2306b6d4" width="22" height="22" align="middle" alt=""> ツールバー／ボタンの役割分担

マネージャーのヘッダーは、明示的なアイコン主導のアクション群として再設計されました。
フラット⇄フォルダーレイアウト切り替え、隠しファイルの表示／非表示、更新、
ダウンロードリスト、Hugging Face へのアップロード、の各機能を独立したボタンとして配置しています。

<img src="https://api.iconify.design/lucide/folder-open.svg?color=%23f59e0b" width="22" height="22" align="middle" alt=""> グラス調アセットパック（フォルダーアイコンとプレビュー無し表示）

インターフェースは、`assets/` 配下に用意された手作りのグラスモーフィズム調アセットパックを利用しています。
フォルダーカードは、静止状態では `Folder-Icons/close-folder_beside-fit.svg` を表示します。
カード上に 1 秒以上ポインターを置くと `folder-opening-animation.svg`（SMIL によるモーフ
アニメーション：0.2 秒の遅延 + 1.35 秒の再生時間）が再生され、1 秒以上ポインターが離れると
`folder-closing-animation.svg` が再生された後、静止画のアイコンに戻ります。一瞬だけカーソルが
通過するようなカジュアルな操作では、フォルダーが開閉することはありません。これらの SVG はバンドルに
インライン化されており（`?raw` + data URI 方式）、各カードが独自の SVG ドキュメントを保持する
形になっているため、追加のリクエストは一切発生せず、画面上に多数存在するカード間でアートワーク内の
グラデーション ID が衝突することもありません。

パンくずリストの各セグメントには、小サイズでの視認性に最も優れたバリアントである
`close-folder_all-fit.svg` の小さなグリフ（14px）が先頭に付与されます。

プレビューを持たないモデルは、グラス調の `NOPREVIEW-Icon/NO-PREVIEW.svg` をデフォルトの
アートワークとして使用します。モデル一覧は `GET /model-manager/no-preview.svg`（`image/svg+xml`
としてそのまま配信され、ベクター画像がラスタライズされることはありません）を直接参照します。
プレビュー配信用のルート自体にはフォールバックの連鎖が存在せず、実際のプレビューファイルを
配信するか、あるいは 404 を返すかのいずれかとなります。旧来のフラットな `no-preview.png`
ラスター画像は廃止されました。

モデルハブのロゴは `AIModelHub-Logos/`（`civitai-icon.svg`、`hf-icon.svg`）に格納されています。
**「モデルページを開く」** ボタンは、モデルのノートに記録されたプラットフォーム（`website`）の
ロゴを背景として、詳細画面のアクション行およびカードホバー時の操作列の双方で表示します。

<img src="https://api.iconify.design/lucide/hammer.svg?color=%2365a30d" width="22" height="22" align="middle" alt=""> ツールチェーン

Biome の採用を試験的に検討しましたが、最終的には従来型の、完全に設定を作り込んだ
ESLint 10 フラット構成 + Prettier のパイプラインに戻す判断を下しました
（詳細は[開発](#development)を参照してください）。

<a id="removed-feature"></a>
<img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="28" height="28" align="middle" alt=""> 削除された機能：バッチスキャン

「モデル情報の一括スキャン」機能は完全に削除されました。この機能は冗長であったためです。
なぜなら、モデルを開くという操作自体が、そのモデルに対してオンデマンドで、
かつそのモデルに関してのみ、従来のスキャン機能が一括で補完していた情報のすべてを
読み込むからです。

`DialogModelDetail` はマウント時に即座に `GET /model-manager/model/{type}/{index}/{filename}`
をリクエストします。このエンドポイントは、safetensors のヘッダーから直接読み取った
`__metadata__` と、ファイルに付随する Markdown ノートを返します。
プレビューは `GET /model-manager/preview/{type}/{index}/{filename}` から配信され、
存在するプレビューファイル（`.webp` / `.png` / `.jpg` / 動画。`name.ext` または
`name.preview.ext` の形式）を解決します。プレビューを持たないモデルについては、モデル一覧が
同梱のグラス調 `NO-PREVIEW.svg` の URL を直接参照するため、このルートにはフォールバック
連鎖が一切存在せず、存在しないファイルに対しては単純に 404 を返します。

ライブラリ全体を走査し、すべてのモデルをハッシュ化して Civitai へハッシュ値で問い合わせる方式は、
同じ情報を得るためのはるかに低速な第二の経路にすぎなかった上、モーダルダイアログ、
グローバルストア、2 つの WebSocket イベント、ディスク上のタスクファイル、専用の設定項目まで
維持する必要がありました。これらはすべて削除されました。

#### フロントエンド

-   `src/components/DialogScanning.vue` および `src/hooks/scan.ts` を削除しました。
-   `App.vue`：ツールバーの `scanning` ボタン、`openModelScanning()`、`DialogScanning` の
    インポートを削除しました。
-   `utils/iconMap.ts`：`mdi mdi-folder-search-outline` のマッピングと
    `FolderSearch` のインポートを削除しました。
-   `en.json` / `zh.json` からスキャン専用の 10 個のキーを削除しました
    （`batchScanModelInformation`、`modelInformationScanning`、`scanModelInformation`、
    `selectedAllPaths`、`scanFullInformation`、`scanMissInformation`、
    `scanCompleted`、`scanCompletedWithErrors`、`setting.scanAll`、
    `setting.scanMissing`）。

#### バックエンド

-   `py/information.py`：`GET` および `POST /model-manager/model-info/scan` ルート、
    `create_scan_model_info_task`、`download_model_info`、
    `get_scan_model_info_task_list`、`get_scan_information_task_filepath`、
    `SCAN_TASK_ID`、およびスキャン専用の `DownloadThreadPool` を削除しました（未使用となった
    `functools` / `thread` のインポートも併せて削除）。
-   `ModelSearcher.search_by_hash` とその 3 つの実装を削除しました。このスキャン機能のみが
    呼び出し元であったためです。`_resolve_model_type` は `search_by_url` が使用しているため維持しています。
-   `py/utils.py`：`recursive_search_files` と `calculate_sha256`（および `hashlib` の
    インポート）を削除しました。いずれもスキャン機能のためだけに存在していたためです。
-   `update_scan_information_task` / `complete_scan_information_task` の WebSocket
    イベントはもはや存在せず、`downloads/scan_information.task` ファイルも書き込まれません。

#### 意図的に維持したもの

名称に「scan」を含むが、バッチスキャン機能の一部ではないものは以下の通りです。

-   `ModelManager.Scan.excludeScanTypes` と `ModelManager.Scan.IncludeHiddenFiles` は
    モデル一覧（グリッドに読み込むタイプ、`.` から始まるファイルを表示するかどうか）と、
    ツールバーの隠しファイル表示切り替えを制御しています。これら 2 つの設定 ID 文字列は
    意図的に変更していません。この ID は ComfyUI がユーザーの設定値を永続化する際のキーで
    あるため、名称を変更すると既存のすべてのインストール環境で保存済みの設定が孤立して
    しまうからです。
-   これら ID の周辺にあるものはすべて「脱スキャン化」を行いました。永続化される要素が
    一切ないためです。設定カテゴリーは（旧「Scan」から）「Model List」に変更され、
    ラベルは（旧「Exclude scan types」から）**「除外するモデルタイプ（カンマ区切り）」** に、
    i18n キーは `setting.modelList` / `setting.excludeModelTypes` に、TypeScript の
    識別子は `configSetting.excludeModelTypes` に、`py/config.py` 内のバックエンド設定
    グループは `model_list` に、それぞれ変更しました（そのため `manager.py` は現在
    `model_list.include_hidden_files` を参照しています）。
-   `ModelManager.scan_models()` / `os.scandir` — モデル一覧を構築する処理
    （ここでの「scan」はオリジナル同様「フォルダーを列挙する」という意味です）。
    この機能を除去された機能と無関係なコードにまで手を入れて名称変更する必要はないため、
    意図的にそのまま残しました。
-   `scan_model_download_task_list()` — ダウンロードタスクの一覧を返す処理。同様の理由です。
-   `src/style.css` 内の Tailwind の「source scan」という表記 — 無関係です。
-   `ui/tree`、`ui/progress`、`useModelFolder`、および `selectModelType` /
    `selectSubdirectory` / `selectedSpecialPath` / `noModelsInCurrentPath` の各文字列 —
    アップロードダイアログ、Hugging Face アップロードダイアログ、モデルエディターと共有されています。

> [!NOTE]
> この変更によって失われるもの：ファイルハッシュを用いて Civitai からプレビューと
> 説明文を一括で事後補完する唯一の手段です。情報を一度も取得していないモデルは、
> プレビューまたはノートが手動で設定される（モデルエディター → プレビュー →
> 「ネットワーク」／「ローカル」）か、あるいはプレビューを伴うダウンロードタスクの作成を
> 通じて再ダウンロードされるまで、プレースホルダーのプレビューのままとなります。既存モデルの
> 情報の閲覧自体には影響がありません。この情報は元々ディスクからオンデマンドで取得されていたためです。

<a id="documentation"></a>
<img src="https://api.iconify.design/lucide/book-open.svg?color=%237c3aed" width="28" height="28" align="middle" alt=""> ドキュメント

各言語版とも完結した、単体で読める使用手順ガイドを用意しています。

-   `[docs/USAGE-EN.md](docs/USAGE-EN.md)` — 英語
-   `[docs/USAGE-JA.md](docs/USAGE-JA.md)` — 日本語
-   `[docs/USAGE-ZN.md](docs/USAGE-ZN.md)` — 中文

これらのガイドは、インストール、両レイアウト、カード操作とグラフへのドラッグ操作、
モデルエディター（フォルダー選択、フォルダー接頭辞付きの名前、プレビュー、説明文）、
ダウンロードとタスクリスト、Hugging Face アップロードの各フェーズと完了メッセージ、
ZipNN 圧縮、設定とロケール、そしてトラブルシューティングの一覧までを網羅しています。

<a id="development"></a>
<img src="https://api.iconify.design/lucide/terminal.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> 開発

Web バンドルをビルドする場合にのみ Node.js が必要です。ComfyUI 内で拡張機能を
実行するだけであれば、Python 以外は何も必要ありません。

```bash
corepack enable          # ピン留めされた pnpm バージョンを使用する
pnpm install
```

| スクリプト              | 内容                                                                                                     |
| ----------------------- | -------------------------------------------------------------------------------------------------------- |
| `pnpm dev`              | Vite 開発サーバー（ComfyUI でのホットリロード用に `web/manager-dev.js` を書き出す）                      |
| `pnpm build`            | `web/` へのプロダクションビルド                                                                          |
| `pnpm build:clean`      | `web/` を削除してから再ビルド                                                                            |
| `pnpm rebuild`          | `node_modules/` と `web/` を削除し、再インストールしてから再ビルド                                       |
| `pnpm typecheck`        | `vue-tsc --noEmit` による型チェック                                                                      |
| `pnpm lint` / `pnpm lint:fix`     | ESLint（フラット構成）                                                                                   |
| `pnpm format` / `pnpm format:check` | Prettier（Tailwind プラグイン込み）                                                                      |
| `python -m mypy --config-file mypy.ini` | バックエンドの静的型チェック（クリーンな状態を維持）                                                     |
| `pnpm fallow`           | Fallow のフルパイプライン：デッドコード + 重複検出 + ヘルスチェック                                      |
| `pnpm fallow:dead` (`:type-aware`)  | 未使用のファイル／エクスポート／型／依存関係、循環参照 — 任意で TS のセマンティック解析パスを追加可能    |
| `pnpm fallow:dupes`     | AST ベースのクローン検出（`mild` モード。詳細は `.fallowrc.json` を参照）                                |
| `pnpm fallow:health`    | 複雑度のホットスポット、リファクタリング対象の抽出、0〜100 のヘルススコア                                |
| `pnpm fallow:fix:dry` / `fallow:fix`      | 自動クリーンアップのプレビュー／適用（必ず dry-run を先に実行すること）                                  |
| `pnpm fallow:audit`     | PR 向けのゲートチェック：今回の変更によって新たに発生した指摘のみを対象とする                            |

> [!WARNING]
> `pnpm dev` は `manager-dev.js` を書き出す前に `web/` ディレクトリ全体を削除します
> （`vite.config.ts` 内の `dev()` プラグインを参照）。これにより、コミット済みの
> プロダクションバンドルである `web/manager.js` と `web/style-*.css` が作業ツリーから
> 削除され、`git status` 上ではこれらが削除済みとして表示されます。この状態のままコミットすると、
> UI が起動しない拡張機能を配布してしまうことになります。コミット前には必ず `pnpm build` を実行し、
> `web/manager.js` が欠落したツリーを絶対にコミットしないようご注意ください。

husky の `pre-commit` フックが、ステージ済みファイルに対して lint-staged
（ESLint `--fix` + Prettier）を実行します。

### Fallow（コードベース インテリジェンス）

[Fallow](https://fallow.tools)（Rust 製、解析エンジン自体に AI は使用していない）は、
リンター群を補完する存在です。リポジトリ全体を単一の依存関係グラフとして読み取り、
未使用のファイル／エクスポート／型／依存関係、循環インポート、クローングループ、
複雑度のホットスポットを報告します。`.fallowrc.json` はエントリーポイント（`src/main.ts`）を
固定し、コミット済みの `web/` バンドル、ベンダリングされた `third_party/`、ドキュメント、
アセットをグラフの対象外とし、プライベート型リークおよび未解決インポートのチェックを
有効化しています。ツリーは「未使用エクスポートゼロ、重複ゼロ」の状態を維持しており、
唯一残っている指摘事項は、`@comfyorg/comfyui-frontend-types` の推移的な型パッケージである
`@comfyorg/comfyui-desktop-bridge-types` を固定するための、意図的な
`pnpm-workspace.yaml` オーバーライドです。`pnpm fallow:fix:dry` は、
`pnpm fallow:fix` が適用するすべての自動削除内容を事前にプレビューできます。

### Lint とフォーマットのスタック

ESLint 10 のフラット構成により、`typescript-eslint`、`eslint-plugin-vue`
（`vue-eslint-parser` 経由）、`eslint-plugin-import-x`（エイリアスを認識したインポート順序制御）、
`eslint-plugin-tailwindcss`（クラスの記述衛生）、そして必ず末尾に配置する必要がある
`eslint-config-prettier` を組み合わせています。フォーマット処理と Tailwind クラスの
ソート処理は、`prettier-plugin-tailwindcss` を伴う Prettier が担当します。

### プロジェクト構成

```text
├─ __init__.py            # ComfyUI のエントリーポイント：依存関係のインストール、ルート登録
├─ py/                    # Python バックエンド（aiohttp のルート、HF/Civitai 連携、タスク処理）
│  ├─ manager.py          #   モデルの CRUD 操作とフォルダー一覧取得
│  ├─ download.py         #   ダウンロードタスク（http + huggingface_hub）
│  ├─ upload.py           #   ローカルファイルのアップロード（パス検証済み）
│  ├─ upload_hf.py        #   Hugging Face へのアップロード
│  ├─ compress.py         #   ZipNN の圧縮／展開（ベンダリング済みコア）
│  ├─ information.py      #   URL による Civitai / HF 検索、プレビュー配信
│  ├─ auth.py · config.py · thread.py · utils.py
├─ third_party/           # ベンダリング済み ZipNN（Python パッケージ + ビルド済み zipnn_core + C ソース）
├─ src/                   # Vue 3 フロントエンド
│  ├─ components/         #   アプリコンポーネント + ui/（reka-ui ラッパー）
│  ├─ hooks/              #   store, models, download, config, dialog, …
│  ├─ utils/ · types/ · locales/
│  ├─ style.css           #   Tailwind v4 のエントリーポイント + デザイントークン
│  └─ main.ts             #   ComfyUI 拡張機能として登録
└─ web/                   # ComfyUI に配信されるビルド済みバンドル（コミット対象）
```

<a id="credits"></a>
<img src="https://api.iconify.design/lucide/heart-handshake.svg?color=%23ec4899" width="28" height="28" align="middle" alt=""> クレジットと帰属表示

ComfyUI‑Model‑Manager‑Neo が存在できているのは、[hayden‑cn](https://github.com/hayden-cn) による
`[ComfyUI-Model-Manager](https://github.com/hayden-cn/ComfyUI-Model-Manager)` が
先に存在していたからに他なりません。本フォークにおける構造上の発想 — モデルフォルダーの抽象化、
WebSocket による進捗プロトコルを備えた再開可能なダウンロードタスクシステム、Civitai / Hugging Face
ページのパーサー、モデルカードをグラフへドラッグして統合する仕組み、モデルエディターのフォーム処理、
さらにはカードサイズのプリセットといった細かな配慮に至るまで、そのすべてが hayden‑cn による設計
です。Neo が変更したのは、見た目、依存関係、そして数多くのバグの修正であり、土台そのものを
新たに発明したわけではありません。このコードベースが現在の形になっている「理由」を理解する最も
確実な方法は、オリジナルのコードを読むことです。アーキテクチャに関する正直な帰属表示は
以下のとおりです。すべてはオリジナルの功績です。

本フォークは GNU General Public License v3.0 の条件に従って使用・改変された派生物です。
Neo における変更点（UI の再構築、PrimeVue の除去、Hugging Face アップロード機能、ZipNN 圧縮、
パッケージの近代化、ツールチェーンの刷新、信頼性・セキュリティの強化、バッチスキャン機能の削除、
および日本語ローカライゼーション）は、同一の GPL‑3.0 ライセンスの下で提供されます。
ライセンスの定めに従い、オリジナルの著作権表示およびライセンス全文は
`[LICENSE](LICENSE)` にそのまま保持されています。

<img src="https://api.iconify.design/lucide/bot.svg?color=%236366f1" width="22" height="22" align="middle" alt=""> Qwen Studio による開発協力

本フォークの大部分は [Qwen Studio](https://chat.qwen.ai/) を用いて構築されました。ZipNN の統合作業 —
ライブラリのベンダリング、ビルド済み `zipnn_core` バイナリの生成、テンソル単位での
圧縮／展開処理の移植 — に加え、グラスモーフィズム UI の再構築、Hugging Face アップロード
フロー、信頼性・セキュリティ面の見直し、そしてデバッグ作業の多くが、Qwen Studio との
緊密な協働のもとで開発されました。その丹念かつ反復的なエンジニアリングは、Neo が現在の堅牢性を
備えるに至った大きな理由であり、本プロジェクトはその貢献に深く感謝しています。

本フォークが役立つと感じた場合は、ぜひアップストリームのリポジトリにスターを付けてほしいと思います。
ここまでの機能のすべては、その土台の上に成り立っているものです。

本プロジェクトは、以下の優れたライブラリ・プロジェクト群の上に構築されています：
[reka-ui](https://reka-ui.com)、[Tailwind CSS](https://tailwindcss.com)、[Lucide](https://lucide.dev)、[VueUse](https://vueuse.org)、[es-toolkit](https://es-toolkit.dev)、[valibot](https://valibot.dev)、[vue-sonner](https://vue-sonner.vercel.app)、
[huggingface_hub](https://github.com/huggingface/huggingface_hub)、[hf_xet](https://github.com/huggingface/xet-core)、[ZipNN](https://github.com/zipnn/zipnn)。

<a id="license"></a>
<img src="https://api.iconify.design/lucide/scale.svg?color=%2394a3b8" width="28" height="28" align="middle" alt=""> ライセンス

GPL‑3.0‑only — 全文は `[LICENSE](LICENSE)` を参照してください。

<div align="center">
Neo が時間の節約になったなら、リポジトリへのスター <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="16" height="16" align="middle" alt=""> と、
[オリジナルの作者](https://github.com/hayden-cn/ComfyUI-Model-Manager) への感謝をぜひお願いします。
</div>
