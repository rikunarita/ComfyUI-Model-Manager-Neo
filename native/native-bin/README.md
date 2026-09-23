# `native-bin/` — 配布用プリビルド ネイティブコア

`py/native.py` が **sys.path に追加して import するだけ** のプリビルド
`mm_core` 拡張モジュールを置くディレクトリです（コンパイル不要・pip 不要・
ネットワーク不要、Plan §2.1‑5）。`third_party/zipnn-core-bin/`（旧 C コア）の
置き換え先で、Phase 7 で旧ディレクトリが撤去されたあとはここが唯一の
ネイティブコア供給経路になります。

## レイアウトと命名

```
native-bin/
├─ linux-x86_64/mm_core.abi3.so       # glibc >= 2.28（Debian 10 / Ubuntu 20.04+）
├─ linux-aarch64/mm_core.abi3.so      # glibc >= 2.28
├─ macos-universal2/mm_core.abi3.so   # x86_64 + arm64（lipo 済み、macOS 11+/10.12+）
└─ windows-x86_64/mm_core.pyd         # MSVC ビルド
```

- すべて **abi3（CPython Stable ABI、abi3‑py310）**: CPython 3.10 以降の
  全バージョンで 1 バイナリが動作します（旧 C コアの版別 .so ×6 が不要）。
- Linux/macOS の `.abi3.so` は CPython の `EXTENSION_SUFFIXES` に含まれる
  正式サフィックスです。**Windows だけは `mm_core.pyd`**（`.abi3.pyd` ではない）:
  Windows CPython の `EXTENSION_SUFFIXES` は `['.pyd']` のみで、`.abi3.pyd` は
  import されません（Plan §4.2.1 の表記を実態に合わせて調整）。
- サイズ予算: 1 ファイル ≤ 4 MB、合計 ≤ 20 MB（CI ゲート、Plan §3.3/R6）。

## 現状（Phase 0）

**バイナリはまだコミットされていません。** Phase 0 はビルド疎通とサイズ予算の
実測が目的で、成果物は CI ワークフロー（`.github/workflows/native.yml`）が
アーティファクトとして検証するだけです（Plan §5.3:「成果物は PR では検証のみ。
main/リリースタグで native-bin/ 更新コミットを自動生成」）。そのため
`py/native.py` は現状 `available() == False`（理由: ディレクトリ不在）を返し、
バックエンドは旧 `third_party` 経路のまま動作します。

## 再生成方法

各 OS のホストで（詳細は [`../README.md`](../README.md)）:

```bash
scripts/build-native.sh --target linux-x86_64 --size-gate     # 任意の Linux ホスト
scripts/build-native.sh --target linux-aarch64 --size-gate    # 任意の Linux ホスト
scripts/build-native.sh --target macos-universal2 --size-gate # macOS ホスト
scripts/build-native.sh --target windows-x86_64 --size-gate   # Windows ホスト
```

コミット時はリポジトリルートの `.gitignore`（`*.so` 等を無視）に
`third_party/zipnn-core-bin/` と同じ `!` 例外の追加が必要です（Phase 7 で整備）。
