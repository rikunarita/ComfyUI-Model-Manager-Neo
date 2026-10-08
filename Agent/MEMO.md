# 開発メモ — ComfyUI‑Model‑Manager‑Neo

> **この文書の目的と位置づけ。** 本ファイルは本リポジトリの開発記録です。
> 2026 年 9 月から 10 月にかけて策定・完了した 3 つの計画
> （Plan.md・Plan-2.md・Plan-3.md — NEO‑PLAN‑2026‑001/002/003）で
> 何を実施し、何が達成されたかを一望できるように要約し、あわせて今後の開発に
> 必要な恒久規程・技術知見・残件を収録します。計測証跡の一次ソースは
> [`../docs/BENCH.md`](../docs/BENCH.md)、開発環境の実測一次ソースは
> [`environment-report.md`](environment-report.md) です。
>
> **計画文書の保存場所。** 4 つの計画書は全実装要件の完了に伴いツリーから
> 削除されました。原文は git 履歴に完全な形で保存されており、
> `git show eb3a317:Agent/Plan.md`（同様に `Agent/Plan-2.md`・
> `Agent/Plan-3.md`。Plan‑4.md は最終形が `git show dcd5624:Agent/Plan-4.md`）
> で復元できます。本メモ内の「Plan §x.y」「Plan‑2 / Plan‑3 /
> Plan‑4」「NEO‑PLAN‑2026‑00N」形式の参照は、これらの履歴文書の節を
> 指します。
>
> **旧記録の参照について。** コード・CI・文書中の「第 N セッション」
> 「MEMO 2026‑XX‑XX」という参照は、git 履歴に保存されている旧開発メモ
> （30 セッション分の逐語記録 — `git show 88b5e9c:Agent/MEMO.md`）を指します。
> 本ファイルはその全面改写版です。
>
> **フェーズ番号について。** 2026‑09‑28 の計画改訂（Plan 版数履歴 2.1）により、
> それ以前の記録にある「Phase 7」（third_party 撤去・USAGE 改訂・リリース準備）は
> 現在の **Phase 8** を指します。

---

## 1. 恒久規程とユーザ決定

### 1.1 ユーザ決定（現在も有効）

- **リリース公開はユーザ専任**: GitHub Release の作成・タグの publish・
  registry への公開・`main` へのマージ PR はユーザが実施します。セッションが
  担うのはバージョン同期コミットと公開前検証（K16 スモーク）までです。
- **圧縮率は速度より優先**: bf16 で 67 % を下回らないという要件に対し、
  C 実装との出力バイト同一による構造的保証で回答しました
  （bf16 実測 0.6623 — BENCH §6.3）。
- **`unsafe` は可能な限り用いない**: フォーマットコアは `unsafe` ゼロで
  目標を達成しました（唯一の例外は安全性レビュー済みの読み取り専用 mmap
  境界 — native/README 参照）。
- **上流 zipnn への issue は起票しない**: C コアのメモリ安全欠陥は Neo 実装内で
  完全に修正し、回帰テストで固定することで担保します（証跡は BENCH §6.4）。
- **バイナリサイズは目安で管理**: 1 本 ≤5 MB（fat binary は per‑slice ≤5 MB・
  ファイル ≤10 MB）、8 本合計 ≤40 MB（Plan‑3 D1 — 超過は warning のみで
  run はブロックしません）。CI のサイズゲートは早期警戒装置として維持し、
  目安超過時はユーザ判断で上限を改定する運用です。
- **HTTP 層は Rust 化しない**: reqwest / axum / utoipa は不採用
  （実測根拠は §4.3）。
- **extended‑notify は導入しない**: notify + debouncer‑full を直接採用
  （根拠は §4.3）。
- **ユーザ環境でのネイティブコア自動ビルドは行わない**: 「セットアップ時に
  コンパイラもネットワークも要求しない」という配布方針を貫き、非対応
  プラットフォームでは理由を明示してデグレードします。手動ビルド手順は
  native/README.md に文書化済みです（Plan‑3 §5 に回答記録）。
- **`demo-assets/` はユーザ管理領域**: セッションは変更しません。
- **CI 実行結果の確認**: ユーザが指示したときにセッションが実施します。
- **フォルダアイコンはスパークル無し**（2026‑10‑05・実機 QA 決定）: アイコン
  刷新と同時に導入したスパークル版ホバーアートワークは「UI 品質を損ねる」の
  実機指摘を受け同日撤去。ホバー表現は CSS フロートのみとします。

### 1.2 開発ワークフロー規程

- **cargo 使用方針**: `check` を常用し、`test` は必要なときだけ、
  clippy / rustfmt を品質向上に活用し、`build` は最終確認のみにします。
- **Rust テスト配置**: 単体 = インライン `#[cfg(test)]`（private 到達可）、
  統合 = `native/crates/znn-codec/tests/`（公開 API のみ）、敵対的 = `fuzz/`。
  差分テスト（旧 `scripts/l2`）は Phase 8 で退役し、L5 公式クロス検証が
  恒久ゲートです。
- **push 前検証は「native 成果物あり」と「なし」の両方で pytest を実行**:
  ci.yml = なし、native.yml = あり。「なし」の再現は
  `mv native/native-bin/<tag>/mm_core.abi3.so /tmp/`。
- **native.yml で pytest を実行する複数ジョブの pip 依存行は同一内容に保つ**:
  削除も同規程で、「削除 → 当該 CI セルでの実行成功確認」までを 1 単位とし、
  テスト側にも明示的な `importorskip` ガードを置きます。実行時の深い所で
  走る推移的 import は、tests の直接 import を grep しても見つかりません
  （前例: safetensors.torch の save_file 経路が numpy を要求）。
- **`api_version` の bump は 4 者同期**: `py/native.py` の `[N, N]` /
  mm‑core `lib.rs` の定数 + テスト / native.yml の abi3‑import アサート /
  pytest のアサート。
- **ベンチ証跡 JSON（`scripts/bench/results/`）は再生成しない**: BENCH 本文が
  参照機の実測値を逐語引用しています。ゲート追加時は決定的な欄のみ
  外科的に追記します（前例: `phase6_front.json` の `rowsParity` /
  `tensorTreeRowsIdentical`）。
- **テストは mutation testing で捕捉力まで証明する**: 対応する回帰を
  意図的に混ぜて失敗、復元して成功、までを確認します。両端が個別に
  テスト済みでも接続部が無テストの「接合部」型ギャップが繰り返しの
  発生源です（§4.5）。
- **fallow（dead‑code + dupes）は CI ゲート**: push 前に
  `pnpm fallow:dead` + `pnpm fallow:dupes`。export を削除するときは
  戻り型・注釈型も併せて private 化すると clean です
  （型を残すと連鎖で unused‑types 警告に落ちます）。
- **fuzz‑long の再ディスパッチはファズ表面が変わったときだけ**: 表面不変なら
  既存 run の証跡と週次スケジュール（日曜 18:00 UTC・7 ターゲット）が
  担保します。PAT からの `workflow_dispatch` はかつて 403（Actions 権限不足）
  だったが、2026‑10‑07 に当日発行 PAT からの dev への dispatch（hours=1・
  run 37572923805）が成功（204）= 成否はトークンの Actions 権限次第。
  成功すればセッション自身がディスパッチして CI 検証まで完結でき、403 の
  場合は従来どおり GitHub UI からユーザへ依頼します。
- **GitHub Actions の更新は 1 action ずつ別コミット**（bisect 可能にするため）。
- **コミット前に必ず `pnpm build` を実行する**: `pnpm dev` は
  `web/manager-dev.js` を書き出す前に **`web/` ディレクトリ全体を削除する**
  （`vite.config.ts` の `dev()` プラグイン）。コミット済みの本番バンドル
  （`web/manager.js` / `web/style-*.css`）がワークツリーから消え、
  `git status` に削除として出るため、その状態でコミットすると UI が
  読み込めない拡張機能を出荷することになります。`web/manager.js` が
  欠けたツリーは絶対にコミットしません。
- **コミットは日本語の conventional commits**（`type(scope): 概要` + 詳細本文）。
  pre‑commit フック = lint‑staged + `pnpm typecheck`。環境リセットで pnpm shim が
  消えた場合は `corepack enable --install-directory /usr/local/bin`
  （さもないとフックが `pnpm: not found` でコミットを落とします）。
- **`core` ダンプをコミットに含めない**（.gitignore 対象外のため
  `git status` で確認）。`native-bin/` の `.so` / `.pyd` は gitignore 対象
  （main / tag で CI が生成し、publish bot のみが force‑add します）。
- **セキュリティゲートの運用（2026‑10‑07・NEO‑PLAN‑2026‑004）**: 5 層体制 =
  CodeQL default setup（Extended・ユーザ設定側）+ security.yml（OSV‑Scanner
  PR 差分/定期フル・zizmor GHAS モード・gitleaks）。ignore/accept は必ず
  **理由付き設定ファイル**（osv‑scanner.toml ×2 / .github/zizmor.yml /
  .gitleaks.toml）に記録し、無記録の抑止を禁止する。zizmor.yml の
  cache‑poisoning 行単位 ignore は**意図的に壊れやすい**（行ずれで検出が
  復活 = 再レビュー強制のフェイルセーフ）。新規ゲートは導入時に必ず
  発火テスト（混ぜて失敗・復元して成功）で捕捉力を証明する。
- **gitleaks 設定は `[extend] useDefault = true` が必須**: カスタム
  .gitleaks.toml は既定ルールセットを**置換**する（allowlist だけ書くと
  検出ルール ゼロ の偽緑 — 2026‑10‑07 に発火テストで実証・公式 README
  「default rules do not apply」）。allowlist は generic‑api-key への
  ルールスコープ `[[rules]]` + `[[rules.allowlists]]`（v8.25+ 様式）。
- **SHA ピンは commit SHA へ解決する**: annotated tag は /git/ref/tags の
  object.sha が **tag object** を指すため /git/tags で dereference 必須
  （rust-cache/pnpm‑action‑setup で誤ピン前例 — zizmor online の
  ref‑version‑mismatch が捕捉）。dtolnay/rust‑toolchain の @stable/@nightly
  は**ブランチ**（tag 不在）のため ref‑pin 方針（zizmor.yml policies +
  uses 行へ監査日と head SHA のコメント併記）。
- **git push が「remote: Internal Server Error」で継続失敗したら
  `git -c http.version=HTTP/1.1 push` を試す**（2026‑10‑07 実証: API 経由の
  ref 作成は成功する receive‑pack 経路固有の障害。GitHub status は
  operational 表示のままだった）。
- **ローカルの K15 実行は必ず `--json-out /tmp/...` 付きで**: 引数なしは
  既定出力先が `scripts/bench/results/phase6_front.json` = **証跡 JSON を
  上書きする**（§1.2 の再生成禁止規程違反。2026‑10‑07 に違反→即時復元の
  前例）。
- **Actions の run 失敗 ≠ job 失敗**: ジョブが物化されない run 失敗
  （ランナー起動失敗クラス）が存在する（前例: native run 37655092156 =
  14/14 物化ジョブすべて success なのに run failure・abi3‑import 4 セル
  不明。次の上位集合 push が 18/18 success で一過性を実証）。判定は
  jobs API の total_count と上位集合 run の結果で行う。
- **lint‑staged はステージされた .py へ ruff を実行する**: 意図的に規則
  違反するファイル（発火プローブ等）は `# ruff: noqa` 必須。hook 失敗時の
  「Task killed: prettier --write」表示は**他タスク失敗の巻き添え表示**で
  あることがある（真因は ruff タスクだった前例）。1 GiB 環境では prettier
  タスク自体が kill されることもあり、事前の `pnpm exec prettier --write`
  が回避策。
- **セッション冒頭はリモートの dev tip を確認する**: 外部からの force‑push
  巻き戻し（2026‑09‑26）から 12 コミットの SHA を GitHub API + ローカル
  reflog で回収・マージした復旧前例があります。`.git` 自体を失った場合は
  リモートから再 clone します（push 済みなら無損失）。

## 2. 開発環境（実測）と再構築手順

### 2.1 スペック

2 vCPU（Skylake‑SP・AVX‑512 あり・**SHA 拡張なし**）/ RAM **1 GiB**（swap なし）/
ディスク ~9.9 GB / Debian 12（ホストカーネル 4.19・Kata VM）/ Python 3.11.2
（`/opt/arena-python`）/ Node v20.20.2 / git 2.39.5。詳細と一次実測は
[`environment-report.md`](environment-report.md) を参照してください。

12 GB モデル級の KPI 実測はこの環境では不可能なため、~256 MB 級で実測し、
検証済みの外挿を BENCH に明記する規程です（推測ではなく「実測 + 外挿」）。
絶対値の判定は参照機（8C/16T・NVMe — Plan §2.2）で行います。

### 2.2 再構築チェックリスト（セッション冒頭）

apt / pip / rustup / node_modules はターンをまたいで永続しません
（ワークスペースのファイルは永続します）。

1. `apt-get update && apt-get install -y build-essential libpython3.11-dev curl pkg-config`
   （clang / mold は不要 — リンカーは rust‑lld が既定です。2026‑10‑01、
   NEO‑PLAN‑2026‑002 Step 1）。
2. rustup（stable）+ `rustup component add rustfmt clippy llvm-tools`。
3. Python 依存: `pip install pytest pytest-asyncio aiohttp markdownify huggingface_hub "hf_xet>=1.5.2,<2.0.0" modelscope_hub pillow numpy safetensors ruff mypy pyyaml`
   - `torch --index-url https://download.pytorch.org/whl/cpu`
     （torch はフルカバレッジ用 — 無いと 11 件が skip）。
4. `corepack enable --install-directory /usr/local/bin` → リポジトリ root で
   `corepack pnpm install --frozen-lockfile`。
5. dependency‑cruiser 18 は Node ≥22 が必須（常設は 20.20.2）→ 公式 tarball の
   Node 22 を /tmp へ展開し `node_modules/.bin/depcruise src`。
6. テスト用 native `.so`: `cd native && CARGO_BUILD_JOBS=1 cargo build -p mm-core`
   → `cp target/debug/libmm_core.so native-bin/linux-x86_64/mm_core.abi3.so`。
   debug ビルドで十分です（api_version ハンドシェーク・全 pytest・bench
   cross‑check が release と同一結果）。
7. 手順 3–4 は `uv sync --frozen` 一発で代替可能（pyproject の
   `[dependency-groups] dev` + uv.lock が dev/test/build 依存 + torch CPU を
   再現 → `.venv/bin/python -m pytest tests`）。pip 手動インストールは
   uv が無い場合のフォールバックです。

### 2.3 環境の癖

過去セッションで遭遇した落とし穴と回避策の実地メモ（rustup‑init の直接取得、
cc 不在時の ziglang による cc / llvm‑ar shim、release LTO ビルドのメモリ逼迫、
apt スループットの劣化、pnpm サプライチェーン検証の OOM、uv `--system` の
対象解釈、bash ツールの変数展開とバックグラウンドプロセスの寿命など）は
[`environment-report.md`](environment-report.md) §11 に集約しました。

## 3. 計測方法論

ベンチスクリプト・テスト・BENCH が「MEMO §3」「MEMO 2026‑09‑23」として
参照する定義です。

- **ゲートプロトコル**: A/B の両側（旧実装 vs 新実装、baseline vs PGO など）を
  **同一セッションで交互計測**（3 ラウンド以上）、**steal ゲート**（共有
  2 vCPU ホストの他プロセスに汚染されたラウンドを破棄して再計測）、
  **サブプロセス分離**、2 連続 PASS を要求します。ゲートなしの計測は
  同一設定でも 2–3 倍揺れます。
- **判定 = 側別中央値比**: min‑of‑N 判定は共有ランナーで外れ値ラウンド同士の
  組み合わせによるアーティファクトを 2 run 連続で生んだため採用しません
  （min / best は参考並記、退行監視は中央値 < 0.95）。steal ゲートは
  バースト的な割当・スケジュール干渉を捕捉できない（/proc/stat の steal に
  現れない）ため、判別手段は安定対照（hash ±0.4 %）とラウンド別表のみです。
  実装 = `scripts/pgo/train.py::summarize_workloads()`（BENCH §13.6）。
- **ラウンド別の生サンプル**（`roundsA` / `roundsB`）を JSON と job summary の
  両方へ記録し、解釈は必ずラウンド別表で行います（N=5）。round 0 は両側とも
  冷間（ページイン・周波数）、15–95 ms 級の微小窓は同一バイナリでも
  側内変動 2.1 倍に達します。
- **共有ランナーの絶対値はゲートにしない**: K15 bench
  （`scripts/bench/front/k15.mjs`）のゲートはすべて同一実行内比率です。
  絶対値は env ブロック付きで記録し、判定は参照機（Plan §2.2）で行います。
- sha2 0.11 の SHA‑256 に **AVX2 バックエンドはありません**（SHA‑NI か
  ソフトウェア実装のみ。`x86-avx2` は SHA‑512 専用）→ SHA‑NI 非搭載機では
  検証ハッシュ ~156 MB/s が e2e の壁になります（内訳は BENCH §7.1）。

## 4. 技術知見・教訓

### 4.1 ビルド / ツールチェーン / CI

- **prettier は完全な依存ツリーで実行する**: prettier‑plugin‑tailwindcss の
  クラス順は tailwindcss 本体 + `tailwindStylesheet`（src/style.css）の解決に
  依存します → `pnpm install --frozen-lockfile` 後の `pnpm format:check` が
  唯一の正です。
- **GH Windows ランナーは `core.autocrlf=true` でチェックアウトする**:
  rustfmt.toml の `newline_style = "Unix"` は全 .rs の fmt ゲートを破壊します →
  既定（Auto）+ `.gitattributes: *.rs text eol=lf` が正解。
- **maturin の universal2 ターゲット名は `universal2-apple-darwin`**。
  macOS の setup‑python（python.org ビルド）はリンク可能な libpython を
  持ちません（フレームワークのみ）→ `cargo test -p mm-core
--no-default-features` は macOS 除外（clippy `--all-targets` +
  ビルド & import 疎通で担保）。
- **Linux から Apple ターゲットへのクロスは PyO3 0.29 で不可**（実測）:
  rustc/pyo3 の `-Wl,-exported_symbols_list`（2 引数形）と
  `-undefined dynamic_lookup` を zig cc が誤変換します（zig 0.15.2 / 0.16.0
  双方）→ macOS ホストビルド + lipo が正経路。
- cargo‑zigbuild + zig 0.16 の `ignoring deprecated linker optimization
setting '1'` 警告は無害です（成果物の glibc ≤2.28 は readelf で確認済み）。
  zigbuild のリンクは `CARGO_TARGET_*_LINKER`（zig 由来の wrapper）が
  `.cargo/config.toml` の設定より優先されます。
- **PyO3 0.29**: 宣言的 `#[pymodule] mod` 構文が正（関数形は deprecated）。
  `use pyo3::prelude::*;` は mod の内側にも必要。**GIL 解放の API 名は
  `py.detach()`**（`allow_threads` ではありません）。`PyErr` は `Ungil` なので
  `PyResult<T>` で返却可能。クロージャへ `&str` 借用は持ち込めないため
  owned 化します。
- **jiter 0.17**: オブジェクト反復は `next_object()` で開始し、後続キーは
  `next_key()`（next_object の反復継続は ExpectedSomeValue）。
- **bincode**: crates.io の `max_stable_version = 3.0.0` は名前占拠を防ぐための
  `compile_error!` プレースホルダです → **2.0.1 が真の安定版**。
- **macos‑universal2 は fat binary**: サイズ予算は per‑arch スライス判定
  （各 ≤5 MB）+ fat ファイルは 2 倍予算。CI の size‑budget は
  **FAT_MAGIC の content 判定**（path 非依存 = download‑artifact の LCA で
  ディレクトリ断片が消えても堅牢）。
- **huggingface_hub 2.0 は `HfApi.list_models(sort=)` の注解を閉じた Literal に
  狭窄します** → `cast(Any, sort)` パターン（`# type: ignore` は
  warn_unused_ignores 環境と hub 未導入環境の双方で壊れるため不採用）。
- **テストは POSIX のエラー文言に依存しない**（`io_ctx` が全プラットフォームで
  「操作 + パス」を付与する形に強化済み）。Windows の報告パスは
  `utils.join_path` で統一し、テストは normalize して比較します。
- CI が書く JSON 証跡は `json.dump(indent=2)` + 末尾改行（prettier ゲート）。
- **pnpm 10+ は `.npmrc` から auth / registry 設定しか読みません**:
  `minimumReleaseAge` 等のサプライチェーン設定は `pnpm-workspace.yaml`
  （camelCase キー）が正です。既定ゲート下では `pnpm update` / `install` の
  検証ステップが 1 GiB 環境で OOM します（回避策は environment-report.md
  §11.3）。当日公開版はゲートが拒否するため、1 日以上経過した版へ pin します。
- **uv**: `uv pip install --system` はアクティブな venv が無いとき PATH 先頭の
  非 venv Python を対象にします（このサンドボックスでは
  `--break-system-packages` が必要。GitHub ランナーの setup‑python には
  `--system` がそのまま刺さります）。torch CPU は `[[tool.uv.index]] explicit` +
  `[tool.uv.sources]` で CPU wheelhouse へ。root pyproject は
  `[build-system]` 無し = `[tool.uv] package = false` で仮想プロジェクト化。
- **zenwebp 0.4.4**（純 Rust WebP codec・`forbid(unsafe_code)`・AGPL‑3.0）:
  エンコードは `EncodeRequest::{lossy, lossless, new}`、静止デコードは
  `oneshot::decode_rgba`（常に RGBA）、アニメは
  `mux::{AnimationEncoder, AnimationDecoder}`。**`AnimationDecoder` のフレームは
  has_alpha により RGBA(4 B)/RGB(3 B) が変わる**ため、
  `znn_codec::webp::decode_animation` は長さで判別し RGBA へ正規化します。
  **PIL は WebP のフレーム毎 duration を公開しない**（GIF は公開）→
  アニメ WebP 入力は native デコードで duration を保持。canvas 次元は
  `ImageInfo::from_webp` でデコード前にガードします（敵対的ヘッダの
  過剰確保防止 = ファズの要点）。
- **GH ランナーの apt ハングは実在します**（native run #80: apt ステップが
  無出力で 6 時間ハングし run 全体が cancelled。同一ステップは前後の run では
  20 秒未満 = ミラー側の一過性ストール）→ 全 apt ステップへ
  `timeout-minutes: 10`、全ジョブへ `timeout-minutes: 60`。
- **maturin `--pgo`（1.15.0）の実装事実**: `pgo-command` は project_root
  （= native/）を cwd にシステムシェル経由（unix `sh -c` / Windows `cmd /C`）で
  実行され、PATH 先頭に一時 venv の bin、`LLVM_PROFILE_FILE` は maturin が設定。
  `llvm-profdata` は rustc sysroot → PATH の順で解決されるため
  **`llvm-tools-preview` component が必須**です。profraw がゼロなら明示的に
  bail します。`pgo-command = "python ../scripts/pgo/train.py"` の相対パスは
  cwd=native/ で正しく、これが train.py を標準ライブラリ専用に設計した
  理由です（requires_dist が空のため venv に何も入りません）。
- **計装 universal2（fat）dylib は macOS でインタプリタ終了時に SIGSEGV**:
  トレーニング自体は完走しますが、終了時のプロファイルランタイム flush で
  クラッシュし profraw が出ません（単一 arch の PE / ELF では再現せず）→
  **macOS は非 PGO 出荷**。macOS ホスト無しではデバッグ不能なため
  推測修正は禁止（再評価は upstream 修正後に arm64 単一 arch から）。
- **PGO × fat LTO の warn‑missing‑function は良性乖離が支配的**（実測 13.81 %:
  ジェネリック実体化・クロージャ実体・計装時に完全インラインされた関数の
  アウトオブライン復元）→ G2 ゲートはしきい値 50 % + 陽性プローブ
  （Total count）。**しきい値を dev（非 LTO）実験で較正してはいけません**
  （乖離が 0.055 % まで縮むためゲートが厳しすぎる側で壊れます）。判定器は
  `scripts/pgo/g2_check.py` に恒久化（mutation 5 変種で検出力を実証）。
  プロファイルの形状（関数集合と missing 比率）はシード固定により
  決定的に再現し、Total count は ±0.1 % のランナー変動がある（rayon の
  並列分割順）ため count 条件は `> 0` のみです。
- **cargo‑zigbuild の zig 探索順**: ① `CARGO_ZIGBUILD_ZIG_COMMAND`
  （非空かつ**パス実在が必須**）→ ② `python3 -m ziglang` → ③ PATH の `zig`。
  ziglang wheel の console script は `python-zig` のみで ③ は永久に不発、
  ジョブ中段の setup‑python 切替で ② も壊れます → **恒久対策はツールチェイン
  導入時に site‑packages 内実体の絶対パスを解決し
  `CARGO_ZIGBUILD_ZIG_COMMAND` を `$GITHUB_ENV` へ pin すること**
  （生成される linker wrapper が同変数を自分で再エクスポートするため、
  1 回の pin でジョブ全体に伝播します）。
- **pyo3 0.29.2 の abi3‑pyXY feature は上向きチェーン**
  （`abi3-py312` ⇒ py313 ⇒ py314 ⇒ py315 ⇒ 素の `abi3`）→ floor の実体は
  「有効化された最小の pyXY」（pyo3‑build‑config `get_abi3_version()` の
  昇順スキャン）。floor のアサートは「最小有効 minor == N」の形で書きます
  （「より高い abi3‑pyXXX が居ないこと」の形は常に誤検出します）。
  `abi3t-py315 = ["abi3t", ffi]`（上向きチェーン無し）。
- **`cargo metadata` に `-p/--package` セレクタは無い** → feature のスコープは
  `package/feature` 修飾名で指定。ゲート helper が `capture_output=True +
check=True` で cargo の stderr を握り潰すと CI ログに traceback しか
  残らないため、非ゼロ時は stderr を写してから exit します。
- **macOS ランナーの /bin/bash は 3.2**: `set -u` 下では空配列が
  ダブルクォート内でも unbound になります → `${arr[*]+"${arr[*]}"}` ガード
  （GNU ソースから自ビルドした 3.2.57 実機で動作確認済み。5.2 でも同一）。
- **GitHub Actions のキャッシュは「ref 単位スコープ × 10 GB/repo」**:
  dev→PR→main の納品形では同一キーが 3 コピー保存され、PR run が作った
  キャッシュは `refs/pull/N/merge` スコープに入り**マージ後はどこからも
  復元できません**（タグ run も同様）→ `Swatinem/rust-cache@v2` の `save-if` を
  main / dev の非 PR イベント限定にしています（7 箇所）。
  **restore‑key フォールバックは `last_accessed_at` を更新する**ため、
  復元不能キャッシュが LRU eviction を生き残り、代わりに live なブランチ
  キャッシュが削除されます → 能動的な削除が必須です:
  `cache-cleanup.yml` + `scripts/actions_cache_sweep.py`
  （PR クローズ時に当該スコープ、週次日曜 03:40 UTC + dispatch で
  pull・tags・世代落ち。削除は非破壊 — 最悪でも cold build が 1 回）。
  上限の引き上げは支払方法の登録なしでは HTTP 402 で不可。rust‑cache の
  キー末尾ハッシュは全 Cargo.toml / Cargo.lock 等が対象のため、依存を触る
  たびに旧世代が残ります（`--older-than-days` の名前ベース削除で一括整理）。
- **runner は `GITHUB_TOKEN` を step の環境変数に自動注入しません**
  （トークンは `secrets.GITHUB_TOKEN` / `github.token` の式コンテキストから
  のみ供給）→ REST を叩く step は必ず
  `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` を明示します。
- **`upload-artifact` の既定保持は 90 日** → 検証用の `native-bin-*` は
  `retention-days: 7`（fuzz‑crashes / pgo‑measure‑report は証拠物件のため
  据え置き）。

### 4.2 フロントエンド / V8

- **C2 comparator（bench ゲートで機械固定）**: V8 は**既定 options の
  `localeCompare`** に内部キャッシュ済み既定 collator の高速経路を持ち、
  hoisted `Intl.Collator` より ×2.1–3.5 速い → 既定 variant は `localeCompare`
  を維持。**options 付き**に高速経路は無く、`{numeric:true}` は hoisted
  numeric Collator が ×23–33 速い → numeric variant のみ Collator 化。
  この設計判断は CI の V8 でも再現しており、Node 更新時に再検証します
  （Plan T2 規程）。
- **shallowRef 移行の手順**: 全消費者の影響棚卸しを先行（doc コメントに
  列挙）→ 読み取り専用または cloneDeep 後操作のみであることを確認 →
  イミュータブル差し替え（`models.value = {...models.value, [folder]: resData}`）。
  getter watch（`() => modelsData.value[type]`）は ref 自体を追跡するため、
  shallowRef でも再代入で発火します。
- **巨大 payload の cloneDeep は隠れコスト**: 65,268 テンソルで 218.5 ms、
  87,195 ノードの tree で 130.0 ms がダイアログを開くたびに発生していました →
  読み取り専用表示 payload は**参照共有**（保存経路がこれらを送らないことで
  安全）+ snapshot 除外 + `toRaw()` 経由の読み取り（Proxy トラップ回避）。
  端到端 ≈1,589 → ≈13 ms（BENCH §11.3.1）。
- **テンソルツリー**: Rust pre‑order 線形符号 + JS 遅延インデックス
  （87k ノードを materialize しません）。**描画行の順序は
  `tensorTreeRowsIdentical` ゲート**が legacy fold と機械照合します
  （collapsed + 全展開 152,462 行）。
- フォルダアイコンの `<img>` は 2026‑10‑05 の刷新で静的 SVG になったため
  `decoding="async"` を適用済み。旧規程「SMIL アニメーションの `<img>` に
  decoding=async は意図的に非適用（タイムライン再開挙動が変わる）」は SMIL
  退役とともに過去のもの。`loading="lazy"` は仮想スクロール済みのため不導入。
- **v-html 注入の生 svg は `size-*` クラスを必ず付ける**（2026‑10‑06 実機バグ）:
  `Button.vue` 基底の `[&_svg:not([class*='size-'])]:size-4` フォールバックが
  クラス無し svg を 16px へ縮め、ラッパー側の `[&>svg]:size-5`（特異度 0,1,1）は
  同フールバック（0,2,1）に負ける。Lucide 兄弟アイコンは明示 `size-*` を持つため
  `:not(...)` で除外され 20px のまま → 同一行で HashReverse アイコンだけ小さく
  見える原因になった。対策は svg ルートへ `size-5` クラスを注入して
  フォールバック対象から外すこと（`HashReverseIcon.vue`）。
- `scripts/bench/front/k15.mjs` は `--cross-check` 無しなら native 不要・約 30 秒
  （縮小パラメータで約 6 秒）。pnpm ストア外の tsc は `MMNEO_TSC` で渡します。

### 4.3 バックエンド（Python / native 接続）

- **HTTP を Rust 化しない実測根拠**（Plan §3.8 / BENCH §11.4 の一次記録）:
  reqwest 0.13 は feature 名変更（`rustls-tls` → `rustls`）で aws‑lc‑sys
  （C/asm・cmake 必須）+ ring を引き込み、「コンパイラ不要」の配布哲学と
  衝突します。最小プローブ cdylib は実測 **~4.9 MB**（HTTP スタックだけで
  サイズ予算の ~1.9 倍超過）・依存 167 crates。native‑tls は OpenSSL 動的リンクで
  zigbuild の glibc 2.28 床を破壊。huggingface_hub 2.0 は httpx 基盤のため、
  Rust 化は「統一」ではなく**第 3 のスタック追加**になります。重い HF 転送は
  hf_xet で既に Rust 化済み。axum（サーバ FW）/ utoipa は aiohttp
  PromptServer 登録モデルに非該当。
- **extended‑notify 不採用の実測根拠**（Plan §3.1 の一次記録）: 単一作者・
  ダウンロード数が本体ライブラリと 3 桁以上差・debouncer‑full の旧版ピン
  （^0.6）・tokio の出荷バイナリ混入。目玉機能（root 再アーム・kind フィルタ・
  ポーリング）は Neo 側で数行で代替可能で、ポーリングは notify 本体の
  PollWatcher に標準搭載。本当に必要なのはグルー（inotify 予算管理・
  network FS 検出・path→type・既定 OFF）= `py/watcher.py` に実装済み。
- **aiohttp parity の契約**（`py/http_client.py`）: requests の timeout
  `(connect, read-between-bytes)` → `ClientTimeout(connect=…, sock_read=…,
total=None)`（**total ではない** — 120 ms 間隔 2 チャンクのストリーミングで
  実測固定）。`HttpStatusError` は `raise_for_status` の文言を**逐語再現** +
  `.response.status_code` を維持（Civitai の 401 誘導文が依存）。JSON は
  **content‑type を検査しない**（`content_type=None` — ModelScope CDN が
  octet‑stream で返す実例）。宣言 charset を尊重し、未知 codec は UTF‑8 へ
  degrade（LookupError 捕捉）。`trust_env=True`（プロキシ環境変数）。
  共有セッションは**イベントループの変化を検出して再作成**
  （None→生成は await を挟まない同期アトミック = 並発初回呼び出しでも安全）。
- **`requests` は modelscope_hub の推移的依存として残ります**
  （`Required-by: modelscope-hub` を実測）— Neo の直接使用ゼロ化後も環境に
  存在します（直接使用ゼロは AST テストで固定）。T8 の利点は依存削減ではなく
  構造です（IO プール専有の解消・方針の一元化・テスト可能性）。
- **IO プール枯渇クラス**: 8 本の io ワーカー上でのブロッキング HTTP は、
  遅い CDN で read timeout（最大 120 秒）分スロットを専有し、scan / hygiene /
  preview が連鎖的に遅れます。ネットワーク待ちはイベントループ、executor には
  CPU 段のみ（同クラス: model‑info ルートの executor 化、watcher arm/release の
  executor 化、resume seeding の executor 化）。
- **GIL 規律**: 長時間・ブロッキングの native API は `py.detach()` で解放します
  （違反の前例: walk_models / move_with_sidecars —
  `test_walk_models_releases_the_gil` で機械固定）。**watcher の arm/release は
  executor 経由、poll はループ上**（mutex swap + 小 JSON = 安い、が設計意図）。
  Python 側の重い段（hash / PIL / ヘッダ解析）は executor。
- **native 化は自動では速くなりません**: `parse_header_json` の重複テンソル名
  検査が線形走査（O(n²)）だったため、64,491 テンソルの MoE で native が
  **×18 の退行**（6,098 ms vs legacy 334 ms）→ `HashMap<name, pos>` O(1)
  last‑wins へ修正し 212 ms（legacy 比 ×1.58 速）。compress も共有経路のため
  6 秒 → 数十ミリ秒。**実規模での端到端計測が必須**です。
- **ヘッダ解析は 1 ルート**: `get_model_header` が metadata + tensors + tree を
  一度に返し、`(mtime_ns, size)` スタンプガードを掛けます（2 回の native 呼び出し
  の間にファイルが差し替わると tree を落とす — フロントの leaf 数検査
  `leaves.length === tensors.length` と二重）。
- **watcher の設計定数**（テストから monkeypatch 可能な module 定数）:
  `SETTING_TTL=5.0` / `TYPE_COOLDOWN=2.0` / `DEGRADE_RETRY=600` /
  `MOUNTINFO_TTL=60`。rescan / type のクールダウンは**消費されたシグナルを
  意図的に間引きます**（30 秒 TTL が correctness の床）。シングルトン
  `watcher.watcher` とクラス `ModelWatcher` は分離済み。
- **request 無しでの設定読み取り**: ComfyUI の `get_request_user_id` は
  single‑user で request に触れない（app/user_manager.py を一次確認）→
  background task は `request=None` で読めます。`--multi-user` では例外 →
  既定値（OFF）へ degrade = 安全側。
- **設定 ID 文字列は ComfyUI が永続化するキーのため改名禁止**
  （`ModelManager.Scan.*` 系 — 改名は既存インストールの保存値を孤立させます）。
  歴史的な ID の吸収は `resolve_setting_key`。
- **既知の非バグ事項**: `decompressedTensors` は native = 実デコード数 /
  legacy = infos エントリ数（ゴースト infos を持つ壊れファイルでのみ差）。
  legacy の「dst 存在チェック後の競合」は native の create_new で構造的に
  解消済み。サーバ kill 中のジョブスレッドは道連れで終了します
  （残った tmp は起動時クリーンアップの 15 分規則が回収。コミット済み成果物は
  rename の原子性により不整合になりません）。
- **アップロード preflight ハッシュ（T1）**: `upload_hf.py` の `hash_local_file` は
  Python hashlib の 1 MiB ループで io_executor 上で走っていました
  （CPU 作業 — プール意味論的にも cpu 側が正）。hashlib も OpenSSL 経由で
  SHA 拡張を使うため純速度差は小さく（BENCH §10.2）、実益はループ除去・
  経路統一・GIL 解放です。
- **`EXTENSION_SUFFIXES` の flavour 行列**（CPython 一次ソースで確定 —
  `Python/dynload_shlib.c` / `dynload_win.c` / `_bootstrap_external.py`）:
  POSIX では **`.abi3*` 項が `#ifndef Py_GIL_DISABLED` の内側、`.abi3t*` 項は
  無条件**。`FileFinder._find_spec` は `name + suffix` しか照合しないため、
  free‑threaded 3.15 では `mm_core.abi3.so` をどの名でも解決できず
  `ModuleNotFoundError` になります。**`Py_GIL_DISABLED` ガードは 3.15 で
  導入された**ため、3.13t / 3.14t は `.abi3.so` を**受理してしまいます**
  （dlopen まで届く）= ローダーが ft < 3.15 を早期拒否する根拠は
  「解決できないから」ではなく「解決できてしまうから危ない」。
  GIL 3.15 は両 family を併記します（abi3‑import の「3.15 GIL × abi3t」セルは
  成立）。**Windows には family 差がファイル名に存在しません**（`.pyd` 2 項のみ）
  → flavour 分離はディレクトリ名（`<tag>` vs `<tag>t`）だけが担い、
  ABI タグ付きファイル名を前提にできるのは POSIX のみです。

### 4.4 ファジング

- **blob_decompress の OOM（fuzz‑long run 1・2）の根因はコード欠陥では
  ありません**: ハーネスの threads=1 が default_threads() と異なるため
  `with_threads` が exec 毎に新規 rayon プールを生成・破棄し
  （OS スレッドの churn → サニタイザメタデータが ~35 B/exec で累積）、
  rss_limit に到達していました → 明示スレッド数のプールをキャッシュ +
  上限ガードで解消（定常窓 ~44 → ~9 B/exec。再ディスパッチ run は
  1.9 億 execs / 3 h 完走・peak RSS 164 MB・クラッシュ 0）。副次対策:
  出力バッファの thread_local grow‑only 化、
  `ASAN_OPTIONS=quarantine_size_mb=32:release_to_os_interval_ms=200`
  （cargo‑fuzz は自前変数を**追記**するため環境変数は子へ到達します）、
  `rss_limit_mb` 4096。OOM 入力（88 B）は corpus へ回帰シード化済み。
- **libFuzzer の OOM レポートは stderr のみで `crash-*` アーティファクトを
  残しません** → アーティファクト 0 件でもジョブログを読みます。
- **現行ターゲットは 7 種**: `huf_decompress` / `zn_header` /
  `codec_decompress` / `st_parse` / `blob_decompress`（キャップ 1 MiB で駆動）/
  `delta_decompress` / `webp_decode`。native.yml の fuzz‑smoke ループと
  fuzz-long.yml の matrix は**同一コミットで**拡張します。
- 18 時間の完走証跡は codec 無変更の間有効です。再ディスパッチはファズ表面が
  変わったときのみ（§1.2）。

### 4.5 テスト規律

- **ゴールデン parity 規程**: 同一 fixture を native と Python 経路の双方で
  実行し（エンジン切替は旧 `MM_NATIVE` 環境変数から `core_if_enabled` 注入へ
  移行済み）、`native == legacy` を完全構造比較します
  （scan / hygiene / header / hash / walk / move / batch）。byte‑exact 復元は
  sha256 で検証。
- **MockHub パターン**（`test_phase6_http.py`）: 実 aiohttp TestServer +
  `calls` 記録で**往復回数と順序**まで固定します（ライブ API 依存ゼロ・
  録画フィクスチャの陳腐化なし）。
- **fake core 注入パターン**: `monkeypatch.setattr(service, "_core", ...)` /
  `monkeypatch.setattr(download.native, "core_if_enabled", ...)` →
  **native バイナリ無しで** inline‑hash / watcher 経路をテスト可能
  （= ci.yml の成果物なし環境でもカバーされます）。
- **`download_model_file_http` を直接駆動するテストは
  `md.get_task_status(task_id).status = "doing"` が必須**（TaskStatus 既定の
  `"pause"` だと書き込みループが協調ポーズで即 break → 0 バイト）。
- watcher テストは必ず**新しい `ModelWatcher` インスタンス**で作ります
  （シングルトンを汚すとクールダウン状態が持ち越されます）。
- executor 配置の検証は**スレッド ident の記録**で決定論的に
  （start/stop は executor、poll はループ上）。
- cancel 伝播の待機は**条件ベース**（`asyncio.wait_for(event.wait(), timeout)`)
  — 固定回数の `sleep(0)` ループは回数依存で理論上 flaky です。
- `stubs.py` は ComfyUI master のセマンティクスをミラーします
  （`safetensors_header` の <8 B ガード差は文書化済み — 呼び出し側の
  `except Exception` が両者を同じ結果へ写像）。`write_safetensors` は
  バイト制御された正準 writer（8 バイト整列・`__metadata__` 先頭・
  insertion / sort 両順）で、torch 往復では書けない「非ソート順ファイルの
  byte‑exact 復元」をテスト可能にしています。
- **`time.monotonic()` は uptime 基準 — テストで「十分大きい」を仮定しない**:
  TTL 失効テストでキャッシュ stamp に絶対原点 `0.0` を使うと、起動直後の
  CI ランナー（uptime < TTL 秒）で「まだ失効していない」判定になります
  （実例: `test_mountinfo_body_is_cached_within_the_ttl`）→ 相対原点
  `now - (TTL + 1)` を使います。**本番コードにも同根の欠陥がありました**
  （watcher のクールダウンが「未放送」を monotonic 0.0 の既定値で符号化 →
  起動 60 秒未満のランナーで初回 rescan 放送が抑制された）→ None sentinel 化 +
  固定時計の回帰テストで決定論化。**教訓: monotonic 比較の「無い」状態は
  必ず None / sentinel で表し、数値原点 0.0 を使いません**。
- **mutation 検証は「アサート無しの try/except‑pass」も探します**
  （例外を要求しておらず、どんな退化でも成功していた前例 →
  `pytest.raises` 化。同型: loop / アニメ ICC の保持が Python 側で未固定 →
  接合部テストの追加で捕捉を実証）。
- **`sys.version_info` の monkeypatch はサードパーティの import 時分岐に
  漏れます**: バージョンピン（GIL 3.12 偽装）下で aiohttp が初回 import されると
  `client_ws.py` の `>= (3, 13)` 分岐が偽になり `typing_extensions.TypeVar`
  経路へ入り、実際の 3.15 ホストでは以降のテストが連鎖して失敗します
  （**一度壊れると回収不能**）
  （CI が無事だったのは収集順の偶然でした）→ ピンを持つテストモジュールは、
  モジュール import 時（どの fixture より前）に必要なサードパーティを
  `importlib.import_module()` でウォームアップしておきます。
- **実 import 機構に触れるテストは「偽装した解釈系」で走らせてはいけない**
  （ピンが差し替えるのは Python 層の属性だけで、`EXTENSION_SUFFIXES` /
  `FileFinder` / `dlopen` は本物の解釈系のまま）:
  (1) 実ホストの信号で走らせる（`_use_real_interpreter` パターン =
  モジュール import 時に `_REAL_VERSION` / `_REAL_ABIFLAGS` /
  `_REAL_GIL_DISABLED` を退避 → monkeypatch で再設定。undo は逆順のため
  二重 setattr でも元の値へ戻ります）、
  (2) 期待ファイル名をハードコードせず flavour（`is_free_threaded()`）から
  導出する、
  (3) tag が None の skip には `tag_rejection_reason()` を出し
  「成果物不足」と「解釈系非対応」を区別する。
  副次利得: floor 未満ホストでピンが tag を捏造し、実 import が未定義
  シンボルで失敗する潜在の誤検出も同時に消えます。
- **浮動小数点変換の parity は「乖離窓」をピン留めする（単一サンプルでは
  検出不能）**: `ns_to_ms` の旧実装 `(ns as f64)/1e6` は epoch ns > 2^53 で
  f64 変換が 256 ns 量子へ不可逆となり、.5 境界近傍で round_ties_even の
  判定が反転 — CPython の `round(int/int)`（int/int は**正確な商の正しい
  丸め**）と約 1/10,000 のタイムスタンプで 1 ms 乖離した（実測:
  2026‑10‑07 macOS integration の test_scan_survives_a_non_utf8_sidecar
  1 件失敗・直前 9 run 連続緑・再実行は緑 = 典型 flake 像）。旧単体テストは
  live-stat 1 サンプル＋小さい合成値（<2^53 = 変換が正確な領域）のみで
  構造的に検出不能。修正 = 整数商＋余り（div_euclid/rem_euclid →
  `q + f64(r)/1e6`。|q|<2^53 で q は f64 正確、r/1e6 の内側丸め誤差 ≤2^-54
  は判定中点（奇数×2^-13）へ届かない = 分母 1e6 と 2^13 の共通因子 2^6 では
  奇数分子が相殺しないため。唯一の完全タイ r=500_000 は q+0.5 が f64 正確）
  = **全 i64 で CPython とビット一致することを証明可能**。負 ns は
  div_euclid が Python divmod と同じ floor 意味論で一致。検証 = 実測乖離 ns
  の両方向ベクタ 3 本の回帰ピン（mutation 検証: 旧実装で CI 観測値ちょうど
  で失敗・新実装で成功）＋ CPython との 3M ランダム照合（現代 epoch・負・
  小値・2^53 境界・i64 極値）で乖離ゼロ（旧式 41 件）。**教訓: 丸め・精度の
  parity 契約は、実測された乖離ベクタと両方向をテストに固定する。**

## 5. 完了した計画とその成果（過去に何をしたか）

3 つの計画の全実装要件は 2026‑09‑23 から 2026‑10‑03 にかけて完了し、
CI と公開パイプラインが正常に実行されることまで確認済みです。計画書本体
（版数履歴・チェックリスト・一次ソース一覧を含む）は git 履歴に一次記録として
保存されています（冒頭の注記参照）。

### 5.1 Plan.md（NEO‑PLAN‑2026‑001）— Rust ネイティブコア化と ZipNN 完全置き換え

Neo の中核処理を Rust ネイティブコア（`mm_core`）へ移行し、vendored ZipNN
C スタックを置き換える計画です。4 つの柱: **信頼性の抜本改善**
（計画策定過程で C コアの再現性ある SEGFAULT とヒープオーバーフローを
実機実証 — Plan 付録 C — Rust によりこの欠陥クラスを構造的に消滅させ、
SHA‑256 端到端完全性検証を新設）、**メモリ効率**（圧縮ピーク RAM を
モデルサイズの約 2 倍から O(チャンク×スレッド数) へ、デルタを約 4–5 倍から
1 GB 未満へ）、**速度**（KPI K1–K16 — Plan §2.2）、**配布拡大**
（CPython バージョン別 C 拡張 ×6・Linux x86_64 のみ → abi3 単一バイナリ ×
4 プラットフォーム・コンパイラ不要）。dtype 対応は 5 種から 22 種へ拡張。
Phase 0–8 の全フェーズが完了しました。

- **Phase 0 — 基盤準備（2026‑09‑23 完了）**: `native/` cargo ワークスペース
  （edition 2024）、CI（native.yml 新設）、ベンチ基盤 + `docs/BENCH.md` の
  ベースライン記録、`py/native.py` ローダー + `MM_NATIVE` スイッチ、
  JSON パーサの確定（8 MB MoE ヘッダで jiter 10.6 ms vs simd‑json 187.6 ms vs
  serde_json 143.6 ms）、Quick Win A1（モデル詳細ルートの executor 化）、
  mold / rustfmt / clippy の導入。
- **Phase 1 — znn‑codec フォーマット中核（2026‑09‑23 実装・09‑25 fuzz
  バジェット達成）**: ZN ヘッダ、ビット並べ替え、平面分割、huff0 / FSE の
  エンコーダ・デコーダ（C からの逐条移植 → **出力は C 実装とバイト同一**:
  L2 ゴールデン差分 9,880/9,880・フル 10,500 ケース GATE PASS・付録 C の
  クラッシュクラス 495/495 を安全処理）、チャンク並列 codec。速度は 8/8 指標
  ×1.09–1.81 で C 超え（virtual‑raw 平面最適化・`unsafe` 不使用で達成）。
  ファズ 3 ターゲットで実バグ 3 件を検出・修正。
- **Phase 2 — safetensors 圧縮/解凍パイプライン + バックエンド接続
  （2026‑09‑24）**: mmap 単一書き込みパス（ピーク RAM = O(最大テンソル)）、
  SHA‑256 端到端検証 + `.corrupt` 退避、paranoid モード、ジョブ API
  （10 Hz ポーリング・GIL 非接触・catch_unwind・完了の権威シグナルは
  outcome レコード）、ws イベント / stats 形状のゴールデン互換、起動時の
  `.tmp` クリーンアップ（15 分の年齢ガード）。公式 pip zipnn 0.5.4 との
  双方向クロス検証ゲート（L5）を CI に新設。K1 / K6 / K13 達成。
- **Phase 3 — デルタ圧縮 + バッチプリミティブ（2026‑09‑25）**: 両側 mmap +
  1 MiB ストリーミング XOR（K4 = ピーク 1 GB 未満・匿名域 O(チャンク)）、
  公式 streaming コンテナ連鎖形式（公式解凍側が 100 % 受理することを L5‑D で
  実証）、`.neo-delta.json` サイドカー + `ftSha256` インライン検証、
  `walk_models` / `move_with_sidecars`（Python 現行とのゴールデン parity・
  GIL 解放をテストで機械固定）。K5 = 付録 C の SEGFAULT クラス 3/3 が
  生産ルートで正常完了 + byte‑exact。api_version 3。
- **Phase 4 — dtype 大幅拡張（2026‑09‑26）**: safetensors 0.8 の全 22 dtype の
  圧縮帯化（K14）— Neo 拡張帯コード 128–146（F64 8 平面・整数系・BOOL・
  FNUZ FP8・F8_E8M0・F4 / F6）、トランケーションモード 1/9/41/8 の
  クリーンな正式実装（C 版の 41/9/1 はコメントアウトされた到達不能コード）、
  `znn_neo_extended` マーカー、`/zipnn/inspect` ルート、UI（dtype 内訳・
  Neo バッジ・確認ダイアログ・i18n×3）、相互運用マトリクスの 5 文書化。
  公式 zipnn は Neo 帯を `ValueError: Unsupported Dtype N` で明示拒否
  （静かな破損ゼロ — L5 E 系で CI 固定）。互換帯の出力バイト同一を維持
  （L2 quick 1,121/1,121）。
- **Phase 5 — スキャン / インデックス / ハッシュ / 更新伝播（2026‑09‑27）**:
  Rust 並列 walk（os.scandir 意味論の忠実移植 + ゴールデン parity）、
  永続 front‑matter インデックス（bincode + blake3 + 原子入替 + 破損時
  自動全再構築 — 再起動を跨ぐ）、`safetensors_header`（jiter・32 MiB 統一
  ガード・comfy.utils 依存の撤去）、`hash_file` / `hasher_*`
  （5 表記 1 パス・1239 MB/s・Civitai 表記ゴールデン）、ダウンロードの
  インライン検証（K7 = 完了時追加 I/O ゼロ）、1 MiB チャンク化（K8）、
  `models_changed` ws 無効化 + フロントの部分再取得。K9 = 5000 モデル
  0.145 s（legacy 比 ×7.5）・K10 = warm 99 ms・K11 達成。実装中に
  ヘッダ解析の O(n²) 重大バグを発見・修正（§4.3）。api_version 4。
- **Phase 6 — フロントエンド表示最適化 + Phase 5 移管項目（2026‑09‑27）**:
  C1 正規表現ホイスティング（keystroke p95 ×3.0）、C2 照合キー化
  （既定は localeCompare 維持・numeric のみ Collator 化 ×22–32 — §4.2）、
  C3 shallowRef、C4 `decoding="async"`、C5 計測基盤（`utils/perf.ts` +
  `__mmNeoPerf` + ヘッドレス計測器 k15.mjs の CI 常設）、テンソルツリーの
  Rust 事前グループ化（65,268 テンソルで ×104 = 1,329 → 12.8 ms・
  Rust == Python == JS の三者同一性を機械固定）、A3 requests→aiohttp 統一
  （モックテスト 17 件）、watch_roots（notify 直接採用・500 ms デバウンス・
  既定 OFF・network root 自動スキップ・inotify 枯渇時は TTL へ degrade）。
  K15 達成（5,050 モデル・keystroke JS 作業 p95 3.96 ms ≤ 16 ms・
  初回グリッド行構築 p95 7.03 ms）。api_version 5。
- **Phase 7 — ツールチェーン現代化・設定統合 T1–T8（2026‑09‑29）**:
  T1 アップロード preflight SHA256 の native 化、T2 Node 26.10.0
  （C2 ゲートを Node 26 の V8 で再検証）、T3 Ruff 0.16.9、T4 uv 導入
  （Python の開発・CI 層専用 — uv.lock コミット・CI 5 ジョブを
  `uv pip install --system` へ）、T5 設定統合（`[tool.mypy]` の pyproject 化・
  prettier / stylelint の package.json 移設・tests/pytest.ini は rootdir 制御の
  ため意図的に非統合）、T6 GitHub Actions の一括更新（checkout / setup-node /
  setup-python v7・upload-artifact v7・download-artifact v8・pnpm-action v6.1 —
  1 action ずつ別コミット）、T7 zenwebp 一気刷新（静止エンコード + アニメ WebP
  保持 + デコード・api_version 6・fuzz 7 本目・AGPL‑3.0 ライセンス整備）、
  T8 requests の直接参照ゼロ化（AST テストで固定）。サイズ目安の 4→5 MB 改定、
  pnpm 12.8.1 への更新、依存の最新安定版一斉更新（vue 3.5.43・vite 8.3.1・
  eslint 10.11.0 ほか）。CI 実行の全ジョブ成功を確認。
- **Phase 8 — third_party 撤去・配布仕上げ・v0.3.0（2026‑10‑01）**:
  旧経路の全削除（compress.py 2,425 → 1,391 行）、`third_party/` 撤去
  （ZipNN MIT + FiniteStateEntropy BSD‑2 の全文を `native/NOTICE` へ継承）、
  `MM_NATIVE` 撤去（単一経路化 — 読み取り系のレジリエンス経路のみ
  Python フォールバックを維持する設計判断を記録）、`publish-native-bin`
  配布機構（main 専用・成果物の content 分類・`git add -f`・bot コミットは
  再トリガーされずループ不可）、L2 / native‑diff の退役（L5 が恒久ゲート・
  証跡 JSON は残置）、v0.3.0 のバージョン同期 + web 再ビルド、
  README×2 / USAGE×3 の全面改訂（フォーク元 2.8.5 との差分を一次照合し
  「Backend & engine」差分表を新設）、純標準ライブラリの `python3 -S` による
  コンパイラ・pip・ネットワークなし動作の Linux 実証（K16）。

### 5.2 Plan‑2.md（NEO‑PLAN‑2026‑002）— rust‑lld 移行と PGO 導入（Step 1–5）

2 本柱: CI から mold / clang を撤去し **rust‑lld**（Rust 1.90 以降の
x86_64‑linux 既定リンカー）へ移行すること（6 時間ハング前例のある apt
ステップの障害面削減が主目的・実行時性能のトレードオフはゼロ）、
出荷バイナリへの **PGO**（release プロファイルは設定上の最適化余地が無く、
実行時性能に残された主要手段でした）。BOLT / Intel BOT / Propeller /
リンカー ICF / LLVM CAS / 成果物への ThinLTO / アロケータ差し替え /
target‑cpu 多変種は一次調査に基づき不採用・保留・監視のみと判定
（Plan‑2 §5）。Step 1–5 は 2026‑10‑01〜02 に完了しました。

- **Step 1（rust‑lld 移行）**: `.cargo/config.toml` の mold 設定を撤去
  （判断根拠のコメントへ置換）、native.yml の apt ステップ削除、
  native/README 改写。fuzz-long.yml の apt ステップ削除は週次実行の成功確認後の
  フォローアップ（R5 — 残件 §7）。
- **Step 2（PGO トレーニングハーネス）**: `scripts/pgo/train.py`
  （標準ライブラリ + mm_core のみ・シード固定の決定論的ワークロード・
  `--measure` モード内蔵・`TRAIN_ROUNDS` で反復数調整）+
  `scripts/pgo/README.md`。3 OS のランナーで完走を確認。
- **Step 3（linux‑x86_64 パイロット計測）**: `pgo-measure` ジョブ
  （workflow_dispatch / コミットメッセージの `[pgo-measure]` マーカー専用）—
  計装ビルド → トレーニング → `llvm-profdata merge` → baseline / PGO 両者の
  zigbuild → G2 検査（プロファイル no‑op の検出）→ 交互 A/B 計測。
  **G1 = PASS**（中央値判定・コールド一貫で最大 ~+10 % の初回実行
  スループット — BENCH §13）。G2 のしきい値は run #106 のログ全件解析により
  1 % → 50 % + 陽性プローブ 3 条件へ再校正（13.81 % は fat LTO の良性乖離）。
  判定統計を min → 側別中央値へ改訂（§3）。
- **Step 4（PGO 本番組み込み）**: linux‑x86_64 は手動三段階（計装は
  ホストネイティブビルド）+ 恒久 G2 ゲート、Windows は maturin `--pgo` の
  三段階が完走、**macOS は計装 fat dylib の終了時 SIGSEGV により非 PGO
  出荷**（§4.1・判断 (c)）、linux‑aarch64 は対象外。build 3 ジョブへ
  `llvm-tools-preview`。size‑budget（4 本 18,118,520 B ≤ 20 MB）・
  run 全体 9 分 21 秒 ≤ 20 分・integration 3 OS が PGO 成果物に対して成功
  （= テストされた成果物が出荷される成果物）。
- **Step 5（ドキュメント・記録）**: native/README の PGO 節、BENCH §13
  （計測 + 判定統計の改訂）、README×2 のエンジン節へ「PGO 最適化済み」を
  追加（linux‑x86_64 / Windows の 2 プラットフォーム限定・BENCH §13 参照付き）。
- プロファイルはビルド毎生成・**コミットしません**（ドリフトゼロ・
  リポジトリ非肥大）。G2 の形状数値（7,618 関数 / 1,052 missing / 13.81 %）は
  3 run 連続で完全一致 = プロファイルの決定論を再現確認済み。

### 5.3 Plan‑3.md（NEO‑PLAN‑2026‑003）— Python 下限 3.12 化と abi3t バイナリ（Step 1–5）

(1) CPython 3.10 の EOL（2026‑10‑01）到達を受け **abi3 フロアを py310 から
py312 へ引き上げ**（ComfyUI の文書化サポート下限と完全一致）、
(2) **CPython 3.15+ のフリースレッド build 向け abi3t 成果物（PEP 803）を
4 プラットフォームタグすべてに追加**して 8 本体制へ、(3) ローダーが
インタプリタの flavour とバージョンを検出して成果物を選択、(4) ユーザ環境での
自動ビルドは導入しない（Plan‑3 §5 に配布哲学の確認を記録）。
Step 1–5 は 2026‑10‑03 に完了し、公開パイプライン（publish 8 本）まで
実働を確認しました。

- **Step 1（floor 3.12 化）**: abi3‑py312・`requires-python >=3.12`・
  ruff py312・mypy 3.12・uv.lock revision 5・CI 解釈系 ×7・abi3‑import セル
  3.12 / 3.14。
- **Step 2（ft feature と `<tag>t` ビルド経路）**: mm‑core の feature 再編・
  `build-native.sh` 8 ターゲット化・toggle ゲート 3 軸・build ×3 への
  host 3.15.0‑rc.2 t ビルド + GIL / ft 両フレーバの import smoke 追加・
  ディレクトリ構造での artifact upload。
- **Step 3（ローダー）**: `is_free_threaded()`（`Py_GIL_DISABLED` /
  abiflags `t`）・`<tag>t` ルーティング・GIL 3.12 / ft 3.15 の floor ガード・
  `diagnostics.freeThreaded`・テスト +4。フリースレッド 3.13 / 3.14 は
  abi3t が未定義のため理由付きでデグレード。
- **Step 4（CI 拡張）**: abi3‑import 4 セル・size‑budget（found 8 ハード +
  本別 5/10 MB ハード + 合計 40 MB 目安〔D1・超過は warning のみ〕）・
  publish 8 エントリ（ディレクトリタグ優先のステージング・bare `.pyd` 拒否
  〔R7〕）・ubuntu の t integration セル（3.15.0‑rc.2t × フル pytest〔D3〕・
  torch / tsc / L5 の脚は GIL セル限定へ条件変更）。
- **Step 5（文書・バッジ）**: README×4・USAGE×4・native/README・pgo README・
  Plan‑3 の状態更新。
- **決定事項 D1–D4**: D1 合計サイズ 40 MB・目安化（ユーザ決定）、
  D2 abi3t は v1 非 PGO（GIL 側の PGO は Plan‑2 のまま維持）、
  D3 t integration は ubuntu のみ（他 OS は import smoke）、
  D4 rc ピン → final への振替は manifest への final 掲載後の別コミット。
- **納品後の安定化**（dev CI の失敗 4 件 + 潜在の誤検出 1 件の修正 —
  いずれも根因を実証付きで特定）:
  ① py315 切替後の「Failed to find zig」→ `CARGO_ZIGBUILD_ZIG_COMMAND` の
  絶対パス pin（§4.1）、
  ② macOS bash 3.2 の空配列 unbound → `${feat[*]+…}` ガード 3 箇所、
  ③ toggle ゲートの `cargo metadata -p`（同セレクタは存在しない）→
  修飾形への変更 + cargo の stderr を CI ログへ転写、
  ④ ゲートアサートの誤検出潜在バグ（pyo3 の abi3‑pyXY 上向きチェーン →
  「最小有効 minor」形へ置換・負例 9 ケースで検出力を実証）、
  ⑤ ubuntu‑t integration の pytest 1 本失敗 = テスト側の 5 段連鎖
  （autouse のバージョンピン → タグ誤誘導 → プローブ名ハードコード →
  成果物 4 タグ一括展開による skip ガード不発 → free‑threaded 3.15 の
  `EXTENSION_SUFFIXES` に `.abi3.so` が無い）— ローダーは正しく拒否しており、
  誤っていたのはアサート → `_use_real_interpreter` の逃避口 + flavour 準拠の
  プローブ名 + `test_extension_suffixes_enforce_the_flavour_split`
  （5 flavour 実測で機械固定）+ aiohttp ウォームアップによる
  サードパーティ import 漏れの除去（§4.5）。
- **公開確認**: CI 全ジョブ成功後、publish‑native‑bin の bot コミットが
  `native/native-bin/` へ **8 本**を配置（abi3 ×4 + abi3t ×4・
  linux‑x86_64 3.93 / linux‑aarch64 3.36 / linux‑x86_64t 3.96 /
  linux‑aarch64t 3.36 / macos‑universal2 6.43 / macos‑universal2t 6.43 /
  windows‑x86_64 3.55 / windows‑x86_64t 3.96 MiB・合計 34.98 MiB =
  D1 目安内・本別予算内）。

### 5.4 納品後の CI 運用と保守（2026‑10‑01〜03）

- **GitHub Actions キャッシュ逼迫への対策**（9.65 GiB / 96.5 % →
  5.08 GiB / 50.8 %）: 即時 prune 16 件 / 4.57 GiB（pull スコープ 10 +
  main の旧世代 6）+ 構造対策 3 コミット — rust‑cache の `save-if` を
  main / dev の非 PR イベント限定に（7 箇所）、`cache-cleanup.yml` +
  `scripts/actions_cache_sweep.py`（PR クローズ時の当該スコープ削除 +
  週次日曜 03:40 UTC + dispatch）、`native-bin-*` artifact の
  `retention-days: 7`。スコープ規則と LRU 挙動の一次調査は §4.1。
  対策後の納品サイクル（dev → PR → main マージ）で新規キャッシュエントリ
  0 件を確認し、`save-if` の両側（true / false）とも実際の run で検証済み。
- **cache‑cleanup 初走失敗の修正**: `GITHUB_TOKEN` が step env に渡って
  いなかった（runner は自動注入しない — §4.1）→ 両 job の script step へ
  明示（1 コミット）。
- **watcher の fresh‑boot flake 修正**（main native run #85 失敗の根因）:
  クールダウンが「未放送」を monotonic 0.0 の既定値で符号化していたため、
  起動 60 秒未満のランナーで初回 rescan 放送が抑制されていました →
  None sentinel 化 + 固定時計の回帰テスト（mutation 検証済み・§4.5）。
- **main 側 CI 障害の解消**: windows integration 3 件（5d18128）・
  clippy 1.99 ドリフト（5fa3679）・ステージングの dir‑move（e6c707d）を
  修正し、実行成功を確認。integration は 3 OS とも native テストを実行する
  構成になりました（import smoke ガード付き）。
- **CI 耐障害性の強化**: 全 apt ステップへ `timeout-minutes: 10` +
  全ジョブへ `timeout-minutes: 60`（run #80 の 6 時間ハング → cancelled
  事案が契機）。actionlint を検証に導入。
- **開発用ファイルの整理**: 計画期間中使用した計測ハーネス
  （`scripts/bench/*.py`・`scripts/l2/`・`znn-cli`）は計画完了に伴い
  ツリーから削除しました（証跡 JSON は `scripts/bench/results/` に残置・
  原文は git 履歴 — docs/BENCH.md 冒頭注記参照）。
- **内部計画識別子の完全除去（2026‑10‑04）**: 計画文書（Plan.md・Plan‑2.md・
  Plan‑3.md）をツリーから削除し（git 履歴に完全保存 — 冒頭注記）、コード・
  CI・ドキュメント・実行時文字列（Rust のエラー/警告メッセージ、ビルドスクリプト
  のログ、CI のジョブサマリとアノテーション、bot コミットメッセージの雛形、
  証跡 JSON の note 欄）から計画文書名と節番号の参照をすべて除去した。
  ユーザーが ComfyUI のサーバーログや UI で内部の計画識別子を目にする経路は
  ゼロになった（Python / Rust / TypeScript の全文字列定数を機械走査して確認。
  配布済みプリビルドバイナリは main での次回 publish‑native-bin 再ビルドで
  反映される）。
- **計画後の保守**: `fix(auth)` — HF キー移行が歴史的な設定 ID も読むようにし、
  表示名統一で永続キーが孤立していた問題を解消（`resolve_setting_key` による
  吸収・`tests/test_auth_key_migration.py`）。`docs` — ユーザー向け文書
  （README×4・USAGE×4）から内部計画参照を除去し、日本語・中国語の表現を
  整備。開発記録（本メモと環境レポート）は Agent/ に保持し、計画文書は
  完了に伴いツリーから削除しました（git 履歴に保存）。

## 6. 現状のキー値（2026‑10‑03 時点）

- **version 0.3.2**（pyproject / package.json / native workspace / web バンドルで
  同期済み。**公開作業はユーザ専任・未実施**）。
- **api_version 6**（4 者同期 — §1.2）。
- **成果物 8 本**（abi3 ×4 + abi3t ×4・合計 34.98 MiB — §5.3）。
  PGO 適用済み = linux‑x86_64 と Windows の GIL 成果物。
- **テスト**: Rust L1 206（znn‑codec）+ 統合 4 + mm‑core 5 /
  pytest 225 passed（native 成果物 + torch あり・2026‑10‑03 実測）・
  ci.yml 相当（成果物なし）では成果物依存テストが設計どおり skip。
- **fuzz 7 ターゲット**（週次日曜 18:00 UTC）。**L5（公式 zipnn 0.5.4 との
  双方向クロス検証）が恒久の互換性ゲート**。
- **ツールチェーン**: CI は Node 26.10.0 / pnpm 12.8.1 / ruff 0.16.9 /
  mypy（pyproject 統合）/ uv。Python floor 3.12・CI の解釈系セルは
  3.12 / 3.14 / 3.15.0‑rc.2（+ free‑threaded）。
- `third_party/` は撤去済み = **mm_core 単一エンジン**。読み取り系経路には
  Python フォールバックが維持されています（§5.1 Phase 8）。

## 7. 残件

- **ユーザ専任**: v0.3.2 の公開作業（GitHub Release・タグ・registry）、
  `demo-assets/` の本キャプチャ差し替え、CI 実行結果確認の指示。
  なお 2026‑10‑05 のフォルダアイコン刷新以降、`hero.webm` /
  `view-folders.avif` 等は刷新前（アンバー icon・開閉アニメ）の姿を写すため、
  差し替えは新 UI 基準で実施します。
- **参照機での計測待ち**: Phase 2 の K2 / K3 再計測（SHA‑NI + NVMe 搭載機）、
  K10 の 5000 モデル ≤100 ms 確認。
- **K11 端到端 ≤40 ms**: processed JSON をルートで直接スピルスする設計は
  `get_model_tensors` の公開契約を変えるため、範囲外と記録済み。
- **実 UI の手動 QA**: USAGE 改訂時に手順を統合済み
  （`__mmNeoPerf` の paint 脚計測が K15 の実測手段）。
- **D4**: native.yml の `3.15.0-rc.2` ピン（`python-version` 9 箇所 +
  コメント 5 箇所）は、actions/python‑versions の manifest に final 版が
  掲載されてから別コミットで振替（PEP 790: rc3 は 2026‑10‑02 実績・final は
  2026‑10‑09 予定）。ft セルは `freethreaded: true` 側で切り替わるため、
  `3.15t` という文字列は書きません。
- **Plan‑2 R5**: fuzz-long.yml の apt（clang + mold）ステップ削除 —
  **完了・検証済み（2026‑10‑07）**: native.yml fuzz-smoke と fuzz-long.yml の
  双方から削除した（mold は -fuse-ld 参照ゼロの不参照・clang は rustc 同梱
  compiler‑rt で不要 = native/.cargo/config.toml の方針どおり）。証跡は三点:
  ① 2026‑10‑04 の週次 run（main@736fbe4・旧ファイル = apt あり）7/7 success
  = R5 の前提「rust‑lld 移行後の初回週次成功」は削除時点で既に充足済み
  （-O + 3 h が rust‑lld で成立し、mold はインストール済みだが不参照）、
  ② dev push の fuzz-smoke（7 ターゲット × 60 s・ASan・-D・clang/mold 無し）
  success、③ PAT から fuzz-long を dev へ hours=1 で dispatch
  （run 37572923805・新ファイル）— 全 7 ジョブ completed success
  （-O ビルド成功 + 1 h 予算完走: 合計 ≈3.25 億 execs・crash/OOM/timeout 0・
  peak RSS 最大 226 MB ≤ 上限 4096・ジョブ毎 ≈65 分）= **clang/mold 不要を
  端到端で実証**し、R5 クローズ。
- **cache‑targets の再考**: native‑build‑linux の `cache-targets: "false"`
  （registry のみキャッシュ）は保留 — cold ビルドの実測を 1 run で計測して
  から判断します。

## 8. セッション 2026‑10‑06 — ハブアップロードのプリフィル導線

- モデル詳細ダイアログの行動列へ **Upload ボタン**を追加（`Upload` lucide）。
  共有 wizard `DialogHfUpload.vue` を `contentProps.initialModel`
  （`{ type, pathIndex, fullname }`）で開く。
- wizard 側は `platform` ステップを維持したまま、hub 選択時にプリフィルが
  あれば `type` / `model` を自動解決（`useModels` キャッシュ優先の
  `fetchModels` 経由）して `upload` フォームへ直飛。**専用画面は不追加**、
  バックエンド無変更。プリフィル対象が消えていた場合は警告トースト
  （`prefillModelMissing`・4 言語）後、通常の手動 wizard へフォールバック。
- 先行例: `SelectionBulkBar.vue` の `files` バッチモードと同じ
  `dialog.open({ key: 'model-manager-hf-upload', ... })` 経路を流用
  （`chooseProvider` のタイトル書換えが同 key を引くため必須）。

## 9. セッション 2026‑10‑05 — フォルダアイコン刷新（Flat Aurora）と SMIL 退役

- **経緯**: デザイン案は 4 案（A–D）→ 詰め 3 案（D2 群）→ モダンフラット進化
  3 案（E1–E3）の順で提示し、ユーザ決定で **E1 "Flat Aurora"**（ペール
  ターコイズの 2 ストップグラデ＋クリスプな半透明ガラス＝フロスト blur 無し
  ＋ファイルシート）を採用。ギャラリーはワークスペース
  `design/folder-icon-proposals*.html` に保存（ID 衝突回避のためインライン
  SVG へサフィックス付与）。
- **資産**: `assets/Folder-Icons/` は最終的に **2 文件** —
  用途名へリネーム済み: `folder-card.svg`（カード）/ `folder-glyph.svg`
  （ブレッドクラムグリフ）。配送キーも `folder-card` / `folder-glyph` で同期。`folder-opening-animation.svg` /
  `folder-closing-animation.svg`（SMIL）と、一旦追加した `folder-hover.svg`
  （スパークル）は削除済み（§1.1 の実機 QA 決定）。
- **コード**: `FolderIcon.vue` = 静的 `<img>` ＋ CSS フロート
  （1.9 s 連続ボブ・`translateY(-5%)`）。1 秒ゲーティングのステートマシンは
  撤去。`py/information.py` の `_SVG_ASSETS` は `folder-card` /
  `folder-glyph` のみ（フォルダ系）。
- **文書**: README / USAGE ×4 言語のフォルダアイコン挙動記述を刷新
  （ホバー＝フロートのみ）。ペールターコイズ採用由来のユーモア
  「_数ある色からペールターコイズを選んだのは、これが **Neo** だからです。_」
  （斜体・パンチライン一行のみ）はユーザ指示の意図的記載。
- **詳細ダイアログ周りの追加改修（2026‑10‑06 続）**: (1) タブの青い選択表示の
  ズレは `TabsList` の `h-9` 対トリガー実高 32px のオーバーフローと、
  active トリガーの `backdrop-blur-md`（transform 済みダイアログ内での描画ズレ
  疑い）が原因 → `h-10` ＋トリガー `h-8` 固定・active blur 撤去で構造的に
  整列。なお実機再指摘（ピル右端が列境界に接し非等間隔）を受け、最終形は
  **等インセットのセグメントコントロール**: TabsList `gap-1` ＋トラック
  `bg-mm-bg/60`（active ピル四周すべて 4px）。(2) 基本情報/Information テーブルの行ホバーでコピーボタン浮上
  （`hooks/clipboard.ts` の `useCopyText` 共有・トースト付き）。行末配置は
  テーブルがパネルから溢れるとボタンも流れて見えなくなるため横スクロールポート
  （`ResponseScroll overflow-x-auto`）へ収容。単一ボタンの左端ピン留めは「1 行
  （垂直中央の行）にしか出ない」との実機指摘を受け撤去し、**行毎の sticky セル**
  （`position: sticky; right: 0`＝溢れる行では表示範囲の右端に固定、収まる行では
  行末）へ再構成。ボタンは `CopyRowButton.vue` へ共有化（fallow dupes 対策）。
  (3) **「ノードをクリップボードへコピー」機能は撤去**（詳細アクション行＋
  カードホバー列のボタン・`copyModelNode`・i18n キー `copyNode` /
  `modelCopied`・README/USAGE 記述すべて）。README へ削除機能節を追加。
- **検証知見**: SVG の視覚検証は **resvg-js**（`@resvg/resvg-js`）を使用。
  cairosvg は SVG フィルタ（feGaussianBlur 等）を silently 無視するため、
  グラスモフィズム表現の検証には**不適**（接地影がぼやけない等で誤判定する）。

## 10. セッション 2026‑10‑07 — ユーザ向け文書の校正・「削除された機能」再構成・CI 簡約・LESS 退役

- **ユーザ向け文書の校正（README×4 / USAGE×4・コミット d08aee4）**:
  (1) `<a id="documentation">` アンカーが「削除された機能: ノードコピー」節の
  直前に誤配置され目次リンクが誤ジャンプしていた → 本来の見出し直下へ移動＋
  `---` 区切り補完。(2)「元版からの変更点」導入の「削除されたのは 2 つ」→
  3 つ（copy-node 節の後追い追加時に導入文が未更新だった）。(3) zh-TW の
  動詞 extended 誤変換「擴充套件」（=拡張パッケージ・名詞）→「擴展」
  （他の 11 箇所は extension の名詞用法で正当なため非変更）。
  (4) USAGE のモデル詳細アクション行ボタン列挙（"The whole action row" =
  網羅表現）に load workflow（v-show=hasPreview・add node と upload to hub の間）
  が欠落 → ソース順どおり追加（4 言語）。(5) 英文の半角ハイフン " - " 4 箇所を
  全角ダッシュへ統一（em-dash 127 箇所に対する逸脱）。数値主張（16 modules /
  42 routes / 5 hash / 7 fuzz / 22 dtype / v0.3.1 / api_version 6）と
  パッケージ差分はフォーク元 v2.8.5 ソースとの一次照合で正確を確認。
  内部リンクは github-slugger 実装で全解決を機械検証。
- **「削除された機能」節の再構成（README×4・コミット 3e78934）**:
  batch scan / copy node の 2 つの H2 を、H2「Removed features」＋ H3 小見出し
  （scan-search / clipboard-x・26px）の 1 セクションへ再構成（What changed 配下
  と同じ階層様式・H3 間の `---` は撤去）。`#removed-features` 新設、目次と
  「元版からの変更点」導入の参照を単一リンクへ集約。既存 deep-link のために
  `#removed-feature` / `#removed-feature-copy-node` は小見出し位置に保持。
- **Plan‑2 R5 完了（コミット 2f751fb・§7 参照）**: native.yml fuzz-smoke と
  fuzz-long.yml の apt（clang + mold）ステップ削除。dev push の fuzz-smoke
  成功（7:49・ステップ一覧に apt 無し）でセル検証済み。さらに PAT からの
  dev dispatch（hours=1・run 37572923805・新ファイル）で全 7 ジョブの
  release+ASan ビルドステップが成功 = -O も clang/mold 不要を実証
  （証跡三点の詳細は §7 R5）。2026‑10‑04 の週次 run（旧ファイル・apt あり・
  main@736fbe4）7/7 success も R5 前提の充足として確認した。native/README の
  「CI の apt ステップも撤去済み」記述はこれで全ジョブに対して真になった。
- **ci.yml の二重 pnpm install 解消（コミット be9e51b）**: Build ステップを
  `pnpm exec vite build` へ（package.json の build スクリプト前置 install は
  ローカル一発実行用。CI では前段の install ステップと重複していた）。
- **LESS 退役（コミット 1970abe）**: `lang="less"` は ModelDescription.vue の
  1 ファイルのみ・内容もネストだけで LESS 固有構文ゼロ（機械走査で実証）→
  `<style module>`（ネイティブ CSS ネスト）へ変換し devDeps から less /
  postcss-less を削除。ビルド出力 CSS は modules ハッシュ正規化後に
  **バイト同一**（67,781 chars・23/23 ルール）= 挙動等価を実証。web/ バンドル
  再ビルドを同梱。K15 ゲート・fallow dead/dupes も PASS。
- **CI 証跡**: dev push（1970abe）で ci.yml verify + native.yml 全ジョブ
  success（fuzz-smoke / integration ×4 / builds ×3 / abi3-import ×4 /
  size-budget・publish は main 専用のため skipped）。native-test のログで
  stable ツールチェーンが **rustc 1.99.0** へ更新されたことを確認
  （dtolnay/rust-toolchain@stable・バージョンピン無しの方針どおり）。
  後日談: ユーザが PR #50 で main へマージ（ec4ddb3・main の CI/native 全緑・
  publish-native-bin が 0dce243 で成果物再ビルド）。新 fuzz-long.yml は main 上の
  ため、2026‑10‑11（日）18:00 UTC の週次 run からは通常運用（3 h 予算）で
  そのまま回る。
- **`ns_to_ms` parity 修正（znn‑codec scan.rs・fix(native) コミット）**:
  v0.3.2 push（036fd74）の native run で macOS integration が 1 件失敗した
  根因は §4.5 の浮動小数点変換の罠（バージョン更新とは無関係の潜在 flake。
  失敗ジョブ再実行は緑・乖離率 ≈1/10,000/タイムスタンプ）。整数商＋余り
  方式へ修正し、CI 観測値の両方向ベクタを回帰テストにピン留め
  （mutation 検証済み）。ローカル検証: rustfmt / clippy -D warnings /
  znn‑codec 206 単体 + 4 統合 全パス（rustc 1.99.0 = CI stable 同版）。

## 11. セッション 2026‑10‑07（夜）— 脆弱性スキャン体制の構築（NEO‑PLAN‑2026‑004）

- **Plan‑4.md（NEO‑PLAN‑2026‑004）を策定し、Step 0–10 を同一セッションで
  完了**した（S5.4/S5.5・A10 = dependabot.yml の発効と初回 PR 確認のみ
  ユーザの dev→main マージ待ち）。詳細な実施記録・証跡・事故と回収は
  **Plan‑4 §10 の「2026‑10‑07（実施）」**が一次ソース。以下は要点のみ。
- **体制（確立済み）**: CodeQL default setup（Extended・JS/TS+.vue・Python・
  Rust build‑none・Actions — ユーザ設定）/ security.yml = OSV‑Scanner
  （PR 差分 + push/週次フル・SARIF・月曜 03:00 UTC）+ zizmor（GHAS モード・
  1.30.1 ピン・online audits）+ gitleaks（v3・fetch‑depth 0・週次全履歴）/
  dependabot.yml（npm・cargo・uv・github‑actions / target dev / cooldown 7 日）/
  uv audit 観察枠（非ブロッキング・UV_MALWARE_CHECK=1 試用）/ ruff S /
  eslint‑plugin‑security 4.2.0 / 全 action SHA ピン（dtolnay のみ ref‑pin 方針）。
- **実測検出は全量対処済み**: source‑map‑js 1.2.1→1.2.2（CVE‑2026‑93749・
  override・**バンドル byte 同一**を実証）/ braces・bincode・paste は
  advisory‑ID スコープの理由付き accept（ignoreUntil 2027‑01‑07 = 四半期
  再レビュー）/ requirements.txt の httpx2/httpcore2 下限シグナル 6 件は
  package@version スコープの ignore（uv.lock 2.13.1 が権威）/ zizmor 142 件
  （template‑injection error 2・artipacked 12・excessive‑permissions 12・
  cache‑poisoning 11・unpinned 60・adhoc 1）→ **online/offline とも
  「No findings to report」**（ignore 13 は全て理由付き記録）。
- **最大の教訓（§1.2 へ規程化済み）**: gitleaks 設定の**偽緑** — allowlist
  のみのカスタム設定が既定ルールを全置換し、ローカルと CI の双方で「no leaks」の
  虚偽報告。発火テスト（PR #53 の 4 プローブ）が初日で捕捉し、
  `[extend] useDefault = true` + ルールスコープ allowlist へ修正（6fdfdb7）。
  修正後の全履歴スキャンがプローブ自体を検出 = 修正と発火の双方を一度に実証。
- **発火テスト証跡（PR #53・クローズ済み）**: osv‑pr failure（braces@3.0.2 =
  GHSA‑grv7‑fg5c‑xmjg）/ gitleaks failure（擬似 api_key・push protection は
  provider pattern のみ阻止するため通過 = 予測どおり）/ zizmor results‑check
  failure（template‑injection）/ CodeQL results‑check failure
  （py/command‑line‑injection）。復元側: PR クローズ + ブランチ削除 +
  prune で dev = gitleaks no leaks・Security success・native 18/18 success
  （1025bbd）。
- **concurrency の落とし穴（2026‑10‑07 実例）**: 失敗 run の
  rerun‑failed‑jobs は**元の run の ref の concurrency グループへ再参加する**
  ため、`cancel‑in‑progress: true` のグループ（native‑refs/heads/dev）では
  旧コミットの再実行が**新コミットの in‑progress run をキャンセルする**。
  flake 検証の再実行は「より新しい run が走っていないこと」を確認してから
  行う（前例: 6fdfdb7 の再実行が dcd5624 の native run を cancelled にした）。
- **CI 側の観察**: CodeQL の main 側 Actions アラート 32 件
  （unpinned‑tag 21 + missing‑workflow‑permissions 11）は dev で解消済み・
  main へのマージ後の再解析で自動クローズされる見込み（要確認）。
  Security run は dev push 7 回連続 success。ci.yml の pytest（3.12）は
  ruff S 導入後も緑（sandbox 3.11 の 1 件失敗は stash 対照で無関係と証明）。
- **Plan‑4 の削除と参照整備（2026‑10‑08）**: 全 Step 完了に伴い Plan‑4.md を
  ツリーから削除（一次記録 = `git show dcd5624:Agent/Plan-4.md`）。コード・
  CI・設定の plan 参照 25 箇所を Agent/ 外ゼロまで整備（機械走査で確認）。
  **osv‑scanner.toml の reason 文字列は osv‑scanner が CI ログへ逐語出力する
  ため文書参照を持たせず自己完結化**した（2026‑10‑04 の実行時文字列除去と
  同一基準。ログ出力される設定値は「実行時文字列」に含めて扱うこと）。
- **K15 内部識別子の残存違反を発見・修正**: locales ×4 の perfMarks 設定
  ラベルが「…（K15）」を保持していた（2026‑10‑04 の走査は .py/.rs/.ts の
  文字列定数を対象にしており **locales JSON が走査範囲外**だった）。除去 +
  web/ 再ビルド済み。**教訓: 識別子除去の機械走査は locales/\*.json を
  必ず含める**。
- **CodeQL アラートの dismiss API**: `dismissed_comment` は **280 文字上限**
  （超過は 422「Only 280 characters are allowed」）。dtolnay の
  unpinned‑tag 7 件を won't fix で dismiss 済み（コメントは zizmor.yml の
  ref‑pin 方針を参照）→ main の open アラート 0。
- **Dependabot は設定発効直後に初回チェックを即時実行する**（schedule を
  待たない）: main マージ当日に 3 PR（pyo3 0.29.3 / torch 2.14.1 /
  development group = frontend‑types 1.56.0 + fallow 3.31.0）が到着し、
  審査のうえ dev へ squash マージ済み（3b2a42a / 3c51783 / cb26b5d）。
  target‑branch dev・groups・typescript ignore・cooldown 7 日の設定準拠を
  全項目実証。マージ後の出荷バンドルは byte 同一（ローカル再ビルド実証）。
  審査基準は「CI 3 ワークフロー緑・diff の妥当性（lockfile 範囲・ソース
  設定維持）・公開日 7 日以上」。uv 系 PR が**実行時依存**（huggingface_hub
  等 4 種）を触る場合のみ requirements.txt の手動同期（D10 規程）が追加で
  必要。
- **残件・監視計画**: ① native run 6fdfdb7 の完走確認（次セッション冒頭）、
  ② main マージ後の Dependabot 初回 PR 形状確認（S5.4/S5.5・A10）、
  ③ zizmor 1.31.0 着弾時の cache‑poisoning ignore 13 件の削除再評価、
  ④ UV_MALWARE_CHECK=1 の native.yml 展開（ci.yml 2 週無事故後）、
  ⑤ uv audit のブロッキング昇格（preview 卒業後）、⑥ osv‑scanner.toml の
  ignoreUntil 2027‑01‑07 三件（braces/httpx2/httpcore2）の四半期再レビュー、
  ⑦ CodeQL PR チェックのしきい値（High or higher）運用観察。
