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

1. [ ] 環境構築: apt（build-essential / clang / mold）+ rustup + zig（cargo-zigbuild）+ pip（maturin / ruff / mypy ほか）
2. [ ] crate バージョンの一次情報再確認（crates.io API、計画書末尾の指示）
3. [ ] Quick Win A1（py/manager.py の executor 化）→ ruff / mypy → 単独コミット
4. [ ] native/ ワークスペース雛形（znn-codec / mm-core / znn-cli / json-bench）+ mold / rustfmt / clippy 設定
5. [ ] ローカルビルド疎通（x86_64-linux native → aarch64-linux / macOS×2 / windows-gnu は zig クロス）+ サイズ実測
6. [ ] import 疎通テスト（linux x86_64、Python 3.11.2）
7. [ ] py/native.py ローダー + MM_NATIVE スイッチ
8. [ ] JSON パーサ確定ベンチ（jiter vs simd-json、8 MB MoE ヘッダー）
9. [ ] scripts/bench/ 一式 + KPI ベースライン計測 → docs/BENCH.md
10. [ ] CI（native.yml 新規 + ci.yml に dev トリガー追加）+ package.json rs:\* スクリプト
11. [ ] Plan.md 進捗マーク更新（§6.2 と §9 を同一コミットで）+ MEMO 追記
12. [ ] dev へコミット & プッシュ → CI 緑を確認（GitHub API でウォッチ）
