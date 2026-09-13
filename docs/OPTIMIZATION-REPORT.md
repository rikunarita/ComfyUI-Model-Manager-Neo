# 最適化精査報告 / Optimization audit (report only — no implementation)

対象: `rikunarita/ComfyUI-Model-Manager-Neo` @ `005a199`
方針: **実装せず、観測とコード読解に基づく報告のみ**。各項目に
「現状 / 問題 / 提案 / 期待効果 / リスク」を付す。優先度は ★(高)〜☆(低)。

検証に用いたもの: `pnpm typecheck` / `lint` / `format:check` / `build`、
`pnpm verify:py`(46) / `verify:e2e`(64)、実物 `huggingface_hub` 1.30.0 と
ローカル Hub エミュレータ、Playwright による実測
(`getComputedStyle` / `elementFromPoint` / ネットワーク計測)。

---

## A. バックエンド

### A-1 ★ プレビュー画像を毎回 PIL で再エンコードしている（最大級の無駄）

- 現状: `py/information.py::get_image_preview_data()` が
  `GET /model-manager/preview/{type}/{index}/{filename}` のたびに
  画像を開き、`thumbnail(1024)` + WebP 再エンコードを行う。
  アニメ GIF / 動画でない複数フレーム画像では**全フレームを毎回デコード**する。
  フラット表示の更新 = 全カードのプレビュー要求 = 全ファイルの再エンコード。
- 問題: CPU・ディスク I/O・レイテンシの三重の無駄。同一バイト列に対して
  応答が毎回変わるため HTTP キャッシュも効かない（ETag / Last-Modified 未送出）。
- 提案:
  1. `(realpath, st_mtime_ns, st_size)` をキーにしたプロセス内 LRU に
     エンコード済みバイト列を保持（上限例: 64 件 / 256 MB）。
  2. 応答に `ETag`（キーのハッシュ）と `Cache-Control: private, max-age=0,
must-revalidate` を付け、`If-None-Match` で 304 を返す。
     ブラウザ側の 2 回目以降はネットワーク往復のみになる。
  3. 動画は `web.FileResponse` のため既にストリーミング配信だが、こちらも
     `ETag` 相当（mtime+size）を付けると再読込が減る。
- 期待効果: 1000 モデルのライブラリ更新でエンコード回数が実質 1/N に。
- リスク: メモリ上限を誤ると肥大化。鍵に mtime を入れるため陳腐化しない。

### A-2 ★ モデル一覧走査が 1 ファイルあたり最大 16 回の `stat` を叩く

- 現状: `py/manager.py::scan_models` → `get_file_info` →
  `utils.get_model_preview_name(entry.path)` が `PREVIEW_EXTENSIONS`
  (8 種) × (`basename.ext` / `basename.preview.ext`) = **16 回の
  `os.path.isfile`** を全モデルファイルに対して実行する。
  `ThreadPoolExecutor(max_workers=4)` で並列化済みだが、I/O 回数は減らない。
- 問題: 1000 ファイルで 1.6 万回の `stat`。NFS / SMB / WSL2 越しでは顕著。
- 提案: ディレクトリごとに `os.scandir` 1 回で名前集合を作り、
  存在判定を集合照合に置き換える（`_check_preview_variants` を
  名前集合版に差し替えるだけで意味は不変）。
- 期待効果: `stat` 回数が O(ファイル数×16) → O(ディレクトリ数)。
- リスク: ほぼ無（同名判定の意味は同一）。シンボリックリンクの扱いだけ再確認。

### A-3 ★ `resolve_model_base_paths()` をリクエストごとに再構築している

- 現状: `utils.get_full_path` / `upload.resolve_model_folder` /
  `information._resolve_model_type` などが呼ぶたびに
  `folder_paths.folder_names_and_paths` を走査して辞書と正規化パスを再構築。
- 問題: 値は ComfyUI 起動中ほぼ不変。プレビュー要求・アップロード検証・
  検索のたびに無駄な走査と文字列生成が発生。
- 提案: 結果をモジュールキャッシュし、(a) 明示的な無効化 API、または
  (b) `folder_paths.folder_names_and_paths` の `id()`/ハッシュ変化時のみ
  再構築。ComfyUI はフォルダ設定変更時にプロセス再起動を前提とするため
  単純キャッシュでも実害は無い。
- 期待効果: リクエストあたりの固定コスト削減。
- リスク: 低。動的に `folder_names_and_paths` を書き換える拡張との併用時のみ注意。

### A-4 ☆ 同期 `requests` + 既定エグゼキュータの共有

- 現状: ダウンロード(`download_model_file_http`)・HF 転送・プレビュー
  エンコード・モデル一覧走査がすべて `loop.run_in_executor(None, …)`
  = **同一の既定スレッドプール**を共有。
- 問題: 大規模ライブラリの更新（A-1/A-2 の重い処理）がプールを占有すると、
  ダウンロードの進捗プッシュや HF 転送がスレッド待ちで遅延する。
- 提案: 用途別にエグゼキュータを分離（`_IO_POOL` / `_CPU_POOL`）、
  またはダウンロードを `aiohttp` ストリームへ書き換えてスレッド自体を廃止
  （下記 A-5）。
- 期待効果: 相互干渉の排除、キャンセル応答性の向上。
- リスク: 中（並列度設計が必要）。

### A-5 ☆ ダウンロードを `aiohttp` の非同期ストリームへ

- 現状: `requests.get(stream=True)` + `iter_content` をワーカースレッドで回し、
  進捗は `run_coroutine_threadsafe` でメインループへ戻す。
- 問題: スレッド・ロック・キャンセル伝播（`CancelledError` がスレッドに
  届かないため `task_status.status == "pause"` をポーリング）という
  複雑さがすべて同期 I/O に起因する。過去パスのコメントにも
  「レスポンスをスレッド内で閉じる」等の対処が積み上がっている。
- 提案: `aiohttp.ClientSession.get` + `content.iter_chunked` へ置換すると、
  一時停止/削除が `await` 点での自然なキャンセルになり、ポーリングと
  スレッド境界が消える。レジュームの `Range` 処理はそのまま移植可能。
- 期待効果: コード量と障害面の削減、メモリ効率（チャンク単位）、
  同時ダウンロード数の上限緩和。
- リスク: 高（挙動互換の作り込みが必要）。**本パスでは触らない判断**。

### A-6 ★ `private.key` が pickle である（セキュリティ寄りの最適化）

- 現状: `py/auth.py` が API キーを `pickle` で永続化。
- 問題: pickle は読み込み時に任意コード実行が可能。`private.key` は
  拡張ディレクトリ（ユーザーが書き込み得る場所）にあり、gitignore 済みとはいえ
  共有マシンでは危険面になる。
- 提案: JSON（+ 可能なら 0600 パーミッション）へ移行し、初回読み込み時に
  pickle を JSON へ自動移行（キーは既にマスク表示のみ）。
- 期待効果: 攻撃面の除去。移行コスト小。
- リスク: 低（移行パスを一枚挟むだけ）。

### A-7 ☆ ローカルアップロードが ComfyUI の `client_max_size` に依存

- 現状: `POST /model-manager/upload` は multipart をそのまま受ける。
  上限は ComfyUI 本体の `web.Application(client_max_size=max_upload_size)`
  （既定 100 MB、`--max-upload-size` で変更可）[1][2]。
- 問題: 既定を超えるモデル（近年のチェックポイントは 5–20 GB）は
  413 で失敗する。UI 側には事前検査も分かりやすいメッセージも無い。
- 提案: (a) 413 を検出して「ComfyUI の `--max-upload-size` を確認」という
  ガイド付きトーストを出す（最小修正）、(b) クライアントでチャンク分割して
  追記書き込みするアップロードプロトコルへ（本格修正）。
- 期待効果: 失敗時の自己説明性、または上限自体の撤廃。
- リスク: (b) は中。

### A-8 ☆ HF アップロードのハッシュ pass が既定プールを長時間占有

- 現状: 第 9 回パスでハッシュを `hash` フェーズとして可視化済み。
  実行は `run_in_executor(None, …)` = 既定プール（A-4 と同じ問題）。
- 提案: ハッシュ専用エグゼキュータ（1–2 スレッド）に分離し、
  進捗スロットル（0.4 s）は維持。
- 期待効果: 数 GB モデルのハッシュ中に他処理が stalls しない。
- リスク: 低。

### A-9 ☆ `DownloadThreadPool` の bookkeeping

- 現状: `running_tasks` (set) と `_tasks` (dict) の二重管理、`_lock` は
  `finally` 内でのみ使用。`submit` の重複ガードは動作する。
- 提案: `asyncio.Task` の dict 一本にし、`task.done()` で判定。
  `cancel()` も同じ dict を参照するだけになる。
- 期待効果: 状態不整合の可能性減、コード減。
- リスク: 低（外部からは `submit/cancel` のみ使用）。

---

## B. フロントエンド

### B-1 ★ モデルカードごとに `ResizeObserver` を生成している

- 現状: `ModelCard.vue` が `useElementSize(container)` を使う（バッジの
  スケール計算のため）。カード数 = Observer 数。
- 問題: 数百〜数千カードで Observer と reactive 更新が大量にぶら下がる。
  仮想スクロール（`ResponseScroll`）で DOM 上の数は絞られているが、
  行単位で生成/破棄を繰り返す。
- 提案: バッジスケールはカード幅 = 親が指定する `width` px から決定的に
  導ける（`cardSize.width`）。`useElementSize` を廃し、props から
  `scale = width / 200` を計算するだけで同等。
- 期待効果: Observer 全滅、スクロール時の GC 圧低下。
- リスク: ほぼ無（幅は親が制御している）。

### B-2 ★ ガラスフォルダ SVG をカードごとに data URI で複製している

- 現状: `FolderIcon.vue` が 4 種の SVG（8.3 KB / 8.3 KB / 17.2 KB /
  17.4 KB）を `?raw` でバンドルし、状態切り替えのたびに
  `data:image/svg+xml` を `<img src>` に設定。フォルダカードごとに
  文字列が DOM 属性として複製される。
- 問題: フォルダが多いライブラリで DOM サイズとメモリが増える。
  加えて data URI は `encodeURIComponent` 済みで実サイズの約 1.3 倍。
- 提案: (a) 拡張ルートから静的配信（`/model-manager/assets/...`）して
  URL を共有（ブラウザが 1 回だけデコード）、(b) SMIL を CSS アニメに
  置き換えて単一 `<svg>` + `<use>`、(c) 状態数を 2 に減らす。
  (a) が最小変更で、第 6 回パスの「全カードが自前の SVG 文書を持つ」
  設計意図（gradient id 衝突回避）も `<img>` 越しなら維持される。
- 期待効果: DOM/メモリ削減、初回描画短縮。
- リスク: 低（`<img>` 経由なら隔離は保たれる）。

### B-3 ☆ 検索・並び替えがキー入力ごとに全件走査

- 現状: `DialogManager.list` / `DialogExplorer.currentDataList` が
  `Object.values(data).flat()` → filter → sort を computed で再計算。
  `ResponseInput` の既定トリガは `change`（blur / Enter）なので連打は
  起きないが、`update-trigger="input"` に変えた瞬間に O(n log n)/キーになる。
- 提案: 入力側を 150 ms デバウンス、または `sort` 結果を
  (key, direction) でメモ化。
- 期待効果: 大ライブラリでの入力応答性。
- リスク: 低。

### B-4 ☆ `PreviewVideo` が全ソースを mp4/webm 二重宣言している

- 現状: `<source :src="src" type="video/mp4">` と
  `<source :src="src" type="video/webm">` の 2 行に**同一 URL**。
- 問題: `.webm` を渡すと 1 番目が MIME 不一致で失敗してから 2 番目に
  落ちる（余分なエラーイベントとコンソールノイズの温床）。
  `.mov` 等は両方不一致で結局 type 推定に頼る。
- 提案: URL の拡張子から `type` を 1 つ決めて 1 行にする
  （`utils/media.ts` に `videoMimeType(url)` を追加）。
- 期待効果: 無駄なソース解決とエラーイベントの除去。
- リスク: 無。

### B-5 ☆ ロケール JSON を 3 言語ぶん丸ごとバンドルしている

- 現状: `src/i18n.ts` が en/zh/ja を静的 import（各 ~10 KB 未圧縮）。
- 提案: `import(`./locales/${locale}.json`)` で遅延読込し、
  起動時は ComfyUI のロケール 1 言語のみ。
- 期待効果: バンドル ~20 KB 減（914 KB 中では小）。
- ロード順の都合で初回描画前に 1 fetch 増えるため、**現状維持も妥当**。
- リスク: 低〜中（FOUC 対策が必要）。

### B-6 ☆ 単一 914 KB チャンク（意図的な設計）

- 現状: `vite.config.ts` が `entryFileNames: 'manager.js'` の 1 チャンク。
- 評価: ComfyUI は `WEB_DIRECTORY` の JS を 1 ファイルとして注入するため
  **分割はできない**。gzip 269 KB は許容範囲。分割の余地は無い旨を明記。

### B-7 ☆ `tw-animate-css` を丸ごと import

- 現状: `style.css` が `@import 'tw-animate-css'`。
- 問題: 使用しているのは `animate-in/out`・`fade-*`・`zoom-*`・`slide-*` の一部。
- 提案: 使用するユーティリティだけを `@utility` で自前定義（既に
  `mm-indeterminate` がある）。
- 期待効果: CSS ~2–4 KB 減。
- リスク: 低（利用箇所の列挙が必要）。

### B-8 ☆ `DialogHfUpload` が種別選択のたびに一覧を取得

- 現状: `fetchModels(type)` が毎回 `GET /models/{type}`。
- 提案: `useModels().data` のキャッシュを参照し、無い時だけ取得
  （`models.refresh(folder)` は既に store 側にある）。
- 期待効果: 往復 1 回減、ダイアログ再開が即時。
- リスク: 低（鮮度はヘッダーの更新ボタンで担保済み）。

---

## C. 最新標準への追従

| #   | 現状                                                                 | 提案                                                                                                 | 備考                                                                  |
| --- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| C-1 | `huggingface_hub>=0.34.0,<1.31.0`（1.30.0 に解決）を**起動時に強制** | 1.31 系の `SliceFileObj.__iter__` 変更と `hf` CLI の version-pairing を検証した上で上限を解放        | 第 7 回パスで意図的に固定済み。**理由付きの固定**なので闇雲に上げない |
| C-2 | `loop.run_in_executor(None, …)` を多用                               | Python 3.9+ の慣用である `asyncio.to_thread(…)` へ                                                   | 純粋に見た目と取消し可能性の改善                                      |
| C-3 | `py` 側に型注釈が一部のみ                                            | `py.typed` 相当の注釈整備と `mypy --strict` の段階導入                                               | CI に載せるのは全関数注釈後                                           |
| C-4 | ESLint 10 / TS 6 / Vite 8 / vue-i18n 11                              | 既に最新メジャー。`typescript-eslint` の `projectService` 移行を検討                                 | type-aware ルールが高速化                                             |
| C-5 | `NodeJS.Timeout` 型を使用                                            | Web 標準の `ReturnType<typeof setTimeout>` / `number` へ                                             | `@types/node` 依存を UI 側から排除                                    |
| C-6 | `husky` + `lint-staged` あり                                         | `pre-commit` に `pnpm typecheck` も追加（現在は lint+format のみ）                                   | 型 regress を push 前に遮断                                           |
| C-7 | CI が無い                                                            | GitHub Actions で `typecheck / lint / format:check / build / verify:py / verify:e2e` を矩阵実行      | harness は自己完結しているのでそのまま走る                            |
| C-8 | `tsconfig` に `sourceMap: true`（typecheck のみ使用）                | `vue-tsc --noEmit` では不要。削除で僅かに高速化                                                      | 影響無                                                                |
| C-9 | アクシビリティ                                                       | 玻璃面の `--mm-muted-fg` コントラスト比を WCAG AA で監査、フォーカスリングの可視化を全操作要素で統一 | 色はホスト変数依存のためホストテーマ別の監査が必要                    |

---

## D. 見送ったもの（理由の明記）

- **ダウンロードの aiohttp 化 (A-5)**: 挙動互換（レジューム、一時停止の
  セマンティクス、進捗頻度）の作り込みが大きく、現行は検証で固まっている。
- **バンドル分割 (B-6)**: ComfyUI の注入方式上不可能。
- **xet 経路での進捗取得**: `hf_xet` は Python 側へチャンクコールバックを
  公開していない。ファイルオブジェクト渡し（= 正確な進捗）と xet の
  二者択一は**設計上のトレードオフ**として維持（README 第 5 回パス記載）。
- **ロケール遅延読込 (B-5)**: 効果が 20 KB に対し FOUC リスクを負う。

---

## 参考文献

[1] Comfy-Org/ComfyUI `server.py` — `web.Application(client_max_size=max_upload_size, …)`
https://github.com/Comfy-Org/ComfyUI/blob/master/server.py
[2] ComfyUI CLI `--max-upload-size`（MB 単位、既定 100）
https://docs.comfy.org/development/comfyui-server/comms_overview
