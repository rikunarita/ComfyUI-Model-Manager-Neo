# `native/` — Rust ネイティブコア ワークスペース

ComfyUI‑Model‑Manager‑Neo の中核処理を Rust へ移行するワークスペースです
（設計・フェーズ計画は [`Agent/Plan.md`](../Agent/Plan.md) を参照）。
**Phase 0 の現状は雛形**で、`mm_core` は可用性・版数 API
（`api_version()` / `core_version()`）のみを提供します。圧縮・スキャン・
ハッシュの実装は Phase 1 以降でこのワークスペースに追加されます。

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

### 検証状況（Phase 0、2026‑09‑23）

| ターゲット            | ビルド経路                          | 検証                             |
| --------------------- | ----------------------------------- | -------------------------------- |
| linux-x86_64          | cargo zigbuild（glibc 2.28 下限）   | ローカル + CI（import 疎通済み） |
| linux-aarch64         | cargo zigbuild（glibc 2.28 下限）   | ローカル（ELF/glibc 確認）+ CI   |
| windows-x86_64 (MSVC) | maturin（Windows ホスト）           | CI（windows-latest）             |
| macos-universal2      | maturin universal2 = 両 arch + lipo | CI（macos-latest）               |

**Linux ホストからの Apple ターゲット クロスビルドは行いません**（実測で確認した
構造的障害: rustc が macOS cdylib に渡す `-Wl,-exported_symbols_list` と pyo3 の
`-undefined dynamic_lookup` の引数形を zig cc が誤変換する。zig 0.15.2 / 0.16.0、
cargo-zigbuild 0.23.4 で確認）。Plan §3.3 の通り macOS 成果物は macOS 上でビルドします。
参考: `x86_64-pc-windows-gnu`（zig）はコードのクロスコンパイル疎通確認には使えますが、
配布物は MSVC ビルド（`mm_core.pyd`）です。
