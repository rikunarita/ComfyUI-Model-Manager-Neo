# 仕様確認回答 / Specification Q&A

対象: `rikunarita/ComfyUI-Model-Manager-Neo` @ `005a199`
すべて実コード（`src/App.vue`・`src/main.ts`・`src/hooks/config.ts`・
`src/hooks/model.ts`・`py/auth.py`・`py/information.py`・`py/utils.py`）に
基づいて回答します。

---

## Q1. ComfyUI 本体トップバーの「Model Manager Neo」ボタンのカスタマイズ可能範囲

ボタンは **3 つの姿**で登録され、それぞれ出自が違います。

| 姿                             | 登録コード    | 内容                                                                                                                                                                                                                             |
| ------------------------------ | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| トップバーの `ComfyButton`     | `src/App.vue` | `new ComfyButton({ icon: 'folder-search', tooltip: t('openModelManager'), content: t('modelManager'), action: openManagerDialog })` を `app.menu.settingsGroup.element` の**直前**に挿入（無ければ `insert()` にフォールバック） |
| コマンド / Extensions メニュー | `src/main.ts` | `commands: [{ id: 'Comfy.ModelManager.Open', label: 'Model Manager Neo', icon: 'pi pi-folder', function }]` + `menuCommands: [{ path: ['Extensions'], … }]`                                                                      |
| レガシーメニューの `<button>`  | `src/App.vue` | `$el('button', { id: 'comfyui-model-manager-button', textContent: t('modelManager'), onclick })` を `app.ui.menuContainer` に追記                                                                                                |

### 設定画面から変えられるもの

**ありません。** 本拡張はボタンに関する `app.ui.settings.addSetting(...)` を
一切登録していないため、ComfyUI の Settings にボタン用の項目は存在しません。
（登録済みの設定は `ModelManager.APIKey.*` / `ModelManager.UI.*` /
`ModelManager.Scan.*` のみ。→ Q3）

### 言語（ロケール）で変えられるもの

ラベルとツールチップは i18n キー経由です。

- `content`（ボタン文字）= `t('modelManager')`
- `tooltip` = `t('openModelManager')`
- レガシーボタンの `textContent` と、開いたウィンドウの**タイトル**も同じキー

したがって ComfyUI のロケールを切り替える（または
`src/locales/*.json` を編集する）だけで、トップバー文字・ツールチップ・
レガシーボタン・ウィンドウタイトルが同時に追随します。
これが**ノーコードで触れる唯一の範囲**です。

### ソース編集で変えられるもの

| 対象                                        | 場所                                                    | 備考                                                  |
| ------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------- |
| アイコン名 `'folder-search'`                | `src/App.vue`                                           | ComfyUI の `ComfyButton` が解決できるアイコン名に限る |
| コマンドの `label` / `icon: 'pi pi-folder'` | `src/main.ts`                                           | `icon` は ComfyUI 本体のアイコン表記                  |
| メニュー配置 `path: ['Extensions']`         | `src/main.ts`                                           | 例: `['Tools']` 等へ変更可                            |
| 挿入位置（settings グループの前）           | `src/App.vue`                                           | `menuContainer` 等へ変更可能                          |
| コマンド ID `Comfy.ModelManager.Open`       | `src/main.ts`                                           | 変更すると既存キーバインド/参照が切れる               |
| ウィンドウの初期/最小サイズ                 | `src/App.vue` の `dialog.open({ minWidth, minHeight })` | カードサイズ設定に連動して計算                        |
| 動作（`openManagerDialog`）                 | `src/App.vue`                                           | 開く処理そのもの                                      |

### できないもの

- ComfyUI 側 UI からの非表示化・並び替え（本体が拡張ボタン個別の
  トグルを持たないため）。
- ボタン単位のテーマ/色指定（ComfyUI のトップバー样式に全面従属）。

---

## Q2. HuggingFace / Civitai の API キー管理方法

実装は `py/auth.py::ApiKey`（シングルトン）+ `src/hooks/config.ts`
（設定 UI）+ `src/components/SettingApiKey.vue`（入力ダイアログ）。

### 保存場所と形式

- **`<拡張ディレクトリ>/private.key`** に pickle 辞書
  `{"civitai": …, "huggingface": …}` として保存。
  `.gitignore` 済み（第 2 回パスで `private.keypackage-lock.json` という
  連結ミスを修正して確実に ignore されるようにした）。
- UI には**マスク表示**（`先頭4文字 + "****" + 末尾4文字`）のみを出す。
- 設定/削除は `POST /model-manager/download/setting`
  （値は base64、`value: null` で削除）。

### 解決優先順位（`get_value`）

1. `private.key` の値
2. 環境変数 — HuggingFace: **`HF_TOKEN`**、Civitai: **`CIVITAI_API_KEY`**
3. `None`

環境変数は「保存値が無いとき」のフォールバックであり、保存値を決して
上書きしません。

### 初回移行

`POST /model-manager/download/init`（起動直後に `useDownload` が呼ぶ）で
`ApiKey.init(request)` が走り、**旧バージョンが ComfyUI のユーザー設定に
保存していたキー**（`ModelManager.APIKey.Civitai` /
`ModelManager.APIKey.HuggingFace`）を `private.key` へ移し、元の設定は
`null` にして消します。移行が 401 等で失敗しても空状態で開始します。

### UI からの操作経路（2系統）

1. **ComfyUI Settings → Model Manager Neo → API Key** の各行
   （鉛筆 = 入力ダイアログ、ゴミ箱 = 確認付き削除）。
   この 2 つのアイコンは ComfyUI 本体の DOM に Vue の `render()` で
   差し込む Lucide アイコンです（PrimeVue 除去後も見えるよう第 3 回パスで修正）。
2. 同ダイアログ（`SettingApiKey.vue`）— 空値は拒否。

### 使用箇所

- HuggingFace: `hf/whoami`・`hf/upload`・HF ダウンロードの
  `Authorization: Bearer …`・HF 検索ヘッダ。
- Civitai: Civitai 検索とダウンロードの `Authorization: Bearer …`。

> 注意: `private.key` は**暗号化されていない**_pickle_ です。
> 共有マシンでは `docs/OPTIMIZATION-REPORT.md` A-6 の JSON 化を推奨します。

---

## Q3. ComfyUI フロントエンド設定の「Model List」「UI」セクション全項目

登録は `src/hooks/config.ts::useAddConfigSettings`。カテゴリは
`[t('modelManager'), <セクション名>, <項目名>]` の 3 段で、ComfyUI の
Settings ダイアログに **Model Manager Neo → Model List / UI / API Key**
の 3 セクションとして現れます。

### Model List セクション（2 項目）

| 設定 ID                                | 型      | 既定    | 表示名（en / ja）                                                                           | 効果                                                                                                                                                                   |
| -------------------------------------- | ------- | ------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ModelManager.Scan.excludeScanTypes`   | text    | 未設定  | _Exclude model types (separate with commas)_ / _一覧から除外するモデル種別（カンマ区切り）_ | カンマ区切りで指定したモデル種別を**フラット/フォルダ両グリッドと各種ピッカーから除外**。`DialogManager` / `DialogExplorer` / `DialogUpload` / `DialogHfUpload` が読取 |
| `ModelManager.Scan.IncludeHiddenFiles` | boolean | `false` | _Include hidden files (start with .)_ / _隠しファイル（. で始まる名前）を含める_            | 名前が `.` で始まるファイル/フォルダを一覧に含める。ツールバーの**目アイコンと双方向で同期**（どちらを変えても他方が追随）                                             |

> **ID が `Scan.*` のままなのは意図**です。この ID 文字列は ComfyUI が
> ユーザー値を永続化するキーであり、バッチスキャン機能削除時に改名すると
> 既存環境の設定が孤児になるため、第 1 回パスで**固定することを明言**し、
> harness で 7 個の ID 全部を pin しています（表示名とカテゴリ名は
> `Model List` へ改名済み）。

### UI セクション（3 項目）

| 設定 ID                       | 型      | 既定                                                          | 表示名        | 効果                                                                                                                                                                                      |
| ----------------------------- | ------- | ------------------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ModelManager.UI.CardSize`    | hidden  | `'size.extraLarge'`                                           | _Card Size_   | カードサイズ選択（Extra Large / Large / Medium / Small / Custom）の**永続化用**。Settings 上は非表示で、マネージャーのサイズドロップダウンが書き込み、`onChange` が `cardSizeFlag` へ反映 |
| `ModelManager.UI.CardSizeMap` | hidden  | 4 プリセットの JSON（`240x320 / 180x240 / 120x160 / 80x120`） | _Card Size_   | **Custom Size ダイアログ**で編集した幅/高さマップの JSON 永続化。`onChange` がパースして `cardSizeMap` へ反映                                                                             |
| `ModelManager.UI.Flat`        | boolean | `true`                                                        | _Flat Layout_ | 起動時の既定レイアウト（`true` = フラット表示、`false` = フォルダ表示）。変更すると開いているウィンドウを閉じてレイアウトを切り替える。ヘッダーの切替ボタンもこの値を書く                 |

### 参考: API Key セクション（2 項目・カスタム描画）

| 設定 ID                           | 型              | 効果                                   |
| --------------------------------- | --------------- | -------------------------------------- |
| `ModelManager.APIKey.HuggingFace` | カスタム render | マスク表示 + 編集/削除アイコン（→ Q2） |
| `ModelManager.APIKey.Civitai`     | カスタム render | 同上                                   |

---

## Q4. プレビュー画像の取得方法と「1 つしか表示されないが全部保存されるのか」

### 取得経路（3 段階）

1. **検索時（メタデータとして）**
   - Civitai: `GET civitai.com/api/v1/models/{id}` の
     `modelVersions[].images[].url` を**全部**集め、
     (a) `model.preview`（URL 配列）として返し、かつ
     (b) 説明 Markdown の **YAML フロントマター** `preview: [ … ]` にも埋めます
     （`py/information.py::CivitaiModelSearcher`）。
   - HuggingFace: リポジトリツリー（`recursive=true`）から画像拡張子のファイルを
     拾い、`resolve` URL 化して同様に配列とフロントマターへ入れます。
   - この段階では**まだ何も保存していません**。作成ダウンロードタスクの
     エディタのカルーセルが回るのはこの配列です。

2. **ダウンロード時（実際に保存されるのは 1 枚だけ）**
   - フロントが `previewUrlToFile(preview)` で**現在選択中の 1 枚**を
     ブラウザで fetch し、`FormData` の `previewFile` として送信
     （CORS 等で失敗した場合は URL 文字列のまま送り、サーバ側で再取得）。
   - バックエンド `utils.save_model_preview()` が
     画像 → **PIL で WebP へ変換**、動画 → 元の形式のまま、
     `<basename>.<ext>`（または `.preview.<ext>`）として**1 ファイルだけ**
     モデルの隣に書きます。以降の取得は
     `GET /model-manager/preview/{type}/{index}/{filename}` が
     実ファイルを配信します（フォールバック連鎖は第 6 回パスで廃止、
     無ければ 404 / 一覧側は `NO-PREVIEW.svg` を直接参照）。

3. **手動設定時**
   - モデル編集の Preview で `Network`（URL）/ `Local`（ドラッグ&ドロップ）を
     選ぶと同じ `save_model_preview()` 経路で 1 ファイルに上書きされます。
     `None` はプレビューファイルを**全て削除**します。

### 「全部保存されるのか」→ **されません**

- ディスクに残るのは**常時 1 ファイル**です
  （`get_model_preview_name()` は拡張子優先順で最初に見つかった 1 つを返す）。
- 残りの URL は**説明 Markdown の YAML フロントマター内の文字列**としてのみ
  生存します（`metadata_block` でパースされ、本文からは隠れます）。
  つまり「全部」は*テキストとして*残るが*画像ファイルとしては*残らない、
  が正確な答えです。
- 例外として、ユーザーが手動で `<basename>.preview.webp` 等の別名ファイルを
  置いた場合は `_check_preview_variants()` が認識し、
  `get_model_all_previews()` が列挙します。ただしモデル一覧が返す
  `preview` は単一 URL 文字列のため、**カルーセル（前/次ボタン）が回るの
  は検索直後のエディタ（配列を持っている状態）に限られます**。

### 補足（配信側の最適化余地）

プレビュー要求のたびに PIL で再エンコードしているため、
キャッシュ/ETag 導入の余地があります
（`docs/OPTIMIZATION-REPORT.md` A-1）。
