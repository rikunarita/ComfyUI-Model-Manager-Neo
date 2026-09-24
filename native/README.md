# `native/` — Rust ネイティブコア ワークスペース

ComfyUI‑Model‑Manager‑Neo の中核処理を Rust へ移行するワークスペースです
（設計・フェーズ計画は [`Agent/Plan.md`](../Agent/Plan.md) を参照）。

**Phase 1（znn-codec フォーマット中核）実装済み**: `znn-codec` クレートが
ZN ヘッダー・ビット並べ替え・平面分割・huff0/FSE（RFC 8878）・チャンク並列
codec を純 Rust で提供し、vendored C コアと**バイト同一の圧縮出力**を生成
します（L2 ゴールデン差分 9,880/9,880 一致）。

**Phase 2（safetensors パイプライン + バックエンド接続）実装済み**:
`safetensors_io`（mmap 読取・キー順保持の正準 Writer・原子入替）、
`znn_tensor`（テンソル単位 ZN ブロック）、`pipeline`（圧縮/解凍ジョブ =
完全性検証・進捗・キャンセル・paranoid モード）と、`mm_core` の
ポーリング型ジョブ API（`zipnn_compress` / `zipnn_decompress` /
`job_progress` / `job_cancel` / `job_result` / `job_error`、api_version=2）。
`py/compress.py` の単体圧縮/解凍ルートが `MM_NATIVE=0/1/auto` でこの経路に
切り替わります（ws イベント・stats 形状はレガシーと完全互換 — ゴールデン
テスト済み）。

## レイアウト

```
native/
├─ Cargo.toml                 # [workspace] resolver=2、共通 profile / lints
├─ Cargo.lock                 # ピン留め（コミット対象、Plan §7 R9）
├─ pyproject.toml             # maturin ビルド定義（wheel は開発・CI 検証用）
├─ .cargo/config.toml         # mold リンカー設定（Linux ネイティブビルドのみ）
├─ rustfmt.toml               # 安定オプションのみ（stable ツールチェーンが正）
├─ clippy.toml                # msrv + doc-valid-idents
├─ crates/
│  ├─ znn-codec/              # 純 Rust ZipNN コーデック（Python 非依存、Phase 1〜）
│  ├─ mm-core/                # PyO3 拡張モジュール `mm_core`（abi3-py310）
│  └─ znn-cli/                # 検証用 CLI（配布しない）
├─ benches/
│  └─ json-bench/             # JSON パーサ選定ベンチ（配布しない、Phase 0）
└─ native-bin/                # 配布用プリビルド成果物（native-bin/README.md 参照）
```

## 方針（Plan §3.3/§3.4 の実装対応）

- **edition 2024 / resolver 2**、`rust-version = "1.85"`（edition 2024 の下限。
  PyO3 の MSRV は 1.83 で、clippy.toml の msrv は Cargo.toml と揃えて 1.85）。
- **abi3-py310**: 1 バイナリで CPython 3.10 以降をカバー（リポジトリの
  `requires-python >= 3.10` と整合）。
- **`panic = "unwind"` 固定**（release profile）: パニックは PyO3 境界で捕捉され
  Python 例外になる。`abort` は ComfyUI プロセスを殺すため禁止。
- **lint**: `clippy::pedantic = warn`（CI は `-D warnings` なので実質 deny）、
  `unsafe_code = deny` + `unsafe_op_in_unsafe_fn = deny` +
  `undocumented_unsafe_blocks = deny`。将来 unsafe を導入する場合は
  `// SAFETY:` コメント必須（レビュー規則、Plan §3.4.2）。
- **サイズ予算**: release profile（`lto = "fat"` / `codegen-units = 1` / `strip`）で
  1 バイナリ ≤ 4 MB（CI ゲート）。Phase 0 の hello world 実測は 0.4 MB 前後。

## ローカル開発環境の導入

### 1. Rust ツールチェーン（全 OS 共通）

```bash
rustup toolchain install stable   # rustfmt / clippy コンポーネント込み
```

### 2. mold リンカー（Linux ネイティブビルドのみ、Plan §3.4.1）

`.cargo/config.toml` が Linux ターゲットのネイティブビルドに
`clang` + `-fuse-ld=mold` を設定します。クロスビルド（cargo-zigbuild）は
zig 側 LLD を使うため mold の影響を受けません（ビルドは成功し、成果物の
glibc 下限も zig が決定します。zig 由来の無害な
`ignoring deprecated linker optimization setting` 警告が出ることがあります）。

```bash
# Ubuntu 24.04 / Debian 12+
sudo apt-get install -y clang mold
# mold パッケージが ld.mold を PATH に提供しない場合:
sudo ln -sf "$(command -v mold)" /usr/local/bin/ld.mold
```

**clang が使えない環境でのフォールバック**: `.cargo/config.toml` の
`linker = "clang"` を外し（または一時的にファイルを退避し）、gcc で
`-B` 方式を使います:

```bash
RUSTFLAGS="-C link-arg=-B/usr/lib/mold" cargo build --release
```

macOS（ld‑prime）と Windows（link.exe）はプラットフォーム既定リンカーを
使用します（mold は ELF 専用）。

### 3. クロスビルド用（Linux ホストから glibc 2.28 ターゲット）

```bash
pip install cargo-zigbuild==0.23.4 ziglang==0.16.0
rustup target add aarch64-unknown-linux-gnu x86_64-unknown-linux-gnu
```

### 4. maturin（wheel ビルド / ローカル install / macOS・Windows 成果物）

```bash
pip install maturin==1.15.0
cd native
maturin build --release            # -> native/target/wheels/*.whl
# macOS のみ: maturin build --release --target universal2
```

## コマンド早見表

リポジトリルートから（package.json の `rs:*` スクリプト、既存 `py:*` と同型）:

| コマンド            | 内容                                                                   |
| ------------------- | ---------------------------------------------------------------------- |
| `pnpm rs:fmt`       | `cargo fmt --all`（native/ 内で実行）                                  |
| `pnpm rs:fmt:check` | `cargo fmt --all -- --check`                                           |
| `pnpm rs:lint`      | `cargo clippy --workspace --all-targets --all-features -- -D warnings` |
| `pnpm rs:test`      | `cargo test`（mm-core は libpython 連携のため下記参照）                |
| `pnpm rs:build`     | `cargo build --release -p mm-core`（ホストターゲット）                 |

`mm-core` のユニットテストは **extension-module なし**でリンクする必要があります
（cdylib 成果物は libpython を意図的にリンクしないため）:

```bash
cd native
cargo test --workspace --exclude mm-core
cargo test -p mm-core --no-default-features   # Python 開発ヘッダ/共有ライブラリが必要
```

## 配布成果物のビルド（native-bin/）

```bash
scripts/build-native.sh --target linux-x86_64 --size-gate
scripts/build-native.sh --target linux-aarch64 --size-gate
scripts/build-native.sh --target macos-universal2 --size-gate   # macOS ホスト
scripts/build-native.sh --target windows-x86_64 --size-gate     # Windows ホスト
```

ビルド成果物の検査（arch / glibc 下限 / libpython 非依存 / Mach‑O fat / PE）は、
readelf・lipo 等の無い環境でも
`python3 scripts/verify_native_binary.py <tag> <file> [--glibc-floor 2.28]`
（純 Python の ELF/Mach‑O/PE パーサ — CI の glibc ゲートと同一判定）で可能です。

### 検証状況（Phase 0 完了、2026‑09‑23、native.yml @ 81854f5 全ジョブ緑）

| ターゲット            | ビルド経路                          | 検証結果                                                                   |
| --------------------- | ----------------------------------- | -------------------------------------------------------------------------- |
| linux-x86_64          | cargo zigbuild（glibc 2.28 下限）   | ローカル + CI 緑。import 疎通: CPython **3.10 / 3.11 / 3.13**（410,416 B） |
| linux-aarch64         | cargo zigbuild（glibc 2.28 下限）   | ローカル（readelf で AArch64 + GLIBC≤2.28 確認）+ CI 緑（383,824 B）       |
| windows-x86_64 (MSVC) | maturin（windows-latest）           | CI 緑。import 疎通: CPython 3.11（163,840 B、`mm_core.pyd`）               |
| macos-universal2      | maturin universal2 = 両 arch + lipo | CI 緑。lipo: x86_64+arm64、import 疎通: CPython 3.11 arm64（666,032 B）    |

fmt / clippy `-D warnings` / test は 3 OS すべてで緑（native-test ジョブ。
mm-core のユニットテストは libpython をリンクできる Linux / Windows で実行、
macOS は setup-python 配布にリンク可能な libpython が無いため対象外 —
macOS の mm-core は clippy --all-targets とビルド&import 疎通が担保する）。

**Linux ホストからの Apple ターゲット クロスビルドは行いません**（実測で確認した
構造的障害: rustc が macOS cdylib に渡す `-Wl,-exported_symbols_list` と pyo3 の
`-undefined dynamic_lookup` の引数形を zig cc が誤変換する。zig 0.15.2 / 0.16.0、
cargo-zigbuild 0.23.4 で確認）。Plan §3.3 の通り macOS 成果物は macOS 上でビルドします。
参考: `x86_64-pc-windows-gnu`（zig）はコードのクロスコンパイル疎通確認には使えますが、
配布物は MSVC ビルド（`mm_core.pyd`）です。

## Phase 1: znn-codec フォーマット中核

### モジュール構成（`crates/znn-codec/src/`）

| モジュール     | 内容                                                                       |
| -------------- | -------------------------------------------------------------------------- |
| `header.rs`    | ZN ヘッダー 32B + packed shape（付録 B.1。敵対的入力の検証込み）           |
| `dtype.rs`     | dtype コード ↔ 平面スキーム表（互換帯。拡張帯 128–255 は Phase 4）         |
| `reorder.rs`   | f32/bf16/f64 の符号・指数ビット並べ替えと逆変換（proptest で全単射を固定） |
| `planes.rs`    | N=1,2,4 平面分割/結合。**C の in-bounds レイアウトとバイト一致**、端数網羅 |
| `bitstream.rs` | FSE/huff0 の後方読みビットリーダー / 前方書きビットライタ（C ミラー）      |
| `fse.rs`       | FSE 正規化カウント表の復号 + 符号（重みテーブル用。C とバイト同一）        |
| `huf/`         | huff0（RFC 8878 §4.2）: 重みヘッダー両経路・X2 デコード・4X エンコード     |
| `codec.rs`     | `zipnn_core`/`combine_dtype` 等価層（チャンク並列 = rayon 専用プール、閾値 |
|                | 0.95、chunkTypes/cumSizes レイアウト）。C が検証しない敵対的ペイロード検証 |

**Phase 2 追加**（同ディレクトリ）:

| モジュール          | 内容                                                                                                                                                                                                                                                                                                                                                       |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `safetensors_io.rs` | コンテナ parse（jiter・JSON 順保持・参照実装 0.8.0 の検証規則を逐条ミラー）+ 正準 Writer（safetensors-rust とバイト同一の再シリアライズ）+ `AtomicWriter`（`.tmp` → fsync → 検証 → rename → 親 dir fsync、インライン SHA-256 対応）                                                                                                                        |
| `znn_tensor.rs`     | テンソル単位 ZN ブロックの生成/復号 + 互換帯 dtype 表（safetensors dtype ↔ ZN コード ↔ torch 名）。fp8 のチャンククランプ（byte14=18 だが実チャンク 128KiB — zipnn.py のクセ）を両方向で再現                                                                                                                                                               |
| `pipeline.rs`       | `compress_file` / `decompress_file`（Plan §4.3/§4.4.3）: mmap ストリーミング（ピーク RAM = O(最大テンソル)）、ワーストケース H_max ヘッダー予約による**単一書き込みパス**、原本 SHA-256 の並行算出、`znn_neo_src_sha256`/`znn_neo_exact` 記録、解凍時の既定検証（不一致時は圧縮ファイルを保持し復元物を `.corrupt` 退避）、paranoid モード、協調キャンセル |

正しい実装の根拠は vendored C ソース（`third_party/zipnn-core/`）と
safetensors 0.8.0 Rust 実装（一次ソース精読、2026‑09‑24）の逐条移植で、
出力バイトは L2 ゴールデン差分（下記）が C プリビルド .so と照合します。
**unsafe はフォーマット中核（Phase 1 範囲）でゼロ**。Phase 2 の追加は
`safetensors_io::StContainer::open` の **read-only mmap 1 箇所のみ**
（memmap2 の安全境界。SAFETY コメント付きでレビュー済み — Plan §3.7 が
選定したゼロコピー設計そのもので、置き換え対象の Python `safe_open` も
同一の mmap 方式。crate の `#![deny(unsafe_code)]` は維持し、当該関数に
局所 `#[allow]` + SAFETY ブロックを付す形）。

### znn-cli（配布しない開発ツール）

```bash
cargo build --release -p znn-cli
znn-cli identity                       # 定数レポート
znn-cli core-compress  IN OUT --num-buf 4 --bits 1 --mode 220 --chunk 262144
znn-cli core-decompress PAYLOAD OUT --orig-len N [--max-output CAP] ...
znn-cli bench IN --op both --runs 5    # steal ゲート付き in-process 計測
znn-cli batch MANIFEST.jsonl RESULTS.jsonl   # L2 ハーネス用バッチ実行
# Phase 2: Python を介さない safetensors パイプライン（手動 QA / bench）
znn-cli st-compress  model.safetensors model.znn.safetensors [--paranoid] [--json-out R.json]
znn-cli st-decompress model.znn.safetensors restored.safetensors [--json-out R.json]
```

`core-*` は C ABI（`zipnn_core` / `combine_dtype`）の完全ミラーです
（`is_review` / `check_th_after_percent` は C 側でも出力に影響しないため
受け入れ・無視。ヘッダー [24:32] への resBufSize 書き込みも C 準拠）。

### L2 ゴールデン差分テスト（`scripts/l2/golden_diff.py`）

C プリビルド .so（`third_party/zipnn-core-bin/linux-x86_64/`、要 Linux x86_64 +
CPython 3.11）をゴールデン生成器に、Rust 出力と**バイト単位**で照合します:

```bash
python3 scripts/l2/golden_diff.py                 # フル 10,500 ケース
python3 scripts/l2/golden_diff.py --quick         # CI ゲート（~1,200）
python3 scripts/l2/golden_diff.py --skip-suite --speed   # 圧縮率/速度ゲート
```

- ケース = 長さクラス（0–9 / チャンク境界 ± / 乱数 / 多チャンク）× エントロピ
  8 種 × パラメータ 8 組。C が SEGFAULT する付録 C クラス（4 平面・最終チャンク
  1–3B）は **Rust 側のみ**実行し「エラーか正常動作」を要求（C には渡さない —
  ドライバプロセスが死ぬため。Phase 0 の `bench_c_defects.py` が C 側判定を記録済み）。
- C の**文書化済み UB 形状**（端数チャンクの 1–3B ヒープオーバーフロー書き込み）
  は fork 隔离子プロセスでゴールデン生成（親プロセスのヒープ汚染防止。golden は
  abort 前に fsync 済み）。
- 結果 JSON は `scripts/l2/results/` にコミット（証跡）。

### L3 ファジング（cargo-fuzz）

```bash
rustup toolchain install nightly && rustup component add rust-src --toolchain nightly
# cargo-fuzz 0.12.0 を PATH へ（0.13.x は musl デフォルトで musl-g++ を要求するため
# gnu ターゲット明示の 0.12.0 をピン留め — CI と同一）
cd native/crates/znn-codec/fuzz
cargo +nightly fuzz build -D --target x86_64-unknown-linux-gnu
cargo +nightly fuzz run huf_decompress   --target x86_64-unknown-linux-gnu -- -max_total_time=300
cargo +nightly fuzz run zn_header        --target x86_64-unknown-linux-gnu -- -max_total_time=300
cargo +nightly fuzz run codec_decompress --target x86_64-unknown-linux-gnu -- -max_total_time=300
cargo +nightly fuzz run st_parse         --target x86_64-unknown-linux-gnu -- -max_total_time=300
cargo +nightly fuzz run blob_decompress  --target x86_64-unknown-linux-gnu -- -max_total_time=300
```

- ターゲット 5 種: `huf_decompress`（敵対的 huff0 ブロック）/ `zn_header`
  （ヘッダー + packed shape、encode∘decode 正規形不変条件）/ `codec_decompress`
  （ペイロード + パラメータ全体、出力キャップ付き）/ **Phase 2 追加**:
  `st_parse`（敵対的 safetensors コンテナ + 正準再構築の不変条件:
  「canonical フラグ ⇔ 再シリアライズが原本とバイト同一」）/
  `blob_decompress`（敵対的テンソル ZN ブロック、**割り当てキャップ付き** —
  整合的な嘘 original_len による OOM 殺人を Err に変える §4.4.2 の要件）。
- シードコーパスは実物コンテナ/ブロック/ヘッダー（`fuzz/corpus/`、コミット済み）。
  Phase 1 開発中にファザーが発見した実バグ 3 件（ヘッダー正規形 1 + 整数オーバー
  フロー 2）は修正済みで、クラッシュ入力は回帰シードとしてコーパスに追加済み。
- ≥8h の本格バジェットは PR ゲートではなく `fuzz-long.yml`（週次スケジュール +
  手動ディスパッチ、3 ターゲット並列 × 3h = 9h）で消化します（Plan §5.1 L3）。
- ローカル 1GiB メモリ環境では release+ASan ビルドが OOM するため `-D`（dev）を
  使用。CI（7GiB+）は release（`-O`）で実行。
