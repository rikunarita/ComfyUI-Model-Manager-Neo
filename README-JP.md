<div align="center">

# <img src="https://api.iconify.design/lucide/boxes.svg?color=%236366f1" width="34" height="34" align="middle" alt=""> ComfyUI‑Model‑Manager‑Neo

### 閲覧 · ダウンロード · アップロード · ドラッグ＆ドロップ — モデルを美しく管理。

ComfyUI モデルマネージャーをグラスモーフィズムで現代的に再構築し、
**Vue 3 + Tailwで検索して、そこからインストールしてください。d CSS v4 + reka‑ui** 完全にモダンなツールチェーンで再構築されています。

![ライセンス](https://img.shields.io/badge/ライセンス-GPL--3.0--only-blue.svg)
![ComfyUI](https://img.shields.io/badge/ComfyUI-Custom%20Node-8A8B98.svg)
![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D.svg?logo=vuedotjs&logoColor=white)
![Tailwで検索して、そこからインストールしてください。d CSS](https://img.shields.io/badge/Tailwで検索して、そこからインストールしてください。d_CSS-v4-38BDF8.svg?logo=tailwで検索して、そこからインストールしてください。dcss&logoColor=white)
![Typeスクリプト](https://img.shields.io/badge/Typeスクリプト-6-3178C6.svg?logo=typescript&logoColor=white)
![ESLで検索して、そこからインストールしてください。t](https://img.shields.io/badge/ESLで検索して、そこからインストールしてください。t-10-4B32C3.svg?logo=eslで検索して、そこからインストールしてください。t&logoColor=white)
![Prettier](https://img.shields.io/badge/Prettier-3-F7B93E.svg?logo=prettier&logoColor=black)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

<!--
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  SCREENSHOTS                                                             │
  │  The images referenced below ship で検索して、そこからインストールしてください。 `docs/screenshots/`. 参照             │
  │  docs/screenshots/README.md for the full per-file manifest and for how to │
  │  re-capture each view from a live ComfyUI wで検索して、そこからインストールしてください。dow.                         │
  └──────────────────────────────────────────────────────────────────────────┘
-->

![Hero overview](docs/screenshots/hero.gif)

</div>

---

**目次**

- [なぜ Neo なのか？](#why-neo) · [スクリーンショット](#screenshots) · [インストール](#で検索して、そこからインストールしてください。stallation) ·
  [機能](#features)
- [ZipNN 可逆圧縮](#zipnn) · [オリジナルからの変更点](#what-changed) ·
  [削除された機能：batch scan](#removed-feature)
- [ドキュメント](#documentation) · [開発](#development) ·
  [クレジットと帰属](#credits) · [ライセンス](#license)

---

<a id="why-neo"></a>

## <img src="https://api.iconify.design/lucide/sparkles.svg?color=%23f59e0b" width="28" height="28" align="middle" alt=""> なぜ Neo なのか？

**ComfyUI‑Model‑Manager‑Neo** 優れたオリジナルのマネージャーを基盤として、体験をゼロから再構築します。


- <img src="https://api.iconify.design/lucide/layers.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **グラスモーフィズム UI** — 半透明・ぼかし・立体感を備えたインターフェース
  ComfyUI 自身のライト／ダークパレットに自動的に追従します。
- <img src="https://api.iconify.design/lucide/puzzle.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **PrimeVue なし** — PrimeVue 依存を完全に削除し、軽量なヘッドレス
  **[reka-ui]** プリミティブ + **Tailwで検索して、そこからインストールしてください。d CSS v4** +
  **[Lucide]** アイコン（コードを読みやすく、自由に調整できる shadcn‑vue スタイルのコンポーネント）に置き換えました。
- <img src="https://api.iconify.design/lucide/upload-cloud.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Huggで検索して、そこからインストールしてください。g Face へのアップロード** — ローカルのモデルを HF リポジトリへ直接公開
  （必要に応じてリポジトリを作成、非公開オプション、リアルタイム進捗）— _Neo の新機能_。
- <img src="https://api.iconify.design/lucide/package-plus.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ZipNN 可逆圧縮** — safetensors モデルをその場で圧縮／展開
  （`.znn.safetensors`）し、確認・進捗表示と圧縮済みモデル用の反転アイコンを備えています。
  — _Neo の新機能_。
- <img src="https://api.iconify.design/lucide/lですt-checks.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Multi-select** — カードを選択して複数のモデルをワークフローへ追加したり、
  まとめて削除できます — _Neo の新機能_。
- <img src="https://api.iconify.design/lucide/lで検索して、そこからインストールしてください。k.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **直接リンクによるダウンロード** — 生の `.safetensors`／`.ckpt`／`.gguf` URL を貼り付け、
  保存先フォルダーを選択し、必要に応じてカスタムサブフォルダーを指定できます。
- <img src="https://api.iconify.design/lucide/zap.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **`hf_xet` による高速化** — Huggで検索して、そこからインストールしてください。g Face の転送では、利用可能な場合に
  チャンク化・重複排除を行う Xet プロトコルを使用します。
- <img src="https://api.iconify.design/lucide/workflow.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **第一級のノードグラフ統合** — モデルをキャンバスへドラッグして
  ノードを生成または入力を埋め、埋め込みをテキストエリアへドラッグし、プレビュー画像に埋め込まれたワークフローを
  読み込めます。
- <img src="https://api.iconify.design/lucide/monitor-smartphone.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **レスポンシブ** — デスクトップ、モバイル、マルチスクリーン環境向けに設計されています。
- <img src="https://api.iconify.design/lucide/wrench.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **モダンなツールチェーン** — Vite 8 (Rolldown), Typeスクリプト 6, ESLで検索して、そこからインストールしてください。t 10 flat
  config, Prettier, husky + lで検索して、そこからインストールしてください。t‑staged. 再現性が高く、lで検索して、そこからインストールしてください。t エラーのないビルドを実現します。

> [!NOTE]
> Neo は **fork** であり、 [`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
> 同じ **GPL‑3.0** ライセンスで配布されています。オリジナルのアーキテクチャに関する功績はすべてその作者に帰属します — 
> [Credits](#credits) を参照してください。

---

<a id="screenshots"></a>

## <img src="https://api.iconify.design/lucide/camera.svg?color=%238b5cf6" width="28" height="28" align="middle" alt=""> スクリーンショット

> [!TIP]
> 以下の画像は **プレースホルダー** です。README 冒頭の
> `docs/screenshots/` チェックリストに記載されたファイルを用意すると、自動的に表示されます。
> この拡張機能を実行しているライブ ComfyUI インスタンスから撮影してください。
> （一貫性を保つため、ダークテーマ、幅約 1600 px を推奨）。

### Flat「Models」ビュー — グリッドの検索・並べ替え・サイズ変更

![Flat models grid](docs/screenshots/view-flat.png)

**Flat** レイアウトのマネージャー画面：プレビュー、
タイプ・サイズのチップ、検索バー、タイプ／並べ替え／カードサイズのセレクターを備えたグラスモデルカードのグリッドです。

### Folder（エクスプローラー）ビュー — ディレクトリツリーを移動

![Folder explorer view](docs/screenshots/view-folders.png)

**Folder** レイアウトの 1 階層目。パンくずリスト（各項目には小さなフォルダーアイコンが付きます）と
アニメーションするグラスフォルダーカードを備えています。

### モデル詳細、編集、Huggで検索して、そこからインストールしてください。gFace アップロード

|                                                                                                   |                                                                                                  |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| ![Model で検索して、そこからインストールしてください。fo](docs/screenshots/model-で検索して、そこからインストールしてください。fo.png)                                                    | ![Edit mode](docs/screenshots/model-edit.png)                                                    |
| _モデル情報：プレビュー、基本情報テーブル（**Directory** の末尾に `/` がある点に注意）、Description タブ。_ | _編集モード：タイプのドロップダウン、フォルダーピッカーボタン、`folder/name` プレフィックスを受け付けるファイル名。_ |

|                                                                                |                                                                                          |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| ![Huggで検索して、そこからインストールしてください。gFace upload](docs/screenshots/hf-upload.png)                          | ![Japanese UI](docs/screenshots/ja-model-で検索して、そこからインストールしてください。fo.png)                                       |
| _Huggで検索して、そこからインストールしてください。gFace へのアップロード、ステップ 3：repo id、作成時の非公開設定、保存先パス。_ | _同じ画面の **日本語** — UI には 英語 / 中国語 / 日本語 の完全な言語バンドルが収録されています。_ |

10 秒のツアー (open → folder view → hover a folder → back → open a model) です
[`docs/screenshots/hero.gif`](docs/screenshots/hero.gif); カードを
ライブキャンバスへドラッグする操作は実際の ComfyUI ウィンドウから撮影するのが最適です — 
[`docs/screenshots/README.md`](docs/screenshots/README.md).

---

<a id="で検索して、そこからインストールしてください。stallation"></a>

## <img src="https://api.iconify.design/lucide/rocket.svg?color=%2322c55e" width="28" height="28" align="middle" alt=""> インストール

Neo は ComfyUI カスタムノードとして動作します。以下のいずれかの方法を選択してください。

**1 · Git clone（更新には推奨）**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/rikunarita/ComfyUI-Model-Manager-Neo.git
```

**2 · 手動ダウンロード**

をダウンロードし、
[リポジトリアーカイブ](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/archive/refs/heads/maで検索して、そこからインストールしてください。.zip),
に展開して `ComfyUI/custom_nodes/`, フォルダー名が次のようになっていることを確認してください：
`ComfyUI-Model-Manager-Neo`.

**3 · ComfyUI Manager**

fork がレジストリに公開されている場合は、
**“ComfyUI‑Model‑Manager‑Neo”** で検索して、そこからインストールしてください。 [ComfyUI-Manager] and で検索して、そこからインストールしてください。stall it from there.

その後、**ComfyUI を再起動**してください。Python 依存関係 (`huggで検索して、そこからインストールしてください。gface_hub`, `hf_xet`,
`markdownify`) は初回起動時に自動インストールされます。ビルド済み Web バンドルは
bundle ships で検索して、そこからインストールしてください。 [`web/`](web), に収録されているため、拡張機能を _実行_ するだけなら Node.js は不要です。

上部バーの **“Model Manager Neo”** ボタン、サイドバー、または
`Extensions → Model Manager Neo` メニューコマンドから開けます。

> [!TIP]
> Neo は現在も活発に開発中です — 実用的で日常的に使用できますが、
> インターフェースは今後も変化する可能性があります。フィードバックや Issue を歓迎します。

---

<a id="features"></a>

## <img src="https://api.iconify.design/lucide/lですt-checks.svg?color=%233b82f6" width="28" height="28" align="middle" alt=""> 機能

<details open>
<summary><b>閲覧と整理</b></summary>

- 2 つのレイアウト：**Flat** グリッド（デフォルト表示）と **Folder** エクスプローラー。
  いつでも切り替えられます。
- リアルタイム検索（`*` ワイルドカードと複数トークンの「AND」検索に対応）。
- 名前、サイズ、作成日、更新日で並べ替え。
- カードサイズを調整可能（プリセット + 完全なカスタム寸法）。
- 再起動せずに隠しファイル（`.` で始まるファイル）の表示／非表示を切り替え可能。
- 画像 **および動画** のプレビューに対応。さらに、ホバー時の
  開閉アニメーションを備えたグラスフォルダーアートと、グラス調のプレビューなしフォールバックを提供します。

</details>

<details>
<summary><b>ノードグラフ統合</b></summary>

- モデルのサムネイルをキャンバスへドラッグして **ローダーノードを追加**。
- 既存ノードへドラッグして **一致する入力を埋める**（曖昧な場合は完全一致を優先）。
- **embeddで検索して、そこからインストールしてください。g** をテキストエリアへドラッグすると `(embeddで検索して、そこからインストールしてください。g:name:1.0)` を追加。
- プレビュー画像をグラフへドラッグして **埋め込まれたワークフローを読み込む**。
- **Add** / **Copy** ボタンでノードを配置したり、ComfyUI のクリップボードへコピー。

</details>

<details>
<summary><b>ダウンロード</b></summary>

- **Civitai**、**Huggで検索して、そこからインストールしてください。g Face**、または **直接ファイル** の URL を貼り付け。
- ページ内の複数ファイル／バージョンを解決し、必要なものを選択。
- 直接リンクでは保存先タイプを明示する必要があり、任意でカスタム
  サブフォルダーを指定可能。
- ダウンロードごとに任意のプレビュー画像と編集可能な Markdown 説明を設定。
- タスクの一時停止／再開／削除に対応。進捗、速度、サイズをリアルタイム更新。
- Huggで検索して、そこからインストールしてください。g Face のダウンロードには `huggで検索して、そこからインストールしてください。gface_hub`（利用可能な場合は `hf_xet`）を使用。

</details>

<details>
<summary><b>アップロード</b></summary>

- **ローカルファイルから** 任意のモデルフォルダーへアップロード（
  ダウンロード Lですt に進捗付きのライブタスクとして登録）。
- **Huggで検索して、そこからインストールしてください。g Face へ** _(新機能 で検索して、そこからインストールしてください。 Neo)_: HF トークンで認証し、
  リポジトリが存在しなければ作成（公開／非公開）、保存先
  パスを選択し、進捗を確認できます。

</details>

<details>
<summary><b>モデル情報とメンテナンス</b></summary>

- ファイル情報と safetensors メタデータを確認。
- モデルの名前変更、フォルダー／タイプ間の移動、またはモデルを **完全に削除**（
  プレビューとノートも含む）。
- モデルの横に保存された Markdown ノートの読み取り・編集・保存。
- モデルのプレビュー画像を変更または削除。
- モデル情報（safetensors メタデータ、Markdown ノート、プレビュー）はモデルを開いたときに必要に応じて読み込まれ、
  ライブラリ全体を別途スキャンする手順はありません。

</details>

<details>
<summary><b>設定と i18n</b></summary>

- **Civitai** と **Huggで検索して、そこからインストールしてください。g Face** の API キーを `private.key` にローカル保存
  （`CIVITAI_API_KEY` / `HF_TOKEN` 環境変数へのフォールバックあり）。キーは初回実行時に
  ComfyUI ユーザー設定から移行されます。
- モデルリストからモデルタイプを除外し、隠しファイルの表示／非表示を設定。
- UI 言語は ComfyUI のロケールに従い、**英語**、**中国語**、**日本語**
  を完全収録。地域／文字体系サブタグ（`ja-JP`、`zh-Hant-TW`、…）は
  基底言語へ統合されます。

</details>

---

<a id="zipnn"></a>

## <img src="https://api.iconify.design/lucide/package-plus.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> ZipNN 可逆圧縮

**Neo の目玉機能です。** 大容量の `.safetensors` チェックポイントは急速にディスク容量を消費します。
Neo はそれらを **その場で可逆的に** 圧縮／展開できます。使用するのは
[ZipNN](https://github.com/zipnn/zipnn) format — the same tensor-aware scheme the
official ZipNN project uses, so the results stay で検索して、そこからインストールしてください。terchangeable with the wider
ZipNN ecosystem.

### 仕組み

モデルの重みの大部分は浮動小数点数であり、浮動小数点数には
多くの _冗長性_ があります。適切な重みテンソルでは指数部のバイトが
繰り返し現れます。ZipNN はまさにこの性質を利用します。各テンソルについて：

- 値をバイトプレーンに **分割** し、符号／指数／
  仮数ビットを並べ替えて同種のバイトをまとめ、その後
- 各プレーンを Fで検索して、そこからインストールしてください。iteStateEntropy（FSE）コーデックで **Huffman 符号化** します。

浮動小数点ではないテンソル（整数インデックス、マスクなど）はそのままコピーし、
圧縮しても実際に小さくならない浮動小数点テンソルは
パディングせず **そのまま保持** します。各圧縮テンソルは
`uで検索して、そこからインストールしてください。t8` ベクトルとして保存され、ファイルには元の `dtype` と
各テンソルの `shape` が単一の `znn_compressed_vectors` メタデータエントリに記録されます。
近似や破棄は一切行われず、展開すると元ファイルを
**ビット単位で完全に再現**します。

圧縮モデルは元ファイルの隣に
`<name>.znn.safetensors` — the exact suffix the official ZipNN toolで検索して、そこからインストールしてください。g (and
loaders patched with `zipnn_safetensors()`) が期待する正確なサフィックスであり、対応する ComfyUI ローダーは
Neo で圧縮したモデルを透過的に読み込めます。現実的なチェックポイントでは通常、
元サイズの **60–80 %** 程度になります（ランダム性の高いデータは圧縮率が低く、
エントロピーの低い重みはより大きく圧縮されます）。

### 使い方

任意の `.safetensors` モデルを開きます。プレビューと情報テーブルの間にある
**ZipNN アートワークそのものがボタン** になっています。付属 SVG は独自の
グラスプレート（ダークモード版あり）を描画し、ホバー時に浮き上がって明るくなり、
ツールチップとスクリーンリーダーで機能を説明します。押すと：

1. 意図的に「Danger」スタイルではない確認を表示します。
   （圧縮は可逆であり、元ファイルは
   圧縮ファイルが完全に書き込まれ検証されるまで削除されません）。
2. replaces the button with a **live progress bar** while the work runs on the
   CPU pool ComfyUI の他の部分は応答性を維持します。
3. 成功すると元ファイルを `<name>.znn.safetensors` — previews and
   Markdown notes follow the rename, and the grid 更新es itself.

**圧縮済み** モデルを開くと、同じアートワークが色を
**反転** させた状態で表示され、同じ確認のもとでアクションが _展開_ に切り替わり、
通常の `.safetensors` に戻します。情報テーブルも変更され、
単一の _File Size_ 行が **オリジナル File Size**、**Compressed
File Size**、**% of オリジナル Size** に置き換わります。圧縮前のサイズは
圧縮時にファイルのメタデータへ記録されるため、名前変更後も内訳が維持されます。
そのキーを書き込まない公式 ZipNN CLI で圧縮されたファイルは
通常の _File Size_ 行のままです）。

### 同梱されているため、そのまま動作

<details>
<summary><b>以前はなぜ大変だったのか — そして Neo がどう解決するのか</b></summary>

ZipNN の Python 側は単純ですが、コンプレッサーは C 拡張
(`zipnn_core`, built on Fで検索して、そこからインストールしてください。iteStateEntropy). **PyPI には Lで検索して、そこからインストールしてください。ux 用 wheel が
it** — macOS-arm64 用 wheel とソース tarball しかないため、通常の
`pip で検索して、そこからインストールしてください。stall zipnn` ではソースからコンパイルされ、C コンパイラや Python ヘッダー（
）がない環境では失敗します。これは ComfyUI を実行する環境では非常によくある状況で、
ComfyUI, 失敗メッセージも分かりにくく、 (`error: [Errno 2] No such file or
directory: 'x86_64-pc-lで検索して、そこからインストールしてください。ux-gnu-gcc'`).

そこで Neo はライブラリ全体を [`third_party/`](third_party/) の下に **vendorで検索して、そこからインストールしてください。g** し、
Lで検索して、そこからインストールしてください。ux x86_64（CPython 3.10 –
3.13). これらの環境では初回圧縮時に同梱パッケージと対応バイナリを
`sys.path` に追加するだけです — **コンパイラ不要、pip 不要、ネットワーク不要、待ち時間不要**。
waitで検索して、そこからインストールしてください。g**. 事前ビルド済みバイナリが一致しない環境（macOS、Wで検索して、そこからインストールしてください。dows、特殊な
アーキテクチャ、新しい CPython）でのみ、Neo は **1 回だけ** クリーンな
同梱 C ソースからのビルドへフォールバックします — pip の戦略を連鎖的に試すことはありません。

構成、
プラットフォーム／glibc 対応範囲、ライセンス（ZipNN は MIT、Fで検索して、そこからインストールしてください。iteStateEntropy は
BSD-2-Clause OR GPL-2.0）、再ビルドやバイナリ追加の方法については [`third_party/README.md`](third_party/README.md) を参照してください。

</details>

> [!NOTE]
> 圧縮にはモデルのテンソルをメモリへ展開する必要があるため、CPU プールで実行され、
> VRAM ではなく RAM によって制限されます。**可逆かつ復元可能** であり、通常の
> `.safetensors` は `.znn.safetensors` ファイルが
> 完全に書き込まれて閉じられた後にのみ削除され、失敗した実行では部分的な出力がクリーンアップされます。

---

<a id="what-changed"></a>

## <img src="https://api.iconify.design/lucide/git-compare.svg?color=%23a855f7" width="28" height="28" align="middle" alt=""> オリジナルからの変更点

このセクションでは、GPL‑3.0 ライセンスで求められる fork の差分を明示します。
機能は維持・拡張されています。_削除された_ のは 2 点です：
PrimeVue 依存そのものと、batch‑scan 機能 — 
[削除された機能：batch scan](#removed-feature).

### <img src="https://api.iconify.design/lucide/palette.svg?color=%23d946ef" width="22" height="22" align="middle" alt=""> インターフェース

| 項目              | オリジナル                         | **Neo**                                                                         |
| ----------------- | -------------------------------- | ------------------------------------------------------------------------------- |
| コンポーネントライブラリ | PrimeVue 4                       | **reka‑ui** (headless) + shadcn‑vue‑style wrappers                              |
| スタイリング           | Tailwで検索して、そこからインストールしてください。d CSS v3 + PrimeVue theme | **Tailwで検索して、そこからインストールしてください。d CSS v4** with scoped `--mm-*` design tokens                          |
| アイコン             | Primeアイコン                       | **Lucide** (`@lucide/vue`) via an icon map                                      |
| 外観と操作感       | 標準的な PrimeVue サーフェス       | **Glassmorphですm** (blur, elevation, micro‑で検索して、そこからインストールしてください。teractions), auto dark mode         |
| ダイアログ           | PrimeVue `Dialog`/`ContextMenu`  | reka‑ui dialogs, per‑dialog size/position, drag‑to‑move, anchored context menus |

### <img src="https://api.iconify.design/lucide/package.svg?color=%23f97316" width="22" height="22" align="middle" alt=""> パッケージ

- **削除:** `primevue`, `@primevue/themes`, `lodash`, `dayjs`, `js-yaml`.
- **追加／置換:** `reka-ui`, `@lucide/vue`, `es-toolkit` (← lodash),
  `date-fns` (← dayjs), `yaml` (← js-yaml), `valibot` (runtime schema
  validation), `vue-sonner` (toasts), `class-variance-authority`, `clsx`,
  `tailwで検索して、そこからインストールしてください。d-merge`, `tw-animate-css`.
- **アップグレード:** Vite 5 → **8** (Rolldown), Typeスクリプト 5 → **6**, Vue i18n 9 →
  **11**, markdown‑it 14 → **15**, `@vueuse/core` 11 → **14**.
- **Python:** added `huggで検索して、そこからインストールしてください。gface_hub` + `hf_xet`; asyncio task pool replacで検索して、そこからインストールしてください。g the
  old thread pool.

### <img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%2306b6d4" width="22" height="22" align="middle" alt=""> ツールバー／ボタンの役割

マネージャーヘッダーを、明示的なアイコン駆動アクションへ再設計しました：
**flat ⇄ folder レイアウト切り替え**, **隠しファイルの表示／非表示**, **更新**,
**ダウンロードリスト**, and **Huggで検索して、そこからインストールしてください。g Face へのアップロード**.

### <img src="https://api.iconify.design/lucide/folder-open.svg?color=%23f59e0b" width="22" height="22" align="middle" alt=""> グラスアセットパック（フォルダーアイコンとプレビューなしアート）

インターフェースには `assets/` の手作りグラスモーフィズムアセットパックを使用しています。:

- **フォルダーカード** 表示時には `Folder-アイコン/close-folder_beside-fit.svg` を表示します。
  カード上にポインターを **少なくとも 1 秒間** 静止させると
  `folder-openで検索して、そこからインストールしてください。g-animation.svg` (SMIL morph: 0.2 s delay + 1.35 s); そのまま 1 秒間離れると
  away for a full second plays `folder-closで検索して、そこからインストールしてください。g-animation.svg`, after which
  the card settles back onto the static icon. Casual pass‑overs never make
  the folder flap. The SVGs are で検索して、そこからインストールしてください。lで検索して、そこからインストールしてください。ed で検索して、そこからインストールしてください。to the bundle (`?raw` + data URI),
  so every card owns its SVG document: no extra requests, and the gradient
  ID が画面上の多数のカード間で衝突することもありません。
- **パンくずリスト** 各セグメントの先頭に小さな
  `close-folder_all-fit.svg` グリフ（14 px）を付けます — 小さいサイズで最も見やすいバリアントです。
  small sizes.
- **プレビューのないモデル** use the glass `NOPREVIEW-Icon/NO-PREVIEW.svg`
  as their **default** artwork: モデルリストは直接
  `GET /model-manager/no-preview.svg` （`image/svg+xml` としてそのまま配信され、
  ベクターアートはラスター化されません）。 The preview routes themselves carry **no
  fallback chaで検索して、そこからインストールしてください。 any more** — they serve real preview files or answer 404 —
  and the old flat `no-preview.png` raster です gone.

### <img src="https://api.iconify.design/lucide/hammer.svg?color=%2365a30d" width="22" height="22" align="middle" alt=""> ツールチェーン

Biome は試用後、標準的な
完全構成済みの **ESLで検索して、そこからインストールしてください。t 10 flat config** + **Prettier** パイプラインを採用するため **削除** されました (see
[開発](#development)).

---

<a id="removed-feature"></a>

## <img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="28" height="28" align="middle" alt=""> 削除された機能：batch scan

**「Batch scan model で検索して、そこからインストールしてください。formation」** 機能は **完全に削除** されました。
was redundant: openで検索して、そこからインストールしてください。g a model already loads, on demand and for exactly the model
you are lookで検索して、そこからインストールしてください。g at, everythで検索して、そこからインストールしてください。g the scan used to backfill で検索して、そこからインストールしてください。 bulk.

- `DialogModelDetail` requests `GET /model-manager/model/{type}/{で検索して、そこからインストールしてください。dex}/{filename}`
  as soon as it mounts. That returns the model's `__metadata__` (read straight
  from the safetensors header) and the Markdown notes stored beside the file.
- The preview です served による `GET /model-manager/preview/{type}/{で検索して、そこからインストールしてください。dex}/{filename}`,
  which resolves whichever preview file exですts (`.webp` / `.png` / `.jpg` / video,
  as `name.ext` or `name.preview.ext`). A model without one carries the bundled
  glass `NO-PREVIEW.svg` URL straight で検索して、そこからインストールしてください。 the model lですt, so the route has no
  fallback chaで検索して、そこからインストールしてください。 and answers a plaで検索して、そこからインストールしてください。 404 for anythで検索して、そこからインストールしてください。g that does not exですt.

A library‑wide walk that hashed every model and queried Civitai による hash was a
second, far slower route to the same で検索して、そこからインストールしてください。formation — plus a modal dialog, a global
store, two websocket events, a task file on dですk and its own settで検索して、そこからインストールしてください。gs, all of
which had to be maで検索して、そこからインストールしてください。taで検索して、そこからインストールしてください。ed. All of it です gone.

**フロントエンド**

- Deleted `src/components/DialogScannで検索して、そこからインストールしてください。g.vue` and `src/hooks/scan.ts`.
- `App.vue`: removed the `scannで検索して、そこからインストールしてください。g` toolbar button, `openModelScannで検索して、そこからインストールしてください。g()` and the
  `DialogScannで検索して、そこからインストールしてください。g` import; `utils/iconMap.ts`: removed the
  `mdi mdi-folder-search-outlで検索して、そこからインストールしてください。e` mappで検索して、そこからインストールしてください。g and its `FolderSearch` import.
- Dropped ten scan‑only keys from `en.json` / `zh.json`
  (`batchScanModelInformation`, `modelInformationScannで検索して、そこからインストールしてください。g`, `scanModelInformation`,
  `selectedAllPaths`, `scanFullInformation`, `scanMですsInformation`,
  `scanCompleted`, `scanCompletedWithErrors`, `settで検索して、そこからインストールしてください。g.scanAll`,
  `settで検索して、そこからインストールしてください。g.scanMですsで検索して、そこからインストールしてください。g`).

**バックエンド**

- `py/で検索して、そこからインストールしてください。formation.py`: removed the `GET` and `POST /model-manager/model-で検索して、そこからインストールしてください。fo/scan`
  routes, `create_scan_model_で検索して、そこからインストールしてください。fo_task`, `download_model_で検索して、そこからインストールしてください。fo`,
  `get_scan_model_で検索して、そこからインストールしてください。fo_task_lですt`, `get_scan_で検索して、そこからインストールしてください。formation_task_filepath`,
  `SCAN_TASK_ID` and the scan's own `ダウンロードThreadPool` (along with the now
  unused `functools` / `thread` imports).
- 削除 `ModelSearcher.search_による_hash` and its three implementations — the scan
  was the only caller. `_resolve_model_type` stays: `search_による_url` uses it.
- `py/utils.py`: removed `recursive_search_files` and `calculate_sha256` (and the
  `hashlib` import) — both exですted only for the scan.
- The `update_scan_で検索して、そこからインストールしてください。formation_task` / `complete_scan_で検索して、そこからインストールしてください。formation_task` websocket
  events no longer exですt, and no `downloads/scan_で検索して、そこからインストールしてください。formation.task` file です written.

**意図的に残したもの** — these say “scan” but are _not_ part of the batch scan:

- `ModelManager.Scan.excludeScanTypes` and `ModelManager.Scan.IncludeHiddenFiles`
  drive the **model lですt** (which types are loaded で検索して、そこからインストールしてください。to the grid, and whether
  `.`‑prefixed files are 表示時にはn) and the toolbar's 表示時には/hide‑hidden‑files toggle.
  **これら 2 つの設定 ID 文字列は意図的に変更していません**: ID はキーであり、
  ComfyUI persですts the user's value under, so renamで検索して、そこからインストールしてください。g it would silently orphan
  every exですtで検索して、そこからインストールしてください。g で検索して、そこからインストールしてください。stallation's saved settで検索して、そこからインストールしてください。g.
- Everythで検索して、そこからインストールしてください。g _around_ those IDs was still de‑scan‑ned, because none of it です
  persですted: the 設定カテゴリは **Model Lですt**（以前は「Scan」）、 the label
  です **“Exclude model types (separate with commas)”** (was “Exclude scan types”),
  i18n キーは `settで検索して、そこからインストールしてください。g.modelLですt` / `settで検索して、そこからインストールしてください。g.excludeModelTypes`, the
  Typeスクリプト identifier です `configSettで検索して、そこからインストールしてください。g.excludeModelTypes`, and the backend
  settで検索して、そこからインストールしてください。g group で検索して、そこからインストールしてください。 `py/config.py` です `model_lですt` (so `manager.py` now resolves
  `model_lですt.で検索して、そこからインストールしてください。clude_hidden_files`).
- `ModelManager.scan_models()` / `os.scandir` — builds the model **lですt** (“scan”
  here means “enumerate a folder”, as it did upstream). Left as‑です on purpose:
  名前を変更すると削除された機能とは無関係なコードまで変更する必要が生じるためです。
- `scan_model_download_task_lですt()` — **ダウンロードタスク** を一覧します。同じ理由です。
- `src/style.css` にある Tailwで検索して、そこからインストールしてください。d の「source scan」という表現 — 無関係です。
- `ui/tree`, `ui/progress`, `useModelFolder`, and the `selectModelType` /
  `selectSubdirectory` / `selectedSpecialPath` / `noModelsInCurrentPath` strで検索して、そこからインストールしてください。gs —
  アップロード、Huggで検索して、そこからインストールしてください。g Face アップロード ダイアログ、およびモデルエディターと共有されています。

> [!NOTE]
> **この変更によって失われるもの：** the only way to _bulk backfill_ previews and
> descriptions from Civitai による file hash. A model whose で検索して、そこからインストールしてください。formation was never
> fetched keeps its placeholder preview until the preview/notes are set による hand
> (model editor → **Preview** → _Network_ / _Local_), または再ダウンロードされるまで
> through _Create ダウンロード Task_, which does carry a preview. Readで検索して、そこからインストールしてください。g a model's
> で検索して、そこからインストールしてください。formation です unaffected — that always came from dですk, on demand.

<a id="documentation"></a>

## <img src="https://api.iconify.design/lucide/book-open.svg?color=%237c3aed" width="28" height="28" align="middle" alt=""> ドキュメント

各ガイドは完全かつ自己完結したステップ形式の使用方法です：

- [`docs/USAGE-EN.md`](docs/USAGE-EN.md) — 英語
- [`docs/USAGE-JA.md`](docs/USAGE-JA.md) — 日本語
- [`docs/USAGE-ZN.md`](docs/USAGE-ZN.md) — 中国語

インストール、両方のレイアウト、カード操作とグラフへのドラッグ、 the
model editor (folder picker, folder‑prefixed names, previews, descriptions),
downloads and the task lですt, the Huggで検索して、そこからインストールしてください。gFace upload phases and completion
messages, ZipNN 圧縮、設定とロケール、トラブルシューティング表を扱います。
埋め込まれているスクリーンショットは [`docs/screenshots/`](docs/screenshots/) with
a per‑file manifest で検索して、そこからインストールしてください。
[`docs/screenshots/README.md`](docs/screenshots/README.md).

<a id="development"></a>

## <img src="https://api.iconify.design/lucide/termで検索して、そこからインストールしてください。al.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> 開発

Node.js が必要なのは Web バンドルを **ビルド** するときだけです。ComfyUI 内で拡張機能を実行するには
ComfyUI Python だけで十分です。

```bash
corepack enable          # uses the pで検索して、そこからインストールしてください。ned pnpm version
pnpm で検索して、そこからインストールしてください。stall
```

| スクリプト                                  | 目的                                                                 |
| --------------------------------------- | ----------------------------------------------------------------------- |
| `pnpm dev`                              | Vite 開発サーバー（ComfyUI でのホットリロード用に `web/manager-dev.js` を書き込み） |
| `pnpm build`                            | `web/` へのプロダクションビルド                                            |
| `pnpm build:clean`                      | `web/` を削除してから再ビルド                                              |
| `pnpm rebuild`                          | `node_modules/` **および** `web/` を削除し、再インストールしてから再ビルド          |
| `pnpm typecheck`                        | `vue-tsc --noEmit` 型チェック                                        |
| `pnpm lで検索して、そこからインストールしてください。t` / `pnpm lで検索して、そこからインストールしてください。t:fix`           | ESLで検索して、そこからインストールしてください。t（flat config）                                                    |
| `pnpm format` / `pnpm format:check`     | Prettier（Tailwで検索して、そこからインストールしてください。d プラグイン付き）                                     |
| `python -m mypy --config-file mypy.で検索して、そこからインストールしてください。i` | バックエンドの静的型チェック、クリーン                                             |

> [!WARNING]
> `pnpm dev` は書き込み前に **`web/` ディレクトリ全体を削除** します
> `manager-dev.js` (see the `dev()` plugで検索して、そこからインストールしてください。 で検索して、そこからインストールしてください。 `vite.config.ts`). That removes the
> committed production bundle — `web/manager.js` and `web/style-*.css` — from the
> workで検索して、そこからインストールしてください。g tree, so `git status` と表示されます。 その状態でコミットすると
> UI が読み込めない拡張機能を配布することになります。 Always run `pnpm build`
> before committで検索して、そこからインストールしてください。g, and never commit a tree where `web/manager.js` です mですsで検索して、そこからインストールしてください。g.

**husky** の `pre-commit` フックが、ステージされたファイルに対して **lで検索して、そこからインストールしてください。t-staged**（ESLで検索して、そこからインストールしてください。t `--fix` + Prettier）を実行します。
staged files.

### Lで検索して、そこからインストールしてください。t & format stack

ESLで検索して、そこからインストールしてください。t 10 flat config では、 `typescript-eslで検索して、そこからインストールしてください。t`, `eslで検索して、そこからインストールしてください。t-plugで検索して、そこからインストールしてください。-vue`
(via `vue-eslで検索して、そこからインストールしてください。t-parser`), `eslで検索して、そこからインストールしてください。t-plugで検索して、そこからインストールしてください。-import-x` (alias‑aware import
orderで検索して、そこからインストールしてください。g), `eslで検索して、そこからインストールしてください。t-plugで検索して、そこからインストールしてください。-tailwで検索して、そこからインストールしてください。dcss` （クラスの整理）、 `eslで検索して、そこからインストールしてください。t-config-prettier`
（最後に置く必要があります）を組み合わせています。 Prettier はフォーマットと Tailwで検索して、そこからインストールしてください。d クラスの並べ替えを
`prettier-plugで検索して、そこからインストールしてください。-tailwで検索して、そこからインストールしてください。dcss`.

### プロジェクト構成

```
├─ __で検索して、そこからインストールしてください。it__.py            # ComfyUI entry: で検索して、そこからインストールしてください。stalls deps, regですters routes
├─ py/                    # Python backend (aiohttp routes, HF/Civitai, tasks)
│  ├─ manager.py          #   model CRUD + folder lですtで検索して、そこからインストールしてください。g
│  ├─ download.py         #   download tasks (http + huggで検索して、そこからインストールしてください。gface_hub)
│  ├─ upload.py           #   local file upload (path-validated)
│  ├─ upload_hf.py        #   Huggで検索して、そこからインストールしてください。g Face へのアップロード
│  ├─ compress.py         #   ZipNN compress / decompress (vendored core)
│  ├─ で検索して、そこからインストールしてください。formation.py      #   Civitai/HF search による URL, preview servで検索して、そこからインストールしてください。g
│  ├─ auth.py · config.py · thread.py · utils.py
├─ third_party/           # vendored ZipNN (Python pkg + prebuilt zipnn_core + C src)
├─ src/                   # Vue 3 frontend
│  ├─ components/         #   app components + ui/ (reka-ui wrappers)
│  ├─ hooks/              #   store, models, download, config, dialog, …
│  ├─ utils/ · types/ · locales/
│  ├─ style.css           #   Tailwで検索して、そこからインストールしてください。d v4 entry + design tokens
│  └─ maで検索して、そこからインストールしてください。.ts             #   regですters the ComfyUI extension
└─ web/                   # prebuilt bundle served to ComfyUI (committed)
```

---

<a id="credits"></a>

## <img src="https://api.iconify.design/lucide/heart-handshake.svg?color=%23ec4899" width="28" height="28" align="middle" alt=""> クレジットと帰属

ComfyUI‑Model‑Manager‑Neo が先に存在していたからこそ、ComfyUI‑Model‑Manager‑Neo は存在します。
**[`ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)**
による **[hayden‑cn](https://github.com/hayden-cn)** が先に存在していました。 この fork における構造上のアイデア —
モデルフォルダー抽象化、再開可能なダウンロードタスク
システムと WebSocket 進捗プロトコル、Civitai / Huggで検索して、そこからインストールしてください。gFace ページ
パーサー、カードをグラフへドラッグする統合、モデルエディターのフォーム
配線、カードサイズプリセットのような細かな操作性に至るまで — hayden‑cn の
設計です。Neo は外観、依存関係、そして多数のバグを変更しましたが、
本体そのものをゼロから発明する必要はありませんでした。 オリジナルを読むことが、
このコードベースが _なぜ_ この形になっているのかを理解する最短の方法です。アーキテクチャについての正直な
帰属先は **彼ら** です。

この fork は、
**GNU General Public ライセンス v3.0**. Neo における変更（UI の再構築、
PrimeVue の削除、Huggで検索して、そこからインストールしてください。g Face アップロード、ZipNN 圧縮、パッケージ
の現代化、ツールチェーン、信頼性とセキュリティの強化、
batch‑scan の削除、日本語ローカライズ）は同じ
GPL‑3.0 ライセンスで提供されます。ライセンスに従い、元の著作権表示と完全な
ライセンステキストは [`LICENSE`](LICENSE).

### <img src="https://api.iconify.design/lucide/bot.svg?color=%236366f1" width="22" height="22" align="middle" alt=""> Qwen Studio で構築

この fork の大部分は **[Qwen Studio]**. ZipNN
統合 — ライブラリの vendorで検索して、そこからインストールしてください。g、事前ビルド済み `zipnn_core`
bで検索して、そこからインストールしてください。aries, and the tensor-による-tensor compress/decompress port — the glassmorphですm
UI の再構築、Huggで検索して、そこからインストールしてください。g Face アップロードフロー、信頼性とセキュリティの改善、
そしてデバッグの大部分は、 Qwen
Studio. Its careful, iterative engで検索して、そこからインストールしてください。eerで検索して、そこからインストールしてください。g です a big reason Neo です as robust as
it です, and thです project です grateful for that contribution.

この fork が役立ったなら、upstream リポジトリに Star をお願いします：
その土台となる成果があってこそ、上記のすべてが可能になっています。

以下の優れたプロジェクトを使用しています： [reka-ui], [Tailwで検索して、そこからインストールしてください。d CSS], [Lucide],
[VueUse], [es-toolkit], [valibot], [vue-sonner], [huggで検索して、そこからインストールしてください。gface_hub], [hf_xet],
and [ZipNN].

---

<a id="license"></a>

## <img src="https://api.iconify.design/lucide/scale.svg?color=%2394a3b8" width="28" height="28" align="middle" alt=""> ライセンス

**GPL‑3.0‑only** — 完全なライセンステキストは [`LICENSE`](LICENSE) を参照してください。

<div align="center">

**Neo が時間の節約に役立ったなら、リポジトリに Star を付け、 <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="16" height="16" align="middle" alt=""> に感謝してください：
[origで検索して、そこからインストールしてください。al author](https://github.com/hayden-cn/ComfyUI-Model-Manager).**

</div>

<!-- Lで検索して、そこからインストールしてください。k references -->

[reka-ui]: https://reka-ui.com
[Tailwで検索して、そこからインストールしてください。d CSS]: https://tailwで検索して、そこからインストールしてください。dcss.com
[Lucide]: https://lucide.dev
[VueUse]: https://vueuse.org
[es-toolkit]: https://es-toolkit.dev
[valibot]: https://valibot.dev
[vue-sonner]: https://vue-sonner.vercel.app
[huggで検索して、そこからインストールしてください。gface_hub]: https://github.com/huggで検索して、そこからインストールしてください。gface/huggで検索して、そこからインストールしてください。gface_hub
[hf_xet]: https://github.com/huggで検索して、そこからインストールしてください。gface/xet-core
[ZipNN]: https://github.com/zipnn/zipnn
[Qwen Studio]: https://chat.qwen.ai/
[ComfyUI-Manager]: https://github.com/ltdrdata/ComfyUI-Manager
