# 開発メモ — ComfyUI‑Model‑Manager‑Neo

> **2026‑09‑28 再編（ユーザ指示）**: 本ファイルは 19 セッション分の逐語ログ
> （約 2,660 行）だったが、「**これからの実装に必要な永続知識**（§1–§5）+
> **圧縮タイムライン**（§6）」へ再編した。**削除された詳細の逐語原文は git 履歴に
> 完全な形で残る** — 発掘は `git show 88b5e9c:Agent/MEMO.md`（再編直前 tip）。
> 計画・設計根拠は [`Plan.md`](Plan.md)、計測証跡は
> [`../docs/BENCH.md`](../docs/BENCH.md)、実行環境の詳細実測は
> [`environment-report.md`](environment-report.md) が一次ソース。
> **フェーズ番号注記**: 2026‑09‑28 の Phase 7/8 繰り下げ（Plan 版数履歴 2.1）に
> より、それ以前の記録中の「Phase 7」（third_party 撤去・USAGE 改訂・リリース）は
> **現在の Phase 8** を指す。

---

## 1. 恒久規程とユーザ決定（セッション着手時に必読）

### 1.1 ユーザ決定（恒久 — 一次記録は Plan.md、ここは索引）

| 日付       | 決定                                                                                                                                                                                                                                | 一次記録           |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| 2026‑09‑23 | 圧縮率は速度より重要（「せめて 67 % は下回らない」）→ バイト同一による構造的保証で回答（bf16 実測 0.6623）                                                                                                                          | BENCH §6.3         |
| 2026‑09‑23 | `unsafe` はできる限り使わない（virtual‑raw で safe のまま目標超過達成し不使用で決着）                                                                                                                                               | Plan §2.4          |
| 2026‑09‑23 | 上流 issue は起票しない。メモリバグは Neo 内で完全修正を担保                                                                                                                                                                        | BENCH §6.4         |
| 2026‑09‑27 | Phase 5 見送り項目（A3 / watch_roots）は Phase 6 へ移管（→ 実施完了）                                                                                                                                                               | Plan §6.2          |
| 2026‑09‑27 | バイナリサイズ **4 MB/本は「目安」**（絶対条件から降格。合計 ≤20 MB はハード上限のまま。CI ゲートは早期警戒装置として維持）                                                                                                         | Plan §3.3 / §6.3   |
| 2026‑09‑27 | **v0.3.0 の公開作業はユーザ専任**（GitHub Release・タグ publish・registry 公開・main へのマージ PR）。セッションはバージョン同期 + 公開前検証（K16 スモーク）まで                                                                   | Plan §6.3 恒久規程 |
| 2026‑09‑27 | HTTP の Rust 化はしない（reqwest/axum/utoipa 不採用 — 実測根拠は §4.3）                                                                                                                                                             | Plan §3.8          |
| 2026‑09‑27 | extended‑notify は導入しない（notify 8.2 + debouncer‑full 0.7 直接採用 — 根拠は §4.3）                                                                                                                                              | Plan §3.1          |
| 2026‑09‑28 | **Phase 7「ツールチェーン現代化・設定統合」新設（T1–T6）**。旧 Phase 7 は **Phase 8** へ繰り下げ                                                                                                                                    | Plan 版数履歴 2.1  |
| 2026‑09‑28 | **T7 zenwebp 導入 + AGPL‑3.0 ライセンス整備を必須化**。**T8 requests 2 箇所の aiohttp 化**（requests は modelscope_hub の推移的依存として残ることを明記）。**Phase 8 の abi3t ストレッチは削除**（随時対応）                        | Plan 版数履歴 2.2  |
| 2026‑09‑28 | **T7 は一気刷新**（第一段階/第二段階を挿まない — 静止+アニメ+WebP デコードを一括。保安面は先送りでなくゲート化）                                                                                                                    | Plan 版数履歴 2.3  |
| 2026‑09‑28 | **T4（uv 導入）一時撤回 → 復元（撤回の撤回）** — 撤回理由（uv はフロントエンドのパッケージ管理不可）は T4 範囲の誤解: T4 は **Python 開発・CI 層専用**（pnpm/フロントエンドは一切変更なし・現状維持）。範囲確認の上、原文どおり復元 | Plan 版数履歴 2.4  |
| （継続）   | `demo-assets/` はユーザが後で追加する — セッションは触らない                                                                                                                                                                        | ユーザ指示         |
| （継続）   | CI 実行結果の確認は、ユーザが次ターンで指示したときにセッションが行う                                                                                                                                                               | ユーザ指示         |

### 1.2 開発ワークフロー規程

- **cargo 使用方針**（Plan §3.4.3）: `check` 常用 / `test` は必要なときだけ /
  clippy・rustfmt を品質向上に活用 / `build` は最終確認のみ。
- **Rust テスト配置**: 単体 = インライン `#[cfg(test)]`（private 到達可）、
  統合 = `native/crates/znn-codec/tests/`（**公開 API のみ**）、
  差分 = `scripts/l2`、敵対的 = `fuzz/`。
- **push 前検証は「native 成果物あり」と「なし」の両方で pytest**
  （ci.yml = なし・native.yml = あり。なしの再現:
  `mv native/native-bin/<tag>/mm_core.abi3.so /tmp/`）。
- **native.yml で pytest を回す 2 ジョブ**（native‑build‑linux の loader
  regression / integration ×3 OS）**の pip 行は同一内容に保つ**
  （片方だけの追加で同種の失敗が再発する — markdownify が前例）。
- **api_version bump は 4 者同期**: `py/native.py` の [N,N] / mm‑core
  `lib.rs` 定数 + test / native.yml abi3‑import の assert / pytest の 3 アサート。
- **bench 証跡 JSON（`scripts/bench/results/`）は再生成しない**: BENCH 本文が
  参照機の timing 値を逐語引用している。ゲート追加時は**決定的な欄だけ外科的に
  追記**する（前例: `phase6_front.json` の `rowsParity` /
  `tensorTreeRowsIdentical`）。
- **テストは mutation testing で捕捉力まで証明する**（対応する回帰を意図的に
  混ぜて失敗 → 復元して成功）。「アサーションが通る」だけでは甘さを見逃す。
  「接合部」型ギャップ（両端は個別にテスト済みでも接続部が無テスト）が
  繰り返し発生源（2026‑09‑28 の 4 件がその例 — §4.5）。
- **fallow（dead‑code + dupes）は CI ゲート**（ci.yml・2026‑09‑28 追加）。
  push 前に `pnpm fallow:dead` + `pnpm fallow:dupes`。export を消すと
  **戻り型/注釈型が連鎖で unused‑types（warn）に落ちる**ので型も併せて
  private 化すると clean（README 公称「未使用 export ゼロ・重複ゼロ」）。
- **fuzz‑long の再ディスパッチは fuzz 表面が変わったときだけ**。表面不変なら
  既存 run の証跡が有効 + 週次スケジュール（日曜 18:00 UTC・6 ターゲット）が
  担保。**PAT は Actions 権限不足 + dispatch の default‑branch 制約で 403** →
  GitHub UI からの手動ディスパッチはユーザ依頼。
- **GitHub Actions の更新は 1 action ずつ別コミット**（bisect 可能 —
  Plan T6 規程）。
- Plan §6.2 の詳細チェックリストと §9 マスターチェックリストは
  **同一コミットで**更新（Plan §6.3）。
- コミット: 日本語 conventional commits（`type(scope): 概要` + 詳細本文）。
  pre‑commit フック = lint‑staged + `pnpm typecheck`。**環境リセットで pnpm
  shim が消えた場合は `corepack enable --install-directory /usr/local/bin`**
  （さもないとフックが `pnpm: not found` でコミットを落とす）。
- **`core` ダンプをコミットに含めない**（.gitignore 対象外 — `git status` で
  確認）。native‑bin の `.so` は gitignore 対象（CI が main/tag で生成）。
- **セッション冒頭は dev tip を確認する**: 過去に外部からの force‑push
  巻き戻し（c3b7919 事件・2026‑09‑26）の前例あり。復旧は GitHub API +
  ローカル reflog から 12 コミットの SHA 回収・マージで実証済み。
  `.git` 自体を失った場合はリモートから再 clone（コミット済みなら無損失）。

## 2. 開発環境（実測）と再構築手順

### 2.1 スペック（詳細は environment-report.md）

2 vCPU（Skylake‑SP・AVX‑512 あり・**SHA 拡張なし**）/ RAM **1 GiB**（swap なし）/
ディスク ~9.9 GB / Debian 12（ホストカーネル 4.19・Kata VM）/ Python 3.11.2
（`/opt/arena-python`）/ Node v20.20.2 / git 2.39.5。
**12 GB モデル級の KPI 実測は不可能** → ~256 MB 級で実測 + 検証済み外挿を
BENCH に明記する規程（推測でなく「実測 + 外挿」）。絶対値の判定は参照機
（8C/16T・Plan §2.2）。

### 2.2 再構築チェックリスト（セッション冒頭 — **apt/pip/rustup/node_modules はターンをまたいで永続しない**。ワークスペースのファイルは永続する）

1. `apt-get update && apt-get install -y build-essential clang mold libpython3.11-dev curl pkg-config`
2. rustup: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal`
   → `rustup component add rustfmt clippy`（stable 1.98.1 で確認）。
3. pip: `pytest pytest-asyncio aiohttp markdownify huggingface_hub "hf_xet>=1.5.2,<2.0.0" modelscope_hub pillow numpy safetensors ruff mypy pyyaml`
   \+ `torch --index-url https://download.pytorch.org/whl/cpu`
   （torch はフル 176 カバレッジ用 — 無いと 11 件 skip）。
4. `corepack enable --install-directory /usr/local/bin` → リポジトリ root で
   `corepack pnpm install --frozen-lockfile`（pnpm 12.3.4）。
5. dependency‑cruiser 18 は **Node ≥22 必須**（この環境は 20.20.2）→ 公式
   tarball の Node v22.20.0 を /tmp へ展開し `node_modules/.bin/depcruise src`。
6. テスト用 native `.so`: `cd native && CARGO_BUILD_JOBS=1 cargo build -p mm-core`
   → `cp target/debug/libmm_core.so native-bin/linux-x86_64/mm_core.abi3.so`。
   **debug で十分**（api_version ハンドシェーク・全 pytest・bench cross‑check が
   release と同一結果。release は §2.3 の OOM）。
7. （Plan Phase 7 T4 の uv 導入後は、このチェックリストの手順 3–4 が
   `uv sync --frozen` 一発になる — T4 の実益）。

### 2.3 環境の癖（過去セッションで踏んだ罠の一覧）

- **release ビルド（lto=fat + codegen‑units=1）は 1 GiB で OOM（SIGKILL）**。
  cargo は `CARGO_BUILD_JOBS=1`（リンク時 `fork: Cannot allocate memory` 対策。
  release LTO でも -j2 は通ることがあるが不安定）。
- **bash ツールへ渡したファイル内容の中の `"$ARENA_WORKSPACE"` 文字列は
  ワークスペース実体の env 変数へ置換される** — heredoc 内の絶対パスが壊れる。
  スクリプトは相対パス（`cd` して実行）か `os.path.dirname(__file__)`。
- **バックグラウンド実行（`nohup … &`）はツール呼び出しをまたぐと殺される** —
  長時間ビルドは `timeout` 付き同期実行。
- apt の HTTP が 25 KB/s まで劣化することがある → `apt-get --print-uris` +
  Python 並列 DL + dpkg キャッシュ経由で回避。rustup / pip / crates.io /
  GitHub API は高速。
- ディスク: torch + rust stable + nightly + fuzz で ~7 GB 使用。
  **native/target の肥大に注意**（fuzz の target は別ツリー）。
- ワークスペーススナップショットは **`.git`・インストール済みパッケージ・
  node_modules 外の大物（native/target 等は除外リスト）を失いうる** —
  再構築は本節の手順通り。

## 3. 計測方法論（bench スクリプト/テストが「MEMO 2026‑09‑23」として参照する定義）

- **ゲート プロトコル（Phase 1 確立・2026‑09‑23）**: legacy vs native を
  **同一セッションで交互計測**（3 ラウンド）、**steal ゲート**（共有
  2 vCPU ホストの他プロセス汚染ラウンドを破棄して再計測）、判定は
  **側別最小値**、**サブプロセス分離**。2 連続 PASS を要求。
  未ゲート計測は同一設定でも 2–3 倍揺れる。
- **絶対値は共有ランナーでゲートにしない**: K15 bench（`scripts/bench/front/k15.mjs`）
  のゲートは全て**同一実行内比率**（before/after を同一実行で計測）。絶対値は
  env ブロック付きで記録し、判定は参照機（Plan §2.2）。
- 参考: C コアは最静穏窓で bf16/f16 圧縮 ~950–1,030 MB/s に達することがある
  （Rust 静穏窓上限 ~740–790、virtual‑raw 後は未観測）— 交互計測が必須の理由。
- sha2 0.11 の SHA‑256 に **AVX2 バックエンドは無い**（SHA‑NI か soft のみ。
  `x86-avx2` は SHA‑512 専用）→ SHA‑NI 無し機では検証ハッシュ ~156 MB/s が
  e2e の壁（BENCH §7.1 に内訳）。

## 4. 技術知見・教訓（将来の実装に影響する分の蒸留）

### 4.1 ビルド / ツールチェーン / CI

- **prettier は完全な依存ツリーで実行**: prettier‑plugin‑tailwindcss のクラス順は
  tailwindcss 本体 + `tailwindStylesheet`（src/style.css）の解決に依存 →
  `pnpm install --frozen-lockfile` 後の `pnpm format:check` が唯一の正。
- **GH Windows ランナーは core.autocrlf=true でチェックアウト**: rustfmt.toml の
  `newline_style = "Unix"` は全 .rs の fmt ゲートを破壊 → 既定（Auto）+
  `.gitattributes: *.rs text eol=lf` が正解。
- **maturin の universal2 ターゲット名は `universal2-apple-darwin`**。
- **macOS の setup‑python（python.org ビルド）はリンク可能 libpython を持たない**
  （フレームワークのみ）→ `cargo test -p mm-core --no-default-features` は
  macOS 除外（clippy `--all-targets` + ビルド&import 疎通で担保）。
- **Linux から Apple ターゲットへのクロスは PyO3 0.29 で不可**（実測）:
  rustc/pyo3 の `-Wl,-exported_symbols_list`（2 引数形）と
  `-undefined dynamic_lookup` を zig cc が誤変換（zig 0.15.2/0.16.0 双方）。
  macOS ホスト ビルド + lipo が正経路。
- cargo‑zigbuild + zig 0.16 の `ignoring deprecated linker optimization
setting '1'` 警告は**無害**（成果物の glibc ≤2.28 は readelf で確認）。
  `.cargo/config.toml` の mold 設定は zigbuild に影響しない
  （`CARGO_TARGET_*_LINKER` 優先）。
- **PyO3 0.29**: 宣言的 `#[pymodule] mod` 構文が正（関数形は deprecated）。
  `use pyo3::prelude::*;` は mod の**内側**にも必要。**GIL 解放の API 名は
  `py.detach()`**（`allow_threads` ではない — E0599。marker.rs 一次確認。
  `PyErr` は `Ungil` なので `PyResult<T>` 返却可。クロージャへ `&str` 借用を
  持ち込めないため owned 化）。
- **jiter 0.17**: オブジェクト反復は `next_object()` 開始・**後続キーは
  `next_key()`**（next_object 反復は ExpectedSomeValue）。simd‑json 0.18 は
  `ValueAsObject/ValueObjectAccess/ValueAsScalar/ValueAsArray` trait import 必須。
- **bincode: crates.io の `max_stable_version = 3.0.0` は `compile_error!`
  プレースホルダ**（xkcd 2347 型のス쿼ットガード — .crate 展開で確認）→
  **2.0.1 が真の安定版**（Plan §3.1 注記）。
- **macos‑universal2 は fat binary**: サイズ予算は per‑arch スライス判定
  （各 ≤4 MB）+ fat ファイルは 2× 予算。native.yml size‑budget は
  **FAT_MAGIC（cafebabe/cafebabf・big‑endian）の content 判定**（path 非依存 =
  download‑artifact の LCA で `macos-universal2` 断片が消えても堅牢）。
- **huggingface_hub 2.0 は `HfApi.list_models(sort=)` の注解を閉じた Literal に
  狭窄** → `cast(Any, sort)` パターン（`# type: ignore` は
  warn_unused_ignores と hub 未導入環境の双方で割れるため不採用）。
- **テストは POSIX エラー文言に依存しない**（`io_ctx` が全平台で
  「操作 + パス」を付与する形に強化済み）。**Windows の separator**:
  報告パスは `utils.join_path` 統一、テストは normalize 比較。
- CI が書く JSON 証跡は `json.dump(indent=2)` + 末尾改行（prettier ゲート）。

### 4.2 フロントエンド / V8

- **C2 comparator の計測事実（bench ゲートで機械固定）**: V8 は**既定 options の
  `localeCompare`** に内部キャッシュ済み既定 collator の高速経路を持つ →
  hoisted `Intl.Collator` より ×2.1–3.5 **速い**（既定 variant は
  `localeCompare` 維持）。**options 付き**に高速経路は無く `{numeric:true}` は
  hoisted numeric Collator の ×23–33 遅い（numeric variant のみ Collator 化）。
  **この設計判断は CI（Node 22 GH ランナー）の V8 でも再現**（第 8 セッション —
  Plan T2 が Node 更新時の再検証を規定）。
- **shallowRef 移行の手順**: 全消費者の**影響棚卸しを先行**（doc コメントに
  列挙）、読み取り専用 or cloneDeep 後操作のみであることを確認 →
  イミュータブル差し替え（`models.value = {...models.value, [folder]: resData}`）。
  getter watch（`() => modelsData.value[type]`）は ref 自体を追跡するため
  shallowRef でも再代入で発火する。
- **巨大 payload の cloneDeep は隠れコスト**: 65,268 tensors で 218.5 ms +
  87,195 ノード tree で 130.0 ms がダイアログ open 毎、dirty 判定の
  JSON.stringify が毎回 → 読み取り専用表示 payload は**参照共有**
  （保存経路がこれらを送らないことで安全）+ snapshot 除外 + `toRaw()` 経由
  読み取り（Proxy トラップ回避）。端到端 ≈1,589 → ≈13 ms（BENCH §11.3.1）。
- テンソルツリー: Rust pre‑order 線形符号 + JS 遅延インデックス（87k ノードを
  materialize しない）。**描画行の順序は `tensorTreeRowsIdentical` ゲート**が
  legacy fold と機械照合（collapsed + 全展開 152,462 行）。
- SMIL アニメーションの `<img>`（フォルダアイコン）に `decoding="async"` は
  **意図的に非適用**（タイムライン再開挙動が変わる）。`loading="lazy"` は
  仮想スクロール済みのため不導入。
- `scripts/bench/front/k15.mjs` は `--cross-check` 無しなら native 不要・約 30 s
  （縮小パラメータ `--models 1500 --keystrokes 40 --moe-layers 12
--moe-experts 8` で約 6 s）。pnpm ストア外の tsc は `MMNEO_TSC` で渡す。

### 4.3 バックエンド（Python / native 接続）

- **HTTP を Rust 化しない実測根拠（2026‑09‑27 — Plan §3.8 / BENCH §11.4 が参照）**:
  reqwest **0.13.5** は feature 名変更（`rustls-tls` 廃止 → `rustls`）で、
  **aws‑lc‑sys（C/asm・cmake 必須）**+ ring（C/asm）を引き「コンパイラ不要」
  配布哲学と衝突。最小プローブ cdylib（同一 release プロファイル）実測
  **4,886,072 B ≈ 4.9 MB** = HTTP スタックだけで予算の ~1.9 倍超過。依存
  **167 crates**。native‑tls は OpenSSL 動的リンクで zigbuild glibc 2.28 床を
  破壊。huggingface_hub 2.0 は **httpx2 基盤**（PyPI requires_dist 一次確認）→
  Rust 化は「統一」でなく**第 3 スタック追加**。重い HF 転送は hf_xet で既に
  Rust。axum（サーバ FW）/ utoipa（Rust ハンドラ OpenAPI）は aiohttp
  PromptServer 登録モデルに非該当。
- **extended‑notify 不採用の実測根拠（2026‑09‑27 — Plan §3.1 が参照）**:
  0.1.3・単一作者・DL 1,286（notify 本体 1.599 億 / debouncer‑full 1,673 万と
  3 桁以上差）、**debouncer‑full ^0.6 の後ろピン**（現行 0.7.0）、tokio を
  出荷バイナリへ混入。目玉機能は Neo 側で数行代替可（root 再アーム・kind
  フィルタ・ポーリングは **notify 本体の PollWatcher 標準搭載**）。本当に
  必要なのはグルー（inotify 予算管理・network FS 検出・path→type・既定 OFF）
  = `py/watcher.py` 実装済み。
- **aiohttp parity の要点（A3 契約 — `py/http_client.py`）**: requests の
  timeout は `(connect, read‑between‑bytes)` → `ClientTimeout(connect=…,
sock_read=…, total=None)`（**total ではない** — 120 ms 間隔 2 チャンク
  ストリーミングで実測固定）。`HttpStatusError` が `raise_for_status` 文言を
  **逐語再現** + `.response.status_code` 維持（Civitai 401 誘導文が依存）。
  JSON は **content‑type を検査しない**（`content_type=None` — ModelScope CDN が
  octet‑stream で返す実例）。宣言 charset 尊重 + 未知 codec は UTF‑8 degrade
  （LookupError 捕捉）。`trust_env=True`（プロキシ環境変数）。共有セッションは
  **ループ変化を検出して再作成**（本番の None→生成は await を挟まず同期
  アトミック = 並発初回呼び出しでも安全。pytest は autouse `close_session()`）。
- **`requests` は modelscope_hub の推移的依存**（`pip show requests` 実測:
  `Required-by: modelscope-hub`）— Neo の直接使用ゼロ化後も環境に残る。
  requirements.txt は不変（T8 のメリットは依存削減でなく構造:
  IO プール専有解消・方針一元化・テスト可能性）。
- **io プール枯渇クラス**（A3/T8/A1 の動機）: 8 本の io ワーカーでの
  ブロッキング HTTP は、遅い CDN で read timeout（最大 120 s）分スロットを
  専有 → scan/hygiene/preview が連鎖的に遅れる。ネットワーク待ちはイベント
  ループ、executor には CPU 段のみ。同クラス: model‑info ルートの
  executor 化（A1）、watcher arm/release の executor 化、resume seeding の
  executor 化（Phase 5 監査 #1）。
- **GIL 規律**: 長時間/ブロッキング native API は `py.detach()` で解放
  （違反の前例: walk_models/move_with_sidecars — 2026‑09‑26 修正、
  `test_walk_models_releases_the_gil` で機械固定）。**watcher の arm/release は
  executor 経由、poll はループ上**（mutex swap + 小 JSON = 安い、が設計意図）。
  Python 側の重い段（hash/PIL/ヘッダ解析）は executor。
- **O(n²) の教訓（Phase 5 実装中に発見・修正）**: `parse_header_json` の重複
  テンソル名検査が `iter().any/position`（O(n)/テンソル）→ 64,491 テンソル MoE
  で native が **6,098 ms = legacy 334 ms の ×18 退行**。`HashMap<name, pos>`
  O(1) last‑wins へ修正 → 212 ms（legacy 比 ×1.58 速）。**compress も共有
  経路**なので 6 s → 数十 ms。教訓: **native 化は自動では速くならない —
  実規模での端到端計測が必須**。
- **ヘッダ解析は 1 ルート**: `get_model_header` が metadata+tensors+tree を
  一度に返す + `(mtime_ns, size)` スタンプ ガード（2 回の native 呼び出し間に
  ファイルが差し替わると tree を落とす — フロントの leaf 数検査
  `leaves.length === tensors.length` と二重）。
- **watcher 設計定数**（テストから monkeypatch 可能な module 定数）:
  `SETTING_TTL=5.0` / `TYPE_COOLDOWN=2.0` / `DEGRADE_RETRY=600` /
  `MOUNTINFO_TTL=60`。rescan/type のクールダウンは**消費されたシグナルを
  意図的に間引く**（30 s TTL が correctness の床）。シングルトン
  `watcher.watcher` とクラス `ModelWatcher` は分離済み。
- **request 無しでの設定読み取り**: ComfyUI `get_request_user_id` は
  single‑user で request に触れない（app/user_manager.py 一次確認）→
  background task は `request=None` で読める。`--multi-user` では例外 →
  既定値（OFF）へ degrade = 安全側。
- **設定 ID 文字列は ComfyUI が永続化するキーなので改名禁止**
  （`ModelManager.Scan.*` 系 — 改名は既存インストールの保存値を孤立させる）。
  解決は `resolve_setting_key`（`scan.watch_model_folders` →
  `ModelManager.Scan.WatchModelFolders`）。
- **既知の非バグ事項**: `decompressedTensors` は native=実デコード数 /
  legacy=infos エントリ数（ゴースト infos の壊れファイルでのみ差）。legacy の
  「dst 存在チェック後の競合」は native の create_new で構造的に解消済み
  （legacy は Phase 8 で消滅）。サーバ kill 中のジョブスレッドは道連れで死ぬ
  （tmp 残りは起動時クリーンアップの 15 分規則が回収。コミット済み成果物は
  rename 原子性で不整合にならない）。
- **T1 の対象（upload preflight ハッシュ）**: `upload_hf.py hash_local_file` は
  Python hashlib の 1 MiB ループで **io_executor 上で走る**（CPU 作業 —
  プール意味論的にも cpu 側が正）。hashlib も OpenSSL 経由で SHA 拡張を使う
  ため純速度差は小さい（BENCH §10.2: SHA‑NI 無し機で native 5 表記
  1239 MB/s vs legacy sha256 単体 1442 MB/s）— 実益はループ除去・経路統一・
  GIL 解放。チャンク毎 `report_progress(PHASE_HASH)` の扱いが設計判断
  （Plan T1）。

### 4.4 ファジング

- **blob_decompress OOM（fuzz‑long run 1・2026‑09‑25）の根因 = コード欠陥では
  ない**: libFuzzer の `rss_limit_mb` 到達。live heap ~25 MB で、実体は
  **アロケータのページ保持**（exec 毎の Vec churn + ASan quarantine 256 MB 級 +
  OS への遅い返却）が ~5,000 万 exec で累積。対策 3 点: 出力バッファの
  **thread_local grow‑only 化**（パイプライン K1 と同型）+
  `ASAN_OPTIONS=quarantine_size_mb=32:release_to_os_interval_ms=200`
  （cargo‑fuzz は自前の `detect_odr_violation=0` を**追記**するだけで環境変数は
  子へ到達 — 実地確認済み）+ `rss_limit_mb` 4096。OOM 入力（88 B）は
  `corpus/blob_decompress/oom-2026-09-25.bin` として回帰シード化。
- **トリアージ注意**: libFuzzer の OOM レポートは **stderr のみで `crash-*`
  アーティファクトを残さない**（アーティファクト 0 件でもジョブログを読む）。
- 現行ターゲット **6**: `huf_decompress` / `zn_header` / `codec_decompress` /
  `st_parse` / `blob_decompress`（キャップ 1 MiB で駆動）/ `delta_decompress`。
  **T7 で 7 本目（敵対的 WebP → デコード経路）を追加** — native.yml の
  fuzz‑smoke ループ（6 ハードコード）と fuzz‑long.yml の matrix を
  **同一コミットで**拡張（Plan T7 ゲート欄）。
- 証跡: run 3 完走で Phase 1 完了条件消化、run 5 全 7 ジョブ SUCCESS、
  **run 6 = 18 h 証跡は codec 無変更の間有効**。fuzz 表面を変えたのは
  Phase 4（8 平面/trunc/dtype 表 → run 6 をディスパッチした理由）。

### 4.5 テスト規律

- **ゴールデン parity 規程**: 同一 fixture を**両エンジン**（`MM_NATIVE=0/1`）で
  → `native == legacy` を完全構造比較（scan/hygiene/header/hash/walk/move/
  batch）。byte‑exact 復元は sha256 で検証。
- **MockHub パターン**（`test_phase6_http.py`）: 実 aiohttp TestServer +
  `calls` 記録で**往復回数と順序**まで固定（ライブ API 依存ゼロ・
  録画フィクスチャの陳腐化なし）。
- **fake core 注入パターン**: `monkeypatch.setattr(service, "_core", ...)` /
  `monkeypatch.setattr(download.native, "core_if_enabled", ...)` →
  **native バイナリ無しで** inline‑hash / watcher 経路をテスト可能
  （= ci.yml の成果物なし環境でもカバーされる）。
- **`download_model_file_http` を直接駆動するテストは
  `md.get_task_status(task_id).status = "doing"` が必須**（TaskStatus 既定
  `"pause"` だと書き込みループが協調ポーズで即 break → 0 バイト）。
- watcher テストは必ず**新しい `ModelWatcher` インスタンス**で作る
  （シングルトンを汚すとクールダウン状態が持ち越される）。
- executor 配置の検証は**スレッド ident 記録**で決定論的に
  （`test_arm_and_release_run_off_the_event_loop` パターン: start/stop は
  executor、poll はループ上）。
- cancel 伝播の待機は**条件ベース**（`asyncio.wait_for(event.wait(), timeout)`）
  — 固定回数の `sleep(0)` ループは回数依存で理論上 flaky。
- `stubs.py` は ComfyUI master のセマンティクスをミラー（2026‑09‑23 再検証。
  `safetensors_header` の <8 B ガード差は文書化済み — 呼び出し側の
  `except Exception` が両者を同じ結果へ写像）。`write_safetensors` は
  バイト制御された正準 writer（8 バイト整列・`__metadata__` 先頭・
  insertion/sort 両順）— torch 往復では書けない「非ソート順ファイルの
  byte‑exact 復元」をテスト可能にしているのはこれ。
- 2026‑09‑28 のテスト精査で追加した 4 件（download ループガード端到端 /
  `.tmp` フィルタ接合部 / type_matcher sibling‑prefix / cancel 条件待ち）は
  全て mutation 検証済み。「**接合部**」（両端は個別テスト済みでも接続部が
  無テスト）を探せ。

## 5. 現状と残件（2026‑09‑28 再編時点）

- **Phase 0–6 完了**（詳細と完了条件の照合は Plan §9）。キー値:
  api_version **5**（4 者同期）/ release `.so` **3,139,424 B = 4 MB 目安の
  75 %**（libpython 非依存・zigbuild glibc 2.28）/ Rust L1 **195** + 統合 **4** +
  mm‑core **5** / pytest **176**（native+torch）・**59 + 117 skip**（成果物なし =
  ci.yml 相当）/ K15 達成（keystroke JS 作業 p95 3.96 ms ≤ 16 ms・テンソルツリー
  ×104）/ fuzz run 6（18 h）証跡は codec 無変更の間有効。
- **Phase 7 未着手**（T1–T8 — 各項目のタスク・一次実測・ゲートは Plan §6.2）。
- **Phase 8 未着手**（third_party 撤去・配布仕上げ・v0.3.0 公開準備。着手ゲート:
  L5 クロス検証 CI が 2 リリースサイクル連続 green）。
- 残件（全セッション共通で持ち越し）: Phase 2 **K2/K3 の参照機再計測**、
  **K10** 5000 モデル ≤100 ms の参照機確認、**K11 端到端 ≤40 ms**（processed
  JSON をルートで直接スピルスする設計 = `get_model_tensors` の公開契約を変える
  ため**範囲外と記録済み**）、**実 UI 手動 QA**（Phase 8 の USAGE 改訂時に
  統合 — `__mmNeoPerf` の paint 脚計測が K15 実測手段）、**demo‑assets**
  （ユーザが後で追加）。
- CI: ci.yml に **fallow ゲート**（2026‑09‑28 追加）と **K15 bench**
  （`tensorTreeRowsIdentical` 含む）、native.yml に **tensor‑tree cross‑check**
  が常設。dev tip は 2026‑09‑28 時点で全緑。

## 6. セッション タイムライン（圧縮版 — 逐語原文は `git show 88b5e9c:Agent/MEMO.md`）

「第 N」は旧 MEMO のセッション番号（Plan 等の「MEMO 第 8 セッション」参照は
この表で解決する）。実装・計測の詳細は Plan §9 / BENCH / 各コミットメッセージが
一次記録。

| #     | 日付       | 概要                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | 2026‑09‑23 | 環境把握 + コードベース精読。**Phase 0**: native ワークスペース雛形・CI（native.yml 新設）・bench 基盤 + BENCH・`py/native.py` ローダー + `MM_NATIVE`・A1 executor 化・JSON パーサ確定（**jiter** 10.6 vs simd‑json 187.6 vs serde_json 143.6 ms）。ツールチェーン知見 → §4.1                                                                                                                                                                                                                                                                                                                                                                                                     |
| 2     | 2026‑09‑23 | 並行独立検証（採用ツリーを再実行・全緑）+ Phase 0 精密監査 + 実装差分クロス監査。補完コミット群                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 3     | 2026‑09‑23 | **Phase 1**: znn‑codec フォーマット中核（ZN ヘッダ・ビット並べ替え・平面分割・huff0/FSE・チャンク並列）— L2 ゴールデン **9,880/9,880 バイト同一**。ユーザ判断 3 件（§1.1）。**virtual‑raw 平面**最適化で 8/8 指標 C 超え                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 4     | 2026‑09‑24 | **Phase 2**: safetensors 圧縮/解凍パイプライン + バックエンド接続（ジョブ API・ws 契約・stats 形状は legacy 完全互換）。実装バグ 6 件の教訓（ジョブ完了競合・paranoid 二重計上・metadata 不在キー・割り当て爆弾キャップ・sha2 バックエンド・並列ハッシャ逆効果）→ §4。CI 修復 3 件                                                                                                                                                                                                                                                                                                                                                                                                |
| 5     | 2026‑09‑25 | Phase 2 精査（5 件修正）+ 実証監査バッテリー ALL CLEAN。**fuzz‑long run 1 の blob_decompress OOM 根因特定・修正**（→ §4.4）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 6     | 2026‑09‑25 | fuzz run 2 失敗の真因（rss_limit 側）修正 → **run 3 完走 = Phase 1 完了条件消化**。**Phase 3**: デルタ圧縮（1 MiB ストリーミング XOR・公式 streaming コンテナ連鎖・`.neo-delta.json` サイドカー）+ バッチプリミティブ（walk_models/move_with_sidecars）。付録 C SEGFAULT クラス解消実証（K5）・api_version 3                                                                                                                                                                                                                                                                                                                                                                      |
| 7     | 2026‑09‑26 | **重大: dev が c3b7919 へ force‑push 巻き戻し** → 12 コミット SHA 回収・マージ復元（→ §1.2 の tip 確認規程）。Phase 3 独立監査: **GIL 解放修正**（walk/move — PyO3 0.29 `py.detach()`、A/B テストで機械固定）→ §4.1                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 第 2  | 2026‑09‑26 | fuzz run 5 監視（全 7 ジョブ SUCCESS 消化）+ **Phase 0–3 最終バグチェック**（delta verify スイッチ 1 件修正 + negative findings）。run 6 不ディスパッチ判断（表面不変）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| 第 3  | 2026‑09‑26 | **Phase 4**: dtype 大幅拡張（safetensors 0.8 全 22 種・8 平面分割・Neo 拡張帯 128–146・truncation 正式実装）— K14 達成。complex64=コード 130 実証（公式 0.5.4 にコード 9 の arm が無い = L5 E2）。run 6 ディスパッチ（18 h）                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| 第 4  | 2026‑09‑26 | Phase 4 CI 確認 + 独立精査: 堅牢化 3 件（confirmSingleZipnn 競合 → confirmEpoch / inspect_safetensors_dtypes 非 object ヘッダ / znnInfo 壊れ JSON）+ negative findings                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 第 5  | 2026‑09‑26 | リポジトリ整理（参照ゼロ確認の上 3 件削除）+ **cargo 使用方針の規程化（Plan §3.4.3）** + `native/crates/znn-codec/tests/` 新設（extended_band 統合 4 テスト）+ ドキュメント記入漏れの完全解消                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 第 6  | 2026‑09‑27 | **Phase 5**: scan / 永続インデックス / hash 5 表記 1 パス / ヘッダ解析 / `models_changed` 更新伝播 — K7–K11 達成（scan 5000 モデル 0.145 s = ×7.5・native==legacy parity）。**O(n²) 重大バグ発見・修正（MoE 6 s → 212 ms）**→ §4.3。api_version 4。macOS universal2 サイズゲート修正（per‑slice + FAT_MAGIC 判定）→ §4.1                                                                                                                                                                                                                                                                                                                                                          |
| 第 7  | 2026‑09‑27 | CI 全緑確認 + **ユーザ決定 5 件の Plan 反映** + **reqwest / extended‑notify の実測証跡**（→ §4.3 — Plan §3.8/§3.1・BENCH §11.4 が参照する一次記録）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 第 8  | 2026‑09‑27 | Phase 5 最終バグチェック（**6 件修正**: resume seeding のループ停止 / lost handle / 永続インデックス無限成長 / 非 UTF‑8 md でフォルダ一覧全滅 / subFolder 破壊 / create‑folder 未伝播 — 全て回帰テスト化）。**Phase 6 完全実装**（C1–C5・テンソルツリー Rust 事前グループ化 + 遅延インデックス ×104・A3 aiohttp 統一 17 テスト・watch_roots 12+4 テスト — K15 達成・api_version 5）。push 後 CI 失敗 2 件修復（skip ガード欠落・markdownify pip 行）+ **独立精査 10 件修正**（executor 化・ロック順序・pending 上限・設定キャッシュ・孤児 cancel・cloneDeep 相殺・charset・mark 実体化・stale payload・validator 15 ケース）。**C2 設計判断の CI ランナー再現**（Plan T2 が参照） |
| 第 9  | 2026‑09‑27 | **Phase 6 最終バグチェック: 機能バグ 0 件**（fresh eyes の negative findings 全領域）。**`tensorTreeRowsIdentical` ゲート新設**（描画行 = collapsed 1 + 全展開 152,462 行を legacy fold と機械照合）。**fallow「未使用 export ゼロ」回復**（13 export + 型 4 を private 化・連鎖含む）+ **fallow の CI ゲート化**。**release ビルドが 1 GiB で OOM → debug .so 規程**（§2.2/§2.3）                                                                                                                                                                                                                                                                                                |
| 第 10 | 2026‑09‑28 | CI 完了確認（CI #140/141・native #51/52 — native #51 全 14 ジョブ緑。fallow バイナリのランナ動作も実証）。**テストコード精査: テストバグ 0 件・甘さ 4 件修正**（download 書き込みループガードの端到端化 / `.tmp` フィルタ接合部 / type_matcher sibling‑prefix / cancel 条件ベース待ち — 全て mutation 検証）→ §4.5                                                                                                                                                                                                                                                                                                                                                                |
| 第 11 | 2026‑09‑28 | **Plan: Phase 7「ツールチェーン現代化・設定統合」新設（T1–T6）+ 旧 Phase 7 → Phase 8 繰り下げ**（§6.1/§7 リスク表/§9/相互参照 5 箇所を同期）。**T7 zenwebp + ライセンス整備 / T8 requests 2 箇所 aiohttp 化を追加・Phase 8 abi3t ストレッチ削除**。「v1」用語を初版/第一段階へ統一。整合性一掃（生きた Phase 7 参照 5 箇所を Phase 8 へ）                                                                                                                                                                                                                                                                                                                                         |
| 第 12 | 2026‑09‑28 | **T7 を一気刷新へ改訂**（段階分け廃止 — 静止エンコード + アニメ WebP 保持 + WebP デコードを一括。保安面は L3 fuzz 新ターゲット + デコード parity + 上流 fuzz 精査の**前提条件化**。fuzz 6 ハードコード 2 ワークフローの同期点を明記）。ドキュメント整合性最終チェック（残存「段階」言及は全て意図的と判定）                                                                                                                                                                                                                                                                                                                                                                       |
| 第 13 | 2026‑09‑28 | **MEMO 全面再編（本再編）**: 逐語ログ 2,661 行 → 永続知識（§1–§5）+ 圧縮タイムライン（§6）。原文は git 履歴（`88b5e9c`）から復元可能                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| 第 14 | 2026‑09‑28 | **T4（uv 導入）撤回（984f48a）→ 同日復元（撤回の撤回）**: 撤回理由「uv ではフロントエンドのパッケージ管理ができない」は T4 の対象範囲の誤解 — T4 の範囲は元来 **Python の開発・CI 層専用**（pip 置換 + uv.lock。pnpm/フロントエンドは一切変更なし・現状維持）。ユーザの範囲確認（「フロントエンドの懸念のみ」）を受け Plan/MEMO を 25a7f00 から原文復元（完了条件 8 項目・T6 の setup-uv・§2.2 手順 7 も復活）。撤回→復元の経緯は Plan 版数履歴 2.4 + git 履歴（984f48a）に記録                                                                                                                                                                                                   |
