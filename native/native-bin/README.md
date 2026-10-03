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
├─ linux-x86_64/mm_core.abi3.so        # glibc >= 2.28（Debian 10 / Ubuntu 20.04+）
├─ linux-aarch64/mm_core.abi3.so       # glibc >= 2.28
├─ macos-universal2/mm_core.abi3.so    # x86_64 + arm64（lipo 済み fat binary）
├─ windows-x86_64/mm_core.pyd          # MSVC ビルド
├─ linux-x86_64t/mm_core.abi3t.so      # フリースレッド CPython 3.15+（glibc >= 2.28）
├─ linux-aarch64t/mm_core.abi3t.so     # 同上
├─ macos-universal2t/mm_core.abi3t.so  # 同上（fat binary）
└─ windows-x86_64t/mm_core.pyd         # 同上（MSVC ビルド）
```

- **GIL 成果物（abi3・CPython Stable ABI、フロア `abi3-py312`）**: 4 プラット
  フォーマ × 1 バイナリが CPython **3.12 以降**の全バージョンで動作します
  （旧 C コアの版別 .so ×6 が不要 — K13/K16）。
- **フリースレッド成果物（abi3t・PEP 803、フロア `abi3t-py315`）**: `<tag>t/`
  ディレクトリの 4 本。CPython **3.15 以降**のフリースレッド build と GIL
  build の**両方**がロードできます（逆にフリースレッド build は通常の abi3
  成果物をロードできないため、`py/native.py` のローダーが解釈系 flavour を
  検出し `<tag>t` だけを渡します）。
- CI（native.yml `abi3-import`）が 4 セルで import を実証します:
  abi3 = CPython 3.12 と 3.14（GIL）、abi3t = 3.15 の GIL build と
  フリースレッド build の両方。
- Linux/macOS の `.abi3.so` / `.abi3t.so` は CPython の `EXTENSION_SUFFIXES`
  に含まれる正式サフィックスです。**Windows だけは `mm_core.pyd`**
  （`.abi3.pyd` / `.abi3t.pyd` ではない）: Windows CPython の
  `EXTENSION_SUFFIXES` は `.pyd` 系のみで、ABI タグ付きファイル名は存在
  しません（Plan §4.2.1 の表記を実態に合わせて調整。flavour の分離は
  ディレクトリ名 `<tag>` / `<tag>t` だけが担います）。
- サイズ予算: **1 バイナリ ≤ 5 MB = ハード上限**（macOS universal2 は
  per‑arch スライス判定・fat ファイルは ≤ 10 MB）、**8 本合計 ≤ 40 MB =
  目安**（超過は warning のみで run はブロックしない — Plan‑3 D1）。
  CI の `size-budget` ジョブが毎 run でゲートし、8 本すべての存在
  （4 abi3 + 4 abi3t の形状契約）も検査します（FAT_MAGIC を content 判定
  するためディレクトリ断片が失われても堅牢）。
- `.gitignore` は `*.so` を無視したままです（**dev/PR ワークツリーでローカルの
  debug ビルドを誤コミットしないため**）。main では `publish-native-bin` ジョブが
  release 成果物を `git add -f` で強制追加します — 一度追跡されれば clone に
  含まれるため、K16（新規 clone がコンパイラ・pip・ネットワークなしで動作）は
  gitignore と両立します。

## バイナリの生成と更新（CI）

`native.yml` の `publish-native-bin` ジョブが **main への push 時のみ**、
3 ビルドジョブ（linux = zigbuild glibc 2.28 床 / macOS = maturin universal2 +
lipo / windows = MSVC。各ジョブが GIL/フリースレッド両 flavour を生成）の
成果物 8 本をこのディレクトリへステージし、差分があるときだけコミット＆
プッシュします（GITHUB_TOKEN・contents: write。トークン由来のコミットは
Actions を再トリガーしないためループしません）。ステージングは
**ディレクトリタグ優先**（upload は `<tag>/` 構造を保持）、content 分類
（ELF e_machine / Mach-O FAT magic / `.abi3t.so` 名）はフォールバックで、
フォールバックは**素の `.pyd` を意図的に拒否**します — Windows の GIL/t 両
成果物は同じファイル名（`mm_core.pyd`）なので、ディレクトリタグだけが両者を
区別できるためです（Plan‑3 R7: 誤ステージは abi3 バイナリをフリースレッド
ユーザーへ配ってしまう）。dev / PR の run は**検証のみ**で publish しません —
dev ワークツリーの `.so` はローカルビルド用（下記）で gitignore のまま、
リリースタグは main が既に持つバイナリをそのまま出荷します。

## 手動再生成（開発用）

各 OS のホストで（詳細は [`../README.md`](../README.md)）:

```bash
scripts/build-native.sh --target linux-x86_64 --size-gate     # 任意の Linux ホスト
scripts/build-native.sh --target linux-aarch64 --size-gate    # 任意の Linux ホスト（zigbuild クロス）
scripts/build-native.sh --target macos-universal2 --size-gate # macOS ホスト
scripts/build-native.sh --target windows-x86_64 --size-gate   # Windows ホスト

# abi3t（<tag>t）は Python >= 3.15 のホスト解釈系が追加条件（PyO3 host >=
# target 制約。GIL build で可）:
scripts/build-native.sh --target linux-x86_64t --size-gate
scripts/build-native.sh --target linux-aarch64t --size-gate
scripts/build-native.sh --target macos-universal2t --size-gate # macOS ホスト
scripts/build-native.sh --target windows-x86_64t --size-gate   # Windows ホスト
```

開発ループでは debug ビルドで十分です（api_version ハンドシェーク・全 pytest・
bench cross-check が release と同一結果）:

```bash
cd native && CARGO_BUILD_JOBS=1 cargo build -p mm-core
cp target/debug/libmm_core.so native-bin/linux-x86_64/mm_core.abi3.so
```
