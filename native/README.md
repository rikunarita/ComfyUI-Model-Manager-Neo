# `native/` — Rust ネイティブコア ワークスペース

ComfyUI‑Model‑Manager‑Neo の中核処理を Rust へ移行するワークスペースです。

**Phase 1（znn-codec フォーマット中核）実装済み**: `znn-codec` クレートが
ZN ヘッダー・ビット並べ替え・平面分割・huff0/FSE（RFC 8878）・チャンク並列
codec を純 Rust で提供し、vendored C コアと**バイト同一の圧縮出力**を生成
します（L2 ゴールデン差分 9,880/9,880 一致）。

**Phase 2（safetensors パイプライン + バックエンド接続）実装済み**:
`safetensors_io`（mmap 読取・キー順保持の正準 Writer・原子入替）、
`znn_tensor`（テンソル単位 ZN ブロック）、`pipeline`（圧縮/解凍ジョブ =
完全性検証・進捗・キャンセル・paranoid モード）と、`mm_core` の
ポーリング型ジョブ API（`zipnn_compress` / `zipnn_decompress` /
`job_progress` / `job_cancel` / `job_result` / `job_error`）。
`py/compress.py` の単体圧縮/解凍ルートがこの経路を駆動します（ws イベント・
stats 形状はゴールデンテストで機械固定。Phase 8 以降、これが唯一の経路です）。

**Phase 3（デルタ圧縮 + バッチプリミティブ）実装済み**（api_version=**3**）:
`delta`（両側 mmap → ヘッダー等長化パディング → 1 MiB ストリーミング XOR →
公式 streaming コンテナ連鎖。ピーク RAM = O(チャンク)、`.neo-delta.json`
サイドカーへ `ftSha256` を記録し復元時にインライン検証、legacy 単一
コンテナ形式も復元可、エラー文言は UI 契約として逐語互換）と `batch`
（`walk_models` 並列 walk = os.walk 意味論の忠実移植、
`move_with_sidecars` = 20 スロット プレビュー/ノート規則の移植。バンドル
意味論は Python 側維持）。`mm_core` 追加 API: `zipnn_delta_compress` /
`zipnn_delta_decompress`（ジョブ）+ `walk_models` / `move_with_sidecars`
（同期）。デルタ/バッチフォルダ ルートもこの経路を駆動します
（付録 C の SEGFAULT クラスはデルタ端到端テストで「正常完了 + byte‑exact」
に固定化 — docs/BENCH.md §8）。L3 ファズに `delta_decompress` を追加
（現行 7 ターゲット — 下記 L3 節）。

**Phase 4（dtype 大幅拡張 — Neo 拡張帯）実装済み**（api_version は **3 の
まま** — 新規 Python API なし、dtype 対応はコーデック内部）:
`safetensors 0.8 の全 22 dtype` を圧縮（K14 達成 — docs/BENCH.md §9）。
8 平面分割/結合（f64 並べ替え融合、`MODE_8PLANES = 88`）、Neo 拡張帯
コード表 128–146（`dtype.rs`）、トランケーション モード 1/9/41/8 の
Neo クリーン正式実装（ゼロ統計自動選択 `select_truncation`・落とし平面は
空 raw チャンク + 復元 0 埋め・構造的に可逆）、sub‑byte（F4/F6）の bits
基準 shape 検証、帯別 byte5 厳格ゲート（互換帯ブロブは正準モードのみ）。
公式 zipnn 0.5.4 は拡張帯ブロブを `ValueError: Unsupported Dtype N` で
明示拒否（scripts/l5 セクション E が pip 実ビルド against で固定）。
**complex128/bcomplex32（code 129/131）は codec 級のみ** — safetensors 0.8
表現が存在しないため、パイプラインの復元は明示エラーで拒否します。

**Phase 5（スキャン / インデックス / ハッシュ / ヘッダー）実装済み**
（api_version=**4**）: `py/manager.py` のライブラリスキャンと
`py/identify.py` のハッシュ、`py/utils.py` の safetensors ヘッダー解析、
`py/download.py` のダウンロード検証を Rust 化（docs/BENCH.md §10 = K7–K11
の証跡）。新モジュール:

- `scan.rs` — `scan_models`（std::fs + rayon の自前並列 walk。`os.scandir`
  意味論の忠実移植: dir symlink 追従 + canonical visited ガード、hidden を
  name set に残す、拡張子大文字小文字区別、20 スロット preview 解決、
  front-matter 4 値、`round(st_ctime_ns/1e6)` を `f64::round_ties_even` で
  Python とビット一致）+ `scan_hygiene`（`os.walk(followlinks=False)` =
  orphan サイドカー + empty フォルダ）。JSON 形状は現行ルートと厳密一致
  （golden parity = `tests/test_phase5_scan.py`）。
- `index.rs` — 永続 front-matter インデックス（bincode 2.0.1 スナップショット
  - blake3 チェックサム + 原子入替 + 破損時自動全再構築 = 常に派生データ）。
    `(path, mtime_ns, size)` → 4 値。`_SITE_CACHE` のプロセス内限界を解消し
    再起動を跨ぐ（K10）。
- `hash.rs` — `MultiHasher`（SHA256 + AutoV1 窓 + AutoV2 + CRC32 バイト反転
  - BLAKE3 を 1 パス、K8）+ `hash_file` + インクリメンタル API
    （`hasher_new/update/finalize` = download インライン検証、K7）。Civitai
    表記は Python 定義とバイト一致で golden 固定。
- `safetensors_io.rs::header_display_json` — ヘッダ専用 jiter 解析（データ
  領域無検証・B4 32 MiB 統一ガード・`{metadata, tensors}` processed JSON）。
  **重複テンソル名検査を HashMap O(1) 化**（旧 O(n²) は 64k テンソル MoE
  ヘッダで 6 s の重大退行 → 212 ms。compress パイプラインも共有経路で高速化）。

mm-core（`phase5.rs`）が `scan_models` / `scan_hygiene` / `safetensors_header`
/ `hash_file` / `hasher_*` / `phase5_diagnostics` を公開（同期・`py.detach()`
で GIL 解放 = 不変条件 2）。SiteIndex のグローバル レジストリ（indexDir 単位）
とハッシャ レジストリ（cap 4096）を保持。**任意項目 A3（requests→aiohttp）と
watch_roots は Phase 6 へ移管**（2026‑09‑27 ユーザ決定。A3 は aiohttp 統一の
まま **Rust 化しない**〔reqwest 不採用〕、watch_roots は
notify + notify-debouncer-full **直接採用**〔extended-notify 不導入〕。
見送り根拠の記録は BENCH §10.5）→ **両方とも Phase 6 で実施済み**。

**Phase 6（テンソルツリー事前グループ化 + ファイル監視）実装済み**
（api_version=**5**、docs/BENCH.md §11 = K15 の証跡）:

- `safetensors_io.rs::encode_tensor_tree` / `tensor_tree_json` — 表示用
  テンソルツリーを Rust で折りたたみ、**pre-order の線形符号**
  `{"v":1,"nodes":[[segment,childCount,tensorCount,totalCount,totalParams],…],
"leaves":[tensorIndex,…]}` で返す（leaf は `header_display_json` の
  `tensors` を index で指す = 二重転送なし。own-leaves-before-children なので
  デコード側はカーソル 1 本）。65,268 テンソル MoE でブラウザ内 fold
  **1,329 ms → 12.8 ms（×104）**。ヘッダ読みは `read_header_region` へ抽出し
  `header_display_json` と共有（同一 B4 32 MiB キャップ・同一 parse 順）。
  深さ爆発（敵対的な多段ドット名）に備え**再帰ではなく明示スタック**。
- `watch.rs`（`watch` feature）— notify 8.2.0 + notify-debouncer-full 0.7.0
  **直接採用**（extended-notify 不導入）。500 ms デバウンス、
  **ポーリング方式**（notify スレッドは GIL を取らず、重複排除済みの
  パス集合へ追記するだけ = ジョブ API と同一哲学）、`ErrorKind::MaxFilesWatch`
  は `degraded` 理由として報告（Python 側が TTL へ degrade）、
  `Event::need_rescan` は full invalidation、Access イベントは除外。
  **`watch` feature は default-on**: 同梱プリビルドが `watch_*` を持たなければ
  設定が永久に動かないため（OFF なのは実行時の設定の方）。サイズ実測
  linux-x86_64 release **4,110,816 B = 予算 5 MB の 78 %**（2026-09-29 T7 zenwebp 込み・目安は同日 4→5 MB 改定）。
- mm-core（`phase6.rs`）— `safetensors_tensor_tree` / `watch_start` /
  `watch_poll` / `watch_stop` / `watch_diagnostics` を公開。Python 側の駆動は
  `py/watcher.py`（asyncio タスク 1 本・1 s ポーリング・network root 自動
  スキップ・type 単位クールダウン）、表示側の消費は `src/utils/tensorTree.ts`
  （遅延インデックス + JS フォールバック エンコーダ）。
- `index.rs` に **entry 上限**（`MAX_ENTRIES = 262_144`、超過時は任意の半分を
  prune）— 派生データなので miss は再パースのみ（Python 側 `_SITE_CACHE` の
  4096 上限と同じ発想。削除済みサイドカーの entry が永遠に残る成長を止める）。

## テスト配置と cargo ワークフロー

- **単体テスト**: 各 `src/*.rs` のインライン `#[cfg(test)]`（private API に
  触るため — Rust 慣行。`delta` のみ `src/delta/tests.rs` へ分割）。
- **統合テスト（公開 API の端到端）**: `crates/znn-codec/tests/`
  （`extended_band.rs` = Phase 4 の K14 ゲートをクレート級で固定）。
- **開発ループ**: `cargo check` 常用 → 必要なときだけ `cargo test` →
  品質ポイントで `cargo fmt` + `cargo clippy -D warnings` →
  `cargo build`（release / build-native.sh）は最終確認時のみ。

## レイアウト

```
native/
├─ Cargo.toml                 # [workspace] resolver=2、共通 profile / lints
├─ Cargo.lock                 # ピン留め（コミット対象）
├─ pyproject.toml             # maturin ビルド定義（wheel は開発・CI 検証用）
├─ .cargo/config.toml         # リンカー方針の記録（rust-lld 既定・target 節は空）
├─ rustfmt.toml               # 安定オプションのみ（stable ツールチェーンが正）
├─ clippy.toml                # msrv + doc-valid-idents
├─ crates/
│  ├─ znn-codec/              # 純 Rust ZipNN コーデック（Python 非依存。
│  │                          #   src/ インライン単体 + tests/ 統合 + fuzz/ L3）
│  └─ mm-core/                # PyO3 拡張モジュール `mm_core`（abi3-py312）
└─ native-bin/                # 配布用プリビルド成果物（native-bin/README.md 参照）
```

## 方針

- **edition 2024 / resolver 2**、`rust-version = "1.85"`（edition 2024 の下限。
  PyO3 の MSRV は 1.83 で、clippy.toml の msrv は Cargo.toml と揃えて 1.85）。
- **abi3-py312**: 1 バイナリで CPython 3.12 以降をカバー（リポジトリの
  `requires-python >= 3.12` と整合。2026‑10 に floor を 3.10 → 3.12 へ
  引き上げ — CPython 3.10 は 2026‑10‑01 に EOL 到達済み・ComfyUI の文書化
  サポート下限が 3.12）。
- **abi3t-py315（`ft` feature）**: フリースレッド CPython
  3.15+ 向けの `<tag>t` 成果物（PEP 803 — 安定 ABI のフリースレッド版）。
  `stable-abi` とは**排他**でビルドする（同時有効化は成果物フレーバをホスト依存に
  するため — native‑test の toggle ゲートが cargo metadata から機械禁止）。
  ビルド host は Python ≥ 3.15 が必要（PyO3 host ≥ target 制約。CI は
  3.15.0‑rc.2 ピン、final 着弾後は表記のみ別コミット振替）。
  成果物は 3.15+ の **t / GIL 両 build** がロード可能（逆にフリースレッド build は
  通常の abi3 成果物をロードできない — ローダーが `<tag>t` だけを渡す理由）。
- **feature 構成**（mm‑core）: `default = ["extension-module", "stable-abi"]` /
  `stable-abi = ["pyo3/abi3-py312"]` / `ft = ["pyo3/abi3t-py315"]`。
  `--no-default-features` は extension-module と stable‑ABI の両方を外す
  （ユニットテスト用 = version‑specific libpython リンク）。ft 成果物のビルドは
  `--no-default-features --features extension-module,ft`（zigbuild 経路）または
  `--no-default-features --features ft`（maturin 経路 — tool.maturin の features が
  `pyo3/extension-module` を常に付与するため）。
- **`panic = "unwind"` 固定**（release profile）: パニックは PyO3 境界で捕捉され
  Python 例外になる。`abort` は ComfyUI プロセスを殺すため禁止。
- **lint**: `clippy::pedantic = warn`（CI は `-D warnings` なので実質 deny）、
  `unsafe_code = deny` + `unsafe_op_in_unsafe_fn = deny` +
  `undocumented_unsafe_blocks = deny`。将来 unsafe を導入する場合は
  `// SAFETY:` コメント必須（レビュー規則）。
- **サイズ予算**: release profile（`lto = "fat"` / `codegen-units = 1` / `strip`）で
  1 バイナリ ≤ 5 MB（CI ゲート・目安）。Phase 0 の hello world 実測は 0.4 MB 前後。

## ローカル開発環境の導入

### 1. Rust ツールチェーン（全 OS 共通）

```bash
rustup toolchain install stable   # rustfmt / clippy コンポーネント込み
```

### 2. リンカー（rust‑lld 既定 — 追加インストール不要）

Linux ネイティブビルドは **rustc 同梱の rust‑lld** を使います
（Rust 1.90 以降、`x86_64-unknown-linux-gnu` の既定リンカー）。
旧 mold 設定（`.cargo/config.toml` の `linker = "clang"` +
`-fuse-ld=mold`）は 2026‑10‑01 に撤去しました — インストール手順は
もう何もありません（CI の apt ステップも撤去済み。2026‑09‑30 の
ミラーハング事故の障害面そのものが消滅しました）。

- **aarch64 ネイティブ開発ビルド**: rust‑lld はまだ既定でないため、
  システム既定リンカーが使われます。lld を明示したい場合のみ
  `RUSTFLAGS="-C linker-features=+lld"` を各自で（配布成果物は
  zigbuild 経路なので影響しません）。
- **クロスビルド（cargo‑zigbuild）**: zig 側 LLD が使われ、成果物の
  glibc 下限（2.28）も zig が決定します。zig 由来の無害な
  `ignoring deprecated linker optimization setting` 警告が出ることがあります。
- **macOS（ld‑prime）と Windows（link.exe）**はプラットフォーム既定
  リンカーを使用します。
- **fuzz（nightly・別ワークスペース）**: cargo の config 探索で
  `native/.cargo/config.toml` を拾いますが、target 節が無いため
  nightly 既定の rust‑lld が使われます（ASan ランタイムは rustc が
  compiler‑rt を同梱するためリンカーに依存しません）。

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

# abi3t（<tag>t — フリースレッド CPython 3.15+・PEP 803）。
# 条件: Python >= 3.15 のホスト解釈系（GIL build で可）・非 PGO:
scripts/build-native.sh --target linux-x86_64t --size-gate
scripts/build-native.sh --target linux-aarch64t --size-gate
scripts/build-native.sh --target macos-universal2t --size-gate   # macOS ホスト
scripts/build-native.sh --target windows-x86_64t --size-gate     # Windows ホスト

# PGO 版（下記「PGO」節参照）:
scripts/build-native.sh --target linux-x86_64 --size-gate --pgo /path/merged.profdata
scripts/build-native.sh --target windows-x86_64 --size-gate --pgo-train  # maturin --pgo（Windows）
# macOS universal2 は非 PGO 出荷（run #107 実証による判断 (c) — 下記 PGO 節）
```

## PGO（プロファイル誘導最適化）

配布バイナリの実行時最適化として、計装ベースの PGO が **linux-x86_64 /
Windows の出荷ビルドに組み込み済み**です（macOS universal2 と
linux-aarch64 は対象外 — 下記。計画・ゲート・不採用技術の根拠を
記録した計画文書は完了に伴いツリーから削除されました — git 履歴から
復元できます）。

- **トレーナ**: [`scripts/pgo/train.py`](../scripts/pgo/train.py) —
  stdlib + mm_core + tests/harness のみの決定論的ワークロード
  （圧縮/解凍/デルタ/スキャン/ハッシュ/ヘッダ/テンソルツリー/WebP の
  全 API 表面）。計装ビルドに対して実行すると `.profraw` を生成します。
  使い方とローカル再現手順は [`scripts/pgo/README.md`](../scripts/pgo/README.md)。
- **Linux x86_64**: `native-build-linux` ジョブが出荷ビルド毎に
  計装ビルド（ホスト native）→ train → `llvm-profdata merge`
  （`llvm-tools-preview` component）→ `build-native.sh --pgo <profdata>`
  （zigbuild + `-Cprofile-use` + `-Cllvm-args=-pgo-warn-missing-function`）
  の三段階を実行し、**恒久 G2 ゲート**（`scripts/pgo/g2_check.py`）で
  プロファイルの no-op 化を機械検出します。G2 のしきい値は run #106 の
  実測で再校正済み: fat-LTO + PGO インライナの良性乖離（計測値 13.81 % =
  ジェネリック実体化 518 + クロージャ 254 + 計装時完全インライン関数の
  アウトオブライン復元 485）は通過し、真の no-op（~100 %）・空プロファイル・
  別ワークスペース由来は失敗します。別途 `pgo-measure` ジョブ
  （workflow_dispatch / `[pgo-measure]` コミットマーカーで起動）が
  baseline との A/B 計測（steal ゲート・**側別中央値での判定** —
  min/best は参考並記。run #108 で min 判定のノイズ脆弱性を実証したため
  2026‑10‑02 の改訂 — BENCH §13.6）で G1（compress/decompress +3 %）を
  job summary へレポートします。
- **Windows**: ピン留めの maturin 1.15.0 が `--pgo` をネイティブ
  サポート（計装 wheel → 一時 venv で `pgo-command` 実行 → 最適化リビルド
  の三段階）。`pyproject.toml` の `pgo-command` が train.py を呼び、
  `build-native.sh --pgo-train` が `--pgo` を透過します。run #107/#108 で
  MSVC 経路の三段階が完走することを実走確認済みです
  （#108 出荷 = 3,738,624 B）。
- **macOS universal2 = 非 PGO（判断 (c)、run #107 で実証）**:
  maturin `--pgo` は計装 universal2 wheel のビルドとトレーニング実行には
  成功しましたが（train.py が全 30 セクション完走・"done in 5.612 s"）、
  **プロセス終了時のプロファイルランタイム書き出し段階で SIGSEGV** し、
  最適化リビルドに到達できませんでした。計装済み FAT dylib 特有の
  障害で、Windows（単一 arch PE）と Linux（単一 arch ELF・自前三段階）
  では再現しません。macOS ホスト無しではデバッグ不能（推測での修正は
  しない — 本ワークスペースの原則）のため、macOS は非 PGO 出荷とします。
  将来的な選択肢は arm64 単一 arch の PGO ビルド（要 upstream 修正待ち）。
  **run #108 で非 PGO 経路の緑を実走確認済み**（fat x86_64 + arm64・
  6,730,080 B・SIGSEGV 再現なし・2 分 41 秒）。
- **linux-aarch64 は PGO 対象外**: クロスコンパイルかつ ARM ランナーが
  無く、x86_64 プロファイルの流用は arch 非互換のため禁止。
- **プロファイルはコミットしません**: ビルド毎生成（ドリフトゼロ・
  肥大ゼロ）。

ビルド成果物の検査（arch / glibc 下限 / libpython 非依存 / Mach‑O fat / PE）は、
readelf・lipo 等の無い環境でも
`python3 scripts/verify_native_binary.py <tag> <file> [--glibc-floor 2.28]`
（純 Python の ELF/Mach‑O/PE パーサ — CI の glibc ゲートと同一判定）で可能です。

### 検証状況（Phase 0 完了、2026‑09‑23、native.yml @ 81854f5 全ジョブ緑）

| ターゲット            | ビルド経路                                                                          | 検証結果                                                                                                   |
| --------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| linux-x86_64          | cargo zigbuild（glibc 2.28 下限）                                                   | ローカル + CI 緑。import 疎通: CPython **3.10 / 3.11 / 3.13**（410,416 B）                                 |
| linux-aarch64         | cargo zigbuild（glibc 2.28 下限）                                                   | ローカル（readelf で AArch64 + GLIBC≤2.28 確認）+ CI 緑（383,824 B）                                       |
| windows-x86_64 (MSVC) | maturin（windows-latest）                                                           | CI 緑。import 疎通: CPython 3.11（163,840 B、`mm_core.pyd`）                                               |
| macos-universal2      | maturin universal2 = 両 arch + lipo                                                 | CI 緑。lipo: x86_64+arm64、import 疎通: CPython 3.11 arm64（666,032 B）                                    |
| linux-x86_64t         | cargo zigbuild `--no-default-features --features extension-module,ft`（非 PGO・D2） | CI 実走待ち（2026‑10‑03 実装。import 疎通 = 3.15.0‑rc.2 GIL + 3.15.0‑rc.2t の両フレーバ）                  |
| linux-aarch64t        | 同上（クロス・非 PGO）                                                              | CI 実走待ち                                                                                                |
| macos-universal2t     | maturin `--no-default-features --features ft` universal2（非 PGO）                  | CI 実走待ち（lipo + 両フレーバ import 疎通）                                                               |
| windows-x86_64t       | maturin `--no-default-features --features ft`（非 PGO）                             | CI 実走待ち（`mm_core.pyd` — PEP 803 も Windows の拡張子は変えない。GIL 版と `<tag>t` ディレクトリで分離） |

**2026‑10‑03 以降の検証マトリクス**: floor 3.12 化により
abi3 の CI 検証解釈系は **3.12 / 3.14**（上表 GIL 行の 3.10 / 3.11 / 3.13 は旧 floor
時代の実証史）。t 4 本の検証解釈系は **3.15.0‑rc.2（GIL）+ 3.15.0‑rc.2t
（フリースレッド）**— 各 build job の両フレーバ import スモーク + abi3‑import の
4 セル + integration の ubuntu t セル（フル pytest = フリースレッド soak、D3）。
D4: 3.15 final が runner manifest へ着弾したら `3.15` / `3.15t` 表記へ別コミットで
振替（ABI は rc1 で凍結済みのため成果物の再ビルドは不要）。

fmt / clippy `-D warnings` / test は 3 OS すべてで緑（native-test ジョブ。
mm-core のユニットテストは libpython をリンクできる Linux / Windows で実行、
macOS は setup-python 配布にリンク可能な libpython が無いため対象外 —
macOS の mm-core は clippy --all-targets とビルド&import 疎通が担保する）。

**Linux ホストからの Apple ターゲット クロスビルドは行いません**（実測で確認した
構造的障害: rustc が macOS cdylib に渡す `-Wl,-exported_symbols_list` と pyo3 の
`-undefined dynamic_lookup` の引数形を zig cc が誤変換する。zig 0.15.2 / 0.16.0、
cargo-zigbuild 0.23.4 で確認）。macOS 成果物は macOS 上でビルドします。
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

| モジュール          | 内容                                                                                                                                                                                                                                                                                                                                   |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `safetensors_io.rs` | コンテナ parse（jiter・JSON 順保持・参照実装 0.8.0 の検証規則を逐条ミラー）+ 正準 Writer（safetensors-rust とバイト同一の再シリアライズ）+ `AtomicWriter`（`.tmp` → fsync → 検証 → rename → 親 dir fsync、インライン SHA-256 対応）                                                                                                    |
| `znn_tensor.rs`     | テンソル単位 ZN ブロックの生成/復号 + 互換帯 dtype 表（safetensors dtype ↔ ZN コード ↔ torch 名）。fp8 のチャンククランプ（byte14=18 だが実チャンク 128KiB — zipnn.py のクセ）を両方向で再現                                                                                                                                           |
| `pipeline.rs`       | `compress_file` / `decompress_file`: mmap ストリーミング（ピーク RAM = O(最大テンソル)）、ワーストケース H_max ヘッダー予約による**単一書き込みパス**、原本 SHA-256 の並行算出、`znn_neo_src_sha256`/`znn_neo_exact` 記録、解凍時の既定検証（不一致時は圧縮ファイルを保持し復元物を `.corrupt` 退避）、paranoid モード、協調キャンセル |

正しい実装の根拠は旧 vendored C ソース（`third_party/zipnn-core/` — Phase 8 で
撤去。git 履歴で参照可）と safetensors 0.8.0 Rust 実装（一次ソース精読、
2026‑09‑24）の逐条移植で、出力バイトは移行期の L2 ゴールデン差分が C プリビルド
.so と**バイト単位で一致**することを実証済みです（9,880/9,880 — 証跡は
`scripts/bench/results/l2_golden_diff.json` にコミット。Phase 8 以降の公式互換の
機械証明は L5 クロス検証〔native.yml integration・pip zipnn 0.5.4〕が担います）。
**unsafe はフォーマット中核（Phase 1 範囲）でゼロ**。Phase 2 の追加は
`safetensors_io::StContainer::open` の **read-only mmap 1 箇所のみ**
（memmap2 の安全境界。SAFETY コメント付きでレビュー済み — 選定された
ゼロコピー設計そのもので、置き換え対象の Python `safe_open` も
同一の mmap 方式。crate の `#![deny(unsafe_code)]` は維持し、当該関数に
局所 `#[allow]` + SAFETY ブロックを付す形）。

### L2 ゴールデン差分テスト（移行期ゲート — Phase 8 で退役）

移行期（Phase 1–7）は C プリビルド .so（`third_party/zipnn-core-bin/`）を
ゴールデン生成器に、Rust 出力と**バイト単位**で照合する L2 差分ゲート
（`scripts/l2/golden_diff.py`・フル 10,500 ケース）を CI（native-diff ジョブ +
fuzz-long の l2-full コンパニオン）で常設していました。Phase 8 の
`third_party/` 撤去とともに**退役**済みです:

- 証跡 JSON は `scripts/bench/results/l2_golden_diff.json` / `l2_speed.json` に
  コミット済み（フル 10,500 ケース GATE PASS・圧縮出力 C とバイト同一
  9,880/9,880・付録 C クラス 495/495 安全処理）。スクリプト本体
  （`golden_diff.py`）と駆動用の `znn-cli batch` は git 履歴から復元できます
  （`znn-cli` クレート自体も計画完了後の整理でワークスペースから削除済み）。
- 退役後の公式 ZipNN 互換の機械証明は **L5 クロス検証**（native.yml
  integration・ubuntu セル）: pip の**公式 zipnn 0.5.4** をランナーで
  ソースビルドし、「Neo(Rust) 圧縮 → 公式解凍」「公式圧縮 → Neo 解凍」+
  テンソルブロブ parity を毎 push で実行します（`scripts/l5/official_cross.py`）。

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
cargo +nightly fuzz run delta_decompress --target x86_64-unknown-linux-gnu -- -max_total_time=300
cargo +nightly fuzz run webp_decode      --target x86_64-unknown-linux-gnu -- -max_total_time=300
```

- ターゲット 7 種: `huf_decompress`（敵対的 huff0 ブロック）/ `zn_header`
  （ヘッダー + packed shape、encode∘decode 正規形不変条件）/ `codec_decompress`
  （ペイロード + パラメータ全体、出力キャップ付き）/ **Phase 2 追加**:
  `st_parse`（敵対的 safetensors コンテナ + 正準再構築の不変条件:
  「canonical フラグ ⇔ 再シリアライズが原本とバイト同一」）/
  `blob_decompress`（敵対的テンソル ZN ブロック、**割り当てキャップ付き** —
  整合的な嘘 original_len による OOM 殺人を Err に変える要件）/
  **Phase 3 追加**: `delta_decompress`（敵対的デルタ連鎖）/ **Phase 7 追加**:
  `webp_decode`（敵対的 WebP → zenwebp デコード経路、canvas 事前ガード）。
- シードコーパスは実物コンテナ/ブロック/ヘッダー（`fuzz/corpus/`、コミット済み）。
  Phase 1 開発中にファザーが発見した実バグ 3 件（ヘッダー正規形 1 + 整数オーバー
  フロー 2）は修正済みで、クラッシュ入力は回帰シードとしてコーパスに追加済み。
- ≥8h の本格バジェットは PR ゲートではなく `fuzz-long.yml`（週次スケジュール +
  手動ディスパッチ、7 ターゲット並列 × 3h = 21h）で消化します。
- ローカル 1GiB メモリ環境では release+ASan ビルドが OOM するため `-D`（dev）を
  使用。CI（7GiB+）は release（`-O`）で実行。
