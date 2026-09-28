<!-- 開発中に書き留めておきたい事柄や、気づいたことなどを自由にメモしてください -->

# 開発メモ（Phase 0 着手）

## 2026-09-23 — 環境把握とコードベース精読メモ

### 実行環境（実測）

- 2 vCPU（Skylake-SP、AVX-512 あり、**SHA 拡張なし**）/ RAM 1 GiB / swap なし / ディスク空き 9.3 GB。
- Debian 12、Python 3.11.2（`/opt/arena-python`）、Node v20.20.2。
- rustc / cargo / gcc / clang / mold / curl / wget は**未インストール**（必要に応じて apt / rustup で導入。
  セッション中は永続するがスナップショットには残らない = 検証は CI でも行う）。
- **制約**: RAM 1 GiB のため「12 GB モデル」級の KPI 実測は不可能。
  → 安全なサイズ（〜256 MB 級）で実測し、スケーリング則（ピーク RAM ≈ 2×、デルタ ≈ 4–5×）を
  実測で確認したうえで外挿値を `docs/BENCH.md` に明記する（推測ではなく「実測 + 検証済み外挿」）。
  KPI 目標の照合環境は計画書通り「8C/16T デスクトップ」なので、bench スクリプトは
  `scripts/bench/` に再利用可能形でコミットし、参照機での再計測を可能にする。

### コードベース読解で確認した事実（Plan.md の記載と突き合わせ済み）

- `py/manager.py` の `GET /model-manager/model/{type}/{index}/{filename}`（get_model_info ルート）は
  `self.get_model_info(model_path)` を**イベントループ上で同期実行**していた（Quick Win A1 の対象）。
  scan / hygiene / update の各ルートは既に `loop.run_in_executor(utils.io_executor(), ...)` 化済みで、
  修正パターンは確立している。
- `py/utils.py` の `get_model_metadata` / `get_model_tensors` は `comfy.utils.safetensors_header`
  （ComfyUI 本体 API）+ `json.loads`。max_size はそれぞれ 1 MB / 32 MB。
- `py/compress.py`:
  - `compress_safetensors` はテンソルごとに `ZipNN(input_format="torch")`、`tensor.clone()` してから圧縮
    （C コアが入力を in-place 破壊するため）。全テンソルを RAM dict に保持 → `save_file`（ピーク ≈ 2×）。
  - `_delta_aligned_bytes` は両ファイル全文 `f.read()` + ヘッダー空間パディング + `ZipNN(bytearray_dtype="float32", delta_compressed_type="byte")`（ピーク ≈ 4–5×）。
  - メタデータキー `znn_neo_original_bytes`（ZNN_ORIGINAL_SIZE_KEY）、デルタサイドカー `.neo-delta.json`
    （キー `basePad` / `ftPad`）。ws イベント `update_zipnn_progress` / `zipnn_complete`。
  - stats キー: `originalBytes` / `compressedBytes` / `tensors` / `compressedTensors`。
- `py/download.py`: `_sha256_of` は 1 MB チャンクのフル再読込（Civitai 検証、L529 で cpu_executor 実行）。
  ダウンロード本体は `iter_chunked(8192)`（L680）。
- `py/identify.py`: `compute_hashes` が 1 パスで SHA256 / AutoV2 / AutoV1（offset 0x100000 + 64 KiB 窓）/
  CRC32（Civitai 表記 = バイト反転）/ BLAKE3（任意）。
- vendored ZipNN（third_party/zipnn 0.5.4）:
  - C コア呼び出しは `zipnn_core.zipnn_core(header, ba, num_buf, bit_reorder, byte_reorder, is_review, chunk, threshold, check_th, threads)` /
    `zipnn_core.combine_dtype(payload, num_buf, bit_reorder, byte_reorder, chunk, orig_len, threads)`。
  - 既定 threads = `min(cpu_count, 16)`、chunk = 256 KB（FP8 のみ min(128 KB, chunk)）、threshold 0.95、
    check_th_after_percent=10（C 側で無効化済み）。
  - dtype コード表（util_header.py）: FLOAT32=1, FLOAT=2, FLOAT64=3, FLOAT16=4, HALF=5, BFLOAT16=6,
    COMPLEX32=7, CHALF=8, COMPLEX64=9, CFLOAT=10, COMPLEX128=11, CDOUBLE=12, UINT8=13, UINT16=14,
    UINT32=15, UINT64=16, INT8=17, INT16=18, SHORT=19, INT32=20, INT=21, INT64=22, LONG=23, BOOL=24,
    QUINT8=25, QINT8=26, QINT32=27, QUINT4X2=28, FLOAT8_E4M3FN=29, FLOAT8_E5M2=30。
    → Plan §4.6.3 の「上流互換帯 1–30」と一致。Neo 拡張帯 128–255 と衝突しない。
  - プリビルド `.so` は cpython-310〜315 ×6（linux-x86_64 のみ、計 ~620 KB）。
    この環境の Python 3.11.2 に対応する `.so` があり、**C コアを直接呼んでベースライン計測できる**。
- CI（.github/workflows/ci.yml）は `push: branches: [main]` + `pull_request` のみ。
  dev への push では走らない → Phase 0 で追加する native CI は dev でもトリガーし、
  既存 ci.yml にも dev トリガーを追加する（ジョブ内容は不変）。
- `.gitignore` は `*.so` / `target/` / `lib/` / `build/` を無視（third_party は `!` 例外で再包含）。
  → `native/target/` は自動的に無視される。将来 native-bin をコミットする際は
  third_party と同様の `!` 例外が必要（Phase 7 のメモ）。
- `.prettierignore` に native/target 系の除外はない → Rust ビルド生成物が prettier に拾われないよう
  `native/target/` を追加する。
- husky pre-commit は lint-staged + `pnpm typecheck`。この環境では node_modules なしのため
  `--no-verify` でコミットし、同等の検査（ruff / prettier / cargo fmt・clippy）はローカル + CI で担保する。
- mypy.ini の files 列挙に `py/native.py` を追加する必要がある。
- `.fallowrc.json` の ignorePatterns に `native/**` を追加する（Rust は TS モジュールグラフ外）。

### リモート CI 状態の調査結果（2026-09-23、GitHub API で確認）

- **現 CI は main / dev とも `Format`（prettier --check）ステップで red**。
  原因は Web アップロード由来の 3 ファイル（lint-staged を通っていない）:
  - `Agent/environment-report.md`（表の再パディング等 106 行 diff）
  - `src/components/ResponseScroll.vue` / `ResponseSelect.vue`
    （`size-full scrollbar-none overflow-auto` → tailwind クラス順のみ。挙動影響なし）
  - `Agent/Plan.md` も同様に未整形だった（進捗マーク編集を機に正規化）。
    → いずれもリポジトリ自身のツール（prettier 3.9.6 = lockfile ピン）で `--write` して修復する。
- dev ブランチでの CI 実行は `pull_request` イベント経由（ユーザーの運用は dev→main PR マージ。
  PR #1 / #2 ともマージ済みで main == dev == 82adaf9 系）。
- **旧 `native` ワークフローの残骸**: 2026-09-22 に別セッションが dev@9f1e564 で
  native.yml（native-test×3OS / native-cross / native-diff / integration）を push していた履歴が
  Actions に残っている（現在のブランチには存在せず、GitHub 上の workflow 定義は active 表示のまま）。
  その run から確認できた**成功実績**（今回 CI 設計の参考にする）:
  - `dtolnay/rust-toolchain@stable` + `Swatinem/rust-cache@v2 (workspaces: native)` ✓
  - ubuntu での `apt-get install -y clang mold` ✓
  - `pipx install cargo-zigbuild` + `pip install ziglang maturin` による
    linux-x86_64 / linux-aarch64（glibc 2.28）クロスビルド + サイズゲート ✓
  - 失敗していたのは windows の `cargo fmt --check`、macos の `cargo test`、
    ubuntu integration のビルド等（旧実装コード側の問題。Phase 1+ の内容だった）。
  - 旧実装は Phase 1–3 相当（fuzz・差分テスト・integration pytest）まで含んでいたが、
    ユーザーがブランチを Web 再アップロードでリセットし、Plan v2.0 で Phase 0 から
    やり直す指示 → **今回は Phase 0 の範囲を厳守する**。
- **Windows の import サフィックス注意**: Windows の `EXTENSION_SUFFIXES` は `['.pyd']` のみで
  `.abi3.pyd` は import できない（Linux/macOS は `.abi3.so` が有効）。
  Plan §4.2.1 の `windows-x86_64/mm_core.abi3.pyd` はそのままでは動かないため、
  成果物は `native-bin/windows-x86_64/mm_core.pyd` とする（ズレは Plan 側に注記）。

### Phase 0 作業手順（自分用チェックリスト）

1. [x] 環境構築: apt（build-essential / clang / mold）+ rustup + zig（cargo-zigbuild）+ pip（maturin / ruff / mypy ほか）
2. [x] crate バージョンの一次情報再確認（crates.io API、計画書末尾の指示）→ **Plan 確認値と完全一致**
3. [x] Quick Win A1（py/manager.py の executor 化）→ ruff / mypy → 単独コミット（047568b）
4. [x] native/ ワークスペース雛形（znn-codec / mm-core / znn-cli / json-bench）+ mold / rustfmt / clippy 設定
5. [x] ローカルビルド疎通 + サイズ実測（linux x86_64/aarch64 = zigbuild glibc2.28 verified、windows-msvc/macos = CI 検証）
6. [x] import 疎通テスト（linux x86_64、Python 3.11.2 + CI で 3.10/3.13 の abi3 疎通）
7. [x] py/native.py ローダー + MM_NATIVE スイッチ（4 モード機能確認済み）
8. [x] JSON パーサ確定ベンチ（**jiter 10.6ms vs simd-json 187.6ms vs serde_json 143.6ms → jiter 確定**）
9. [x] scripts/bench/ 一式 + KPI ベースライン計測 → docs/BENCH.md
10. [x] CI（native.yml 新規 + ci.yml に dev トリガー追加）+ package.json rs:\* スクリプト
11. [x] Plan.md 進捗マーク更新（§6.2 と §9 を同一コミットで）+ MEMO 追記
12. [x] dev へコミット & プッシュ → CI 緑を確認（GitHub API でウォッチ）

### Phase 0 完了記録（2026‑09‑23）

- **CI 全緑**（native.yml @ dev 81854f5）: native-test（ubuntu/windows/macos:
  fmt・clippy `-D warnings`・test）、native-build-linux（zigbuild ×2 + glibc 2.28
  ゲート + import 疎通）、native-build-macos（universal2 + lipo + import）、
  native-build-windows（MSVC + import）、abi3-import（**CPython 3.10 と 3.13** で
  同一 .so 疎通 = abi3 主張の機械的検証）、size-budget（4 本計 1,624,112 B ≤ 20 MB）。
  既存 ci.yml も dev@81854f5 で緑（Format 修復完了）。
- 成果物サイズ（CI 実測）: linux-x86_64 410,416 B / linux-aarch64 383,824 B /
  windows-x86_64 163,840 B / macos-universal2 666,032 B — 全て予算 4 MB の 1/6 以下。
- コミット構成（dev）: 047568b（A1 単独）→ 71a4ce3（prettier 正規化 + dev トリガー +
  進捗マーク）→ 99b3727（native ワークスペース + CI + ローダー）→ 16cb759（bench +
  BENCH.md）→ 5bfca37（tailwind クラス順正規化）→ 81854f5（CI 3 件修復）→
  最終（Plan [x] + BENCH §5 CI 実測反映）。
- **Phase 1 着手時の申し送り**: BENCH.md §6 の観察（特に get_model_metadata の
  1 MiB ガード問題、e2e 律速の内訳、デルタ倍率 5.4x）と、本 MEMO の
  クロスビルド/ツールチェーン知見を参照のこと。

### Phase 0 実施中に得た知見・教訓（重要）

- **prettier は完全な依存ツリーで実行すること**: prettier-plugin-tailwindcss の
  クラス順は tailwindcss 本体 + `tailwindStylesheet`（src/style.css のカスタム
  ユーティリティ）の解決に依存する。prettier 単体インストールでは
  ResponseScroll/Select.vue のクラス順が CI と食い違った（`scrollbar-none` は
  カスタムユーティリティで、完全解決時は `size-full` の**後**が正）。
  → `pnpm install --frozen-lockfile` 後の `pnpm format:check` が唯一の正。
- **GH Windows ランナーは core.autocrlf=true でチェックアウト**する → rustfmt.toml の
  `newline_style = "Unix"` は全 .rs で fmt ゲートを破壊する。既定（Auto）+
  `.gitattributes: *.rs text eol=lf` の組み合わせが正解（旧 native.yml 試行の
  windows fmt 失敗も同じ原因だったと判明）。
- **maturin の universal2 ターゲット名は `universal2-apple-darwin`**
  （`universal2` ではない。maturin 1.15.0 バイナリの文字列テーブルで確認）。
- **macOS の setup-python（python.org ビルド）はリンク可能な libpython を持たない**
  （フレームワークのみ）→ `cargo test -p mm-core --no-default-features` は
  macOS でリンク不能（未定義 __Py_IncRef 等）。Linux/Windows のみで実行し、
  macOS は clippy --all-targets + ビルド&import 疎通で担保する構成にした。
- **Apple ターゲットへの Linux からのクロスビルドは pyo3 0.29 では不可**（実測）:
  rustc/pyo3 が出す `-Wl,-exported_symbols_list`（2 引数形）と
  `-undefined dynamic_lookup` を zig cc が誤変換（zig 0.15.2/0.16.0 双方で確認。
  pyo3-build-config ソースで出力形式を確認済み）。Plan §3.3 の正规経路
  （macOS ホストでビルド + lipo）が正。
- cargo-zigbuild + zig 0.16 の linux クロスでは
  `warning: linker stderr: ignoring deprecated linker optimization setting '1'`
  が出るが**無害**（成果物の glibc 上限 2.28 は readelf で確認済み）。
  .cargo/config.toml の mold 設定は zigbuild のリンカー選択に影響しない
  （CARGO_TARGET_*_LINKER 環境変数が優先）ことも実測で確認。
- PyO3 0.29 では**宣言的 #[pymodule] mod 構文**が正（関数形は deprecated）。
  `use pyo3::prelude::*;` は mod の**内側**にも必要。
- jiter 0.17 のオブジェクト反復: 開始は `next_object()`、**後続キーは
  `next_key()`**（next_object を繰り返すと ExpectedSomeValue エラー。ソースで確認）。
  simd-json 0.18 は `ValueAsObject/ValueObjectAccess/ValueAsScalar/ValueAsArray`
  trait の import が必要。borrowed object のキーは `&str`。
- **ベンチ結果の要点**（詳細は docs/BENCH.md）:
  - K5 の SEGFAULT は生産デルタ経路（delta_compress_files）でも到達可能であることを
    手組みペア（総長 %256KiB=1）で実証。safetensors 公式シリアライザはヘッダーを
    8 バイト整列するため、奇数剰余は「任意ヘッダー長を持てる実ファイル」で生じる。
  - K11 は Plan 見込み（200–400ms）より深刻（中央値 930ms、json.loads 506ms）。
  - 副次発見: `get_model_metadata` の 1MiB ガードが大型 MoE の `__metadata__` を
    黙って空にする（Phase 5 B4 で 32MiB へ統一する設計入力）。
  - mm_core import 6ms / 44MiB vs ensure_zipnn 初回 1.69s / 241MiB（実体は torch import）。
- 旧 native.yml 試行（dev@9f1e564、ユーザーがリセット）の成功実績
  （rust-cache workspaces:native、apt mold、pipx cargo-zigbuild 等）は
  今回の CI 設計に反映。同試行の windows fmt 失敗原因も上記 autocrlf と判明。
- ユーザーは作業中に dev@71a4ce3 までを main へマージ済み（PR #3）。
  main の Format 失敗（4a0969c）は dev の 5bfca37 で修復済み → 次回マージで解消。

---

## 2026-09-23（並行第 2 セッション）— 相互検証と補完コミットの記録

同じタスク（Phase 0 実行）を並行して進めた第 2 セッションの記録。作業中に
本ブランチへ上記の Phase 0 実装一式が push されたため（`99b3727`…`aa07c62`）、
**競合する重複実装を force せず、CI 実走済みのそちらを正として採用**し、
独立検証と欠けている補完のみを行った（保守的原則: 誤修正防止・破壊的
履歴操作の回避）。第 2 セッションがローカルに作った同規模の実装
（native ワークスペース・bench スイート・ローダー）は参考 branch
`phase0-session2-local`（未 push）に保存してある。

### 採用ツリーの独立検証結果（この環境で再実行・すべて green）

- ruff check / format（py・scripts）、mypy（py/native.py 込み 14 ファイル）。
- native: `cargo fmt --check` / `clippy --workspace --all-targets
--all-features -- -D warnings` / `test --workspace --exclude mm-core` /
  `test -p mm-core --no-default-features`（libpython3.11-dev 導入のうえ実リンク確認）。
- `scripts/build-native.sh --target linux-x86_64 --size-gate` → 410,336 B の
  abi3 .so（GLIBC ≤2.28・libpython 非依存）。ローダー実測: `load()` 1.78 ms、
  `core_version() = 0.3.0-alpha.0+81854f536`（build.rs の git フォールバック動作）、
  MM_NATIVE=0/1/auto の全経路と diagnostics を機能確認。
- 第 2 セッションが独立に計測した KPI ベースライン（自前の bench スイート、
  /tmp/mmneo-bench/results.json）は docs/BENCH.md の値と**同一傾向で一致**:
  K5 SEGFAULT 8/8 再現（対照 14 ケース往復一致・逸脱 0）、K9 cold 1.70 s /
  warm 0.50 s（BENCH: 1.33/0.50）、K11 get_model_tensors 348 ms（BENCH: 中央値
  930 ms — 1 GiB 環境の GC バラつき。オーダー同一）、jiter 12.1 ms vs
  simd-json 173 ms（BENCH: 10.6 vs 187.6 → **jiter 確定は双方一致**）、
  ensure_zipnn 1.83 s、実モデル clip_l 246 MB の圧縮ピーク 705.7 MB
  （≈2.9×・床引き 1.9× — BENCH の 2.2–2.6× と整合）、往復 SHA-256 全一致。

### 補完として追加したもの（このコミット群）

- **pytest スイート `tests/`**（採用ツリーに未整備だった L4 層の Phase 0 分）:
  ComfyUI スタブ（comfyanonymous/ComfyUI master から 2026-09-23 再取得し
  一致確認）、`mmneo_py` 合成パッケージ import（実 `__init__.py` 非実行）、
  A1 回帰テスト（mm-io スレッド実行 + 0.4 s 解析中のイベントループ tick 生存 +
  実ペイロード + 欠損ファイルのエラー化）、ローダー 8 テスト（タグ写像・
  モード正規化 off/false/no・on/true/yes・auto 実ハンドシェイク・MM_NATIVE=0・
  =1 の RuntimeError・バイナリ不在の理由・未知プラットフォーム・API 不一致の
  拒否と **sys.modules 非汚染**）。ローカル 11/11 green（両起動形）。
- **pytest ≥8 の Package 収集問題への二重対策**: pytest ≥8 は `__init__.py` の
  あるディレクトリを Package 収集し setup で import するため、ComfyUI エントリ
  ポイントを持つリポジトリ直下では全テストが CollectError になる（実測）。
  `tests/pytest.ini`（rootdir/confcutdir を tests/ へ）+ 直下 `conftest.py` の
  `pytest_collectstart` ガードで、`pytest tests` でも素の `pytest` でも green。
- **py/native.py の小さな堅牢化**: ハンドシェイク（api_version 範囲）不合格の
  モジュールを `sys.modules` から pop する（拒否したモジュールが後続の
  `import mm_core` に漏れないように）。回帰テスト付き。
- **CI 配線**: ci.yml の ruff 対象を `tests scripts conftest.py` へ拡張 +
  pytest ステップ追加（依存に pytest/pytest-asyncio/aiohttp/pyyaml/requests。
  バイナリ要のローダーテストは verify ジョブでは skip、実バイナリ検証は
  native.yml 側が担当）。package.json: `py:test` 追加、`py:lint`/`py:format`
  対象拡張（scripts/bench 既存分も ruff clean であることを確認済み）。
- **Plan.md 事実注記**（Phase 0 の一次検証で確定した分。本文の意味は変えない）:
  Windows 成果物名 `mm_core.pyd`（EXTENSION_SUFFIXES 実機検証）、
  bincode 3.0.0 = コンパイル不能プレースホルダ（xkcd 2347）→ 2.0.1 採用、
  rustfmt の imports_granularity 系は nightly 専用、clippy msrv 実効値 1.85、
  A1/ローダーの回帰テスト参照。

### 環境系の再確認メモ（第 1 セッション記述の裏取り）

- mold 2.42.1（GitHub release）は libatomic1 必須。clang は `-fuse-ld=mold` を
  **PATH 上の `ld.mold` 検索**で解決する（mold README 一次確認）— symlink 必須。
  採用ツリーの native.yml にも同 symlink ステップあり（双方独立に同じ結論）。
- cargo-zigbuild と native/.cargo/config.toml（clang+mold）は共存する
  （zigbuild がリンカーをオーバーライド）。zig LLD の
  「ignoring deprecated linker optimization setting '1'」warning は無害。
- `cargo test -p mm-core --no-default-features` は libpython リンクが必要
  （Debian: `apt-get install libpython3.11-dev`。CI: setup-python で足りる。
  macOS は framework のみでリンク不可 → 採用ツリーの CI 除外は妥当）。
- prettier の vue/md 正規化は **plugin（prettier-plugin-tailwindcss）込みの
  lockfile ピン版**で行うこと。node_modules 無し環境では /tmp の npm 環境へ
  symlink して実行（実行後削除）。plugin 無し整形は CI の Format ゲートと
  不一致になり赤くなる（前セッションで実害確認済み）。

### Phase 0 精密監査（2026-09-23、dev tip 088e72e に対して実施）

ユーザー指示「Phase 0 のバグが潜んでいないか精密に確認」への対応記録。
**検証方法**: 全ソース精読 + 一次実証（cargo metadata / C ソース読解 +
実バイト比較 / CI ログ突合 / コミット済み results/*.json の再現実行）。

**問題なしを確認した項目（抜粋）**:

- BENCH.md の全数値が scripts/bench/results/*.json と一致。CI ログ
  （size-budget / abi3-import）とも一致（410,416 / 383,824 / 163,840 /
  666,032 B、計 1,624,112 B。CPython 3.10.21 / 3.13.15 import 実測）。
- **再現実行**: scan（cold 1.358s / warm 0.516s / 5,016 エントリ ←
  コミット値 1.332 / 0.501 / 5,016）、header（中央値 738ms ← コミット値
  930ms、彼らの観測レンジ 453–1,091ms 内。テンソル数 64,491 完全一致）、
  hash（280.4 / 338.4 MB/s ← 278.3 / 340.2、ダイジェスト 3 者一致）、
  delta（ratio 0.6891 完全一致・byteExact=True・+173MiB 再現）、
  **生産デルタ経路の SEGFAULT(signal 11) 再実証**。
- znn-codec 定数は vendored huf.h の**行番号レベル**で一致（L72/L117/L118）。
- json-bench: simd-json の可変コピーは計測領域内（公平）、3 パーサの
  ダイジェスト一致検証付き。build-native.sh: 厳密な wheel 抽出（候補 1 件
  強制）・サイズゲート・Windows 名 mm_core.pyd。native.yml: glibc 床検査の
  sort -Vu 論理、artifact パス構造、abi3-import の PYTHONPATH すべて正しい。
- 81854f5 の CI 修復 3 件はすべて妥当（universal2-apple-darwin 名・
  .gitattributes *.rs eol=lf・macOS テスト除外と代替担保）。
- Phase 0 全レンジ（82adaf9..HEAD）で web/・demo-assets/・src/ の実質変更は
  ゼロ（vue 2 件はクラス順往復で正味 0）・**init**.py 無変更・
  実行時コードから py.native を import する箇所なし（Phase 2 まで不活性）。

**発見して修正したバグ（4 件）**:

1. **【中】extension-module トグルが無効化されていた** —
   `native/Cargo.toml` の workspace.dependencies.pyo3 が
   `features = ["extension-module", "abi3-py310"]` を無条件指定 →
   `pyo3 = { workspace = true }` 継承により crate 側
   `--no-default-features` でも **extension-module が常に ON**
   （cargo metadata の resolve で実証: 修正前 全モード ON / 修正後
   default=ON・no-default=OFF）。現 CI が緑だったのは dev プロファイルの
   リンク単位粒度（Linux）と python3.lib インポート（Windows）による
   **偶然**で、Phase 2 で #[pyfunction] を触るテストが追加された瞬間に
   Linux のテストリンクが壊れる潜在バグ。修正: workspace 指定から除去
   （crate の default feature が唯一のスイッチに）+ native.yml に
   cargo metadata ベースの**トグル回帰ガード**を追加（cargo tree -e features
   は crate 由来の feature エッジを描画しない表示癖があるため不使用）。
   修正後も配布バイナリは**バイト同一**（sha256 一致で証明 —
   既定 features は不変のため）。
2. **【小】core_version() のコミットスタンプ陳腐化** — build.rs が
   `.git/HEAD` のみ watch するため、同一ブランチへの新コミットを検知せず
   古いハッシュが焼き込まれる（実証: HEAD=088e72e なのに +81854f536）。
   修正: build-native.sh が `MM_CORE_COMMIT`（git short=9、呼び出し側の
   明示指定を尊重）を export + build.rs に rerun-if-env-changed 追加。
   修正後: explicit99 / 088e72e56 の双方が正しく反映されることを実測。
3. **【小】bench の fp8 パラメータが生産経路と不一致** —
   `_DTYPE_PARAMS["fp8e4m3"]` の bit_reorder=0 に対し、生産経路
   （zipnn.py compress の TORCH dispatch）は **1** を書く（実ヘッダー
   ダンプで確認）。ただし C コアは num_buf=1 で bits_mode を
   **一切消費しない**（split_bytearray_dtype8 は引数に取らず、combine は
   memcpy — ソース解析 + 32MB 実証: bits=0/1 でペイロード**バイト同一**・
   相互復号可能）ため**コミット済み計測値はそのまま有効**。パラメータを
   1 へ修正し、証明をコメントに記録。
4. **【小】bench スイートの移植性・忠実性** —
   (a) `from py import ...` が site-packages の top-level `py.py`
   （旧 pytest 系の `py` ライブラリ等）に **shadow される**
   （regular module は namespace package に sys.path 順に関係なく勝つ）。
   この環境で実際に ImportError を再現 → common.import_extension() が
   `py` 名をリポジトリの py/ へ明示ピン留めするよう修正（再生成した
   フィクスチャで scan/header/hash/delta 全再実行成功）。
   (b) `SUPPORTED_PT_EXTENSIONS` が ComfyUI master 実物と不一致
   （.pt2/.sft 欠落、.pickle 過剰）→ master 準拠へ修正
   （計測値への影響なし: ライブラリは .safetensors のみ）。
   (c) bench_zipnn e2e の `"originalSha256" in spec` ガードが
   None 値でも真になり、>512MB モデルで byteExact 誤検出する潜在バグ →
   `spec.get(...)` の truthy 検査へ修正。

**監査後の全ゲート再実行**: cargo fmt / clippy -D warnings / test（default・
--no-default-features 両方）/ ruff / mypy / pytest 11/11 / スモーク /
prettier --check . / Cargo.lock 無変更 — すべて green。

### 実装差分クロス監査（2026-09-23、dev vs phase0-session2-local）

ユーザー指示により、採用実装（dev）と並行セッションの別実装
（local branch `phase0-session2-local`、未 push）を全面差分比較した。
**同一仕様の独立実装 2 本の差分はバグの探し合いに最適**で、実際に
dev 側の潜在バグ 1 件・CI カバレッジ欠落 1 件を発見、有用ツール 2 件を移植した。

**発見（dev 側）と対処**:

1. **【潜在バグ】ローダーの出自未検証** — `py/native.py load()` は
   `sys.path.append(bin_dir)` + `importlib.import_module("mm_core")` だが、
   `import_module` は **sys.modules 命中時にパス探索を短路**する。他所
   （別拡張の同名思様物・迷入 pip パッケージ）の `mm_core` が先に
   import 済みだと、native-bin を一切読まずにそれが採用され、
   `api_version()==1` を返す協調的な偽物ならハンドシェイクも通過する。
   別実装は spec_from_file_location + `__file__` 一致検査でこの穴が
   無かった。→ **origin guard を追加**（realpath prefix 検査、
   normcase で Windows 大文字小文字吸収。他所のモジュールは
   所有権がないので sys.modules から**追い出さない**）。回帰テスト
   `test_foreign_sys_modules_mm_core_is_rejected` で固定（12/12 green）。
2. **【CI 欠落】実成果物に対するローダーテストが未実行** — ci.yml の
   pytest は native-bin 不在のため auto ロード + ハンドシェイクのテストが
   **skip**、native.yml の import 疎通は素の `import mm_core`（PYTHONPATH）で
   **ローダー経由ではない**。別実装の integration ジョブ（build → pytest）が
   埋めていた穴。→ native-build-linux に「Loader regression tests against
   the built artifact」ステップを追加（zigbuild 実バイナリに対して
   tests/ 全 12 件を実行）。

**移植（別実装 → dev、監査で価値を確認した分）**:

3. `scripts/bench/bench_c_defects.py` — **Plan 付録 C.3 の全 22 ケース行列**
   （dtype32 クラッシュ 8: 262145/6/7・524289/90/91・低エントロピー 2、
   対照 9: 262144・262148・64・67・1000000–1000003、dtype16 5: 262144・
   262146・1000002・65・262145）。dev 既存の 3 ケース + 生産経路デモを
   補完し、付録の表を 1 コマンドで機械再検証できる。実行済み:
   **SEGFAULT 8/8・対照往復一致 14/14・逸脱 0**（results/c_defects.json
   としてコミット。BENCH §4.3 に追記）。Phase 1 の Rust 回帰テストは
   この行列をそのまま固定化する。
4. `scripts/verify_native_binary.py` — 純 Python の ELF/Mach‑O/PE 検証
   （e_machine・GLIBC 上限・libpython 非依存・universal2 スライス・
   python3.dll 以外 の Python DLL 参照検出）。readelf/lipo の無い
   サンドボックスや任意ホストでのローカル検証用（CI の readelf ゲートの
   補完）。legacy .so ×6 の GLIBC_2.34 もこれで独立再証した。

**差分比較で「バグなし」と判定した主な設計差**（記録のみ）:

- json-bench: dev 版は fs::read + ダイジェスト 3 者一致検証（正しさ優位）、
  別版は mmap 借用（Phase 5 のアクセスパターン実証）。jiter の計測値は
  どちらも同一結論（10.6ms vs 12.1ms、 simd-json に 15–17×勝）。
- build-native.sh: dev 版は wheel 抽出を「候補ちょうど 1 件」で強制
  （より厳密）。別版の --check-cross（非リンク ターゲットの cargo check）は
  CI が実ビルドで上位互換するため不移植。
- ローダー API: dev 版（load()->bool + diagnostics）は min/max API 範囲と
  MM_NATIVE の off/false/no 別名まで持つ。別版の MM_NATIVE_PATH は dev では
  PYTHONPATH + origin guard が同等機能を果たす。
- Cargo: dev 版の workspace.lints 一元化と clippy.toml doc-valid-idents は
  別版（crate 属性 + 個別 allow）より保守性が上。bincode 3.0.0
  プレースホルダ警告は dev では Plan.md 注記が担う（等価）。
- e2e スループットのセッション間差（dev 記録 141–172 MiB/s vs 別実装計測
  237 MiB/s 級）はフィクスチャ形状（テンソル数/サイズ）と単発計測ノイズの
  範囲。**KPI ゲートは「同一ハーネス・同一フィクスチャでの新旧比」で
  判定する**という BENCH.md 冒頭の方法論がこれを吸収する（Phase 2 では
  ベースライン再計測を同一 run で実施すること）。

## 2026‑09‑23 — Phase 1 実装セッション（znn-codec フォーマット中核 + L2/L3）

**成果**: `znn-codec` 全 8 モジュール（header/dtype/reorder/planes/bitstream/
fse/huf{weights,tree,encode,decode}/codec）を unsafe ゼロで実装。znn-cli に
C ABI ミラー（core-compress/core-decompress）+ batch + steal ゲート付き bench。
L2 ハーネス（scripts/l2/golden_diff.py）で **フル 10,500 ケース GATE PASS:
圧縮出力バイト一致 9,880/9,880（100 %）、相互解凍両方向全通過、付録 C クラス
495/495 安全処理（クラッシュ 0）、圧縮率差 Δ0.0000 %**。L3 ファズ 3 ターゲット
（シード 69 件コミット）+ CI 配線（native.yml: native-diff/fuzz-smoke、
fuzz-long.yml: 週次 3h×3=9h + l2-full）。L1 = 68 テスト緑（proptest 含む）。

**重要な発見・確定事実**:

1. **Plan §4.6.2 の f64 並べ替え式が全単射でなかった**（`>>12`/`0x0008…`/
   `0x0007…` = mantissa bit 51 を落とし bit 52 を死蔵 → 任意 u64 の ~50 % が
   往復失敗、実測 100,045/200,000、1.5→1.0）。訂正式（sign→bit 52、man 52 bit
   全保持）を Plan 表に注記済み。proptest が恒久固定。**推測でなく実証で
   計画書のバグを捕まえた事例** — Phase 4 の f64 実装は reorder.rs の
   proptest 済み定数をそのまま使うこと。
2. **C コアの「静かな UB」はロングラン driver プロセスを殺す**: 端数ケースの
   1–3B ヒープオーバーフロー書き込みが蓄積し `free(): invalid size` 等で
   abort（L2 初期版が実測で死亡）。対策 = UB 形状のゴールデン生成を
   **fork 隔离子プロセス**で実行（golden は self-decompress 前に fsync →
   子が後から abort しても golden は有効。実測 125 件の信号死を吸収し
   9,880 golden 全件で C 自己往復も検証済み）。heap-safe 形状
   （nb=1 全長 / length%nb==0）のみ in-process 高速経路。
3. **C のホール alphabet（ギャップ付き maxSV）挙動は経験的に決定論的**:
   buildCTable はゼロカウント シンボルの tree[].nbBits を明示初期化しない
   （スタック履歴依存の UB 懸念）が、dense→sparse を同一ワーカー スレッドで
   連続圧縮しても出力は単独圧縮とバイト同一（=実効的にゼロ）。Rust 実装は
   ホールを nb_bits=0 に確定初期化 → この条件下で C とバイト一致を L2 で確認。
   （理論上の C 潜在バグだが実機再現せず — upstream 報告書には主欠陥のみ記載。）
4. **huff0 ライタのフラッシュ周期は出力バイト不変**（直列ビット順序のみが
   バイト列を決める。C の flushBits が 8B 書き pos を floor(bits/8) 進める
   構造の帰結）。これにより 4→5 シンボル/フラッシュへの変更（huffLog≤11 で
   5×11+7=62<64 が保証）がバイト同一を保ったまま可能 — L2 9,880 件が実証。
5. **計測方法論（この 2vCPU 共有機では必須）**: 未ゲート計測は同一設定で
   2–3 倍揺れる。C 自身も Phase 0 記録と当日クリーン窓で最大 2.4 倍乖離
   （f32 解凍 1722→718、f16 圧縮 613→1020）→ **Phase 0 記録値との比較は無効、
   同一セッション比較のみ有効**。確立したプロトコル = /proc/stat steal ゲート
   （窓の tick 容量 ~5 % 超を棄却、C 側 Python ループと Rust 側 znn-cli bench
   の両方に同一規則を実装）+ 交互ブロック + 側別最小値（=干渉ゼロ窓の上限）。
6. 最適化の実測履歴（f16 32MB 圧縮 e2e、2T）: 初期 313 → 4-way hist + packed
   CTable + デコード窓 → 372 → スクラッチ再利用（平面/ライタ/dtable）→ 720 台 →
   nb=1 ゼロコピー + take() → fp8 ×1.37、split2 16B ブロック化（968→2,055MB/s、
   **32B 化は逆効果 1,698** で却下）→ 並列アセンブリ + writer 5-flush →
   最終 734–790。デコードは 4 ストリーム インターリーブ（C の ILP 構造）+
   固定長 [DeltX2;4096] 表（境界検査消去）で f32 ×1.86–2.20。
7. **速度ゲート現状（判断待ち）**: 8 指標中 6 が ×1.20–1.86 で C 超え。
   bf16/f16 **圧縮**のみ ×0.72–0.84（C の当日クリーン窓 ~1,010–1,020 MB/s は
   Phase 0 記録 337–800 の上限も 27 % 超える異常速。Phase 0 記録比では全 dtype
   同等以上）。残差の内訳は実測で「安全 Rust の初期化税」（並列アセンブリ用
   out 27MB zero-fill + raw 平面 clone = トラフィック +45 %）と gcc の memcpy
   律速経路。scoped unsafe（MaybeUninit）で ×0.9–1.0 到達の見積りだが
   workspace `unsafe_code=deny`（Plan §3.4.2）と衝突 → **ユーザ判断に委ねた**
   （選択肢: (a) 記録ベースライン比でゲート充足として [x]、(b) scoped unsafe
   承認、(c) 現状の文書化済み逸脱で確定）。
8. 環境/ツールチェーン: cargo-fuzz は **0.12.0 ピン**（0.13.x は musl 既定で
   x86_64-linux-musl-g++ を要求 → runner/サンドボックスに無い。gnu ターゲット
   明示で ASan 動作）。nightly + rust-src 必須（--build-std 既定）。ローカル
   1GiB では release+ASan の rayon コンパイルが OOM（SIGKILL）→ **-D（dev）で
   スモーク**、CI（7GiB+）は release。array_chunks(_mut) は 1.98 でも
   unstable → MSRV 1.85 維持のため chunks_exact + try_into で代替（性能差は
   実測ノイズ内）。ディスク逼迫時は native/target/debug（1.1GB、再構築可能）
   を削除して凌いだ。
9. fuzz が検出した実バグ 3 件（全て修正 + 回帰シード化）: (a) byte13 の
   下位 7bit を非ストリーミング時に保持 → encode∘decode 正規形不一致
   （decode 側で 0 に正規化。zipnn.py も下位 bit は読まない）、
   (b) cumSizes 平面オフセットの usize 加算オーバーフロー（release では
   ラップして span 検査をすり抜け得た → u64 checked_add + 事前検証）、
   (c) `orig_len + chunk - 1` が cap 検査前でオーバーフロー（cap 検査を
   最前へ移動 + div_ceil 化）。

### 追記（同日・ユーザ判断と最終最適化）

- **ユーザ判断 3 点**（ask_user 応答）: (1) 圧縮率は速度より重要 —
  「せめて 67 % は下回らない」→ バイト同一による構造的保証で回答
  （bf16 実測 0.6623。BENCH §6.3）。unsafe は「できる限り使わない」指示
  （safe 策の virtual-raw で目標超過達成のため不使用で決着）。
  (2) fuzz-long は今すぐディスパッチ希望 → **PAT の Actions 権限不足 +
  schedule/dispatch の default-branch（main）制約で 403**。GitHub UI からの
  手動ディスパッチ（branch: dev, hours: 3）をユーザに依頼する形に。
  (3) 上流 issue は起票せず、Neo 内でメモリバグ完全修正を担保（BENCH §6.4）。
- **virtual-raw 平面**（最後の大型 safe 最適化）: raw 確定の平面は
  スクラッチにも clone にも落とさず、アセンブリ フェーズで
  `planes::extract_plane` が src チャンクから出力スライスへ直接展開
  （split()[b] とのバイト一致は dedicated テスト + L2 10,500 で固定）。
  効果: bf16 圧縮 ×0.78→×1.18–1.29、f16 ×0.72→×1.31–1.45 — **8/8 指標で
  C 超え**（連続 2 実行、同一 steal ゲート プロトコル）。C のポインタ
  スワップ（compressedData = 平面バッファ itself）を safe Rust で再構成した
  形で、clone 経路の C よりトラフィックが少ない。
- 速度計測の残存注意点: C は最静穏窓で bf16/f16 圧縮 ~950–1,030 MB/s に
  達することがある（Rust 静穏窓上限 ~740–790、virtual-raw 後は未観測）。
  ゲートは同一セッション交互計測（側別最小値）で判定 — 2 連続 PASS。
- 最終状態: L1 69 / L2 フル PASS / L3 スモーク PASS / clippy -D warnings 0 /
  fmt / ruff / mypy / pytest 12 / prettier 全緑、CI（verify + native 11
  ジョブ、native-diff・fuzz-smoke 含む）全緑。Phase 1 の [x] 化は
  fuzz ≥8h 初回実行完了待ち（機械的步骤のみ）。

## 2026‑09‑24 — Phase 2 実装セッション（safetensors パイプライン + バックエンド接続）

### Phase 0–1 最終確認（このセッションの冒頭、ユーザ指示分）

**再実行して全ゲート緑を確認**（dev tip f51ecd8 に対して）:
cargo fmt / clippy `-D warnings` / test（L1 69 + mm-core）/ ruff check+format /
mypy 14 files / pytest 12（実 zigbuild 成果物に対するローダーテスト込み）/
**L2 quick GATE PASS**（1,200 ケース: byte‑identical 1,121/1,121、mismatch 0、
付録 C クラス 63 安全処理）/ build-native.sh linux-x86_64 サイズゲート OK /
リモート CI 12 チェック全緑（GitHub API で確認）。

**発見した潜在バグと対処**（Phase 2 実装に先立ち修正・回帰テスト化）:

1. `codec::decompress_container` の **fp8 チャンククランプ欠落** —
   zipnn.py は num_buf==1 のとき C に `min(128KiB, 2^byte14)` を渡すが
   （ヘッダー byte14 は 18 のまま = 生産 fp8 ブロックの実チャンクは 128KiB）、
   同関数は byte14 由来の 256KiB をそのまま使っていた。Phase 1 では
   呼び出し元が無く（L2 はチャンクを明示引数で渡す）未顕在化 —
   Phase 2 が最初の消費者になるところだった。修正 + テスト
   `fp8_container_chunk_clamp`。
2. **バージョンゲート欠落**（Plan §7 R10 の緩和策「ヘッダーのバージョン
   バイト厳密検査」が未実装だった）: `ZnHeader::decode` が 0.5.0–0.5.4
   以外を明示エラーにするよう強化（将来の上流フォーマット変更の
   静かな誤デコード防止）。テスト `decode_gates_the_container_version`。
3. **fuzz-long のディスパッチ経路の訂正**: admin 権限 PAT でも
   workflow_dispatch は **404**（fuzz-long.yml が default branch に無い
   → workflow 未登録。GitHub UI にも表示されない）。Phase 1 完了条件の
   消化経路は **dev→main マージのみ**（Plan の当該項を訂正済み）。
   main は dev の内容に対して独自変更ゼロ（マージコミット 3 件のみ、
   `git diff dev...origin/main` 空で確認）。

### Phase 2 実装（成果物）

- **znn-codec 新モジュール**: `safetensors_io.rs`（parse/正準 Writer/
  AtomicWriter）、`znn_tensor.rs`（テンソル ZN ブロック + dtype 表）、
  `pipeline.rs`（compress_file/decompress_file + Progress/Hooks/JobOpts）。
  codec に `zipnn_core_into`/`combine_dtype_into`/`*_with(cancel)` を追加
  （既存 API は無変更で温存 — L2/znn-cli との互換維持）。
- **safetensors 0.8.0 の一次ソース精読**（github v0.8.0 tag:
  tensor.rs / slice.rs / bindings python lib.rs を DL して確認 — 推測ゼロ）:
  Writer は dtype アライメント降順→名前でソート、`__metadata__` 先頭、
  compact serde_json、**8B 整列までスペースパディング**、Reader は
  dense/exact-coverage/size 整合を強制、`keys()` はソート済み、
  **メタデータは HashMap = キー順がプロセスごとにランダム**（← レガシー
  往復の byte‑exact が複数キーで偶然依存だった潜伏バグ。Neo は順序保持で
  構造的に解決）、`f.metadata()` の None と `{}` は別物（→
  `znn_neo_src_meta_absent` キー新設の根拠）。
- **mm-core**: `jobs.rs`（レジストリ + GC + catch_unwind）+ pymodule に
  6 関数（api_version=2 へ bump、py/native.py の範囲も [2,2] へ同期、
  native.yml の abi3 assert も更新）。
- **py/compress.py**: `_run` に native 経路（10 Hz ポーリング、ws 契約
  完全維持）、cancel ルート、`cleanup_stray_files()`（`__init__.py` から
  io_executor で起動）、レガシー解凍の Neo キー strip 拡張 +
  meta_absent 尊重。batch/delta は Phase 3 までレガシー温存。
- **テスト**: Rust L1 98（+29）、pytest 43（+31: pipeline 22 + routes 9）、
  L5 スクリプト `scripts/l5/official_cross.py`。
- **CI**: native.yml に `integration` ジョブ（3 OS。ubuntu = フル
  （torch 導入 → 両経路 + L5 pip zipnn 0.5.4 ソースビルド相互検証）、
  win/mac = native 経路のみ（MMNEO_SKIP_LEGACY=1 + torch プローブで
  ソースビルド暴走を防止））。fuzz-smoke/fuzz-long を 5 ターゲット化。

### 実測で発見して修正した実装バグ（今回の教訓群）

1. **ジョブ完了競合**: パイプラインが phase=Done を設定してからスレッドが
   outcome を記録するまでの窓で `job_result` が「未完了」を返す
   （bench ハーネスが実測で検出 — RuntimeError）。`job_progress` は
   outcome のみを終端信号とし、窓の間は `verify` を報告する方式へ。
2. **paranoid の進捗二重計上**: 内部検証デコードが同じ Progress を
   駆動して done>total（UI 200 %）。内部 Hooks は progress=None に。
3. **メタデータ不在情報の喪失**: 原本に `__metadata__` が無い場合、
   復元が `{}` を追加して byte‑exact を壊す（Rust テストが即検出）→
   `znn_neo_src_meta_absent` キーで記録・尊重（レガシー側も）。
4. **並列ハッシャは 2 vCPU で逆効果**: channel + 専用スレッドを実装して
   実測 → 0.60 s → 0.65 s に**悪化**（空きコア無し + clone トラフィック +
   無制限キューの RSS 増 = K1 危険）。inline へ revert（判断は常に実測 —
   BENCH §7.1 の「正直な注記」に記録）。
5. **割り当て爆弾**: 敵対的ブロブが「整合的な嘘」（shape×elem ==
   original_len == 1 TiB）で resize → OOM abort → ComfyUI 死亡の経路が
   あり得た。per-tensor キャップ（既定 64 GiB、`decompress_tensor` は
   blob×64 フロア 16 MiB）+ checked 累積オフセットで Err 化。テスト +
   fuzz ターゲット `blob_decompress`（キャップ 1 MiB で回す）で固定。
6. **sha2 0.11 の SHA‑256 に AVX2 バックエンドは無い**（README 一次確認:
   x86 は SHA‑NI か soft のみ。`x86-avx2` は SHA‑512 専用）→ SHA‑NI の
   無いマシンでは検証ハッシュ ~156 MB/s が e2e の壁になる（BENCH §7.1 に
   内訳実測を記録。設計は Plan 通り sha2 維持 = OpenSSL バインディングは
   Plan §3.1 が明示的に不採用）。

### 計測（KPI）と正直な判定

- 詳細は **BENCH §7**（同一セッション・側別ベスト窓・ steal 記録の
  Phase 1 確立プロトコル）。要点: K1 限界倍率 **1.2×/0.8×**（レガシー
  2.6×/1.7×）、byte‑exact 3/3、K13 不変（44 MiB/6 ms）。K2 ×0.46 /
  K3 ×0.24 は **sha2-soft が壁の ~85 %**（検証 OFF 実測: 解凍 352 MB/s =
  ×1.18）。SHA‑NI + NVMe 外挿は K2 ×1.3–2.0 / K3 ×1.2–2.1 の境界 →
  Plan 完了条件は「参照機再計測」を残して [/]（未達フェーズを閉じない
  規程 §6.3 に従う）。
- L5 ローカル実行: pip zipnn 0.5.4（ソースビルド成功、cp311 wheel 生成）
  との相互検証 **GATE PASS**（A/B/C 全方向）。ベンダ版との同一性の
  機械的証明になった。
- L3 スモーク（新ターゲット、dev+ASan、この 1 GiB 機）: st_parse
  **462,024 runs / 91 s クラッシュ 0**、blob_decompress 20,770 runs / 91 s
  クラッシュ 0、既存 3 ターゲットも再スモーク緑（codec リファクタ後）。

### 環境メモ（今回セッション）

- apt の HTTP が 25 KB/s まで劣化（aliyun ミラー自体は urllib で 0.7 s 応答）
  → `apt-get --print-uris` + Python 並列 DL + dpkg キャッシュ経由で回避
  （109 debs を数分）。rustup / pip（torch cpu 含む）/ crates.io / docs.rs /
  GitHub raw はすべて高速。
- リンク時の `fork: Cannot allocate memory`（1 GiB）→ cargo は `-j 1`
  （clippy/test）。release LTO ビルドも -j 2 で通る（28–77 s）。
- ディスクは torch + rust toolchain + nightly + fuzz target で 9.9 GB のうち
  ~7 GB 使用。**native/target の肥大に注意**（fuzz の target は別ツリー）。
- heredoc 内に `"$ARENA_WORKSPACE"` 直書きをすると環境側で `$ARENA_WORKSPACE` に
  置換されて壊れることがある → Python スクリプトは `os.getcwd()` 相対で書く。

### Phase 2 push 後の CI 修復ラウンド（2026‑09‑24、f51ecd8→f4c1a4c）

push 後の CI で 3 件のゲート失敗 → いずれも修正して再 push（本体設計は不変）:

1. **verify/Format**: `scripts/bench/results/native_e2e.json` が
   `json.dump(indent=1)` で prettier 不一致 → indent=2 + 末尾改線へ
   （スクリプト側も修正 — 将来の再生成がゲートを割らないように。
   znn-cli `--json-out` も末尾改線を付与）。
2. **verify/mypy（既存コードの被弾）**: CI の pip が **huggingface_hub 2.0.0**
   を解決するようになり（requirements は `>=1.32.0` の開放範囲）、
   `HfApi.list_models(sort=)` の注解が閉じた Literal に狭まって
   `py/search.py:180` が arg‑type 違反に。ローカルで hub 2.0.0 を入れて
   再現確認のうえ `cast(Any, sort)` で修復（実行時ゼロ影響・
   バージョン非依存。`# type: ignore` は warn_unused_ignores と
   hub 未導入環境の双方で割れるため不採用）。
3. **native-test(windows)/integration(windows)**:
   (a) mm-core ジョブテストのアサートが POSIX エラー文言依存 →
   `io_ctx` が **ENOSPC 以外でも常に「操作 + パス」を付与**するよう
   強化（ユーザ向けメッセージとしても正しい方向）し、アサートは
   プラットフォーム非依存の 2 語に。(b) `cleanup_stray_files` の報告
   パスが Windows で separator 混在（normalized root + os.path.join）→
   `utils.join_path` へ統一、テストも normalize 比較に。
   ※ 同 run で **znn-codec 99 テストは Windows で緑**（AtomicWriter の
   rename/fsync・mmap・thread::scope すべて Win32 で動作）、macOS
   integration も緑 — 新パイプラインのクロスプラットフォーム性は
   CI で機械確認済み。
4. CI 証跡（737ffef, ubuntu integration）: pytest **43 passed**
   （レガシー経路 + native 経路 + クロスパス + L4 コーパス）、
   **L5 GATE PASS**（pip zipnn 0.5.4 実ビルド: A/B/C 全方向）、
   コアバージョンスタンプ `0.3.0-alpha.0+737ffef31` 正常。

## 2026‑09‑25 — Phase 2 精査セッション（ユーザ指示「一切のバグが含まれていないか精査」）

**セッション跨ぎの注意**: ワークスペースのスナップショットは `"$ARENA_WORKSPACE"` 配下の
通常ファイルのみ永続化するため、`.git`・`/opt` のツールチェーン・pip/apt パッケージは
消失していた（native-bin の成果物とソースは生存）。再クローンして `.git` を復帰、
ツールチェーンを再構築してから精査を実施した（環境構築は前セッションの
`/tmp/rebuild-env.sh` 方式: apt `--print-uris` + Python 並列 DL、rustup、pip）。

### 精査で発見し修正したバグ（5 件）

1. **【中】`_cleanup_targets` が dst 本体を削除していた** — 両パイプラインとも dst は
   最終 atomic rename でしか生成されないため、失敗時に dst が存在すればそれは
   「route の存在チェック後に他者が作ったファイル」。これを削除するのは狭いが
   実在するデータ喪失競合。partial（`.tmp`/`.verify.tmp`/`.tmp.fix`）のみの削除へ
   修正 + 単体テスト（sentinel dst の生存を assert）。
2. **【中】並行ジョブの tmp 相互破壊** — `AtomicWriter::new` が既存 `{dst}.tmp` を
   無条件 truncate していた: 同一 dst への二重サブミット（UI の二重クリック、
   複数 ComfyUI インスタンス）で 2 ジョブが同一ファイルへインターリーブ書込み →
   静かな破損。`create_new`（O_EXCL）+ 若年 tmp（<15 分）は明確なエラーで拒否、
   陳腐 tmp（≥15 分 = クラッシュ残骸、起動時掃除と同じ年齢規則）は引き継ぎ。
   テスト追加（拒否 + backdate 引き継ぎ）。
3. **【中】2 の導入で顕在化した相互作用** — native ジョブ失敗時の Python 側
   `_cleanup_targets` 呼び出しが、create_new に拒否された「第 2 ジョブ」の失敗
   ハンドラから「第 1 ジョブが書込み中の tmp」を削除し得た。native 経路の
   Python 側クリーンアップを撤去（Rust の Drop ガードが cancel/panic/ENOSPC を
   含む全失敗路で tmp 削除を保証 — 44 pytest で再確認。legacy 経路は
   save_file→os.replace 間に例外窓があるため Python 側掃除を維持）。
4. **【低】`commit()` の rename 成功後 fsync_dir 失敗で Err** — 「成果物は確定済み
   なのにジョブは失敗」（リトライは target already exists に当たる）という
   矛盾状態。rename 成功をコミット点とし、dir fsync 失敗は warning 化
   （内容は finish() で fsync 済み。dir エントリ非永続の最悪ケース =
   rename 不反映 = **原本無傷**で legacy と同一のエクスポージャ）。
   `take_dir_sync_warning()` でパイプライン warnings へ昇格。reject_to も同様に
   best-effort 化。
5. **【低】書込み側 MAX_HEADER_SIZE ガード欠落** — 参照リーダは 100 MB 超の
   ヘッダーを拒否するのに、Writer 側は無検査だった（病的ソース: 上限近くの
   ヘッダー + 巨大 infos で「標準ツールが読めない出力」を生む経路）。
   `guard_header_size` を両パイプラインの region 構築直後に追加 + 単体テスト。

**改善（バグではない）**: `/model-manager/zipnn/available` が
native を優先短路して二エンジン報告（`engine`/`reason` 追加 — 後方互換）。
native 可用時は torch import（初回 ~1.5 s のループブロック要因）を回避。
`io_ctx` は ENOSPC 以外でも常に「操作 + パス」を付与（POSIX/Win32 の
メッセージ差に依存していたテストアサーションも平台非依存化）。

### 実証監査バッテリー（/tmp/audit/battery.py、ALL CLEAN）

- **A. torch(safetensors‑rust 0.8.0) 実物 Writer との正準性証明**:
  mixed dtype（bf16/f32/f16/fp8/I64/BOOL/scalar）× メタデータ 4 変種
  （複数キー+unicode / 単一 / 無し / 空）で `canonical=true`、
  **byte‑exact 復元**、`load_file`/`safe_open` 全テンソル一致、
  no‑meta 復元に `__metadata__` が湧かない / empty‑meta は `{}` 維持。
  → 「Neo の正準 Writer = 参照実装とバイト同一」の主張が実物against で証明された。
- **B. 敵対的テンソル名**（引用符/バックスラッシュ/制御文字/絵文字サロゲート
  ペア/日本語/220 文字）: infos 値が Python `json.dumps`（ensure_ascii）と
  完全一致 + byte‑exact 往復。
- **C.** Neo 成果物（圧縮/復元）を公式 safe_open が読めること。
- **P. 書込み失敗注入**（RLIMIT_FSIZE→EFBIG、SIGXFSZ=IGN で子プロセス内強制）:
  ジョブはクリーンに failed（`I/O error: File too large`）、dst/tmp 残骸ゼロ、
  原本無傷 — 「ディスク満杯」QA 項目の機械的実証（ENOSPC と同一の错误経路）。
- **Q. SIGKILL クラッシュ復旧**（64 MiB ジョブを 0.15/0.6/1.2 s で kill）:
  commit 前 kill → dst 不在・掃運可能な tmp のみ・原本無傷。commit 後 kill →
  dst は**完全かつ検証可能**（解凍 → verified=sha256 → byte‑exact）。
  どの窓でも torn file が存在しない（rename 原子性の実証 = 手動 QA
  「強制終了復旧」の機械化）。
- **D. 250 シード・ランダム掃引**: dtype 12 種×メタデータ 5 変種×正準/非正準
  ヘッダー×unicode 名×0要素テンソル×空ファイル — **0 issues**
  （exact=1→sha256+byte‑exact、exact=0→structural+意味一致、残骸ファイル 0）。
- **F.** 0 テンソルコンテナ 3 変種 byte‑exact。**N.** 解凍途中キャンセルで
  残骸なし。**O.** 並行 2 ジョブ成功。
- 再実行系: L5 GATE PASS（pip zipnn 0.5.4）、L2 quick GATE PASS（1,121/0）、
  pytest **44**、Rust **100+5**、clippy/fmt/ruff/mypy（hub 2.0.0 同梱で再現）・
  prettier 全緑。bench 証跡 JSON は最終バイナリで再生成（BENCH §7.1 の表を
  同期: K2 ×0.45 / K3 ×0.25 — 判定と内訳は不変、sha2‑soft 律速）。

### fuzz‑long（Phase 1 残項）

ユーザの dev→main マージ（PR #5）で workflow 登録が有効化 → **API ディスパッチ
成功**（2026‑09‑25 02:55 UTC、branch dev、hours=3、5 ターゲット並列 = 15 h
予算 ≥ Plan §5.1 の 8 h）。run: actions/runs/36088280583。完了・緑を確認できたら
Plan §6.2 Phase 1 完了条件と §9 を [x] 化すること（本セッション中に完了を
待てない場合は次のセッションで run 結果を確認）。

### 残った既知の非バグ事項（記録）

- レガシー経路の「dst 存在チェック後の競合」は Phase 2 前の昔からある挙動で、
  native 側は create_new で構造的に解消済み。legacy は Phase 7 で消滅する。
- 解凍 stats の `decompressedTensors` は native=実際にデコードした数、
  legacy=infos エントリ数（ゴースト infos のある壊れファイルでのみ差が出る。
  形状ゴールデンは両者一致）。
- サーバプロセス kill 中のジョブスレッドは道連れで死ぬ（tmp は残る →
  起動時クリーンアップが 15 分規則で回収。コミット済み成果物は rename 原子性で
  不整合にならない）。

### fuzz‑long run 1 完走と blob_decompress OOM の根因・修正（2026‑09‑25 続セッション）

**run 36088280583（head 3b3a3af、hours=3、02:55 UTC ディスパッチ）最終結果**:

| ジョブ                   | 結果       | 実走                     |
| ------------------------ | ---------- | ------------------------ |
| l2‑full（10,500 ケース） | SUCCESS    | 6 m                      |
| fuzz st_parse            | SUCCESS    | 3 h 02 m（クラッシュ 0） |
| fuzz codec_decompress    | SUCCESS    | 3 h 02 m（クラッシュ 0） |
| fuzz huf_decompress      | SUCCESS    | 3 h 02 m（クラッシュ 0） |
| fuzz zn_header           | SUCCESS    | 3 h 02 m（クラッシュ 0） |
| fuzz blob_decompress     | **FAILED** | 1 h 54 m で OOM 終了     |

**blob_decompress OOM の根因**（コード欠陥ではない）:

- libFuzzer の `rss_limit_mb=2048` 到達による abort。ヒーププロファイルの
  live heap は **~25 MB** — リークでもメモリ安全性バグでもなく、
  **アロケータのページ保持**: (a) ハーネスが exec ごとに新規 `Vec` を
  確保・解放する churn、(b) ASan 既定の quarantine（256 MB 級）と
  OS への遅いページ返却。~5,000 万 exec で累積し上限に到達した。
- **トリアージ注意**: libFuzzer の OOM レポートは stderr に出るだけで
  `crash-*` アーティファクトを残さない（アーティファクト 0 件でも
  ジョブログを見ること）。OOM 時の入力（88 B）は
  `corpus/blob_decompress/oom-2026-09-25.bin` として回帰シード化。

**修正（3 点、コミット 4cce777）**:

1. ターゲットの出力バッファを **thread_local grow‑only** 化
   （パイプライン K1 と同型。`decompress_tensor_into` が内部で
   clear+resize するため呼び出し側は確保を再利用するだけ）。
2. workflow に `ASAN_OPTIONS=quarantine_size_mb=32:release_to_os_interval_ms=200`
   （cargo‑fuzz は自前の `detect_odr_violation=0` を**追記**するだけで
   環境変数は子プロセスに到達することを実地で確認済み）。
3. `rss_limit_mb` 2048 → 4096（残余勾配に対するヘッドルーム）。

**ローカル A/B 実証**（dev ビルド + ASan、同一コーパス、各 ~7 分）:

- 修正ターゲット + ASan 既定: 357,829 execs、クラッシュ 0。RSS は
  #16k まで 43→399 MB（quarantine 充填のウォームアップ）後、
  ~40 B/exec に減衰しながら緩増（#262k で 423 MB、末尾 427 MB）。
- 修正ターゲット + ASan チューニング: **410,558 execs、クラッシュ 0、
  RSS 108→131 MB**（ウォームアップ充填が消滅）、exec/s 850→975。
- 外挿: CI run 1（旧ハーネス、release）は ~5,000 万 execs で 2048 MB
  到達 ≒ 一定 ~38 B/exec。新構成の最悪線形外挿でも 3 h（release で
  ~7,500 万 execs）≒ 131 MB + ~2.9 GB < 4096 MB。勾配は減衰傾向なので
  実測はさらに低い見込み（~1 GB 級）。
- 運用注意: `cargo fuzz run` は発見入力を `corpus/<target>/` に
  **書き込む**（今回のローカル実行で数百件生成 → キュレーション済み
  7 件以外は削除した。commit 前に `git status` で確認すること）。

**環境ロールバック事故の記録（重要）**: 前セッション区間
（2026‑09‑25 ~05:00–06:50 UTC 相当: OOM トリアージ → 修正 → コミット
2f6224c → push「成功」表示 → 再ディスパッチ表示）は**サンドボックスの
ロールバックで失われ、GitHub に一切到達していなかった**。実証:
remote dev tip = 972ff73（API）、`GET /commits/2f6224c` → **422**、
events API に 03:37 UTC 以降の dev push なし、fuzz‑long の run は
36088280583 の 1 件のみ。ワークスペースの untracked ファイル
（corpus シード）のみが幸存。force push は使っておらずユーザ作業の
破壊はなし。本セッションで修正を**再作成・再実証**したのが 4cce777。
**教訓: push は local の git 出力を信じるだけでなく API で remote tip を
検証する**（dispatch 404 の裏取りと同法）。

**本セッションの全ゲート再検証（最終ツリー 4cce777 に対して）**:

- `cargo fmt --all --check` ✓ / fuzz ターゲット rustfmt ✓
- `cargo clippy --workspace --all-targets --all-features -D warnings` ✓
- `cargo test`: znn‑codec **100** + mm‑core（no‑default‑features）**5** ✓
- `.so` 再ビルド（build‑native.sh linux‑x86_64）: **決定論的**
  （2 回ビルドで sha256 一致 `7c44396…dcbc1`、1,026,536 B）。
  `verify_native_binary.py` → `ok: true`、max_glibc **GLIBC_2.28** ✓。
  無害 warning 1 件（zig ld の `-O1` 非推奨通知）は CI と同一
  （native‑build‑linux ログに 2 件 = 両 arch 分、を実物で確認）。
  **ロールバックを幸存していた旧 `.so`（992,520 B、mtime 03:23）は現行
  ソースの決定論的再ビルドと不一致**（CI@972ff73 の x86_64 成果物は
  1,026,872 B — ローカルとの 336 B 差はビルドパス長由来）→ 来歴不明
  （stale）として破棄し、本セッションの全結論はフレッシュビルドに
  基づく。精査修正の回帰テストも新 `.so`/現行ソースで緑を明示確認:
  `atomic_writer_commits_and_aborts`（create_new 並行拒否・young tmp
  保護・stale 採用）、`header_size_guard_rejects_oversized_regions`、
  `test_cleanup_targets_never_deletes_dst_itself` ほか。
- L4 pytest **44/44** ✓ / L2 quick **GATE PASS** ✓（注意: quick 実行は
  `scripts/l2/results/golden_diff.json`（コミット済み証跡）を上書きする →
  `git checkout --` で復元した）/ L5 公式 zipnn 0.5.4 **GATE PASS** ✓
- ruff format（37 files）+ ruff check ✓ / prettier（yml・md）✓
- 新規 fuzz ターゲットのローカル実行 41 万 execs クラッシュ 0 ✓

**再ディスパッチ**: run **36114455354**（head **4cce777**、hours=3、
08:43 UTC queued、5 ターゲット + l2‑full）。**この run の全 5 ターゲット
SUCCESS を確認して初めて Plan §6.2 Phase 1 完了条件と §9 を [x] 化する**
（run 1 の 4/5 緑は旧ハーネスの実績として有効だが、blob_decompress の
3 h 完走は未証明のため）。

## 2026‑09‑25（続々セッション）— fuzz‑long run 2 失敗の真因特定と修正、Phase 3 着手

### run 36114455354（修正 4cce777 込み）も blob_decompress が OOM で失敗 — 真因は別だった

**GitHub API + ジョブログで実証**（ユーザ指示「run 2 の全 5 ターゲット成功確認」への回答:
**4/5 SUCCESS + l2‑full SUCCESS、blob_decompress は 11:40 UTC に OOM 終了**）:

- OOM 時の live heap は **26 MB**（quarantine 25.7 MB ≤ 上限 32 MB = ASan チューニングは
  効いていた）のに RSS peak **4,097 MB > 4,096 MB**。OOM 入力 `oom-da39a3ee…` は**空**
  （= 特定入力ではなく累積で上限到達）。RSS は exec 数に**完全線形**（~35.5 B/exec —
  run 1 の ~38 B/exec とほぼ同じ = 前回の修正では保持率はほぼ減っていなかった）。
- **真因**: ハーネスは `threads = 1` を渡すが、runner の `default_threads()` は 4。
  `codec::with_threads` は「明示数 ≠ default」のとき**毎回新規 rayon プールを
  build + destroy** していた → exec ごとに OS スレッド 1 本を spawn/teardown
  （スレッド 1 本あたり ~35 B のランタイム/サニタイザ メタデータがプロセス生存中
  累積 — live heap に現れないため前回「アロケータのページ保持」と誤診された）。
  ハーネスのコメント「threads pinned to 1 (no pool churn)」は**意図と実装が逆**だった。
- **傍証**: `codec_decompress` は `threads: 0`（グローバルプール = 生成 1 回）で
  両 run とも 3 h 緑。5 ターゲット中で per‑exec スレッド churn があったのは
  blob_decompress のみ。
- **修正（コミット de1a153）**: 明示スレッド数ごとのプールを `CUSTOM_POOLS`
  （LazyLock<Mutex<HashMap<usize, Arc<ThreadPool>>>>）にキャッシュ。上限ガード
  （>64 は build せず global pool フォールバック — 出力バイトはスレッド数非依存、
  `threads_param_does_not_change_output` が固定）でスレッド爆発も防止。
  回帰テスト `explicit_thread_counts_reuse_cached_pools`（Arc::ptr_eq + ワーカー
  スレッド ID 再利用 + ガード）。
- **ローカル A/B 実証**（dev+ASan、同一コーパス、各 300 s、この 2 vCPU/1 GiB 機）:
  現行 = RSS 71→94 MB（+23 MB / 222 k exec、cov 飽和後の定常窓 **~44 B/exec**）→
  修正後 = 82→88 MB（+6 MB / 247 k exec、定常窓 **~9 B/exec**）。CI release 外挿
  ~8 B/exec × ~110 M exec ≈ **0.9 GB << rss_limit 4,096 MB**。
- **再ディスパッチ**: run **36148521214**（head **de1a153**、hours=3、14:35 UTC）。
  **この run の全 5 ターゲット SUCCESS 確認で Plan §6.2 Phase 1 完了条件と §9 を [x] 化**。
- 修正コミット前の全ゲート再検証: cargo fmt / clippy `-D warnings` / test 101+5 ✓、
  pytest **44/44** ✓（新ビルド .so 1,030,544 B に対して）、ruff / mypy 14 files ✓、
  **L2 quick GATE PASS**（1,121/1,121 byte‑identical・付録 C クラス 63 安全処理）、
  **L5 公式 zipnn 0.5.4 GATE PASS**（A/B/C 全方向）、prettier ✓。
- 教訓: 「rss_limit OOM = アロケータのページ保持」と決めつけず、**スレッド churn も
  RSS 累積源**になる（ASan は生成スレッドごとのメタデータを保持する）。live heap が
  小さいのに RSS が線形増加する場合、確保源はヒープ外（スレッド/シャドウ/mmap）を疑う。

### Phase 3 実装セッション（同日続 — デルタ + バッチプリミティブ）

**成果物**（コミットは run 3 確認と併せて記録）:

- `znn-codec::delta`（新モジュール）: 両側 mmap → ヘッダー等長化パディング
  （legacy `_delta_aligned_bytes` の zero-copy 版 = 仮想 Rendering 4 領域）→
  1 MiB ストリーミング XOR → **公式 streaming コンテナ連鎖**を AtomicWriter
  で逐次書込み。ftSha256 は圧縮と並行スレッド（§4.4.3‑1 パターン）、
  サイドカーはエンジンが delta 本体の commit 直後に原子コミット
  （失敗 = ジョブ失敗 → Python は ft を消さない = データ喪失なし。
  ルート側は「committed‑but‑sidecar‑less のみ dst 削除」で
  "失敗時は成果物を残さない" 不変条件を回復 — Phase 2 の
  並行ジョブ tmp 保護の教訓も継承: native 失敗時に Python は
  `.tmp` を一切触らない）。
- 復元: streaming 連鎖 + legacy 単一コンテナの双方を受理。期待総長は
  base rendering から**厳密に既知**なので、敵対的 original_len は
  resize 前に legacy 文言（"Length of delta file has to match…"）で Err
  （割り当て爆弾防止）。unpad はストリーミング状態機
  （prefix 書換 → header → pad skip → data）。検証は inline sha
  （AtomicWriter ハッシャ）→ 不一致は `.corrupt` 退避 + デルタ保持。
  paranoid は tmp の再デコード → sha 比較 → rename 前（Phase 2 同型、
  内部 Hooks は progress=None）。
- **一次ソース発見（相互運用）**: 公式デルタ文件的 method バイトは 0–4
  いずれでもあり得る — zipnn.py API 既定 AUTO(=0)（実機ヘッダーダンプで
  確認: byte7=0）、公式 CLI `zipnn_compress_file_delta.py` は既定 HUFFMAN
  だが `--method AUTO/ZSTD/...` 受理、float32 byte コンテナでは
  `compress_bin` が method によらず**常に zipnn_core（Huffman）**を通り、
  公式解凍 `decompress_bin` は byte7 を**読まない**（zstd 分岐は
  `dtype_size = 0 # Need to implement` のデッドコード）。→ デルタ復号のみ
  `ZnHeader::decode_delta/parse_delta`（method ゲートなし）で R12
  「公式出力 100 % 受理」を満たす。**テンソル経路は Phase 2 の厳格ゲートを
  維持**（Plan B.1 — Neo/公式 safetensors スクリプトは常に HUFFMAN=1）。
  L5‑D2 が AUTO(0) 単一コンテナと HUFFMAN(1) streaming の両公式表記を
  カバー。
- `znn-codec::batch`（新モジュール）: `walk_models`（ignore crate 並列、
  os.walk 意味論の忠実移植: 隠しファイル包含・symlink‑dir 非追跡/非ファイル
  扱い・不能読ディレクトリ静黙スキップ・lossy UTF‑8 名・sorted 安定順。
  3 モード = Python 3 walker の写像で**ゴールデン parity テスト**）と
  `move_with_sidecars`（20 スロット × 8 拡張 プレビュー + .md/.txt
  （拡張子小文字照合・大文字保持）+ 「dst 存在時は上書きしない」規則の
  移植 — `_delta_sidecar_move` との parity テスト）。定数は全て Python 側
  から opts で受領（単一の真実 = py/utils）。
- `mm-core`（api_version **3**）: `zipnn_delta_compress/decompress`
  （ジョブ化、meta は Python がサイドカーを読んで dict で渡す — 欠損時は
  空 dict = legacy 同一の劣化）、`walk_models`（JSON 配列）/
  `move_with_sidecars`（同期）。py/native.py の exact レンジ [3,3]、
  native.yml abi3 assert・Phase 2 テストの assert も同期。
- `py/compress.py`: デルタルート（worker/worker_body 化 + `_poll_native_job`
  抽出 = Phase 2 と共通ポーリング、phase map は delta 語彙）とバッチルート
  （native 時は ensure_zipnn を**呼ばない** = torch import 回避、
  `_run_native_job_sync` で executor 内ブロックポーリング、per‑file handle
  登録でバッチもキャンセル可、walk/sidecar move を Rust プリミティブへ）。
  バンドル意味論関数は全て Python のまま（Plan 規定）。
- **計測（K4/K5、docs/BENCH.md §8）**: `bench_native_delta.py` 新設
  （§7 と同一プロトコル）。限界 RSS: native +66.8/+54.2 MiB
  （2.09×/1.69× — 内訳は mmap clean ページ主体、匿名は O(1MiB)）vs
  legacy +173.6/+183.1（5.43×/5.72× 匿名コピー）→ 12GB 換算 <1GB 構造達成。
  K5: SEGFAULT クラス k∈{1,2,3} 全て生存 + byte‑exact（Phase 0 の同
  フィクスチャで legacy は signal 11 死亡と実証済み）。壁時間: native 圧縮
  0.304s（sha インライン込み）≈ legacy 0.295s（検証なし）、解凍 +0.09s 差
  = sha2‑soft 律速（§7.1 同型）。
- テスト: L1 132（delta 20 + batch 11 + プール回帰 1）、pytest **59**
  （Phase 3 +15: 両経路ゴールデン・クロスパス双方向・SEGFAULT クラス
  ルート・文言ゴールデン 3 種・.corrupt/paranoid/cancel・バッチ往復 +
  デルタ入り + 両エンジン parity・プリミティブ parity）、L5 GATE PASS
  （D1/D2‑single/D2‑stream）、L2 quick 再 PASS（1,121/1,121）、L3 新
  ターゲット `delta_decompress`（シード 7 件 = 実成果物系 + 敵対的系、
  スモーク 122,186 execs クラッシュ 0）、fuzz‑smoke/fuzz‑long 6 ターゲット化。
- バイナリ 2,376,240 B（ignore/serde_json/delta 増、予算 57 %）。

**運営メモ**: run 3（36148521214、de1a153 = プールキャッシュ修正）の
全 5 ターゲット緑確認で Phase 1 を [x] 化。Phase 3 push 後に
**run 4**（delta_decompress 込み 6 ターゲット）をディスパッチして
新サーフェスの 3h バジェットも消化する（週次スケジュールも 6 ターゲット）。

### run 36148521214 完走 — Phase 1 完了条件消化（2026‑09‑25 17:36 UTC）

- **全 6 ジョブ SUCCESS**: l2‑full + 5 fuzz ターゲット × 3 h（GitHub API で
  確認）。blob_decompress の最終ログ: **189,822,394 execs / 10,801 s 完走、
  最終 peak RSS 164 MB（limit 4096 MB の 1/25）、クラッシュ 0、
  exec/s 17,574（run 2 = 10,777 比 +63 %）**。プール churn は RSS 保持源
  であると同時にスループット税でもあった（exec ごとのスレッド spawn/join
  が消えた分がそのまま速度に返ってきた）。
- 実測保持率は ~0.6 B/exec（54→164 MB の大半はコーパス 266 KB + 探索状態）
  — ローカル A/B からの外挿（~8 B/exec → ~0.9 GB）すら保守的だった。
- Plan §6.2 Phase 1 完了条件と §9 を **[x] 化**（誤診だった「アロケータの
  ページ保持」の記録も真因に訂正済み）。
- **run 4 = 36162273129**（head 3bcb52b = Phase 3 ツリー、6 ターゲット × 3 h、
  run 3 終了を受けて自動開始）を新サーフェス（delta_decompress）の 3 h
  バジェット消化としてディスパッチ済み。完了確認は次セッション or
  週次スケジュール（日曜 18:00 UTC、6 ターゲット化済み）が担保する。
- Phase 2 精査バッテリーのデルタ版をこの環境で再実施（/tmp/audit3、
  **ALL CLEAN**）: P = EFBIG 注入でジョブ failed・残骸ゼロ・原本無傷、
  Q = SIGKILL（書込み中 → 掃運可能 tmp のみ / commit 後 → 成果物完全 +
  解凍検証 byte‑exact、どの窓でも torn file なし）、O = 二重サブミットで
  第 2 ジョブが create_new ガードに拒否され第 1 の成果物は検証可能。

## 2026‑09‑26 — 失われた dev 履歴の復元 + Phase 3 独立監査セッション

### セッション冒頭の重大発見: dev が c3b7919 へ force‑push 巻き戻しされていた

- **2026‑09‑26 05:03:54 UTC** の dev への push イベント（head `c3b7919d6` = PR #5
  マージ点。CI run #118 / native run #29 が誘発され両方緑）を GitHub API が記録。
  9/25 のセッションが push していた **12 コミット**（`d393587`…`c42513f` —
  Phase 2 精査修正 5 件、fuzz blob_decompress OOM 真因修正 2 件、Phase 3 実装本体、
  Phase 1 完了マーク）が dev/main 双方から消失していた（本セッションのクローン
  05:10 UTC の tip = c3b7919）。
- 復元: オブジェクトは GitHub に生存 → **SHA 指定 `git fetch origin <full‑sha>`** で
  9 コミットを回収（author は全て rikunarita = ユーザ自身の過去セッション作業。
  残り 3 コミット d393587/7178e32/4cce777 系は比較 API 経由で確認）し、
  `git merge --no‑ff c42513f` で dev へ復元（**efade4a**。履歴の書き換えなし =
  保守原則。tree は c42513f と完全一致を `git diff` 空で確認）。CI 証跡
  （fuzz‑long run 2/3/4、CI #113–#117、native #22–#28）が再びブランチから
  到達可能な SHA に紐づいた。
- **教訓（前セッションの「環境ロールバック事故」記録の再確認）**: ブランチは
  サンドボックス外でも巻き戻り得る。セッション開始時は `git ls‑remote` の tip を
  MEMO 末尾の記録と照合してから着手すること。ズレていたら force‑push の事実を
  ユーザに報告し、失われた作業の SHA 回収可能性を最初に確認する。

### 「fuzz‑long run 2 の全 5 ターゲット成功確認(~11:45 UTC)」への回答（GitHub API 実証）

**run 2（36114455354、head `4cce777`、08:43 UTC 開始）は 4/5 SUCCESS + l2‑full
SUCCESS であり、全緑ではない**: `blob_decompress` が **11:40:19 UTC に OOM 終了**
（RSS peak 4,097 MB > rss_limit 4,096 MB。live heap 26 MB = コーデックのメモリ
安全性欠陥ではなくスレッド churn 由来のランタイム メタデータ累積）。他 4 ターゲット
（st_parse / zn_header / codec_decompress / huf_decompress）は **11:44:14–11:44:30 UTC
に 3 h 完走 SUCCESS** — 「~11:45 UTC に 5 ターゲット」の認識はこの完了時刻群に
一致するが、5 本目は失敗している。真因と決着（復元済みコミット + 本セッションの
再確認）:

| run | head SHA  | 結果                                                                                                                                                                                                                              |
| --- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `3b3a3af` | 4/5 + l2‑full 緑。blob_decompress OOM（rss 2048 MB・旧ハーネス）                                                                                                                                                                  |
| 2   | `4cce777` | **4/5 + l2‑full 緑。blob_decompress は OOM 再発**（4096 MB でも ~35.5 B/exec の線形増加が 3 h で到達）                                                                                                                            |
| 3   | `de1a153` | **5/5 + l2‑full 緑（~17:36 UTC）** — 真因修正（`with_threads` の per‑call プール生成破棄 → CUSTOM_POOLS キャッシュ）後。blob_decompress 1.9 億 execs・peak RSS 164 MB・クラッシュ 0 = **Phase 1 完了条件（fuzz ≥8 h）の真の証跡** |
| 4   | `3bcb52b` | **6/6 緑（~20:39 UTC）** — Phase 3 ツリー。新ターゲット `delta_decompress` の 3 h 完走を含む                                                                                                                                      |

- 修正コミット 2 件（`4cce777` = ハーネス thread_local 化 + ASan チューニング +
  rss_limit 4096、`de1a153` = プール キャッシュ化 + 回帰テスト
  `explicit_thread_counts_reuse_cached_pools`）は巻き戻しで失われており、
  **復元しなければ週次 fuzz‑long（日曜 18:00 UTC）で blob_decompress の OOM が
  再発し続ける状態だった** — 本セッションの復元で解消。
- Phase 2 の「バグなし」最終確認の結論: 現行 dev tip（復元 + 本監査）は、
  Phase 2 精査セッションが発見した 5 バグの修正（d393587/7178e32）を**含み**、
  下記の再検証バッテリーが全緑。Phase 2 完了条件の残件は依然
  「参照機での K2/K3 再計測 + 実 UI 手動 QA」のみ（この環境では代替不能）。

### 独立再検証バッテリー（復元ツリー + 下記 GIL 修正に対し、全て本セッション実測）

- `cargo fmt --all --check` ✓ / `cargo clippy --workspace --all‑targets
--all‑features -- -D warnings` ✓（Rust 1.98.1 stable 再導入）
- `cargo test --workspace --exclude mm-core`: znn‑codec **132 緑**（監査回帰
  `atomic_writer_commits_and_aborts`（create_new 並行拒否・stale 引き継ぎ）/
  `header_size_guard_rejects_oversized_regions` /
  `explicit_thread_counts_reuse_cached_pools` の個別緑も明示確認）+
  `cargo test -p mm-core --no-default-features` **5 緑**
- `.so` 再ビルド（build‑native.sh linux‑x86_64、zigbuild glibc 2.28）:
  **2,375,424 B**（≤4 MB ゲート OK）、`verify_native_binary.py` ok:true、
  import 実証: `api_version()=3`・delta/batch 4 API 存在・`core_version()=
0.3.0‑alpha.0+efade4a1e`（マージコミット スタンプ）
- **L2 quick GATE PASS**: byte‑identical 1,121/1,121・mismatch 0・付録 C クラス
  63/63 安全処理・rust_err_other 0（`--out /tmp` でコミット済み証跡は不変）
- **L4 pytest 60 緑**（復元時の 59 + 本監査の新規 GIL 回帰 1。torch 2.14.0+cpu /
  safetensors 0.8.0 / hub 2.0.0 同梱環境）
- **L5 GATE PASS**（pip zipnn 0.5.4 実ビルド）: A/B/C 全方向 + **D1（Neo
  streaming デルタ → 公式解凍 byte‑exact）/ D2‑single / D2‑stream（公式デルタ
  両表記 → Neo 解凍）** = Phase 3 セクション D もこの環境で再現
- **K4/K5 独立再計測**（bench_native_delta.py、同一セッション交互 3 ラウンド +
  SEGFAULT クラス）: 限界 RSS 倍率 native **2.13×/1.69×** vs legacy
  **5.39×/5.72×**（÷2.5/÷3.4 — BENCH §8 の 2.09×/1.69× と一致）。SEGFAULT
  クラス total%256KiB∈{1,2,3} = **3/3 生存 + byte‑exact**
  （`k5AllSurvivedByteExact: true`。各 +3 MiB・圧縮 0.005 s）。壁時間は
  native 圧縮 0.134 s（**ftSha256 インライン込み**）< legacy 0.211 s、
  解凍 0.104 s vs 0.129 s — 本セッションの窓では native が legacy を上回った
  （セッション間比較は無効・同一セッション比のみ有効の原則通り）
- ruff check + format（38 files）✓ / mypy **14 files Success**（hub 2.0.0 で
  再現 = f4c1a4c の cast 修正が現行 PyPI 解決でも有効）/ `pnpm install
--frozen-lockfile` → `pnpm format:check`（prettier + tailwind plugin）全ファイル ✓
- L3 ローカルスモークは**意図的に未実施**: 本セッションのコード変更は mm‑core の
  GIL 解放のみで fuzz 6 ターゲットは全て znn‑codec 表面（delta_decompress 含む）=
  変更ゼロ。run 4 の 3 h 緑実績がそのまま有効で、push 時の CI fuzz‑smoke
  （6×60 s）+ 新 tip への fuzz‑long ディスパッチ（run 5）が担保する。

### 監査で発見し修正した不備（本セッションの唯一のコード変更・1 件）

**【中】`walk_models` / `move_with_sidecars`（同期プリミティブ）が GIL を
解放していなかった** — Plan §4.2.2 設計不変条件 (2)「長時間 API は
`py.allow_threads()` で GIL 解放」への違反。バッチ ルートは
`batch_process_folder`（cpu_executor 内）から `mm.walk_models` を呼ぶが、
Rust 並列 walk の全行程で GIL が保持される → **executor 経由であっても
イベントループ（ws 配信含む）が walk 中フリーズ**する。legacy の `os.walk` は
バイトコード境界で GIL を手放してループがインターリーブできたため、
ネットワーク ストレージ + 大規模ライブラリ（Plan §1.2.2 #9 の環境）では
秒級の応答性退行になり得た（課題 #6 / K12 が潰したのと同じクラスの问题）。
preflight の `_walk_files`（イベントループ上で同期実行 — legacy からの
既存挙動で native 化によりむしろ高速化）は本修正の対象外・構造変更なし。

- 修正: 引数抽出（GIL 必要）後に **`py.detach()`** で walk/直列化と
  readdir/rename を GIL フリー実行（mm‑core jobs.rs の 2 関数 + lib.rs 签名）。
- **PyO3 0.29 の API 名は `allow_threads` ではなく `detach`**（一次ソース:
  pyo3‑0.29.2 src/marker.rs L562 `pub fn detach<T, F>(self, f: F) -> T
where F: Ungil + FnOnce() -> T`。`PyErr` は `Ungil`（err/mod.rs L48）なので
  `PyResult<T>` の返却可。stable では `Ungil = Send + 'static` blanket
  （marker.rs L192））。クロージャへ `&str` 借用を持ち込めないため
  root/src/dst は owned 化（String/PathBuf）。**Plan §4.2.2 の文言も
  `py.detach()` 注記付きへ更新済み**（次フェーズの実装者が同じ罠
  （allow_threads 名での E0599）を踏まないように）。
- **A/B 実証**: 新規 pytest `test_walk_models_releases_the_gil`
  （1,500 ファイル ツリー。スピン Python カウンタスレッドは walk 実行中に
  GIL を得られて初めて進む → 解放されていなければ delta=0 で決定論的に失敗）が
  **修正前バイナリで FAIL（counter 前進ゼロ）→ 修正後バイナリで PASS**。
  GIL 解放の事実を機械的に固定した（CI integration 3 OS で毎回実行される）。
- 付随観察（**再現せず・参考記録**）: A/B の旧バイナリ実行に一度だけ
  リポジトリ直下へ 26 MB の ELF コアダンプ（`core`、ulimit -c unlimited 環境）が
  出現。同一条件の再実行では再現せず、修正版バイナリでは pytest フルスイート
  複数回で未発生。GIL 飢餓スレッド + インタプリタ shutdown の偶発競合と推定するが
  確証なし（旧バイナリは差し替え済みで追及不能）。削除済み・追跡外。
  今後 `core` が見えたら**コミットに含めない**こと（.gitignore 対象外のため
  `git status` で確認）。

### 運営メモ（次セッション向け）

- 本セッションの push 構成: efade4a（復元マージ）→ fix(mm-core) GIL 解放 +
  回帰テスト → docs（MEMO/Plan 更新）。push で CI + native が自動実行、
  fuzz‑long は新 tip へ **run 5** をディスパッチ済み（6 ターゲット × 3 h —
  成功確認はユーザ側次ターン / 週次スケジュール）。
- native‑bin の成果物（.so）は gitignore 済みでコミット対象外（CI が
  main/tag で生成する運用 — Phase 0 確立）。
- Phase 3 の Plan 完了条件 [x] は本監査の再検証で**実態と一致**を確認した。
  残るプロジェクト全体の残件: Phase 2 K2/K3 参照機再計測、実 UI 手動 QA
  （Phase 7 の USAGE 改訂時に統合）、Phase 4 以降。

## 2026‑09‑26（第 2 独立セッション）— fuzz‑long run 5 監視 + Phase 0–3 最終バグチェック

### GitHub Actions 確認結果（ユーザ質問「fuzz‑long が 1 時間 30 分経っても終わらない」への回答）

**結論: run 5 は 3 h バジェットの正常実行中であり、修正は不要だった。**

| run                         | head                  | 状態                                                                                                                                                                      |
| --------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| native #32                  | `3ad33b6`（dev tip）  | **SUCCESS — 14 ジョブ全緑**（native‑test×3 OS / native‑build linux・macos・windows / abi3‑import 3.10・3.13 / integration×3 OS / native‑diff / fuzz‑smoke / size‑budget） |
| CI #121                     | `3ad33b6`             | **SUCCESS**（verify: typecheck / lint / lint:css / deps / format / build / mypy / ruff / pytest）                                                                         |
| fuzz‑long #5（36222860726） | `6bfe6d7`             | **in_progress**（06:08:37 UTC dispatch、workflow_dispatch、actor=rikunarita = 前セッションのディスパッチ）。l2‑full は SUCCESS、6 fuzz ターゲットは実行中                 |
| native #30 / #31            | `fc59463` / `6bfe6d7` | cancelled — native.yml の concurrency `cancel‑in‑progress: true` による**設計動作**（短時間の 3 連続 push で旧 run が取消）。異常ではない                                 |

**「1.5 h 経っても終わらない」の根拠（API 実測）**:`hours` 入力は REST API に露出しないため実測で裏取りした —
各ターゲットの「Fuzz … for the scheduled budget」ステップ開始は **06:10:23–06:10:50 UTC**（jobs API の steps）、
run 4 の同ステップ実測は **3 h 00 m 53 s**（17:38:19→20:39:12）→ **ETA は 09:11–09:15 UTC**。
hours=1 なら ~07:11、hours=2 なら ~08:11 に終了しているはずで、08:15 時点で 6 ターゲット全て
fuzz ステップ実行中という観測は hours=3 とのみ整合（前セッション MEMO の運営メモ「run 5 = 6 ターゲット × 3 h」とも一致）。
libFuzzer はクラッシュ/OOM 検出時にジョブを即 fail するため、**2 h 超の走行継続 = ここまでクラッシュゼロ**
（run 3/4 と同様の挙動）。09:00 UTC 時点でも 6 ターゲット in_progress を再確認した。

head が tip `3ad33b6` でなく `6bfe6d7` なのは dispatch が最終コミットに先行したためで、
両者の差分は **.gitignore の 6 行のみ**（`git diff --stat` で確認）= fuzz 対象コードはゼロ差。

### 環境再構築（セッション冒頭ロールバック对策）

apt（aliyun ミラーは今回 1.8 MB/s に回復 — package list 不完整が最初の install 失敗原因で、
update 再実行で解消）→ build‑essential / clang / mold 1.10.1 / libpython3.11‑dev、
rustup stable **1.98.1**、pip: ruff **0.16.8**（CI ピン）/ mypy / pytest / torch 2.14.0+cpu /
safetensors 0.8.0 / cargo‑zigbuild 0.23.4 / ziglang 0.16.0 / maturin 1.15.0 /
zipnn 0.5.4（ソースビルド成功）、corepack → pnpm 12.3.4 + `pnpm install --frozen-lockfile`。

**新教訓**: `nohup … &` のバックグラウンドプロセスは、起動元のツール呼び出しがタイムアウト
終了すると**プロセスグループごと巻き込まれて死ぬ**（実測: 最初の cargo 実行が ~9 分で静黙死）。
長時間ビルドは **`setsid`** でセッションから切り離すこと（2 回目以降は完走）。

### 全ゲート再検証（修正前ツリー 3ad33b6 に対し、全て本セッション実測・全緑）

- cargo fmt ✓ / clippy `--workspace --all-targets --all-features -D warnings` ✓
- cargo test: znn‑codec **132**（debug + release 両方）✓ / mm‑core `--no-default-features` **5** ✓
- ruff check + format（39 files）✓ / mypy **14 files Success** ✓（huggingface_hub 2.x 環境 =
  f4c1a4c の cast 修正が現行 PyPI 解決でも有効であることを再確認）
- `.so` 再ビルド（build‑native.sh linux‑x86_64、zigbuild glibc 2.28）: **2,375,424 B —
  前セッション記録とバイト単位で同一サイズ**（決定論的ビルド）、size gate OK、
  `verify_native_binary.py` ok:true / **GLIBC_2.28** / libpython 非依存、
  import 実証 `api_version()=3`・10 API 全存在・`core_version()=0.3.0‑alpha.0+3ad33b696`
  （**MM_CORE_COMMIT スタンプが現行 tip = build.rs 陳腐化修正の実証**）
- pytest **60 passed・skip ゼロ**（実バイナリ against — GIL 回帰テスト込み）
- **L2 quick GATE PASS**: byte‑identical **1,121/1,121**・mismatch 0・付録 C クラス **63** 安全処理・
  forbidden_rust_err 0・c_self_unverified 0（`--out /tmp` でコミット済み証跡は不変）
- **L5 GATE PASS**（pip zipnn 0.5.4 実ビルド against）: A/B/C + **D1 / D2‑single / D2‑stream** 全方向

### Phase 0–3 最終精査で発見し修正したバグ（1 件・本セッションの唯一のコード変更）

**【低・潜在 API 欠陥】`delta::delta_decompress` の verify スイッチで match 腕が逆転** —
テンソル側パイプライン（pipeline.rs）は期待 sha を verify でゲートしてから match する
（`let src_sha = if opts.verify { sha_recorded } else { None }`）ため `verify=false` が
正しく「Skipped + 正直な警告」になるが、デルタ側は **raw の `meta.ft_sha256`** で match し、
ハッシャ有効化のみ `want_sha = verify && is_some()` でゲートしていた。帰結:

1. `verify=false` + ftSha256 記録あり（**Neo デルタ成果物は全て記録あり**）→ digest=None が
   `(Some, None)` 腕に落ちて **"internal: hasher produced no digest despite a recorded
   ftSha256" エラーでジョブ失敗**（同腕の「unreachable」コメント自体が誤り — 到達可能だった）、
2. `verify=false` + 記録なし → `(None, _)` 腕が **「ftSha256 is recorded but verification was
   disabled」と嘘の警告**（記録がないのに「記録があるが無効化された」と言う）。

**本番ルートは無影響**: py/compress.py のデルタ呼び出し 2 箇所（ルート L1686・バッチ L1368）は
`{"threads": 0}` のみを渡し verify は既定 true。ただし `jobs.rs::parse_opts` は `"verify"` を
受理し lib.rs の docstring も `verify (default true)` を公開しており、**API 文書に従う将来の
呼び出し側が確実に踏む**生きた API 表面の欠陥だった（Plan §4.4.3‑2 の「検証 OFF スイッチは
plan が示唆する対称性のためのもの」= スイッチは機能する前提で存在する）。

- **修正**: pipeline.rs と同型化 — `sha_expected = if opts.verify { meta.ft_sha256.as_deref() }
else { None }` を導入し `want_sha = sha_expected.is_some()`、match を `(sha_expected, digest)`
  へ。`(Some, None)` が真に到達不能（内部不変条件）になり、`(None, _)` は**サイドカー記録の有無で
  正直に分岐**（警告文 2 種は既存のものを正しい条件へ割り当て直しただけ）。
- **A/B 実証**: 新回帰テスト `verify_off_skips_the_recorded_sha_with_an_honest_warning` が
  **修正前コードで FAIL**（panic 文言 = `internal: hasher produced no digest despite a recorded
ftSha256` — 予測と逐語一致）→ **修正後 PASS**。テストは両腕を固定: verify=false+記録あり →
  Skipped + "disabled" 警告 + byte‑exact 復元 + `.corrupt`/tmp 残骸なし、記録なし →
  "no ftSha256" 警告 **かつ** "disabled" 文言を出さない。
- **修正後の再検証（全緑）**: fmt ✓ / clippy `-D warnings` ✓ / L1 **133**（debug + release）✓ /
  mm‑core 5 ✓ / `.so` 再ビルド **2,375,264 B** + size gate + verify ok + api 3 ✓ /
  pytest **60**（新バイナリ against）✓ / **L5 再実行 PASS** ✓ / **L2 quick 再実行 PASS**
  （znn‑cli 再ビルド後 1,121/1,121・mismatch 0・付録 C 63）✓ / prettier `format:check` ✓
  （pnpm 完全依存ツリー、lockfile ピン版）

### 今セッションが fresh eyes で集中的に確認しバグなしと判定した領域（negative findings）

- **mm‑core**: jobs.rs（レジストリ + gc（1 h / 4,096 cap）・spawn 失敗路の terminal 記録・
  catch_unwind → ジョブエラー化・job_progress の outcome 権威 terminal 窓・handle 登録/払底）、
  lib.rs（API_VERSION 3 = native.py exact レンジ / native.yml abi3 assert / lib.rs テストの三者同期）
- **py/native.py**: origin guard（realpath + normcase）、ハンドシェイク、sys.modules 非汚染、
  MM_NATIVE 4 モード、diagnostics
- **py/compress.py 全ルート**: `_run` / `_run_batch` / `_run_delta` / `_poll_native_job` /
  `_run_native_job_sync`（handle の finally 抹消、lambda 既定引数による late‑binding 回避）、
  `_cleanup_targets`（dst 非削除）/ `_cleanup_delta_failure`（native 時 tmp 非接触・
  committed‑but‑sidecar‑less のみ dst 削除）、`cleanup_stray_files`（15 分年齢ガード・
  `.corrupt` 報告のみ）、cancel ルート（legacy 応答分岐）、worker 二重例外ガード
- **batch.rs ⇔ Python parity**: 3 walker（拡張子**大文字小文字区別付き**比較 = splitext +
  folder_paths と同一、symlink‑dir 非追跡・symlink‑file 候補・壊れ symlink = file 扱い
  （os.walk の is_dir 例外挙動と一致）、不能読ディレクトリ静黙スキップ、root 非 prune、
  sorted 安定順）、`py_splitext` の先頭ドット規則、move_with_sidecars（slot‑major 20×8・
  desc sorted + isfile + 拡張子大文字小文字保持・never overwrite・makedirs・本体非移動）
- **AtomicWriter**: create_new + 15 分 stale 引き継ぎ、commit = rename 地点、dir fsync
  warning 化、reject_to、Drop ガード、`.tmp` 命名の両パイプライン一致
- **delta.rs（修正箇所以外）**: Rendering 4 領域 copy_range の境界代数、Unpadder 状態機
  （prefix 書換・pad skip・finish 枯渇検査）、decode_delta_container の remaining_expected
  割り当てキャップ + fp8 クランプのデルタ面適用、streaming 連鎖の境界 walk（clen≥32・
  checked_add・truncated エラー）、単一コンテナ受理、`create_dir_all`（legacy makedirs parity）、
  paranoid（内部 Hooks progress=None・rename 前）、サイドカー原子コミット + 失敗 = ジョブ失敗
- **pipeline.rs**: H_max 上界の構成（worst_infos 全集 + より長い shape/dtype + source
  オフセットの単調性）、seek‑back patch が最後の書込みであること、rewrite_with_header
  フォールバック（`.tmp.fix` = Python 掃除対象と一致）、並行 source sha（scoped thread・
  cancel 伝播）、checked offset 累積、stream_write 4 MiB 分割、paranoid の `.verify.tmp`
  二重 suffix も起動掃除に捕捉されること
- **safetensors_io**: validate_entries（dense・exact‑coverage・ビット境界・サイズ一致）、
  build_header_region（serde_json 最小エスケープ・8B スペースパディング・`__metadata__` 先頭）、
  py_escape_json_string（json.dumps ensure_ascii: 小文字 hex・サロゲートペア）、
  py_dumps_compressed_vectors（Python 既定 separators）
- **znn_tensor / codec / header / dtype**: dtype 表 = MEMO の実証記録と一致、fp8 チャンク
  クランプ（ヘッダーは 18・実行時のみ min(128 KiB)）、inspect の shape×elem==original_len、
  blob×64 floor 16 MiB キャップ、CUSTOM_POOLS + MAX_EXPLICIT_THREADS=64 ガード（de1a153 の
  修正が現行ツリーに生存）、ヘッダー バージョンゲート 0.5.0–0.5.4、decode_delta の method
  ゲート免除 vs テンソル経路の厳格ゲート
- **CI 配線**: native.yml 14 ジョブ / ci.yml（ruff 対象・pytest）/ fuzz‑long.yml（6 ターゲット・
  ASAN_OPTIONS・rss_limit 4096）— 全て MEMO 記録と一致
- **fuzz 6 ハーネス**: thread_local 再利用バッファ、threads=1 + プールキャッシュ前提、
  delta ターゲットの単一 blob 両側導出 + 1 MiB 出力キャップ

**バグではないが確認して記録する items**（Phase 0 以前からの既存設計・文書化済み既知残件 —
いずれも今回の最終チェック範囲で意図的に未変更）:

- `ZIPNN_TASKS` は増えるのみで削除されない（1 タスク ~200 B — HF upload タスクと同形の既存設計。
  GC 方針の導入はスコープ外）
- `is_enospc` は Linux EDQUOT(122) を列挙しない（メッセージ cosmetics のみ — 一般的な quota は
  ErrorKind::StorageFull 経路で捕捉される）
- コミット rename が「route の dst 存在チェック後に第三者が作った dst」を上書きする理論窓
  （legacy の os.replace と同一窓 — Phase 2 精査時に既知として記録済み）

### 運営メモ（次セッション / ユーザ向け）

- 本セッションの push 構成: fix(znn‑codec)（verify スイッチ修正 + 回帰テスト）→ docs（MEMO/Plan）。
  push で CI / native が新 tip に対して自動実行（fuzz‑smoke 6×60 s が fuzz 表面を再検証）。
- **fuzz‑long run 6 はディスパッチしない判断**: 本修正は fuzz 表面に一切触れない
  （`delta_restore_fuzz` → `delta_restore` / `decode_delta_container` / `Unpadder` はゼロ変更。
  変更したのは fuzz が呼ばない `delta_decompress` の verify 分岐のみ）ため、**run 5
  （head 6bfe6d7）の 3 h×6 証跡は現行ツリーに対してそのまま有効**。18 h ランナーバジェットの
  保守的運用 + 週次スケジュール（日曜 18:00 UTC・6 ターゲット）が担保。
- run 5 の ETA は **09:11–09:15 UTC** — ユーザ次ターンで完了確認を（全 7 ジョブ success +
  クラッシュアーティファクト 0 件）。確認できたら本 MEMO の run 表に結果を追記すること。
- プロジェクト全体の残件は不変: Phase 2 K2/K3 の参照機再計測、実 UI 手動 QA（Phase 7 統合）、
  Phase 4 以降。

### run 5 完走 — 全 7 ジョブ SUCCESS（2026‑09‑26 09:13:14 UTC、本セッションで確認・消化）

上記 ETA（09:11–09:15 UTC）通りに完走。**Phase 3 新ターゲット `delta_decompress` の
初 3 h バジェット消化を含む、6 ターゲット × 3 h = 18 h の追加証跡**（run 4 に続く 2 回目）。

| ジョブ                | 結果    | 最終統計（ジョブログの libFuzzer DONE 行）                                                |
| --------------------- | ------- | ----------------------------------------------------------------------------------------- |
| l2‑full（10,500 件）  | SUCCESS | 06:15:03 UTC 完了（6 m）                                                                  |
| fuzz st_parse         | SUCCESS | cov 2,482・exec/s 16,338・最終 RSS **198 MB**                                             |
| fuzz zn_header        | SUCCESS | cov 247・exec/s 24,397・最終 RSS **142 MB**                                               |
| fuzz codec_decompress | SUCCESS | cov 1,605・exec/s 4,228・最終 RSS **211 MB**                                              |
| fuzz huf_decompress   | SUCCESS | cov 541・exec/s 11,486・最終 RSS **171 MB**                                               |
| fuzz blob_decompress  | SUCCESS | **#183,708,290 DONE**・cov 1,472・exec/s 17,008・最終 RSS **172 MB**（lim 4,096 の 1/24） |
| fuzz delta_decompress | SUCCESS | cov 1,617・exec/s 7,617・最終 RSS **205 MB**                                              |

- blob_decompress は run 3（1.90 億 execs・164 MB・17,574 exec/s）とほぼ同一 =
  **プールキャッシュ修正（de1a153）の効果が長期 run で安定再現**。RSS は全ターゲットで
  上限の 1/20 以下、libFuzzer エラー行ゼロ、クラッシュアーティファクトゼロ。
- head `6bfe6d7` と現行 tip `bd47254` の実コード差は delta.rs の verify 分岐
  （fuzz 表面外）+ docs のみ → **この証跡は現行ツリーの fuzz 表面に対してそのまま有効**
  （push 済みの native #33 fuzz‑smoke 6×60 s が新 tip の表面を機械再検証）。

## 2026‑09‑26（第 3 セッション）— Phase 4 実装（dtype 大幅拡張・Neo 拡張帯）

**完了**: Plan §6.2 Phase 4 の全タスクを実装・全ゲート緑・[x] 化。
コミット構成（dev）: ce7cbc9（codec コア層: 8 平面/トランケーション/dtype 表）→
8c50af7（テンソル/パイプライン層: 全 22 dtype・マーカー・select_truncation）→
9b20bcf（py バックエンド + L4 53 テスト + inspect ルート）→ 9804571（L5 セクション E）→
6972bb3（fuzz シード 14 件 + 8 平面表面）→ 6965fc6（UI: 確認文/圧縮方式行/バッジ/i18n×3 + web バンドル）→
bef8f08（bench_phase4_dtypes.py + K14 証跡 JSON + BENCH §9）→ f124c90（README×2/USAGE×3 相互運用マトリクス）→ 本 docs コミット。

### 着手前の一次実証（この環境で実行、推測ゼロ）

- **公式 zipnn 0.5.4（pip 実ビルド）の失敗モード**: 互換帯 f32 ブロブの
  byte15 を 9/128/130/137/3/24 へパッチして投入 → **全て
  `ValueError: Unsupported Dtype N`**（`decompress_bin` の dtype 分岐に
  それらの腕が無い）。公式 compress も complex64/float64/int32/bool で
  ValueError（"Support only…"）。→ **C64 は Neo 帯 130 で確定**
  （Plan §4.6.3 の未確定事項が実証で決着。L5 E2 が CI で恒久固定）。
- **torch 2.14.0 実機**: dtype 全数 dir() 確認 — `bcomplex32`/`complex32/128`/
  `uint16/32/64`/`float8_e8m0fnu`/`float4_e2m1fn_x2`/`uint1–7` は存在、
  **`float6_*_pe` は存在しない**（Plan §4.6.1 の予想はリリースに
  含まれず。Web 検索でも該当名ゼロ件）→ F6 系の infos には safetensors 名
  （"F6_E2M3"）を記録（実在しない torch 名を捏造しない方針）。
- **safetensors 0.8.0（pip + GitHub v0.8.0 tensor.rs 一次ソース）**:
  Dtype enum 22 種（F4=4bit・F6_E2M3/E3M2=6bit・F8_E8M0=8bit）。
  `safetensors.torch.save` 実測: F4 テンソルは **shape がニブル数に倍化**
  （uint8 [4] → F4 shape [8]、data 4 B）→ sub‑byte の shape 検証は
  **bits 基準**（nelem×bits/8 == original_len + バイト境界）で実装。
  `complex128`/`complex32`/`bcomplex32` は save 不可（KeyError /
  view_as_complex 非対応）→ code 129/131 は **codec 級のみ**
  （pseudo st 名 "C128"/"BC32"、pipeline 復元は
  「safetensors 0.8 表現なし」の明示エラーで拒否 = 標準ツールが読めない
  ヘッダーを絶対に書かない）。
- **C コアのトランケーション**: dtype32 の 41/9/1 は
  **コメントアウトされた死にコード**、dtype16 の 8/1 は split が
  plane1 を NULL のまま返し compression_worker が
  compChunksSize/Type[1] を**未初期化のままコンテナに書く**（しかも
  py_combine_dtype は `oneBufRatio[b] = numBuf` で ratio を上書きするため
  復号側も整合しない）。zipnn.py からも到達不能（uint32‑numpy 経路は
  先頭 raise のデッドコード）→ **トランケーションは Neo 独自のクリーン
  意味論で正式実装**（Neo 帯専用なので公式互換性の制約を受けない —
  公式はどのみち dtype code で拒否する）。

### 実装（設計決定を含む）

- **dtype.rs**: Neo 拡張帯コード表 128–146（Plan §4.6.3 の割り当てそのまま）、
  **MODE_8PLANES = 88** 新設（上流が定義/書込みする全 byte5 値
  {0,1,8,9,10,41,169,220,255} と非衝突 — 8 平面は上流に存在しないため
  Neo が値を定義する。ニモニック = 8 平面）。PlaneScheme に
  bits_per_elem/band/trunc_modes を追加、`plane_mask(byte5, n)` が
  **検証表とマスク導出の単一の真実**（validate_mode はそのラッパ化）。
- **トランケーションのコンテナ形式 = 「numBuf 維持」案を採用**: 落とし
  平面は空 raw チャンク（type 0・cumSizes 差分 0）として構造に存在し続ける
  → コンテナのサイズ代数（types_len/cums_len/plane_base/uniform）が
  **無変更**（L2 のバイト同一性が構造的に保証される最小差分）。マスク
  {2pl: 1=[T,F] 8=[F,T]; 4pl: 41=[T,T,T,F] 9=[T,T,F,F] 1=[T,F,F,F]}。
  復元は 0 埋め（C combine_buffers_dtype16 の 8/1 と同じデータフロー）。
  整列強制（orig_len/chunk % word == 0）、敵対的コンテナ（落とし平面の
  type≠0 / 非ゼロ長 / cum タンパリング）は Corrupt エラー（L1 固定）。
- **planes.rs**: split8/join8（u64 語変換融合・64B ブロック転置・tail
  bytes 0..rem 無変換 = C in‑bounds の一般化）+ split_masked/join_masked/
  extract_plane_masked（kind≠None は拒否 — トランケーションは整数専用
  のため bit_reorder=0 のみ正当）+ validate_layout（F64↔8 平面の
  相互排他）。**互換帯の既存経路は 1 バイトも変更なし**（マスク分岐は
  truncated 時のみ = L2 1,121/1,121 で機械証明）。
- **codec.rs**: num_buf∈{1,2,4,8}・kind_for(1,8,_)→F64（8 平面が f64
  scheme を含意）・圧縮/解压の双方でマスク対応（chunk_sizes/exp の
  マスク導出・落とし平面の type/長検証・join_masked）。decompress_container
  に **帯別 byte5 厳格ゲート**（scheme.allows_mode: 互換帯ブロブは正準
  モードのみ受理 — 公式エンコーダはトランケーションを絶対に書かないため、
  互換帯 + trunc モードの組み合わせは敵対的ファイル限定 → 推測復号せず拒否）。
  decode の exp 合計検査は truncated のみ免除（構造上 kept×elems で
  cur_len を覆わない — 整列は入口で証明済み）。
- **znn_tensor.rs**: DTYPE_TABLE 単一表（code ⇔ st 名 ⇔ torch 名 ⇔
  bit_reorder。幾何は dtype.rs から導出 = 二重表のドリフトを構造化防止、
  一致性テスト `table_is_consistent_with_the_dtype_module` で全行固定）。
  全 22 st dtype + pseudo 2 種。`select_truncation`（ゼロ統計: 上位
  平面から early‑exit 走査、I16/U16 は low‑zero→mode 1 / high‑zero→mode 8、
  I32/U32 は 41/9/1。**負値は上位 0xFF のため自動的に非トランケート**）。
  inspect_tensor の shape 検証を bits 基準へ（F4/F6 対応 + 境界強制）+
  帯別モード ゲート。bit_reorder の decode は**寛容のまま**（公式が
  reorder_signbit オプションを持つ歴史のため、互換帯で新規厳格化しない —
  1 平面は C と同様に無視）。
- **pipeline.rs**: 全 dtype 圧縮帯化（Band enum 廃止 — compressible_scheme =
  Option<TensorScheme>、None は防御的 pass‑through のみ）。「out‑of‑band
  floats」警告は消滅（対象ゼロ）。**extended マーカー = 「Neo 帯ブロブが
  実格納された」時のみ**（H_max 計画は worst_extended で必ず鍵を予算化 →
  実 meta は部分集合 = 領域超過が原理的に起きない。size 則で pass‑through
  した Neo テンソルはファイルを公式互換のままにする — テストで固定）。
  復元計画に pseudo dtype 拒否（dtype_bitsize None → 明示エラー）。
- **py/compress.py**: `POST /model-manager/zipnn/inspect` 新設
  （ヘッダのみ解析・io_executor 経由・エラーは `{"error":…}` +
  success:true で返しダイアログを絶対にブロックしない）+
  `COMPAT_ST_DTYPES` 分類表（**Rust 表との parity を pytest が機械固定**:
  分類器の extended 判定 == エンジンが書くマーカー、を全 22 dtype で照合）。
  レガシー経路は無変更（拡張帯ファイルの legacy 解凍は vendored の
  `Unsupported Dtype` 明示エラー = テスト化、legacy 圧縮の f64 raise も
  既存挙動のまま = テスト化）。
- **UI（Plan §4.6.4）**: 圧縮確認は**即時表示 → inspect 到着で
  インプレース更新**（表示を遅らせない・settled/visible ガードで
  閉じたダイアログを触らない・失敗時汎用文フォールバック）。
  Information タブ「圧縮方式」行（infos 集計 `name×count` 降順）+
  Neo 拡張バッジ/ツールチップ + rawRows から znn_* 記帳キー除外
  （数 KB の infos JSON 生表示の解消）。i18n en/ja/zh・web バンドル再構築。
- **fuzz**: シード 14 件（生産経路で生成した実ブロブ: f64/i64 8 平面・
  bool/e8m0/f4 1 平面・c64・i32 trunc 1/9/41・u16 trunc 8・落とし面
  type タンパリング（エラー経路誘導）・拡張 .znn の st_parse 種子。
  生成時に byte5 モードを機械検証）。codec_decompress の num_buf 表面を
  {1,2,4} → {1,2,4,8} へ拡張（byte_reorder は元々任意 u8 = 88/41/9/1/8 を
  カバー）。**fuzz ワークフロー変更不要**（6 ターゲットが新表面を自動被覆、
  push 時の fuzz-smoke + ディスパッチ run 6 が担保）。
- **CI 変更不要を確認**: api_version 3 のまま（新 Python API なし —
  inspect は Python 側。native.yml の abi3 assert==3・py/native.py [3,3]・
  ローダーテストの三者同期は不変）。integration の pytest/L5 が新テストを
  自動収容（win/mac は torch なし → importorskip / MMNEO_SKIP_LEGACY で
  skip 済み）。native-diff（L2 quick）は互換帯不変のためそのまま緑。

### 検証バッテリー（全てこの環境で実測・最終ツリー against）

- cargo fmt ✓ / clippy `--workspace --all-targets --all-features -D warnings` ✓
- L1 **155**（debug + release 両方 ✓、+22: planes 8/masked・dtype 表・
  znn_tensor 全 dtype/truncation/ゲート・pipeline Phase4 5 種・codec 8 平面/trunc/タンパリング）
- mm-core `--no-default-features` **5** ✓
- **pytest 113**（+53: tests/test_phase4_dtypes.py — 全 22 dtype 往復 ×
  マーカー × 分類 parity・torch 実物 save_file 全 dtype 往復（uint16/32/64・
  e8m0fnu・float4_x2・fnuz 込み、公式 load_file での読み戻し照合）・
  truncation byte5 端到端（9/1/41/8/220）・BOOL 0.125/E8M0 実測・
  マーカー不在 semantics・legacy 明示拒否・inspect ルート契約・
  破損ファイルの error フィールド化）— 実バイナリ against、skip ゼロ
- **L2 quick GATE PASS**: byte‑identical **1,121/1,121**・mismatch 0・
  付録 C クラス 63 安全処理・forbidden_rust_err 0（**互換帯の出力バイトが
  Phase 3 と完全同一** = Phase 4 の変更が互換帯に一切触れていない証明）
- **L5 GATE PASS**（pip zipnn 0.5.4 against）: A/B/C/D 退行なし +
  **E0–E4 新設全 PASS**（E1: Neo 帯 4 コードの明示拒否・E2: C64 帯域
  実証・E3: 公式 SafeOpen テンソル単位契約・E4: 拡張フィクスチャ往復）
- ruff check + format（41 files）✓ / mypy 14 files ✓ / pnpm typecheck ✓ /
  eslint ✓ / prettier format:check ✓ / pnpm build ✓（web バンドル同梱コミット）
- **K14 証跡**: bench_phase4_dtypes.py → 22/22 往復 PASS
  （results/phase4_dtypes.json コミット。BOOL **0.125** = Plan §4.6.2 の
  「約 1/8」実測一致・F64 0.515・I64 0.313・I32 trunc41 0.532・C64 0.802・
  trunc 自動選択 9/1/8 の実証 0.500/0.250/0.500・全件 verified=sha256 +
  byte‑exact・code/byte5 の実測値が表と一致）
- .so 再ビルド（zigbuild glibc 2.28・最終コミット スタンプ）: サイズは
  2,399,960 B（+24.7 KB、予算 4 MB の 57 %）・size gate OK・
  verify_native_binary ok（GLIBC_2.28 上限・libpython 非依存）

### バグではないが確認して記録する items（Phase 4 の設計境界）

- **L5 フィクスチャの vocab（I32）は Phase 4 で Neo ブロブ化**（公式は
  pass‑through のまま）= 意図的 diverge。L5 A/C を帯域認識へ更新し、
  「公式 pass‑through 側が原本バイトを保持」することも検査化。
- test_blob_parity の U8 テンソル（100 B の bytes(range)）は**両エンジン
  とも size 則で pass‑through**（決定論的データなので parity は安定维持）。
- `get_model_metadata` の 1 MiB ガード（MoE の巨大 infos で metadata 空 →
  バッジ/内訳行が非表示になり得る）は Phase 5 B4（32 MiB 統一）の既知残件
  — Phase 4 のスコープ外（既存制限、実測 600 テンソル級では ~48 KB で無影響）。
- F6 系 infos の dtype 文字列は safetensors 名（"F6_E2M3"）— torch 名が
  実在しないため（実機確認）。legacy 解凍側はどのみち code 145/146 で
  明示拒否なので infos 文字列の消費者は Neo/UI のみ。
- I64/U64 にトランケーションなし（Plan §4.6.2 表の通り — 8 平面の
  ゼロ上位面は huff0 が数バイトへ潰すため実測上の損失は小さい:
  I64 0.313）。

### 運営メモ（次セッション / ユーザ向け）

- push で CI（verify）+ native（native-test×3/build×3/abi3-import/
  integration×3/native-diff/fuzz-smoke×6）が新 tip に対して自動実行。
  **結果確認はユーザ次ターン**（ユーザ指示）。
- **fuzz-long run 6 はディスパッチ済み**（Phase 4 が fuzz 表面を変更した
  ため run 5 の証跡では新表面を覆わない: codec の 8 平面/trunc 分岐・
  dtype 表 128–146・新シード 14 件。6 ターゲット × 3 h = 18 h、head は
  最終 tip）。完了確認は次ターン / 週次スケジュール（日曜 18:00 UTC）。
- プロジェクト全体の残件: Phase 2 K2/K3 の参照機再計測、実 UI 手動 QA
  （Phase 7 統合）、Phase 5 以降。

## 2026‑09‑26（第 4 セッション）— Phase 4 push 後の CI 確認 + 独立精査（fresh eyes）

### GitHub Actions 確認結果（ユーザ要求分、GitHub API + ジョブログ実測）

**Phase 4 tip `94e553c32` に対して全 run SUCCESS**:

| run                         | 結果                        | 実測詳細                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| --------------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CI #126                     | **SUCCESS**                 | verify（typecheck/lint/lint:css/deps/format/build/mypy/ruff/pytest）                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| native #37                  | **SUCCESS — 14 ジョブ全緑** | native-test×3 OS / native-build×3 / abi3-import 3.10・3.13 / integration×3 OS / native-diff / fuzz-smoke / size-budget。integration(ubuntu) のジョブログで **pytest `113 passed`** と **L5 GATE: PASS**（core stamp `0.3.0‑alpha.0+94e553c32` = CI ビルド成果物 against）を確認                                                                                                                                                                                                                                                                    |
| fuzz‑long #6（36261689593） | **SUCCESS — 全 7 ジョブ**   | l2‑full **10,500 ケース GATE PASS**（mismatch 0）+ 6 ターゲット × 3 h 完走・**クラッシュ 0**: blob_decompress **176,664,658 execs**（cov **1,647** = run 5 の 1,472 から増加 — 新 Phase 4 表面に到達の証左・rss 170MB）/ codec_decompress 40,994,671（cov **1,772** ← 1,605・rss 215MB）/ zn_header 250,355,306（rss 139MB）/ huf_decompress 131,204,538（rss 170MB）/ st_parse 214,869,564（rss 204MB）/ delta_decompress 143,778,455（rss 179MB）。**Phase 4 の新 fuzz 表面（8 平面・トランケーション・Neo コード帯）の 3 h バジェット消化完了** |

### 環境ロールバックと復旧（セッション冒頭）

前ターン終了後にサンドボックスがロールバック: `.git`・apt/rustup/pip パッケージ・
`native/target` が消失（ソースツリーと `native-bin/*.so` は生存 — 前回精査セッションと
同型の事象）。`git clone` → `.git` 復帰で dev == origin/dev == `94e553c`・
**作業ツリー差分ゼロ**を確認してからツールチェーンを再構築（apt → rustup → pip →
pnpm install --frozen-lockfile）。生存 .so（stamp `f124c908d` = docs のみ差の
同一 Rust ツリー）でバッテリーを実行し、修正後にフルゲート再実行。

### 独立精査で発見し修正した不備（3 件 — いずれも堅牢化級、データ破損なし）

1. **【低・UI 競合】`confirmSingleZipnn` の事前チェック結果が「別の新しい確認
   ダイアログ」を書き換え得た** — モデル A の圧縮確認 → 即閉じて モデル B の
   確認 → A の `/zipnn/inspect`（遅い方）が到着すると、ガード
   （settled/visible/options 非 null）を全て通過して **B のダイアログ文を A の
   dtype 一覧で上書き**する窓が存在（`confirmState.options` は reactive proxy の
   ため参照同一性で自分のダイアログを識別できない）。修正: モジュール級
   **`confirmEpoch`**（require ごとに ++、コールバックは自分の epoch のみ更新可）。
   UI はモーダルなので実害確率は低いが、二重クリック/連打で再現可能な
   論理欠陥だった。
2. **【低・py】`inspect_safetensors_dtypes` が「JSON としては妥当だが object で
   ないヘッダー」（例 `[1,2,3]`）で AttributeError** — ルート側の try/except が
   拾うため 500 にはならないが、ヘルパの契約（`{"error": …}` を返す）に反する。
   `isinstance(header, dict)` ガード追加 + pytest ケース追加
   （`test_inspect_helper_survives_broken_files` に non‑dict ヘッダーを実装）。
3. **【低・UI】`znnInfo`（圧縮方式行）が `znn_compressed_vectors` の値が配列/
   文字列等の壊れ JSON のとき意味不明な集計（`?×3` 等）を描画し得た** —
   parse 後に「plain object か」を判定し、違えばセクションごと非表示に。

### fresh eyes で集中確認しバグなしと判定した領域（negative findings）

- **planes.rs**: split8/join8 の索引代数（64B ブロック転置・scalar 残り語・
  tail bytes 0..rem の無変換配置 = 2/4 平面の C in‑bounds 一般化）と
  fused revert の対称性、masked 3 関数の validate（n∈{2,4}・kind None 強制・
  全落としマスク拒否・整列強制・プレーン長検証）、mask 版 extract の
  split_masked parity（テスト + 実測）
- **codec.rs**: 入口検証順（plane_mask → trunc 整列 → chunk==0 → threshold NaN →
  cancel — 旧 validate_mode と同一の到達可能性）、trunc 時の chunk_sizes/exp
  導出（last_total % n == 0 の証明付き）、落とし平面の type/長さ厳格検査
  （タンパリング 2 種のテスト固定）、`exp 合計 != cur_len` 検査の truncated
  免除が整列ゲートに依存する構造、n==1 の mask 寛容（C memcpy 準拠）と
  compress 側の厳格（10 のみ）の非対称が C と一致、PLANE_SCRATCH/HUF_SCRATCH の
  cross‑job 再利用（resize 意味論で安全）、decompress_container の
  帯別 allows_mode（互換帯ブロブの trunc モード偽装を拒否）
- **dtype.rs**: plane_mask 表 ⇔ TRUNC_16/32 定数 ⇔ C の 8/1 データフロー
  （mode 8 = 上位バイト保持 + 下位 0 埋め = combine_buffers_dtype16 と同型）の
  三者一致、alias code 2/5 の正規化経路、canonical_mode の n 導出、
  masked_plane_sizes の full‑mask 委譲（互換帯は plane_sizes のまま =
  L2 の 10,500 byte‑identical が機械証明）
- **znn_tensor.rs**: DTYPE_TABLE ⇔ dtype.rs 幾何の一致性テスト、select_truncation
  の決定表（負値 I32 = 0xFF 上位 → 非トランケート、全ゼロ → mode 1、
  256 の倍数 U16 → mode 8）と early‑exit 走査、bits 基準 shape 検証の
  F4 実測整合（torch save が shape をニブル数で書くことの確認込み）、
  blob_chunk クランプの Neo 1 平面型への一貫適用
- **pipeline.rs**: extended_stored ⊆ worst_extended の包含証明（H_max 超過が
  原理的に起きない）、truncation が infos/H_max に与える影響ゼロ
  （torch_name/shape 不変）、pseudo dtype 拒否の位置（plan 段階 = 書込み前・
  部分出力なし）、BOOKKEEPING 6 鍵の strip 網羅（recompress テストで
  マーカー単一意図も固定）
- **実証バッテリー（/tmp/audit4/battery.py、生存 .so against、ALL CLEAN 20 項目）**:
  B1 paranoid × truncation × マーカー（残骸ゼロ）・B2 cancel 部分出力なし・
  B3 複数チャンク F64（1.2 MB = 5 チャンク 8 平面）byte‑exact・B4 複数チャンク
  U16 mode‑8（600 KB = 3 チャンク）・B5 拡張ファイル破損 → failed + 原本保持 +
  `.corrupt` 退避・B6 奇数ニブル F4 → 「byte boundary」明示失敗 + 残骸なし・
  B7 非 {0,1} BOOL バイトの不透明往復・B8 **デルタ × F64 モデル**（dtype 非依存の
  float32‑on‑bytes 意味論の確認、verified=sha256）・B9 inspect の graceful
  （デルタ .znn / non‑dict ヘッダー / 分類器 extendedDtypes 正確性）
- **フロントエンド**: request アンラップ（{success,data} → data）と
  inspectZipnnModel の null フォールバック、GlobalConfirm の settle/closeToken
  交互作用（epoch ガード後）、rawRows 正規表現のキー網羅
  （znn_compressed_vectors + znn_neo_*）、Tooltip import・i18n 補間 {dtypes}
- **CI 配線**: api_version 3 不変（native.yml assert / py/native.py [3,3] /
  ローダーテストの三者同期がそのまま有効）、integration の win/mac スキップ
  経路（torch importorskip / MMNEO_SKIP_LEGACY）が CI 3 OS 113 passed で実証、
  fuzz 6 ターゲットが新表面を自動被覆（run 6 の cov 増加が到達を証明）

**バグではないが確認して記録する items**:

- `pnpm deps`（dependency‑cruiser）はこのサンドボックスの node 20.20.2 では
  起動不能（要求 ^22||^24||>=26）— **CI の verify ジョブは同ステップ緑**
  （#126）なのでコード起因ではない（環境差分。CI は ci.yml で **node 22** をピン留め =
  ゲートは常にサポート済み node で走る）。
- select_truncation のゼロ統計は最大 word‑1 回のストライド走査
  （early‑exit 付き — 非トランケート可能データは先頭数要素で終了）。
  巨大整数テンソルでトランケート可能な場合のみ数パスの追加コスト
  （圧縮自体の平面分割より小さい）。実測（bench §9）で問題なしを確認済み。
- mode 8/9/41/1 の「 compressor が嘘をつかない」前提（落とす平面の全ゼロ）は
  パイプラインでは select_truncation が保証し、ファイル級では sha256 検証が
  ネットになる。codec 単体 API（decompress_tensor）はモードを信頼する設計
  （コメントで明記）— 敵対的ファイルは検証層で必ず捕まる。

### 検証（修正後・全ゲート再実行）

- pytest **113 passed**（新ケース込み・生存 .so against、Rust ツリーは
  94e553c と同一のため CI 証跡と等価）・ruff check/format ✓・mypy 14 files ✓
- pnpm typecheck ✓・eslint ✓・prettier format:check ✓・**pnpm build ✓
  （web バンドル再生成 — zipnn.ts/ModelInformation.vue の修正を反映）**
- Rust 側は今セッション**無変更**（修正は py/ts/vue/tests のみ）→
  clippy/L1/L2/L5 の CI 証跡（native #37 / fuzz‑long #6）がそのまま有効

### 運営メモ（次セッション向け）

- 本セッションの push 構成: fix(ui+py) 3 件の堅牢化 + web バンドル +
  MEMO（本節）。push で CI/native が新 tip に対して再実行される
  （fuzz 表面・Rust は無変更のため fuzz‑long の再ディスパッチは不要 —
  run 6 の 18 h 証跡が現行ツリーの fuzz 表面に対して有効。週次
  スケジュール（日曜 18:00 UTC）も担保）。
- プロジェクト全体の残件は不変: Phase 2 K2/K3 の参照機再計測、実 UI 手動 QA
  （Phase 7 統合）、Phase 5 以降。

## 2026‑09‑26（第 5 セッション）— CI 確認 + リポジトリ整理 + 開発ワークフロー規程 + ドキュメント記入漏れ解消

ユーザ指示の 4 タスク（Phase 4 実装の翌セッション。tip `971f072` から開始）。

### 1. GitHub Actions 成功確認（API + 全ジョブ conclusion 実測）

**監査修正 tip `971f072ed` に対して CI #127 / native #38 とも全ジョブ
SUCCESS**（native #38 = 14/14、CI #127 = verify 緑）。前ターン確認分の再掲:
CI #126 / native #37（14 ジョブ）/ fuzz‑long #6（7 ジョブ、l2‑full 10,500
GATE PASS + 6 ターゲット 3 h クラッシュ 0）も全て SUCCESS。
**Phase 4 の全 CI 証跡が確定した**。

### 2. ファイル・フォルダ整理（削除は参照ゼロを確認してから実施）

**削除（3 件）** — いずれも全リポジトリ grep で参照ゼロを確認済み:

- `native/crates/znn-codec/examples/fse_dbg.rs` — Phase 1 の FSE 往復
  デバッグ用使い捨てツール（知見は fse.rs のテストと MEMO に恒久化済み）。
- `native/crates/znn-codec/examples/stage_bench.rs` — Phase 1 のステージ別
  マイクロベンチ（split2 の 16B ブロック決定の測定値は planes.rs コメントに
  恒久記録済み。速度ゲートの正式器は `znn-cli bench` = L2 系譜）。
- `tests/_smoke_native.py` — 手動スモーク（docstring 自身が
  「test_phase0_native_loader.py で正式に exercised」と明記 = 完全冗長。
  pytest は `_` 接頭辞を収集しないため CI 対象でもなかった）。

**保持を再確認したものは削除しない**（誤削除防止の判断記録）:
`native/benches/json-bench`（BENCH §3 の計測器・run_all.sh/README が参照 =
JSON パーサ選定の再現経路）、`fuzz/corpus/*`（Phase 1 からの意図的コミット

- Phase 4 シード 14 件・oom 回帰シード含む）、`scripts/bench/results/*.json`
  （証跡）、`third_party/*`（L2 ゴールデン生成器 + レガシー経路 — Phase 7 まで）、
  `docs/upstream/zipnn-core-defect-report.md`（参考保管 — Plan §6.2 Phase 1 の
  記録通り）、`demo-assets/`（**ユーザ指示: 触らない**）、web/（配布バンドル）。
  examples/ 削除は Cargo.toml メンバ変更不要（自動発見）で、CI の
  `cargo test/clippy --all-targets` はビルド対象が減るだけ（ゲート不変）。

### 3. cargo 使用方針の制定 + `tests/` フォルダ新設（Plan §3.4.3）

- **Plan §3.4.3「cargo 使用方針（開発ワークフロー）」を追記**（ユーザ指示の
  4 規則: check 常用 / test は必要なときだけ + tests/ フォルダで管理 /
  clippy・rustfmt を品質向上に活用 / build は最終確認のみ）。§6.3 進捗管理
  規程からもポインタ追加。
- **`native/crates/znn-codec/tests/` を新設**し、最初の統合テスト
  `extended_band.rs`（**公開 API のみ**の端到端 4 テスト）を配置:
  全 22 dtype の blob 往復（truncation 自動選択込み・I32/U32 は mode 9 を
  アサート）・codec 級 pseudo dtype（C128/BC32）往復 + dtype_bitsize 不在
  確認・帯別モード ゲート（互換帯ブロブの trunc 偽装拒否 / Neo 整数の
  1・8 正当）・**互換帯 = 公式 5 dtype ちょうど + Neo コード 128–146 が
  重複/欠落なく全割り当て**の表固定。→ クレート級 K14 ゲートが Python/.so
  経路から独立して `cargo test` 一発で回る（L1 155 + 統合 4 = **159**）。
- 配置規程: 単体 = インライン `#[cfg(test)]`（private 到達 — Rust 慣行、
  155 個を移動するリファクタはリスクのみ）、統合 = `crates/znn-codec/tests/`、
  差分 = scripts/l2、敵対的 = fuzz/。native/README と lib.rs モジュール doc
  にも同期記載。

### 4. ドキュメント記入漏れの完全解消（このセッションで洗い切って修正）

- **Plan §4.6.1 訂正注記**: torch **2.14.0 リリースに float6\_\*\_pe は存在
  しない**（第 3 セッションの実機実証）+ F6 の infos 記録方針 + uint1–7 は
  safetensors 表現なしで**対象外**（コード未割り当て — GGUF 同様の §2.3 扱い。
  complex128/bcomplex32 との違い〔codec 級コードあり〕を明記）。
- **README / README‑JP「仕組み」節の整合修正**: 「非 float テンソルはそのまま
  コピー」は公式レシピ（=レガシー経路）の記述 → 「**Neo の Rust コアはこれらも
  圧縮する**（2 帯域 — マトリクス節へのリンク）」に明確化。Phase 4 のマトリクス
  節と矛盾していた最後の箇所。
- **USAGE‑EN/JA/ZN**: 「浮動小数点テンサルの Huffman 圧縮」→「テンサルの
  Huffman 圧縮 — Rust コアは全 dtype（下の dtype カバレッジ節参照）」+
  公式ローダーの透過読みは**互換帯**に限る旨を明記。
- **py/compress.py**: モジュール docstring に「これはレガシー vendored
  レシピのポート。native エンジン（既定）は全 22 dtype を 2 帯域で圧縮」の
  注記追加 + `ZNN_EXTENDED_KEY` コメントの「Phase 4（未来）」時制を
  実装済みへ更新。
- **tests/harness.py**: 陈旧参照 `gen_fixtures.py` → `gen_synthetic.py`（2 箇所、
  実在ファイル名へ）+ 「pass‑through class」系コメント 3 箇所を Phase 4
  実態（Neo 帯で圧縮・レガシーは pass‑through/raise）へ更新。
- **Rust doc コメントの陳腐化一掃**: codec.rs `CoreParams`（num_buf に 8 平面・
  byte_reorder に 88/トランケーション・chunk の 128 KiB クランプ対象を
  「single‑plane 型」へ一般化）、`decompress_container` の Errors 節
  （「Phase 4 codes」→ 未割り当てコード + 帯別モード ゲートの記述へ）、
  planes.rs `extract_plane`（{1,2,4,8} + kind ゲート）、lib.rs モジュール表
  （planes N=8 / znn_tensor 全表 / テスト配置規程）、mm-core lib.rs の
  フェーズ別 API 表面（Phase 4 = **API 変更なし・api_version 3 維持**を明記 —
  将来のバンプ判断の根拠が doc 上に残る）。
- **native/README.md**: Phase 1–3 の実装済み段落に **Phase 4 段落を追加**
  （22 dtype・8 平面・MODE_8PLANES=88・トランケーション・帯別ゲート・
  L5 E の拒否実証・C128/BC32 の codec 級限定）+「テスト配置と cargo
  ワークフロー」節（Plan §3.4.3 同期）+ レイアウト樹の znn-codec 行に
  tests//fuzz/ の注記。

### 検証（整理 + 規程 + 文書修正の全てに対して再実行・全緑）

- cargo fmt ✓ / clippy `--workspace --all-targets --all-features -D warnings` ✓ /
  **cargo test: znn‑codec 155（インライン）+ 4（tests/ 統合）+ mm‑core
  `--no-default-features` 5 ✓**（examples 削除後のワークスペースも健全）
- pytest **113 passed**（harness/py のコメント級変更後も実バイナリ against で再実行）
- ruff check/format ✓・mypy 14 files ✓・pnpm typecheck/eslint/format:check ✓・
  **pnpm build ✓（web バンドルは src 無変更のためハッシュ不変 = 再生成差分なし）**
- prettier: 編集した md 全件整形済み（Plan/MEMO/README×2/USAGE×3/native README）

### 運営メモ（次セッション向け）

- 本セッションの push 構成: chore（整理 3 件削除）→ feat/test（tests/ 新設 +
  Plan §3.4.3）→ docs（記入漏れ一掃 + MEMO 本節）。push で CI/native が
  新 tip に対して自動実行（Rust は**doc コメントと tests/ 追加のみ** —
  fuzz 表面はゼロ変更なので fuzz‑long の再ディスパッチは不要。run 6 の
  18 h 証跡が有効なまま）。
- 残件は不変: Phase 2 K2/K3 参照機再計測、実 UI 手動 QA（Phase 7 統合）、
  Phase 5 以降。**次フェーズ（Phase 5）着手時は §3.4.3 の cargo 規程と
  tests/ 管理規程に従うこと**。

## 2026-09-27（第 6 セッション）— Phase 5 実装（スキャン/インデックス/ハッシュ/更新伝播）+ Phase 4 最終バグチェック

**完了**: Plan §6.2 Phase 5 の必須項目を全て実装・全ゲート緑・[x] 化。任意項目
（A3 requests→aiohttp / watch_roots）は Plan の「任意」表記に従い本フェーズ見送り
（根拠は BENCH §10.5）。api_version 3→4。

### 環境再構築（セッション冒頭ロールバック対策）

前ターン後にサンドボックスがロールバック: rustc/cargo/gcc/clang 消失・pip パッケージ
消失（ソースツリーと `.git` は生存）。apt（build-essential/clang/mold/libpython3.11-dev）
→ rustup stable 1.98.1（+rustfmt/clippy）→ pip（ruff 0.16.8/mypy/pytest/maturin 1.15.0

- numpy/safetensors/torch 2.14.0+cpu）→ pnpm install --frozen-lockfile。apt ミラーは
  今回 9 MB/s と高速。cargo は 1 GiB 制約で CARGO_BUILD_JOBS=1。

### crate バージョンの一次確認（推測ゼロ）

crates.io API で再確認（2026-09-27）: **bincode 3.0.0 は依然 compile_error!
プレースホルダ**（xkcd 2347、.crate 実展開で lib.rs 全体が compile_error! と確認）→
実体安定版 **2.0.1**（70 KB）を Plan §3.1 注記通り採用。blake3 1.8.7 / crc32fast 1.5.2
/ yaml-rust2 0.13.0 / notify 8.2.0 / notify-debouncer-full 0.7.0 = Plan 確認値と一致。

### 実装（znn-codec 新モジュール + mm-core + Python 切替 + フロント）

- **scan.rs**（新）: std::fs + rayon の自前並列 walk（os.scandir 意味論の忠実移植 =
  dir symlink 追従 + canonical visited ガード〔循環 symlink でハングしない robustness
  改善〕・hidden を name set に残す・拡張子大文字小文字区別・20 スロット preview 解決・
  front-matter 4 値・stat）+ scan_hygiene（os.walk(followlinks=False) 意味論 = orphan
  サイドカー + empty フォルダ）。JSON 形状は現行 scan_models と厳密一致（serde
  camelCase + 安定ソート (pathIndex, path)）。**createdAt/updatedAt = round(st_ctime_ns/1e6)
  を f64::round_ties_even で Python とビット一致**（実機 stat で cross-check 実証・
  Linux/macOS は OS 別 MetadataExt::st_ctime、Windows は created()）。
- **index.rs**（新）: 永続インデックス（bincode 2.0.1 スナップショット + blake3
  チェックサム + 原子入替 + 破損/不一致時自動全再構築 = 常に派生データ R7）。
  (path, mtime_ns, size) → front-matter 4 値。RwLock で並列 scan から共有。
- **hash.rs**（新）: MultiHasher（SHA256 + AutoV1 窓 + AutoV2 + CRC32 バイト反転 +
  BLAKE3 を 1 パス）+ hash_file + インクリメンタル API（download インライン検証用）。
  Civitai 表記を Python 定義とバイト一致で L1 固定。
- **safetensors_io.rs**: header_display_json 追加（ヘッダ専用 jiter 解析・データ領域
  無検証 = truncated ファイルでも表示可・B4 32 MiB 統一ガード・processed JSON 返却）。
- **mm-core phase5.rs**（新）: scan_models/scan_hygiene/safetensors_header/hash_file/
  hasher_new・update・finalize/phase5_diagnostics を PyO3 公開（同期・py.detach で
  GIL 解放 = 不変条件 2）。SiteIndex のグローバルレジストリ（indexDir 単位）+ ハッシャ
  レジストリ（cap 4096 + oldest eviction）。**api_version 3→4**。
- **Python 切替**: native.py に core_if_enabled()（共有ヘルパ・MM_NATIVE 尊重・
  compress.py native_core() もこれへ委譲）/ manager.py scan_models・scan_hygiene
  （native + legacy 双方に安定ソート追加 = golden parity・失敗時 legacy フォールバック）/
  utils.py get_model_metadata・get_model_tensors（B4・native + legacy 32 MiB）+
  get_index_cache_dir / identify.py compute_hashes（native hash_file・Civitai 4 表記
  golden）/ download.py A2（_DOWNLOAD_CHUNK 1 MiB）+ B1 インライン検証（hasher へ
  チャンク供給・resume は部分ファイル page-cache シード・200 リセット/416 リトライ/
  pause を全分岐処理・_download_complete は inline sha 優先 + _sha256_of フォールバック）。
- **models_changed**: utils.notify_models_changed（delete/update でブロードキャスト・
  download 完了/ZipNN 完了は既存 ws ブロードキャストが届くため二重発行せず）+
  フロント model.ts リスナー（部分再取得 refreshModels(type,{background})・generation
  ガードで二重再取得吸収・loadedOnce ガード）。web バンドル再構築。

### テスト（golden parity = native == legacy を機械固定）

- test_phase5_scan.py（11）: scan_models（両 hidden モード・preview 単/画廊・
  front-matter 4 値・timestamp・pathIndex・index 永続）・scan_hygiene（orphan/empty）・
  safetensors_header（metadata + tensors 形状）・compute_hashes（SHA256/AutoV2/AutoV1/
  CRC32 + BLAKE3）・インクリメンタル hasher（chunk 非依存 == hash_file）。
- test_phase5_download.py（3）: _download_complete の inline sha 検証（match 完了/
  mismatch 削除+raise/フォールバック _sha256_of）。
- **フルスイート 127 passed**（既存 113 + Phase 5 新規 14・torch 2.14/safetensors 0.8
  同梱・release .so against）。既存テストの api_version==3 アサートを 4 へ更新
  （native.yml/py.native.py/mm-core lib.rs test/pytest の四者同期）。
- **test_phase0_native_loader の sys.path 分離を強化**: get_model_metadata が native を
  ロードするようになったため、先行テスト（phase0_a1）が実 native-bin を sys.path に
  残すと loader 分離テストが実 .so を拾って失敗 → autouse fixture で setup 時に
  native-bin エントリを scrub（本番では正しい挙動・テスト分離の脆弱性だった）。

### 計測（K7–K11、BENCH §10・同一セッション legacy vs native）

- **K9**: 5000 モデル合成ライブラリ QA = native **0.145 s**（5016 entries）vs legacy
  1.082 s（**×7.5**）+ **native==legacy の完全 parity 機械確認**（完了条件「5000
  モデル QA」）。3000 モデル cold 0.124 s（×5.1）。
- **K10**: warm **99 ms ≤ 100 ms**（3000 モデル・永続インデックスで front-matter
  再パース消滅）。5000 はこの機で ≈165 ms（参照機 ≤100 ms 見込み）。
- **K8**: 5 表記 1 パス **1239 MB/s**（SHA-NI なし・BLAKE3 込み）→ 10 GB ≈8.3 s ≤15 s・
  sha256 三者クロスチェック MATCH。
- **K7**: インライン検証で完了時追加 I/O ゼロ（_sha256_of フル再読込を native 経路から
  削除・legacy フォールバックのみ残置）。
- **K11**: Rust ヘッダ解析 ≈10 ms ≤40 ms（jiter・GIL 解放）+ 端到端 get_model_tensors
  **212 ms**（legacy 334 ms の ×1.58・GIL 占有時間約半減 = K12 改善）。

### 実装中に発見・修正した重大バグ（O(n²)）

**parse_header_json の重複テンソル名検査が O(n²)** だった（tensors.iter().any/position
の線形走査 × テンソル数）→ 64,491 テンソルの MoE ヘッダで native get_model_tensors が
**6,098 ms**（legacy 334 ms の **×18 遅い重大退行**）。HashMap<name,pos> の O(1)
last-wins 置換へ修正（セマンティクス・順序・odd フラグ完全保持 — L1 181 + pytest 127
緑で固定）→ **212 ms**。**この経路は compress パイプライン（StContainer::parse）も
共有するため、64k テンソル級 MoE 圧縮のヘッダ解析も 6 s → 数十 ms へ高速化**
（Phase 2 からの潜在バグを Phase 5 の表示経路が顕在化・fresh eyes で捕捉）。

### Phase 4 最終バグチェック（fresh eyes・バグなし）

select_truncation（ゼロ統計 + 整列ガード + 負値 0xFF 非トランケート + 2 平面特殊
mode 8）・masked plane（validate/split/join/extract の n∈{2,4}/kind None/整列/落とし面
検証）を精査 → 過去 4 回の監査と整合・バグなし。**Phase 4 codec 経路（codec/dtype/
planes/znn_tensor/pipeline）は本セッションで変更ゼロ**（git diff 空で確認・scan/hash/
index/header は新モジュール）→ Phase 4 は安定（全テスト緑）。

### 任意項目（A3 / watch_roots）の見送り判断（Plan の「任意」表記に従う）

BENCH §10.5 に根拠を記録。A3（requests→aiohttp）はネットワーク経路の async リファクタ
でライブ API なしでは回帰テスト不能・executor 経由で現状動作・identify の主目標
（ハッシュ native 化）は達成済み。watch_roots は notify ファイル監視サブシステムで
任意・既定 OFF・`watch` feature 宣言済み（将来の土台）。必須の更新伝播（models_changed

- 30 s TTL）が UI 起因の全変更をカバーし、外部変更は TTL フォールバックが担保。
  いずれも完了条件 K7–K11 に不含。

### 全ゲート再検証（release .so against・全緑）

- cargo fmt ✓ / clippy --workspace --all-targets --all-features -D warnings ✓ /
  cargo test: znn-codec **181**（+26）+ mm-core --no-default-features **5** ✓
- release .so（host build）**2,869,968 B**（予算 4 MB の 68 %・Phase 4 比 +468 KB =
  scan/hash/index/header + blake3/bincode/crc32fast/yaml-rust2）・verify_native_binary
  ok（libpython 非依存）・api_version 4・10+ API 全存在
- pytest **127 passed** / ruff check+format ✓ / mypy 14 files ✓ / pnpm typecheck ✓ /
  eslint ✓ / prettier format:check ✓ / **pnpm build ✓（web バンドル再生成 =
  models_changed リスナー反映・manager.js に models_changed 確認）**

### 運営メモ（次セッション向け）

- **api_version 3→4**: native.yml abi3 assert / py/native.py [4,4] / mm-core lib.rs
  API_VERSION + test / pytest の四者同期済み。CI の abi3-import は 4 を assert。
- CI: ci.yml は既存の pytest tests で新テストを自動収容・native.yml integration も同様。
  **fuzz 表面は不変**（scan/hash/index/header は fuzz ターゲット外・codec 無変更）→
  fuzz-long 再ディスパッチ不要（run 6 の 18 h 証跡が有効）。push で CI/native が
  新 tip に対して自動実行（結果確認はユーザ次ターン指示）。
- native-bin の .so は gitignore（CI が main/tag で生成）。ローカルの release .so は
  テスト用（host glibc 2.36・CI は zigbuild glibc 2.28）。
- 残件: Phase 2 K2/K3 参照機再計測、Phase 5 任意項目 A3/watch_roots（将来）、実 UI
  手動 QA（Phase 7 統合）、K10 5000 モデル ≤100 ms の参照機確認、K11 端到端 ≤40 ms
  （processed JSON をルートで直接スプライスする設計 = get_model_tensors の公開契約を
  変えるため本フェーズ範囲外・記録）。Phase 6 以降。

### 追加（同日・push 後 CI native #42 の macOS サイズゲート失敗を修正）

**症状**: push 後の native #42（head 59968ab）で **native-build-macos のみ失敗**
（`SIZE BUDGET EXCEEDED: 4801936 > 4194304 bytes`）。他は全緑 — native-test×3
（**macOS 含む** = scan.rs の `MetadataExt::st_ctime` が macOS でコンパイル・テスト
通過を実証）・native-build-linux/windows・**native-diff（L2 byte-identical =
parse_header_json の O(n²) 修正が byte-exact 安全であることを CI が機械確認）**・
fuzz-smoke・abi3-import 3.10/3.13（api_version 4）。integration/size-budget は
macos 依存で skipped だった。

**根因**: macos-universal2 は **x86_64 + arm64 の 2 アーキを含む fat binary**。
Plan §3.3「1 バイナリ ≤ 4 MB」は単一アーキ前提のヒューリスティックで、Phase 5 の
機能追加（scan/hash/index/header + blake3/bincode/crc32fast/yaml-rust2）で
linux-x86_64 が 2.4→2.87 MB へ成長し、universal2 fat が **4.8 MB**（各スライス
≈2.4 MB は予算内だが fat 合計が 4 MB 超）に到達。

**修正（fat binary は「1 バイナリ = 1 アーキスライス」で予算判定）**:

- `build-native.sh`: `finish()` に budget 引数を追加。`build_macos_universal2` は
  `lipo -thin` で **各アーキスライスを ≤4 MB でゲート**（Plan の「1 バイナリ」に
  忠実）+ fat ファイルは `finish` に 2× 予算（8 MB）を渡す。単一アーキ対象
  （linux x86_64/aarch64・windows）は 4 MB のまま。
- `native.yml` size-budget ジョブ（ubuntu = lipo 不可）: **content 判定**で
  FAT_MAGIC（0xcafebabe/0xcafebabf・big-endian on disk）を検出し fat のみ 8 MB
  予算（path 非依存 = download-artifact の LCA で `macos-universal2` 断片が
  保たれない場合でも堅牢）。他は 4 MB・合計 20 MB は不変。ローカルで ELF
  （7f454c46 → 4 MB・2.87 MB PASS）と fat magic（cafebabe → 8 MB）を検証。
- Plan §3.3 に universal2 fat binary の per-slice 予算注記を追記。native.yml
  冒頭コメントも同期。

**native-bin 合計 ≈12 MB ≤ 20 MB（R6 リポジトリ肥大ガードは充足）**。単一アーキ
成果物は全て ≤4 MB を維持。修正は build-native.sh + native.yml + Plan のみ
（Rust/Python コードは無変更 = 再ビルド不要・既存の全ゲート証跡は有効）。

## 2026-09-27（第 7 セッション）— CI 全緑確認 + ユーザ決定 5 件の Plan 反映（A3/watch_roots の Phase 6 移管・サイズ予算の目安化・リリース公開のユーザ専任化）

### CI 全緑確認（ユーザ要求分・GitHub API + ジョブログ実測）

**CI #132 / native #43（head `05cb8c7` = サイズゲート修正コミット）とも
全ジョブ SUCCESS**（native #43 = 14/14）。修正の実証データ:

- **native-build-macos 緑**: per-slice ゲートが設計通り動作 —
  x86_64 スライス **2,520,856 B** ≤4 MB / arm64 スライス **2,262,416 B** ≤4 MB /
  fat 4,801,936 B ≤8 MB。
- **size-budget 緑**: 4 バイナリ合計 **13,039,208 B ≤20 MB**。macOS 成果物は
  **magic `cafebabe` の content 判定**で 8 MB 予算を適用 — 実ダウンロード
  artifact の path は `artifacts/mm_core.abi3.so` で **`macos-universal2` 断片を
  含まなかった**（upload-artifact v4 の LCA 挙動）= path 判定案では失敗しており、
  content 判定の設計判断が実証された。他: linux-x86_64 2,913,576 / linux-aarch64
  2,478,512 / windows .pyd 2,845,184 B（全て ELF/PE magic → 4 MB 予算）。
- **integration 緑**: ubuntu **pytest 127 passed + L5 GATE: PASS**（Phase 5
  golden parity が CI 実ビルド成果物 against で緑）/ windows・macos 各
  **20 passed, 107 skipped**（native 経路のみ = 設計通り）。
- native #42（修正前）で **native-test×3・native-diff・fuzz-smoke・abi3-import
  3.10/3.13 が既に緑**だったことが、O(n²) 修正の byte-exact 安全（L2）と
  api_version 4 同期と macOS での scan.rs（MetadataExt::st_ctime）コンパイル・
  テスト通過を先行実証していた。

### ユーザ決定 5 件（2026-09-27・すべて Plan/MEMO に恒久記録）

1. **Phase 5 の見送り項目（A3 / watch_roots）は Phase 5 リストから削除し
   Phase 6 へ移管**（Plan §6.2 Phase 5/6・§6.1 表・§9・状態行を同期更新。
   Phase 6 のタイトルも「フロントエンド表示最適化 + Phase 5 移管の任意項目」へ）。
2. **バイナリサイズの 4 MB 予算は「目安」**（絶対条件から降格 — Plan §3.3 に
   決定注記、§6.3 に恒久規程、R6 緩和策・§5.3 CI 表・Phase 7 タスクを同期。
   CI サイズゲートはリポジトリ肥大の早期警戒装置として**維持**し、超過は
   ユーザ判断で上限改定する運用。native-bin 合計 ≤20 MB はハード上限のまま）。
3. **リリース v0.3.0 の公開はユーザが実施する — セッションは勝手に公開しない**
   （GitHub Release 作成・タグ publish・registry 公開・main へのマージ PR 操作は
   ユーザ専任。セッションは「公開準備」= バージョン同期コミット + 公開前検証
   まで。Plan §6.2 Phase 7 のリリース行 + §6.3 進捗管理規程の両方に明記）。
4. **requests→aiohttp 統一（A3）の Rust 化はしない**（reqwest/axum/utoipa
   不採用 — Plan §3.8 に決定 + 実測根拠を注記）。
5. **extended-notify は導入しない**（watch_roots は notify 8.2.0 +
   notify-debouncer-full 0.7.0 の直接採用で確定 — Plan §3.1 選定表の不採用
   候補欄に根拠付きで記録）。

### 調査の実測証跡（将来セッションが再調査しないための記録・すべて一次ソース）

**reqwest 系（2026-09-27、この環境で実測）**:

- reqwest **0.13.5**（crates.io: 2026-09-08 更新・DL 7.47 億・MSRV 1.85 =
  ワークスペース床と一致）は **feature 名が変わっている**: `rustls-tls` は
  廃止で `rustls`（プローブが解決エラーで実証）。`rustls` 指定で
  **aws-lc-rs 1.18.1 / aws-lc-sys 0.45.0（C/asm・cmake 必須 — この環境でも
  cmake を apt 導入するまでビルド不能だった = 実証）** + ring 0.17.14（C/asm）
  - rustls 0.23.45 を引き込む。native-tls は OpenSSL 動的リンクで
    zigbuild glibc 2.28 床を破壊するため論外。rustls に純 Rust の成熟
    crypto provider は不在 = **どの TLS 経路でも C/asm がビルドに入る**。
- **サイズ実測**: /tmp のプローブ crate（reqwest rustls+json+gzip + tokio rt +
  serde_json・公開関数 1 個）を mm-core と同一 release プロファイル
  （lto=fat/codegen-units=1/opt-level=3/strip/panic=unwind）でビルド →
  **librq_probe.so = 4,886,072 B（≈4.9 MB、strip 済み・ELF 検証済み）**。
  HTTP スタックだけで現行 mm_core 本体（linux 2.91 MB）より大きく、統合時は
  全プラットフォームで 4 MB 目安を ~1.9 倍超過する試算。依存グラフは
  **167 crates**（現行ワークスペース lock 全体 139 = dev/bench/CLI 込み総数）。
- **axum 0.8.9** = 「HTTP routing and request handling library」（サーバ
  フレームワーク）、**utoipa 6.0.0** = 「Compile time generated OpenAPI
  documentation for Rust」（Rust ハンドラ用）— いずれも crates.io 公式
  description で確認。本拡張はルートを ComfyUI の aiohttp PromptServer へ
  登録するモデル（py/config.py）なので**非該当**。
- **huggingface_hub 2.0.0 は httpx2 基盤**（PyPI metadata の requires_dist で
  確認: `httpx2<3,>=2.0.0`）→ 残り 11 箇所の薄い JSON 呼び出しを Rust 化しても
  プロセス内は aiohttp（サーバ+DL）/ httpx2（hub 系）/ reqwest の
  **第 3 スタック追加**になり「統一」にならない。重い HF 転送は hf_xet で
  既に Rust。

**extended-notify（2026-09-27、crates.io API + 公式 README で確認）**:

- 実在: **0.1.3**（2025-12-10 初版・2026-06-26 更新・MIT・単一作者
  estokes/extended-notify）。総 DL **1,286**（recent 457）。
- 正体は **notify ^8.2 + notify-debouncer-full ^0.6 のラッパー**
  （debouncer-full は現行 0.7.0 = **土台より 1 世代後ろピン**）+ tokio ^1.48 +
  futures + anyhow + file-id + arcstr + derive_builder + enumflags2 + fxhash +
  poolshark。README の追加機能: 未存在 path の監視（祖先+ポーリング）・
  interest フィルタ・RAII ハンドル・ポーリングフォールバック・tokio の
  async EventHandler バッチ配信。
- 不採用の要点: (a) 成熟度（notify 本体 DL **1.599 億** / debouncer-full
  **1,673 万** と 3 桁以上の差・単一作者 0.1.x）、(b) tokio 混入 = 既定 OFF の
  任意機能のために出荷バイナリへランタイム追加（reqwest プローブが示すサイズ
  コスト）・Neo 設計は Python 側 asyncio からの watch_poll で tokio 不要、
  (c) 目玉機能は Neo 側で代替可能（root 再アーム数行・kind フィルタ数行・
  ポーリングは **notify 本体の PollWatcher が標準搭載**〔docs.rs で確認〕）、
  (d) debouncer-full 0.6 ピン。hotwatch 0.5.0 は 2023 年止まりで候補外。
- Neo の watch_roots で本当に必要なのは crate ではなくグルー: inotify watch
  予算管理（Linux per-directory・max_user_watches 枯渇時 TTL へ degrade）・
  ネットワーク FS 検出→自動無効化（PollWatcher での代替は 5,000 ファイル樹の
  定期 stat = 再スキャン同コストなので TTL がその役目を担う）・path→type
  判定→models_changed（Phase 5 実装のリスナーを無改修再利用）・既定 OFF。

### このセッションのドキュメント編集（コード変更ゼロ）

- **Plan.md**: §6.2 Phase 5 から見送り 2 項目を削除 → Phase 6 へ移管
  （決定・制約〔Rust 化しない/extended-notify 不導入〕+ 実施時の条件付き）。
  Phase 6 タイトル/§6.1 表/§9/状態行を同期。§3.3 + §6.3 + R6 + §5.3 +
  Phase 7 タスクで 4 MB を「目安」化（20 MB 合計はハード上限維持）。
  Phase 7 リリース行を「公開準備」へ限定 + §6.3 に「リリース公開はユーザ
  専任」規程。§3.8 に reqwest 不採用注記（実測根拠付き）・§3.1 watch 行の
  不採用候補に extended-notify・§4.7.2-2 に Phase 6 移管ポインタ・§4.8-A A3 行
  の実施フェーズを Phase 6 へ。Phase 0 の履歴行（「サイズ ≤4 MB/本」完了記録）は
  歴史的事实のため不変。
- **native/README.md**: Phase 5 段落の「本フェーズ見送り」→「Phase 6 へ移管 +
  確定方針」へ更新。
- **BENCH §10.5**: 見送り記録（歴史）はそのままに、後続のユーザ決定
  （移管・Rust 化しない・extended-notify 不導入・4 MB 目安化）を引用ブロックで
  追記。
- **MEMO（本節）**: CI 全緑証跡 + 決定 5 件 + 実測証跡を記録。
- CI ワークフロー/ビルドスクリプトは**無変更**（ゲートは現行上限を施行する早期警戒装置として維持 — 目安化は計画レベルの位置づけ変更。relax が必要に
  なったらユーザ判断で上限改定）。

### 運営メモ（次セッション向け）

- 本 push は docs のみ（Plan/MEMO/BENCH/native README）→ CI/native が新 tip に
  自動実行されるが、コード無変更のため結果は #132/#43 と同じ見込み
  （確認はユーザ次ターン指示時）。
- **Phase 6 着手時の約束事**: C1–C5（計測駆動）+ 移管の A3（aiohttp 統一・
  挙動 parity + モックテスト）/ watch_roots（notify 直接採用・既定 OFF・
  degrade + primitive テスト）。いずれも任意項目で K15 完了条件には不含。
- **v0.3.0 の公開作業は行わないこと**（バージョン同期・公開前検証まで）。
- 残件は不変: Phase 2 K2/K3 参照機再計測、K10 5000 モデル ≤100 ms の参照機
  確認、K11 端到端 ≤40 ms（processed JSON のルート直スピルス設計 = 公開契約
  変更を伴うため範囲外と記録済み）、実 UI 手動 QA（Phase 7 統合）。

## 2026-09-27（第 8 セッション）— Phase 5 最終バグチェック（6 件修正）+ Phase 6 完全実装（C1–C5・テンソルツリー Rust 化・A3・watch_roots）

**完了**: Plan §6.2 Phase 6 の**全項目**（任意項目 A3 / watch_roots を含む）を実装し、
全ゲート緑で [x] 化。api_version 4→5。着手前の Phase 5 精査で **6 件**のバグを
発見・修正（すべて回帰テスト化）、Phase 6 の実装中に既存バグ **1 件**を追加発見・修正。

### 環境再構築（セッション冒頭ロールバック対策 — 第 6 セッションと同型）

apt（build-essential/clang/mold/libpython3.11-dev/curl）→ rustup stable **1.98.1**
（+rustfmt/clippy）→ pip（ruff/mypy/pytest/pytest-asyncio/maturin/numpy/safetensors/
torch 2.14.0+cpu/**markdownify・huggingface_hub・hf_xet・modelscope_hub・pillow** =
`-r requirements.txt`。A3 のテストは `py/information.py` を import するため
markdownify/PIL が必須）→ pnpm 12.3.4 + `pnpm install --frozen-lockfile`。
**dependency-cruiser 18 は Node ≥22 必須**（この環境は 20.20.2）→ 公式 tarball の
Node v22.20.0 を作業領域外へ展開して `depcruise src` を実行
（**136 modules / 409 dependencies、違反 0**）。cargo は 1 GiB 制約で
`CARGO_BUILD_JOBS=1..2`。debug ビルド 1 m 36 s、release（lto=fat）2 m 02 s。

**この環境の重要な癖（次セッション向け）**: bash ツールへ渡した**ファイル内容の中の
`"$ARENA_WORKSPACE"` 文字列はワークスペース実体の env 変数へ置換される**。heredoc 内の
Python 文字列リテラルに絶対パスを書くと `""$ARENA_WORKSPACE""` のような壊れた構文に
なり、`write_file` で書いた絶対パスは実体と一致せず `FileNotFoundError` になる。
**スクリプト内は相対パス（`cd` して実行）か `os.path.dirname(__file__)` を使うこと。**
もう一つ: **バックグラウンド実行（`nohup … &`）はツール呼び出しをまたぐと殺される**
（cargo build を裏で回して途中で消えた）。長時間ビルドは `timeout` 付きの同期実行で。

### Phase 5 最終バグチェック（ユーザ指示「念のため精査」）— 発見 6 件、全て修正

対象を Phase 5 の差分（`scan.rs` / `index.rs` / `hash.rs` /
`safetensors_io::header_display_json` / `mm-core phase5.rs` / `py/native.py` /
`manager.py` / `utils.py` / `identify.py` / `download.py` / フロント
`models_changed` リスナー）に絞って精読 + 実走査。**codec 経路は Phase 4 の
4 回監査と整合（変更ゼロ）**、scan/index/hash の golden parity も再確認した上で、
以下を修正した（詳細表は BENCH §11.5）。

1. **resume 時のイベントループ停止（重大・応答性）**: インライン検証のシード読み
   （部分ファイル全文）が `download_model_file_http` の中で**同期実行**されていた。
   「page-cache だから安い」は同一プロセス内の再開でのみ成立し、ComfyUI 再起動後の
   resume は cold read = 10 GB で数秒、websocket も全リクエストも止まる
   （Plan §1.2.2 課題 6 と同じクラス）。`io_executor` へ移動し、失敗時はハッシャを
   破棄して従来の `_sha256_of` 再読込検証へ degrade（正しさ不変）。
2. **失われたハッシャ handle でダウンロード全体が失敗し得た**: native 側 registry は
   4096 で oldest eviction するため、理論上は稼働中の handle が消えて
   `hasher_update` が `KeyError` → 書き込みループから例外が伝播し**バイト列が正常な
   ダウンロードが失敗**する。try/except で inline 検証だけ放棄するようにした。
3. **永続インデックスの無限成長**: `SiteIndex` に上限が無く、削除済みサイドカーの
   entry が永遠に残る（Python 側 `_SITE_CACHE` は 4096 上限）。
   `MAX_ENTRIES = 262_144` を新設し超過時に任意の半分を prune（派生データなので
   miss は再パースのみ — R7 の設計思想のまま）。
4. **不正 UTF‑8 の `.md` 1 個でフォルダ一覧が全滅（legacy 経路）**:
   `open(..., encoding="utf-8").read(4096)` の `UnicodeDecodeError` が
   `except OSError` を抜けて `get_file_info` → ルートまで伝播し
   `Read models failed` になっていた。`errors="replace"` にして native の
   `from_utf8_lossy` と挙動を統一（**両エンジン同一値**であることをテストで固定）。
5. **base path を繰り返す副フォルダで `subFolder` が壊れる（legacy 経路）**:
   `str.replace(prefix, "")` が**全**出現を削除していた（native は `strip_prefix`
   で正しい）。`removeprefix` へ。preview URL と rename/delete の fullname が
   別ファイルを指し得たため、放置すると実害のある経路だった。
6. **フォルダ新規作成が他クライアントへ伝わらない**: `create-folder` ルートだけが
   `models_changed` を送っていなかった（delete/update は送る）。
   `reason="create-folder"` でブロードキャスト（生成ガードが二重取得を吸収）。

**Phase 6 実装中に mock テストが検出した既存バグ（7 件目）**:
`_ms_plain_description` の leaf 判定が `node[-2] == "leaf"` のみで、実 API /
同関数 docstring 記載の属性 dict 形 `["span",{"data-type":"leaf"},"…"]` を
一度も拾わず **ModelScope owner のプロフィール説明ツールチップが常に空**だった
（c404bcc 由来の潜在バグ）。両形を受理する `is_leaf_marker` にして固定。

### Phase 6 実装（Plan §6.2 の全項目）

- **C1**: `src/utils/modelFilter.ts` 新設（`buildSearchTokens` /
  `buildModelRows` / `filterModels` / `chunkRows`）。`DialogManager.vue` の
  per-model `tokens.map(buildRegex)` を撤去し、filter→sort→chunk を**純関数 1 本**に
  （コンポーネントとヘッドレス計測器が同一コードを測る）。
- **C2**: **計測で設計を修正した**（下記「計測」参照）。`compareText` =
  `localeCompare` 維持 / `compareTextNumeric` = hoisted numeric Collator。
  旧直呼び 7 箇所（DialogManager・DialogExplorer×2・model.ts・ModelInformation×3）を
  全て共有モジュール経由に集約。
- **C3**: `hooks/model.ts` の `models` を `shallowRef` へ。**影響棚卸しを先行実施**し、
  全 12 消費者（App.vue / DialogManager×2 / explorer〔cloneDeep 済み〕/
  DialogHygiene / DialogModelDetail〔getter watch〕/ DialogCreateTask /
  DialogHfUpload / ModelBaseInfo / useTypeSizes / useModelFolder〔cloneDeep 済み〕/
  stars・selection は別ストア）が読み取り専用または複製後に操作することを
  doc コメントに列挙（R8 のロールバック単位 = この 1 行）。
- **C4**: `decoding="async"` を raster プレビュー 7 箇所へ（`ResponseImage`×2・
  `ModelCard`〔実際のスクロール源〕・`ModelPreview`・`PreviewLightbox`・
  `DialogCreateTask`・`DialogIdentifyHash`・`DialogHfUpload`）。SMIL アニメの
  フォルダアイコン等はタイムライン再開挙動を変えるため**意図的に非適用**。
- **C5**: `src/utils/perf.ts`（ring buffer + P50/P95/P99 + `__mmNeoPerf` ハンドル +
  既定 OFF + 設定 `ModelManager.UI.PerfMarks`）+ 計測点 6 種 +
  **ヘッドレス計測器 `scripts/bench/front/k15.mjs`**（CI 常設）。
- **テンソルツリー Rust 事前グループ化**: `encode_tensor_tree` /
  `tensor_tree_json`（pre-order 線形符号）+ `mm_core.safetensors_tensor_tree` +
  `utils.get_model_header`（metadata/tensors/tree を 1 ルートで = 詳細ルートの
  ヘッダ解析回数を増やさない）+ `src/utils/tensorTree.ts`（**遅延インデックス**:
  87k ノードを materialize しない。JS フォールバック エンコーダも同モジュールに
  置き、レンダリング経路は 1 本）。`ModelInformation.vue` は行生成のみ差し替え
  （キー・折りたたみ・500 件ページングは不変）。
- **A3（requests → aiohttp）**: `py/http_client.py` 新設 + `search.py` /
  `information.py` / `identify.py` の **10 箇所**を移行（`utils.py` の preview 取得
  2 箇所は PIL パイプライン内で executor 実行のまま = Plan の対象外。内訳は
  search 6 / information 3 / identify 1）。parity の要点: タイムアウトは
  `(connect, sock_read, total=None)` へ忠実写像（**total ではない**ことを実測テストで
  固定）、`HttpStatusError` が requests の `raise_for_status` 文言を**逐語再現**し
  `.response.status_code` も維持（Civitai 401 誘導文が依存）、JSON は content-type
  を検査しない（`requests.json()` 準拠 — ModelScope CDN が octet-stream で返す
  実例あり）、`trust_env=True` でプロキシ環境変数を踏襲。3 者並列検索は nested
  ThreadPoolExecutor を廃し `asyncio.wait` の**部分結果契約を維持**
  （`SWEEP_MARGIN` 定数化でテスト可能に）。identify の**二重スレッドホップ**
  （io worker 内から `cpu_executor().submit(...).result()`）も解消。
- **watch_roots**: `znn_codec::watch`（notify 8.2.0 + notify-debouncer-full 0.7.0
  直接採用・500 ms デバウンス・ポーリング方式 = notify スレッドが GIL を取らない・
  `MaxFilesWatch` → `degraded`・`need_rescan` → full invalidation・Access 除外）+
  `mm_core.watch_start/poll/stop/diagnostics` + `py/watcher.py`（asyncio タスク 1 本・
  1 s ポーリング・path→type 最長一致・type 単位 2 s クールダウン・`.tmp` 除外・
  network root 自動スキップ・degrade 600 s クールオフ・native 不在でも静かに TTL）+
  設定 `ModelManager.Scan.WatchModelFolders`（**既定 OFF**・i18n×3・
  `MM_WATCH_ROOTS` 上書き）+ `app.on_startup/on_cleanup` フック +
  `GET /model-manager/watch-status`（読み取り専用）。フロントは**無改修**。
  **request 無しでの設定読み取り**は ComfyUI `app/user_manager.py` /
  `app/app_settings.py` を一次ソースで確認して採用（single-user では
  `get_request_user_id` が request に触れない。`--multi-user` では例外 →
  既定値 OFF に degrade = 安全側）。`watch` cargo feature は **default-on**
  （同梱バイナリが `watch_*` を持たなければ設定が永久に動かないため）。

### 計測（K15・C1/C2・テンソルツリー — BENCH §11、同一実行内 before/after）

2 vCPU / 1 GiB / Node v20.20.2（system ICU）、5,050 モデル・200 keystroke・
65,268 テンソル MoE。**ゲートは同一実行内比率**なのでランナー非依存。

- **K15 keystroke（JS 作業）**: naive p95 **10.57 ms** → 出荷経路 **3.96 ms**
  （**×2.7**、C1 のみでは 3.49 ms = ×3.0。4 回実行の幅: naive 10.57–14.23 /
  出荷経路 3.20–3.96 ms = ×2.7–4.0）。**≤ 16 ms 予算の 25 %**。
- **K15 初回グリッド**: 行構築 p95 7.95 → **7.03 ms**（scan 自体は Phase 5 K9 =
  0.145 s）。paint 脚は実 UI 側で `mm.grid.queryToPaint` として計測可能。
- **描画行は naive と完全一致**（`rowsAreIdentical` ゲート）。
- **C2 の設計判断（重要 — Plan の前提が一部逆だった）**: 5,050 名ソートで
  `a.localeCompare(b)` **1.47 ms** vs hoisted `Intl.Collator().compare`
  **5.13 ms（×3.5 遅い）**。V8 は**既定 options の localeCompare に内部キャッシュ
  済み既定 collator の高速経路**を持つ。一方 options 付きは高速経路が無く
  `{numeric:true}` は **291.23 ms** vs hoisted numeric Collator **9.30 ms
  （×31.3 速い）**。→ 既定 variant は `localeCompare` を維持し、numeric variant
  のみ Collator 化。**両選択を bench ゲートで機械固定**（V8 の挙動が変われば CI が
  知らせる）。Plan §4.8‑C2 に実装注記を追記済み。
- **テンソルツリー**: ブラウザ内 fold **1,328.62 ms** → Rust payload デコード
  **7.68 ms** + 折りたたみ行描画 **5.09 ms** = **12.77 ms（×104）**。payload は
  **2.73 MB / 87,195 ノード**（leaf は `tensors` の index = 二重転送なし）。
  JS フォールバック経路でも 712 ms（sort が消える分だけ旧より軽い）。
- **Rust == Python 参照 == JS エンコーダの三者同一性**: pytest 5 件（Rust vs
  Python 参照、scalar / `(unnamed)` / 点無し名 / MoE 形 / leaf index 整合 /
  root 集計）+ bench `--cross-check`（**2,086 テンソル / 2,892 ノード /
  66,993 B がバイト一致**）。

### 全ゲート再検証（release .so against・全緑）

- cargo fmt ✓ / **clippy `--workspace --all-targets --all-features -D warnings` ✓** /
  cargo test: znn-codec **195**（Phase 5 の 181 から +14 = tensor tree 5・watch 8・
  index cap 1）+ 統合 4（extended_band）+ mm-core `--no-default-features` **5** ✓
- **pytest 176 passed**（Phase 5 の 127 から **+49**: tensor tree 6・A3 http 19・
  watcher 18・download seeding 3・scan 監査回帰 3）
  / **native バイナリ無しの ci.yml 相当でも 59 passed・117 skipped・0 failed**
- ruff check + format ✓ / **mypy 16 files ✓**（`py/http_client.py`・`py/watcher.py`
  を mypy.ini へ追加）/ pnpm typecheck ✓ / eslint ✓ / prettier ✓ /
  **dependency-cruiser ✓（136 modules / 409 deps、違反 0・Node 22 で実行）** /
  **`pnpm build` ✓**（web バンドル再生成、`__mmNeoPerf` / `WatchModelFolders` /
  `(unnamed)` を manager.js 内で確認）
- release `.so`（host build）**3,139,424 B = 予算 4 MB の 75 %**（Phase 5 の
  2,869,968 B から **+269 KB** = notify/debouncer-full + tensor tree）。
  `verify_native_binary.py`: **libpython 非依存 ✓**（NEEDED = libgcc_s/libm/libc/
  ld-linux のみ）。`max_glibc 2.34 > floor 2.28` は **host ビルドのため期待通り**
  （CI は zigbuild で 2.28 に固定 — 第 6 セッションの記録と同じ）。
- api_version **4→5** を 4 者同期（`py/native.py` [5,5]・`mm-core lib.rs` +
  その test・`native.yml` abi3-import・pytest の 3 アサート）。
- **fuzz 表面は不変**（codec 無変更。`safetensors_io` は関数追加と
  `read_header_region` 抽出のみで、パイプラインは `StContainer::parse` 側 =
  触っていない。scan/hash/index/watch は fuzz ターゲット外）→
  **fuzz-long 再ディスパッチ不要**（run 6 の 18 h 証跡が有効）。

### CI（GitHub Actions）の変更

- `ci.yml`: **`Frontend K15 bench (C5)`** ステップを追加（Build の後）。
  `src/utils` 実物を tsc でコンパイルして before/after を同一実行内で計測し、
  ゲート（比率 + parity）で失敗する。絶対値は記録のみ（判定は参照機）。
- `native.yml`: integration（ubuntu）に **`Tensor-tree wire cross-check
(Rust == TypeScript)`** を追加。pnpm ストアが無いジョブなので typescript を
  `/tmp/mmneo-tsc` へ npm install し `MMNEO_TSC` で渡す（実ビルド成果物 against）。
  abi3-import の assert を **5** へ更新。
- ワークフロー/ビルドスクリプトの他の部分は無変更（`watch` が default-on のため
  `build-native.sh` に `--features` 追加は不要 = 4 プラットフォーム全てが
  `watch_*` を持つ）。

### 運営メモ（次セッション向け）

- **残件（Phase 7 向け）**: third_party 撤去・`MM_NATIVE` スイッチ撤去・
  README/USAGE 全面改訂・バイナリサイズ最終最適化・v0.3.0 の**公開準備まで**
  （公開作業そのものはユーザ専任 — §6.3 規程）。L5 クロス検証 CI が
  2 リリースサイクル連続 green かのゲート確認を最初に。
- Phase 2 K2/K3 の参照機再計測、K10 5000 モデル ≤100 ms の参照機確認、
  K11 端到端 ≤40 ms（公開契約変更を伴うため範囲外と記録済み）は**不変**。
  実 UI 手動 QA は Phase 7 で統合（今回追加した `__mmNeoPerf` の paint 脚計測が
  その際の K15 実測手段になる）。
- `py/http_client.py` の共有セッションは**ループ変化を検出して作り直す**。
  pytest-asyncio は テスト毎に新ループなので、`tests/test_phase6_http.py` は
  autouse fixture で `close_session()` する（しないと "Unclosed client session"
  警告と次テストでの再作成ノイズ）。
- watcher は**シングルトン `watcher.watcher`** とクラス `ModelWatcher` を分離済み。
  テストは必ず**新しいインスタンス**で作ること（シングルトンを汚すと
  クールダウン状態が持ち越される）。
- `scripts/bench/front/k15.mjs` は `--cross-check` 無しなら native 不要・約 30 s。
  CI セルは縮小パラメータ（`--models 1500 --keystrokes 40 --moe-layers 12
--moe-experts 8`）で約 6 s。

### 追加（同日・push 後）— CI 失敗 2 件の修正 + Phase 6 独立精査で発見した 10 件

push 後の CI（#136 / native #47）が失敗。原因を特定して修正し、さらに
「Phase 6 の実装にバグが無いか精査せよ」というユーザ指示に対して独立精査
（fresh eyes）を実施した。**CI 失敗 2 件 + 精査で 10 件**を修正、全て回帰テスト化。

#### CI 失敗の原因（2 件 + 同種の潜在 1 件）

1. **ci.yml `verify` の pytest 3 件失敗** — `test_phase5_scan.py` に追加した
   監査回帰テスト 2 本（3 パラメータ）が `_set_engine(monkeypatch, "1")` で
   native 経路を要求するのに **`_require_native()` の skip ガードを付け忘れ**た。
   ci.yml にはビルド成果物が無い（native-bin は gitignore、成果物は native.yml が
   ビルド）ため `MM_NATIVE=1 but the native core is unavailable` で失敗。
   → 両テストに `_require_native()` を追加。**ローカルは .so があるため緑で、
   CI 相当環境を再現して初めて出た**（以後、push 前に
   `mv native/native-bin/.../mm_core.abi3.so` で成果物なしのスイートも回すこと）。
2. **native.yml `native-build-linux` の "Loader regression tests" 10 件失敗** —
   `ModuleNotFoundError: No module named 'markdownify'`。A3 のテストが
   `py/search.py` → `py/information.py`（module-level で markdownify + PIL を
   import）を初めて import する経路なのに、このジョブの pip 行が
   `pytest pytest-asyncio aiohttp pyyaml requests pillow` だけだった。
   **integration ジョブも同じ欠落**（native-build-linux の失敗で skip されていた
   ため未顕在化）。→ 両方の pip 行に `markdownify` を追加 + テスト側にも
   `pytest.importorskip("markdownify" / "PIL")` の明示ガード（最小環境では
   collection error ではなく skip になる）。
3. **同種の潜在失敗を CI 相当の再現で発見** — `test_network_root_skip_is_logged_once`
   が native core の有無に依存していた（`_core()` が None だと root 選別まで
   到達しない）。root 選別は純 Python なので**fake core を注入**して
   バイナリ非依存に修正（「arm しようとしたら AssertionError」の形で
   network-only ライブラリが arm しないことも同時に固定）。

修正後の実測: **成果物なし（ci.yml 相当）59 passed / 117 skipped / 0 failed**、
**成果物あり（native.yml 相当）176 passed**。front bench は CI #136 で
**PASS 済み**（Node 22 / GH ランナー: keystroke p95 1.19 ms・C1 ×3.53・
numeric ×33.4・既定 localeCompare ×2.15 速い・tree ×73.0）= **C2 の設計判断が
CI ランナーの V8 でも再現した**ことの独立証跡。

#### Phase 6 独立精査 — 発見 10 件（全て修正 + 固定）

| #   | 領域                                    | 症状 / 根因                                                                                                                                                                                                                                                                                                                                              | 修正                                                                                                                                                                                                                                                                                                                               | 固定                                                                                                                          |
| --- | --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1   | py/watcher.py                           | **`watch_start` / `watch_stop` がイベントループ上で実行**されていた。arm はライブラリ全体の walk + ディレクトリ毎の inotify watch 登録で数秒かかり得る（Phase 5 監査 #1 と同じ欠陥クラス）                                                                                                                                                               | io_executor へ移動。`_release_session` は async 化し、cancel 中でも `asyncio.shield` で確実に解放（notify スレッドのリーク防止）                                                                                                                                                                                                   | `test_arm_and_release_run_off_the_event_loop`（実行スレッドを記録して固定。poll は設計通りループ上）                          |
| 2   | watch.rs                                | **`shared.errors` のロックを `Debouncer::watch()` の間保持**していた。kqueue/FSEvents は watch 呼び出しを watcher スレッドへ渡して待つ一方、その同じスレッドが走るイベントハンドラは `errors` をロックする = **ロック順序反転（macOS でデッドロックし得る）**                                                                                            | arm 中の報告はローカル Vec に集めて後からマージ（ロックを跨がない）                                                                                                                                                                                                                                                                | clippy/fmt + 既存 watch テスト 4 件                                                                                           |
| 3   | watch.rs                                | **pending パス集合が無制限**。2 poll 間のバルクコピー（ライブラリ全体の複製等）で集合と次の poll の JSON が無限に伸びる                                                                                                                                                                                                                                  | `MAX_PENDING_PATHS = 4096` を超えたら **1 回の `rescan`（全面無効化）へ畳んで clear**（Python 側は `{type: null}` を配信するだけ）                                                                                                                                                                                                 | `a_burst_collapses_into_one_full_rescan`                                                                                      |
| 4   | py/watcher.py                           | (a) 設定を**毎秒**読んでいた（= 既定 OFF のユーザでも `comfy.settings.json` の同期読み込みが 1 Hz でイベントループ上に発生）(b) network root のスキップを**毎秒 log**（スパム）(c) `rescan` 配信にクールダウンが無く、queue 溢れが持続すると毎秒全面再スキャン                                                                                           | (a) `SETTING_TTL = 5.0` のキャッシュ (b) root 毎に 1 回だけ log（解消したら再報告可）(c) `RESCAN_KEY` で type と同じクールダウンを適用                                                                                                                                                                                             | `test_setting_is_cached_for_the_ttl` / `test_network_root_skip_is_logged_once` / `test_rescan_broadcast_honours_the_cooldown` |
| 5   | py/search.py                            | 3 者並列 sweep の実行中に**クライアントが離脱すると provider coroutine が 3 本オーファン化**（旧 executor 版は `pool.shutdown(cancel_futures=True)` が担っていた）                                                                                                                                                                                       | `asyncio.wait` を `except BaseException` で囲み、全 task を cancel して再送出                                                                                                                                                                                                                                                      | `test_search_sweep_cancels_providers_when_the_client_goes_away`                                                               |
| 6   | ModelContent.vue / ModelInformation.vue | **Rust 事前グループ化の効果が相殺されていた**: `useModelFormData` の `cloneDeep(props.model)` が 65,268 テンソル（**218.5 ms**）と 87,195 ノードの payload（**130.0 ms**）まで深複製し、`editorState()` の dirty 判定が両方を**毎回 JSON.stringify**（open / reset / 判定のたび）。加えて deep `ref` 経由の走査は Proxy トラップ込みで fold 本体より高い | 読み取り専用表示 payload（`tensors` / `tensorTree`）を**参照共有**に変更（保存経路は元々これらを送らない = `buildUpdatePayload` は preview/description/type/pathIndex/fullname のみ）+ snapshot から除外 + `ModelInformation.vue` は `toRaw()` 経由で読む。端到端で ≈1,589 → ≈13 ms（**×120**、BENCH §11.3.1）                     | typecheck/eslint + bench の parity ゲート（表示は不変）                                                                       |
| 7   | py/http_client.py                       | JSON デコードが**宣言 charset を無視**（`requests` は `Response.text` 経由で尊重する）+ 未知 codec 名で `LookupError` が 500 として逃げる                                                                                                                                                                                                                | charset 準拠 + UTF-8 フォールバック（RFC 8259）。`LookupError` を捕捉                                                                                                                                                                                                                                                              | `test_declared_charset_is_honoured_and_a_bogus_one_degrades`                                                                  |
| 8   | utils/perf.ts                           | **`perfMark` / `perfMeasure` が export されているだけで未使用**（文書は「performance.mark 計測基盤」を謳っていた）                                                                                                                                                                                                                                       | `perfTime` が `name:start` / `name:end` の mark 対 + `performance.measure` を実際に発行（DevTools Performance パネルに見える）。anchor mark は measure 後に clear（長セッションで溜めない）。無効時は boolean 1 回 + 直呼びのまま                                                                                                  | bench が `perfTime` を経由して計測（同一コード経路）                                                                          |
| 9   | utils/tensorTree.ts + py/utils.py       | **stale payload の検出が無かった**: `tensors` と tree はサーバ側で 2 回の別パースなので、間にファイルが差し替わると（ZipNN の rename・外部ダウンロード）別のテンソル表に対するツリーを描き得た                                                                                                                                                           | (a) デコーダに `leaves.length === tensors.length` 検査（不一致は JS フォールバックへ）(b) `get_model_header` が 2 回の native 呼び出しを `(mtime_ns, size)` で挟み、変化していれば tree を落とす                                                                                                                                   | `test_tensor_tree_is_dropped_when_the_file_changes_mid_read` + bench の validator 15 ケース                                   |
| 10  | scripts/bench/front                     | **payload 検証（防御分岐）に一切のカバレッジが無かった**（このリポジトリの TypeScript に単体テストランナーは無い）                                                                                                                                                                                                                                       | 計測器に **15 ケースの accept/reject ゲート**を追加（版数違い・配列欠落・タプル形・非文字列 segment・負値/非有限・範囲外/非整数 leaf index・own count 不一致・pre-order 構造破綻〔存在しない子 / 二重 root〕・空 node 表・別テンソル表のツリーを拒否し、正常/空ヘッダ/実 payload は受理）= `tensorTreeValidatorRejectsBadPayloads` | CI（ci.yml + native.yml cross-check）が毎回実行                                                                               |

#### このラウンドのゲート（全て緑）

- cargo fmt ✓ / clippy `--workspace --all-targets --all-features -D warnings` ✓ /
  cargo test: znn-codec **195**（watch +4 = record の dedupe/Access 除外・
  バーストの rescan 畳み込み・need_rescan・予算エラーの degrade と error 上限）+
  統合 4 + mm-core 5 ✓
- pytest **176**（+9: charset・cancel・race guard・watcher 6）/
  **成果物なし環境でも 59 passed・117 skipped・0 failed** ✓
- ruff ✓ / mypy 16 files ✓ / typecheck ✓ / eslint ✓ / stylelint ✓ / prettier ✓ /
  dependency-cruiser 136 modules 違反 0 ✓ / `pnpm build` ✓
- release `.so` **3,139,424 B**（予算 75 %・libpython 非依存）
- bench ゲート **PASS**（`tensorTreeValidatorRejectsBadPayloads` 追加後も全緑・
  cross-check は 66,993 B バイト一致のまま）

#### 運営メモ（追記）

- **push 前の検証は「native 成果物あり」と「なし」の両方で pytest を回すこと**
  （ci.yml は成果物なし、native.yml はあり。今回の失敗 1・3 はこの差分）。
- native.yml で pytest を回す 2 ジョブ（native-build-linux の loader regression /
  integration ×3 OS）の pip 行は**同一内容に保つこと**（`markdownify` 追加を
  片方だけすると同じ失敗が再発する）。
- watcher の arm/release は必ず executor 経由（`_tick` を直接呼ぶテストでも
  スレッドを検証している）。`SETTING_TTL` / `TYPE_COOLDOWN` / `DEGRADE_RETRY` /
  `MOUNTINFO_TTL` はテストから monkeypatch 可能な module 定数。

## 2026-09-27（第 9 セッション）— Phase 6 最終バグチェック（バグなし）+ 描画行 parity ゲート新設 + fallow 不変条件の回復と CI ゲート化

ユーザ指示「念のため Phase 6 のバグを精査し、見つかり次第修正、バグが無くなるまで
検証・デバッグを反復」に対するセッション。**機能バグは 0 件**（第 8 セッションの
独立精査 10 件が正しく、全ゲート緑をこの環境で再現）。加えて (1) テンソルツリーの
**描画行 parity ゲート**を bench に新設（カバレッジギャップ解消）、(2) Phase 6 で
**漂移していた fallow「未使用 export ゼロ」不変条件を回復**（13 export + 型 4 つを
private 化）、(3) 同不変条件を **ci.yml のゲート化**（今回の漂移は fallow が CI で
強制されていなかったことが原因）。

### 環境再構築（セッション冒頭ロールバック対策 — 第 6/8 セッションと同型）

apt（build-essential/clang/mold/libpython3.11-dev/curl/pkg-config）→ rustup stable
**1.98.1**（+rustfmt/clippy）→ pip（ruff/mypy/pytest/pytest-asyncio/aiohttp/
markdownify/huggingface_hub/hf_xet/modelscope_hub/pillow/numpy/safetensors +
**torch 2.14.0+cpu** = フル 176 カバレッジ用）→ corepack pnpm 12.3.4 +
`pnpm install --frozen-lockfile`。**dependency-cruiser 18 は Node ≥22 必須**
（この環境は 20.20.2）→ 公式 tarball の Node v22.20.0 を `/tmp` へ展開して
`depcruise src` を実行（136 modules / 409 deps、違反 0）。native `.so` は
**debug ビルド**（`cargo build -p mm-core` = extension-module 既定）を
`native/native-bin/linux-x86_64/mm_core.abi3.so` へ配置（gitignore 対象・68 MB）。
**release（lto=fat）ビルドは 1 GiB で OOM（SIGKILL）**するため、テスト/検証は
debug で十分（api_version ハンドシェークは同一）。

### 全ゲート再検証（この環境で実測・全緑）

- **Rust**: `cargo test -p znn-codec` **195** + 統合（extended_band）**4** +
  `cargo test -p mm-core --no-default-features` **5**、clippy
  `--workspace --all-targets --all-features -D warnings` ✓、`cargo fmt --check` ✓
- **Python**: pytest **176 passed**（native + torch あり）/ **59 passed・117 skipped**
  （native なし = ci.yml 相当、`mv` で成果物を退避して再現）、ruff check ✓、
  ruff format ✓、mypy **16 files** ✓
- **Frontend**: typecheck ✓、eslint ✓、stylelint ✓、prettier ✓、
  dependency-cruiser ✓（136/409、違反 0・Node 22）、`pnpm build` ✓
  （**決定的** — 同一ハッシュの chunk を再生成、manager.js は export 削除分のみ差分）
- **K15 bench**: 全ゲート PASS（keystroke p95 予算内・C1 ×2.6–4.4・C2 numeric ×24・
  既定 localeCompare 維持・tree ×60–104・rowsAreIdentical・tensorTreeParity・
  **tensorTreeRowsIdentical〔新設〕**・validator 15 ケース）、`--cross-check`
  **rustJsTreeIdentical: true**（Rust == JS エンコーダ バイト一致）
- **fallow**: dead-code **検出 = 意図的な pnpm-workspace override のみ**（exit 0）・
  dupes **0**・health/audit も exit 0

### fresh eyes 精査 — 機能バグなしと判定した領域（negative findings）

Phase 6 差分の中核を全て実読 + 実走査し、以下がいずれも健全であることを確認した
（推測でなく一次コード against）:

- **py/http_client.py**: `get_session` の None→生成は await を挟まず**同期アトミック**
  （起動時の並発初回呼び出しでも二重生成しない）。loop 変化時のみ入る
  `await close_session()` 分岐に理論上のレースがあるが、本番は loop が変わらない
  ため到達せず（テストは autouse fixture が直列化）。`decode_json` の charset 準拠 +
  `LookupError` フォールバック、`fetch_bytes_capped` の読みながら cap、
  `HttpStatusError` の requests 逐語文言 + `.response.status_code` 維持 — 全て正しい。
- **py/watcher.py**: `type_matcher` の最長一致 + 一度だけ realpath、rescan/type の
  クールダウン（消費された rescan 信号を意図的に間引く = TTL が床）、
  `_release_session` の `asyncio.shield`（cancel 中でも notify スレッド解放）、
  arm/poll の executor 分離 — 設計通り。
- **py/search.py**: 3 者並列 sweep の `except BaseException` cancel（オーファン化防止）、
  `run()` が `Exception` のみ捕捉（CancelledError は伝播 = task が正しく cancelled 化）、
  avatar/owner の distinct 並列 gather + キャッシュ、civitai の sort_keys 後段ソート。
- **py/identify.py**: 二重スレッドホップ解消（recorded_hashes=io / compute_hashes=cpu /
  lookup=loop）、`{**computed, **hashes}` の記録値優先。
- **py/utils.py `get_model_header`**: `(mtime_ns, size)` で 2 回の native 呼び出しを挟み、
  変化時は tree を落とす（stale payload ガード）— フロントの leaf 数検査と二重。
- **native watch.rs**: arm 中の報告をローカル Vec に集めて後マージ（ロック順序反転の
  解消）・poll_json は paths/errors/degraded を**逐次**ロック（同時保持なし）・
  stop は debouncer をロック外で `stop_nonblocking`・`MAX_PENDING_PATHS` 超過で
  1 rescan へ畳み込み・errors 64 上限 — デッドロック/リークなし。
- **native safetensors_io `encode_tensor_tree`**: parent index < child index 不変条件に
  よる逆順集計の正しさ、pre-order own-leaves-before-children の線形符号、
  frame-stack による非再帰 emit（深名でスタック溢れしない）、saturating 集計。
- **src/utils/tensorTree.ts `createTensorTreeIndex`**: leafOffset = tensorCount の累積、
  `leaves.length === tensors.length` の stale ガード、subtree/parent の再構築 +
  second-root / 未完 frame / `subtree[0] !== size` の構造検証（敵対的 payload を拒否）。
- **C3 shallowRef（hooks/model.ts）**: 全 15 消費者を実査 — store は record 全体を
  置換するのみ、消費者は読み取り / `cloneDeep`（explorer・useModelFolder）/ ローカル
  配列への push のみで **in-place 変更ゼロ**。`.sort()` は全て copy/clone 後
  （`[...x].sort` / `slice().sort` / filter 結果）。DialogModelDetail の
  `watch(() => modelsData.value[type])` は shallowRef でも再代入で発火（getter が ref を追跡）。
- **ModelContent.vue / ModelInformation.vue**: 表示専用 payload（tensors/tensorTree）の
  参照共有は「読み取り専用 + 保存経路が送らない」で安全、`editableState()` が snapshot
  から除外、ModelInformation は `toRaw()` 経由で Proxy トラップ回避。leaf の
  `segment: tail || tensor.name` フォールバックは**legacy（873581f）と逐語同一**
  （空 segment 名の表示も回帰なし）。

### このセッションの変更（3 点 — 全て検証済み）

1. **描画行 parity ゲート `tensorTreeRowsIdentical`（scripts/bench/front/k15.mjs）**:
   遅延インデックス描画（`renderRows` = 出荷経路）が legacy 入れ子ツリー walk と
   **同一の行キー列**（`f:<path>`/`t:<name>`、folders→leaves、DFS、ノード内
   naturalCompare 順、500 件ページング）を出すことを、折りたたみ（root 直下 1 行）と
   **全展開（MoE 84×256 = 152,462 行）**の両方で毎回照合。従来の `tensorTreeParity`
   （root 集計 + 直下 children のみ）が届かない**描画順・再帰・ページングの回帰**を
   捕捉する。証跡 JSON（`scripts/bench/results/phase6_front.json`）に決定的な
   `rowsParity`（collapsed 1 / expanded 152462）+ `gates.tensorTreeRowsIdentical` を
   外科的に追記（参照 timing 値と `rustJsTreeIdentical:true` は保持 = 再生成しない）。
   BENCH §11.3 の「表示は不変」をこのゲートで機械固定した旨に更新。
2. **fallow「未使用 export ゼロ」不変条件の回復**: Phase 6 の utility モジュールが
   bench/自ファイル内でのみ消費される helper を export していた（第 8 セッションの
   ゲートに fallow が無く未検出）。`fallow fix` で 13 値 export を private 化
   （modelFilter: buildTokenRegex/filterModels/chunkRows/compareTextNumeric、
   perf: perfMark/perfMeasure/perfSamples/perfSummary/perfReset/perfHandle、
   tensorTree: TENSOR_TREE_VERSION/UNNAMED_SEGMENT、zipnn: inspectZipnnModel〔Phase 4 由来〕）
   - 型 re-export `TensorTreeNodeTuple` を除去。**private 化の連鎖**で表面化した型
     （ZipnnInspect/PerfHandle → PerfSample/PerfStat）も private 化（fallow の
     `unused-types`=warn / `unused-exports`=error の区別を実測で確認）。全シンボルは
     grep で**外部参照ゼロ**（コメント/ドキュメント参照のみ）を逐一確認してから実施。
     typecheck/eslint/build/bench/fallow 全て緑で無破壊を確認（web バンドル再生成 =
     minify 差分 5 行のみ、機能同一）。README/README-JP の Fallow 節も更新。
3. **ci.yml に fallow ゲート新設**: `Dead code & duplication (fallow)` ステップ
   （`pnpm fallow:dead` + `pnpm fallow:dupes`）を dependency-cruiser の後に追加。
   ERROR レベル規則（unused-exports/unused-files/unresolved-imports）がビルドを
   失敗させる（warn の unused-types/private-type-leaks と意図的な override は
   exit 0 = クリーンツリーで緑）。**今回の漂移は fallow が CI で強制されて
   いなかったことが原因**なので、再発を機械的に防ぐ。fallow は locked devDep
   （`pnpm install --frozen-lockfile` で決定的に install）・Rust バイナリ
   （Node 版非依存）・Debian 12 で動作確認済み = ランナでの flakiness リスク低。

### 運営メモ（次セッション向け）

- **fallow は CI ゲートになった**（ci.yml）。push 前に `pnpm fallow:dead` +
  `pnpm fallow:dupes` を回すこと。export を消すと**その戻り型/注釈型が連鎖で
  unused-types（warn）に落ちる**ので、型も併せて private 化すると clean になる
  （error ではないので CI は落ちないが、README の「ゼロ」不変条件は型も含む）。
- **release ビルドは 1 GiB で OOM する**（lto=fat + codegen-units=1）。native テスト/
  検証は **debug ビルドの `.so`** で十分（api_version ハンドシェーク・全 pytest・
  cross-check が同じ結果）。サイズゲート確認時のみ CI（zigbuild）に任せる。
- **bench の証跡 JSON は再生成しない**（`--json-out` は既定で committed パスだが、
  CI は `/tmp` へ書く）。timing 値は BENCH §11 が逐語参照する参照機のものなので、
  ゲート追加時は**決定的な欄だけ外科的に追記**する（今回の rowsParity がその例）。
- 不要ファイル整理: **削除対象なし**を一次調査で確認（コミット済み junk/`__pycache__`
  ゼロ、`json-bench` は BENCH §2 の証跡計測器、`third_party`/`znn-cli`/`scripts/l2`・
  `l5`・fuzz corpus は CI/Phase 7 が参照、web バンドルに孤児なし = Phase 6 で旧
  ja/zh chunk は差し替え済み）。demo-assets はユーザが後で追加するため対象外。

## 2026-09-28（第 10 セッション）— CI 完了確認 + テストコードのバグ/甘さ精査（4 件修正、全て mutation 検証）

ユーザ指示「GitHub Actions の完了確認」+「テストコードのバグ・テストの甘さを精査・
修正せよ」に対するセッション。**テストバグ（誤アサーション）は 0 件**、
**カバレッジギャップ/脆弱アサーション 4 件**を修正（いずれも mutation testing で
「回帰を捕捉できること」を実証）。production code は**一切変更していない**
（差分は tests/ の 3 ファイルのみ）。

### CI 完了確認（GitHub API 実測）

第 9 セッションの push（2410f11）に対する Actions は**全て success**:
CI #140（push）/ #141（PR）・native #51（push）/ #52（PR）。native #51 は
**全 14 ジョブ green**（native-test×3 OS / native-build×3 / native-diff〔L2〕/
fuzz-smoke〔L3〕/ abi3-import 3.10+3.13 / integration×3〔L4/L5 + tensor-tree
cross-check + 新 rowsIdentical ゲート〕/ size-budget）。ci.yml #140 は新設の
`Dead code & duplication (fallow)` ステップを含め全ステップ green（fallow バイナリが
ubuntu-latest ランナで正常 install/run することも実証）。

### テスト精査の方針と範囲（fresh eyes・一次コード against）

基盤（`harness.py` の byte-exact safetensors writer / DTYPE_BITS の bit 境界 assert /
決定的 LCG、`stubs.py` の ComfyUI master 忠実ミラー〔filter_files_extensions・
safetensors_header の差分も文書化〕、`conftest.py`）+ 全 phase テストを実読。
**総じて極めて高品質**を一次確認: byte-exact roundtrip（sha256）、golden metadata
contract（`znn_compressed_vectors` == Python `json.dumps` 逐語）、native==legacy parity
（scan/hygiene/header/hash/walk/move/batch）、degrade 経路、executor スレッド検証
（`test_arm_and_release_run_off_the_event_loop`）、実 aiohttp モックサーバ
（往復回数まで固定）、15 ケースの validator。**誤アサーション・偽陽性テストは
発見されず**。Phase 5/6 監査の全修正（6+10 件）に対応する回帰テストが存在することも
突き合わせて確認した。

### 修正 4 件（全て mutation testing で有効性を実証）

1. **download 書き込みループのガード接合部が未検証**（test_phase5_download.py）:
   旧 `test_hasher_update_on_a_lost_handle_raises_and_is_caught_by_the_loop` は
   名前/docstring が「ループが捕捉する」と謳うのに、実際は **native の KeyError
   送出（前提条件）しか検証しておらず**、Phase 5 監査 #2 の本体（`hasher_update`
   失敗 → `except` で `hasher=None` → 書き込み継続 → `_download_complete` の
   `_sha256_of` re-read で検証完了）という**接合部が無テスト**だった。
   → 端到端テスト `test_write_loop_survives_a_lost_hasher_handle_and_rereads` を新設
   （ローカル aiohttp TestServer + **fake core**〔hasher_update が KeyError、
   hasher_finalize は呼ばれたら AssertionError〕で `download_model_file_http` を駆動。
   **native 不要 = ci.yml でも実行**。1.5 MiB=2 chunk で「最初の失敗後も書き続けて
   完走・正しい sha・inline digest 未 stage・progress 100%」を固定）。旧テストは
   `..._raises_keyerror` へ改名し docstring を実態（前提条件）に是正。
   **mutation 検証**: ガードの try/except を外すと KeyError が伝播してテスト失敗。
   ※ 駆動時の注意: TaskStatus 既定 status が `"pause"` だと書き込みループが即 break
   する（協調ポーズ）。実オーケストレータ `download_model` は呼び出し前に
   `status="doing"` にするので、テストも `md.get_task_status(task_id).status="doing"`
   を設定する（これを忘れると 0 バイトで "pause" になる）。
2. **`.tmp` フィルタの接合部が未検証**（test_phase6_watcher.py）: `_interesting`
   （`.tmp` 除外）は単体テスト済みだが、`_tick` が実際にそれを適用して
   「Neo 自身の atomic write チャーンではブロードキャストしない」ことは未検証だった
   （回帰すると ZipNN 圧縮/ダウンロードのたびに再スキャン嵐）。
   → `test_tmp_artefacts_alone_do_not_broadcast` を新設（`.tmp` のみの poll 報告で
   `models_changed` ゼロ + `stats["events"]==0`）。**mutation 検証**: `_tick` の
   `if _interesting(...)` を外すとブロードキャストして失敗。
3. **type_matcher の sibling-prefix が未検証**（test_phase6_watcher.py）: 区切り文字を
   考慮した前方一致（`prefix = root.rstrip(sep)+sep`）は正しいが、古典的バグ級
   （naive `startswith(root)` だと `/models/ck_old` が root `/models/ck` に誤マッチ）
   を固定するテストが無かった。→ `test_types_for_path_maps_the_longest_root_first` に
   sibling ディレクトリの assert を追加。**mutation 検証**: `startswith(root)` に
   変えると失敗。
4. **cancel 伝播テストの脆弱なタイミング依存**（test_phase6_http.py）:
   `test_search_sweep_cancels_providers_when_the_client_goes_away` が固定回数の
   `for _ in range(5): await asyncio.sleep(0)` で cancel 伝播を待っていた（回数依存で
   理論上 flaky）。→ 条件ベースの `await asyncio.wait_for(cancelled.wait(), timeout=5)`
   へ（伝播完了を待つ・孤児化時は timeout で大声で失敗）。**mutation 検証**:
   search.py の `for task: task.cancel()` を外すと TimeoutError で失敗。

### 検証（テストのみの変更・全緑）

pytest **178 passed**（native + torch = native.yml 相当、第 9 の 176 から **+2** =
新規 2 件は native 不要）/ **58 passed・120 skipped**（native なし = ci.yml 相当、
56→58）・ruff check ✓・ruff format ✓（49 files）・mypy 16 files ✓（py/ 無変更）。
frontend ゲート（typecheck/eslint/stylelint/prettier/build/bench/fallow）は src/ を
触っていないため影響なし（再実行不要）。native `.so` は debug ビルドで再作成
（release lto=fat は 1 GiB で OOM するため）。

### 判断記録（保守側 = 追加しなかったもの）

- **resume seeding の executor オフロード（Phase 5 監査 #1）は thread 検証を
  追加しなかった**: 206 + Range + 実 hasher（seed+残りで正しい sha を出す）+
  スレッド記録が必要で複雑/脆弱になる。seeding の**正確性**は
  `test_seed_hasher_from_file_matches_a_whole_file_hash` が、**「重い native 呼び出しを
  loop 外で」パターン**は `test_arm_and_release_run_off_the_event_loop`（watcher）が
  既に固定しているため、限界価値 < 脆弱テストのリスクと判断。

### 運営メモ（次セッション向け）

- **テストは mutation testing で「回帰を捕捉できること」まで検証すること**
  （今回 4 件全てで実施: ガード/フィルタ/一致/cancel を意図的に壊して失敗を確認 →
  復元）。アサーションが「通る」だけでは甘さの見逃しになる。
- `download_model_file_http` を直接駆動するテストは **status="doing" の設定が必須**
  （既定 "pause" だと書き込みループが即 break）。fake core は
  `monkeypatch.setattr(download.native, "core_if_enabled", lambda: Fake())` で注入でき、
  **native バイナリ無しで** inline-hash 経路を検証できる（ci.yml カバレッジになる）。
- テストスイートの品質は極めて高い（byte-exact golden / parity / 逐語 contract /
  degrade / thread 検証）。今後テストを増やす際は「既存の強いパターンの踏襲」と
  「mutation で捕捉力を証明」を基準にすること。

## 2026-09-28（第 11 セッション）— Phase 7 新設・T7/T8 追加・Phase 8 ストレッチ削除（ユーザ決定 3 件）+ 番号繰り下げの整合性一掃

ユーザ指示による Plan.md 改訂（版数 **2.1 → 2.2**）と、フェーズ番号繰り下げに
伴う**リポジトリ全体の整合性確認**を実施。コードの挙動変更はゼロ
（コメント/docstring/ドキュメントのみ）。

### Plan.md 改訂（ユーザ決定 — 版数履歴 2.1/2.2 に恒久記録）

1. **Phase 7「ツールチェーン現代化・設定統合」を新設**（T1 アップロード
   preflight SHA256 の Rust 化〔既存 `mm_core.hash_file` へ接続〕/ T2 Node
   v26.10.0〔nodejs.org dist 実測 = v26 系最新・2026‑09‑21・vite 8.2.2 と
   dependency-cruiser 18.4.0 の engines 充足を一次確認〕/ T3 Ruff 0.16.9
   〔PyPI latest 実測・ci.yml ピン 0.16.8 から更新〕/ T4 uv 導入
   **開発・CI 層限定**〔ランタイムの requirements.txt / `utils.pip_install`
   契約は維持・uv 0.12.19 実測〕/ T5 mypy.ini → pyproject.toml `[tool.mypy]`
   統合〔**mypy 2.3.1 の自動発見をサンドボックス実測で実証**・
   tests/pytest.ini は rootdir/confcutdir 制御のため意図的に非統合〕/
   T6 設定ファイル全面見直し〔GitHub Actions major 更新を API 実測で列挙:
   checkout v4→v7.0.1 / setup-node v4→v7.0.0 / setup-python v5→v7.0.0 /
   upload-artifact v4→v7.0.1 / download-artifact v4→v8.0.1 /
   pnpm-action-setup v4→v6.1.0 / setup-uv v10.2.0・1 action ずつ別コミット規程〕）。
   **旧 Phase 7（third_party 撤去・配布仕上げ・リリース）は内容そのまま
   Phase 8 へ繰り下げ** — §6.1 総覧・§7 リスク表（R1: 1–8 / R3・R6: 0,8 /
   R10: 1,8 / R13: —）・§9・本文相互参照 5 箇所を同期。
2. **T7「zenwebp 導入 + ライセンス整備」を追加**（ユーザ決定・ライセンス整備の
   明記を指示）。一次確認（crates.io API + GitHub 実査 2026‑09‑28）:
   zenwebp **0.4.4**（imazen = Imageflow 開発元・created 2026‑01‑24・35,026 DL・
   crate 722,687 B・最新コミット 2026‑09‑27・1,727 コミット・fuzz 基盤あり・
   「pure‑Rust WebP codec — lossy (VP8) / lossless (VP8L) encode+decode +
   alpha・animation・ICC/EXIF/XMP」）→ **§3.8 の「純 Rust ロッシー WebP
   エンコーダ不在」評価は陳腐化**（§3.8 に 2026‑09‑28 追記）。同系 webpx
   （668,335 DL）は libwebp の C バインディングのため対象外。設計:
   第一段階はエンコードのみ（デコードは信頼できない CDN 入力の保安面 =
   PIL/libwebp 実績維持・zenwebp デコードは fuzz 成熟後に別途判断）、
   第二段階でアニメ GIF/WebP の**アニメ WebP 保持**（現行は先頭フレーム
   固定化 = 実 UX 劣化）。**AGPL‑3.0/商用デュアルライセンス**
   （LICENSE-AGPL3 + LICENSE-COMMERCIAL 実査・AGPLv3 §13 = GPLv3 結合許可・
   ローカルアプリのためネットワーク条項は実質無作用）のため**ライセンス整備
   (a)–(e) を必須条件化**（§8 節 / native/NOTICE〔Phase 8 の third_party
   LICENSE 継承と統合〕/ README×2 Credits / registry 要件再確認 /
   §3.7 crate 表 + Cargo.toml）。サイズゲート（現在 3,137,312 B = 4 MB
   目安の 75 %）と api_version bump（4 者同期）も規定。
3. **T8「utils.py 残り requests 2 箇所の aiohttp 化（A3 完了）」を追加**。
   対象 L687（save_model_preview = DL 完了経路）/ L750（エディタ保存）。
   メリットは構造的: IO プール枯渇解消（read timeout 120 s × 8 slots 専有 →
   イベントループへ）・http_client 方針一元化（PREVIEW_TIMEOUT 定数は
   定義済み）・MockHub テスト化。**requests は modelscope_hub の推移的依存
   として残ることを明記**（pip show 実測: Required‑by modelscope-hub —
   依存削減ではない）。
4. **Phase 8 のストレッチ項目（自由スレッド Python 向け abi3t ビルド実験）を
   削除**（ユーザ決定）。R13 緩和策を「計画外の随時対応」へ更新
   （PEP 803 = abi3t は CPython 3.15+・PyO3 `abi3t-py315` 対応済み・
   maturin は PyO3/maturin#3064 で整備中）。Phase 8 見出し下注記に削除記録。

### 用語統一（ユーザ追加質問「v1 ってなんですか?」への対応）

T1/T7/§3.8 追記/版数履歴で使っていた「v1」は**タスク内の最初の実装段階**の
意（製品版本号 v0.3.0 等とは無関係）だが誤解を招くため、**「初版」（T1）/
「第一段階」（T7 — 「第二段階」= アニメ WebP 保持と対になる）**へ統一
（4 箇所）。なお §4.2.2 付近 L1190 の既存「v1 バイナリ」は api_version 1 の
歴史的言及で**別の意味**のためそのまま（混同注意 — 今回統一した理由）。

### 整合性一掃（リポジトリ全体 grep・全件一次確認）

- **生きた参照 5 箇所を Phase 7 → Phase 8 へ更新**（いずれも旧 Phase 7 =
  third_party/レガシー経路撤去を指す前方参照）: `py/native.py` モジュール
  docstring、`native/native-bin/README.md` ×2、
  `native/crates/znn-codec/src/znn_tensor.rs` の //! doc、
  `tests/test_phase4_dtypes.py` docstring。全て同長置換 = 整形・挙動への
  影響ゼロ。
- **歴史記録は不改変（規程通り）**: MEMO 各セッションと BENCH 内の
  「Phase 7」は当時の記録。Plan の Phase 8 見出し下注記 + 版数履歴 2.1 の
  「過去の MEMO / セッション記録中の Phase 7 参照は現在の Phase 8 を指す」で
  解決済み（セッションログの書き換えは行わない）。
- **誤検出の確認**: BENCH §10.1 / Plan §4.7.2‑3 の「ストレッチ
  （差分ペイロード `?since=<gen>`）」は**別の設計項目**で abi3t と無関係
  （存置）。§3.2 / 付録 A の abi3t 記述は PyO3 の**能力記述**（作業項目で
  ない）ため削除と整合。README×2 / USAGE×3 / docs / native README /
  third_party README / .github ワークフローに古い Phase 7 参照・WebP 評価・
  zenwebp 参照が無いことを grep で確認。
- 検証: prettier 緑（Plan/MEMO/native-bin README）・ruff check + format 緑
  （py 2 ファイルはコメントのみ）・cargo fmt は同幅置換のため影響なし
  （doc comment 内テキスト）。

### 運営メモ（次セッション向け）

- **フェーズ番号は Plan.md §6 が正**: Phase 7 = ツールチェーン現代化・
  設定統合（T1–T8）・Phase 8 = third_party 撤去・配布仕上げ・リリース。
  旧 MEMO の「Phase 7」は現 Phase 8。
- T7 実施時の注意: §3.8 の 2026‑09‑28 追記・ライセンス整備 (a)–(e)・
  サイズゲート・api_version bump の 4 者同期・PIL フォールバック維持
  （`_encode_preview` 分離構造がロールバック単位）。T8 実施時の注意:
  requests 推移的依存残存の明記・挙動 parity 契約（寛容な warning+skip /
  RuntimeError 文言 / blob: 拒否 / ローカル分岐 / raise_for_status 逐語）・
  update_model が executor 内で走るための呼び出し鎖再構成の設計判断。
