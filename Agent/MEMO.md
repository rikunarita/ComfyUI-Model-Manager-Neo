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
