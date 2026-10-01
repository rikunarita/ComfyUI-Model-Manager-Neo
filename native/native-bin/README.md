# `native-bin/` — 配布用プリビルド ネイティブコア（唯一の供給経路）

`py/native.py` が **sys.path に追加して import するだけ** のプリビルド
`mm_core` 拡張モジュールを置くディレクトリです（コンパイル不要・pip 不要・
ネットワーク不要、Plan §2.1‑5）。Phase 8 で旧 `third_party/`（vendored C コア）
が撤去され、ここが**唯一のネイティブコア供給経路**になりました: ZipNN の
圧縮/解凍/デルタ/バッチ、スキャン、ヘッダ解析、ハッシュ、プレビュー WebP
codec はすべてこのコアが実行します（ロード失敗時の挙動は機能ごと —
ZipNN 系は明確なエラー、読み取り系は Python フォールバックへデグレード）。

## レイアウトと命名

```
native-bin/
├─ linux-x86_64/mm_core.abi3.so       # glibc >= 2.28（Debian 10 / Ubuntu 20.04+）
├─ linux-aarch64/mm_core.abi3.so      # glibc >= 2.28
├─ macos-universal2/mm_core.abi3.so   # x86_64 + arm64（lipo 済み fat binary）
└─ windows-x86_64/mm_core.pyd         # MSVC ビルド
```

- すべて **abi3（CPython Stable ABI、abi3‑py310）**: CPython 3.10 以降の
  全バージョンで 1 バイナリが動作します（旧 C コアの版別 .so ×6 が不要 —
  K13/K16）。CI（native.yml `abi3-import`）が CPython 3.10 と 3.13 の両方で
  import を実証します。
- Linux/macOS の `.abi3.so` は CPython の `EXTENSION_SUFFIXES` に含まれる
  正式サフィックスです。**Windows だけは `mm_core.pyd`**（`.abi3.pyd` ではない）:
  Windows CPython の `EXTENSION_SUFFIXES` は `['.pyd']` のみで、`.abi3.pyd` は
  import されません（Plan §4.2.1 の表記を実態に合わせて調整）。
- サイズ予算（Plan §3.3 / R6）: **1 バイナリ ≤ 5 MB = 目安**（macOS universal2
  は per‑arch スライス判定・fat ファイルは ≤ 10 MB）、**合計 ≤ 20 MB = ハード
  上限**。CI の `size-budget` ジョブが毎 run でゲートします（FAT_MAGIC を
  content 判定するためディレクトリ断片が失われても堅牢）。
- `.gitignore` は `*.so` を無視したままです（**dev/PR ワークツリーでローカルの
  debug ビルドを誤コミットしないため**）。main では `publish-native-bin` ジョブが
  release 成果物を `git add -f` で強制追加します — 一度追跡されれば clone に
  含まれるため、K16（新規 clone がコンパイラ・pip・ネットワークなしで動作）は
  gitignore と両立します。

## バイナリの生成と更新（CI）

`native.yml` の `publish-native-bin` ジョブが **main への push 時のみ**、
3 ビルドジョブ（linux = zigbuild glibc 2.28 床 / macOS = maturin universal2 +
lipo / windows = MSVC）の成果物を content ベースで分類してこのディレクトリへ
ステージし、差分があるときだけコミット＆プッシュします（GITHUB_TOKEN・
contents: write。トークン由来のコミットは Actions を再トリガーしないため
ループしません）。dev / PR の run は**検証のみ**で publish しません —
dev ワークツリーの `.so` はローカルビルド用（下記）で gitignore のまま、
リリースタグは main が既に持つバイナリをそのまま出荷します。

## 手動再生成（開発用）

各 OS のホストで（詳細は [`../README.md`](../README.md)）:

```bash
scripts/build-native.sh --target linux-x86_64 --size-gate     # 任意の Linux ホスト
scripts/build-native.sh --target linux-aarch64 --size-gate    # 任意の Linux ホスト（zigbuild クロス）
scripts/build-native.sh --target macos-universal2 --size-gate # macOS ホスト
scripts/build-native.sh --target windows-x86_64 --size-gate   # Windows ホスト
```

開発ループでは debug ビルドで十分です（api_version ハンドシェーク・全 pytest・
bench cross-check が release と同一結果 — MEMO §2.2）:

```bash
cd native && CARGO_BUILD_JOBS=1 cargo build -p mm-core
cp target/debug/libmm_core.so native-bin/linux-x86_64/mm_core.abi3.so
```
