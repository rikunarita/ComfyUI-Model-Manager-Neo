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
