# Agent/Plan.md — Windows ARM64 配布・表記整合・残件完全クローズ計画書

| 項目           | 内容                                                                                         |
| -------------- | -------------------------------------------------------------------------------------------- |
| 版数           | 2.0                                                                                          |
| 更新日         | 2026-11-27（UTC）                                                                            |
| 対象リポジトリ | `rikunarita/ComfyUI-Model-Manager-Neo`                                                       |
| 対象ブランチ   | `dev`（`main` への反映はユーザーのマージ／公開作業）                                         |
| 文書の位置づけ | living document。以下の 5 件を**同一計画として完了**させるための、実装可能で検証可能な計画書 |
| 文書番号       | なし。内部の計画固有識別子は最終状態に残さない                                               |
| 成功の定義     | 5 件すべてが、実装・CI・文書・一次証跡により「済んだ」と機械的に判定できること               |

> この文書の適用開始以後、従来の完了済み計画文書の番号・節参照・タスク固有語を、
> コードや文書へ持ち直さないこと。本書自身も最終スキャンの対象であり、
> 完了時には内部識別子のない形へ正規化する。

---

## 0. この計画の結論と非目標

### 0.1 結論

次の 5 件を、別々の小修正として扱わず、ひとつの配布・文書・品質改善として完了させる。

1. **Windows ARM64 専用のネイティブ実行バイナリを、配布可能な状態まで完全サポートする**
2. **README 冒頭のタグ群を x86 系の誤表記から x86_64/x64 へ修正し、Windows ARM64 タグを追加する**
3. **本リポジトリの一時 GitHub Actions ワークフローで、各種最適化を実測し、採否を明示判断する**
4. **残留する内部計画・内部表記を一つ残らず修正・削除する**
5. **`Agent/MEMO.md` §7 の古い残件リストを、「未更新なだけ」であるというユーザー回答に基づき、全件完了済みとして適切に更新する**

### 0.2 非目標・禁止事項

- `main` へ直接 push しない。実装・文書・CI 変更は `dev` → PR とする。
- GitHub Release、タグ作成、レジストリ公開、利用者向けバイナリの最終リリースは、従来どおりユーザー専任とする。
- 未確認の最適化を「たぶん速い」で出荷しない。必ずこのリポジトリの Actions 実測と計測ログを一次根拠にする。
- ファイル名の変更だけ先に行い、参照更新を後回しにしない。
- 生成物を手編集しない。`web/manager.js` や `tsconfig.tsbuildinfo` のような生成／キャッシュ成果物は、元ソース修正後に再生成・再判定する。
- 参照機測定・手動 QA・公開作業など、ユーザー専任だった事項を、証拠なしに「完了」へ書き換えない。ただし今回のユーザー明示回答を、手動・非公開領域についての完了判断の根拠として使う。
- 証跡 JSON の値を、数値比較・追跡可能性を壊す形で書き換えない。`git` 履歴を保全したうえで、内部識別子だけを正規化する。
- 40 MB の総容量ガイドラインを、単に「収まらないから」だけで緩めない。緩和可否は測定結果とともにユーザーへ明示する。1 バイナリ 5 MiB のハードゲートはいかなる場合も緩めない。
- Windows ARM64 が未完成のまま、タグだけ追加した成果物を「サポート済み」と表示しない。

### 0.3 前提となる権威ルール

優先順位は次のとおり。

1. 実コード・`git` 履歴・CI 実行ログ・GitHub API が示す事実
2. 現行 `MEMO.md` / `BENCH.md` に明記された一次判断
3. 2026-11-27 のユーザー明示指示
   - §7 は「最新状態の未転記」であり、本来の残件はすべて済んでいる、という回答
4. 上流公式文書と一次測定
5. 推測

2 と 3 が衝突した場合は、勝手に解釈せず、該当箇所を残してユーザーへ確認する。
1 と 3 が衝突した場合も、数値を捏造せず、差分を明示して停止する。

---

## 1. 2026-11-27 時点の現状（一次確認済み）

### 1.1 Windows ARM64

現状の出荷対象は次の組み合せのみ。

| 系統              | abi3（GIL）                   | abi3t（free-threaded, CPython 3.15+） |
| ----------------- | ----------------------------- | ------------------------------------- |
| linux-x86_64      | あり                          | あり                                  |
| linux-aarch64     | あり                          | あり                                  |
| macos-universal2  | あり（Intel + Apple Silicon） | あり（Intel + Apple Silicon）         |
| windows-x86_64    | あり                          | あり                                  |
| **windows-arm64** | **なし**                      | **なし**                              |

現状の根拠:

- `scripts/build-native.sh` が受理する Windows target は x86_64 のみ
- `.github/workflows/native.yml` の Windows build は `windows-latest`（x64）
- `scripts/verify_native_binary.py` が期待する PE machine は AMD64 (`0x8664`) のみ
- `publish-native-bin` の配布対象リストは 8 本だけ
- `py/native.py` は Windows の `AMD64` / `x86_64` だけを `windows-x86_64` 系へマップし、ARM64 では prebuilt を返さない
- Windows ARM64 wheel の検証経路（wheel tag / PE machine / loader smoke / ARM64 Python）は未実装

GitHub-hosted runner としては、次の公式ホスト型実行環境が利用可能。

- `windows-11-arm`
- `windows-11-vs2026-arm`

Visual Studio 2026 搭載イメージは 2026-08-20 に一般提供済みで、`windows-11-vs2026-arm` を明示利用できる。`windows-11-arm` は VS2026 への移行が 2026-09-末までに完了している。

- GitHub Changelog: Windows 11 arm64 VS2026 image generally available  
  <https://github.blog/changelog/2026-08-20-windows-11-arm64-vs2026-image-generally-available/>
- GitHub Docs: GitHub-hosted runners reference  
  <https://docs.github.com/en/actions/reference/runners/github-hosted-runners>

公開リポジトリの標準 runner は Windows ARM64 で 4 vCPU / 16 GB、プライベートでは 2 vCPU / 8 GB。
実装計画では public runner の性能を前提に「絶対最短」とは書かず、実測値を一次根拠にする。

### 1.2 README 冒頭タグ群

現行 4 言語の冒頭では、少なくとも次が使われている。

- `Linux x86_64`
- `Linux aarch64`
- `macOS universal2`
- `Windows x64`

ユーザー指摘のとおり、Windows を裸の `x86` と読み取れる／混同される表記は不完全である。
README 本体では `Windows x86_64` / `Windows x64` と表記されているが、冒頭タグと artifact 表記を統一し、Windows ARM64 タグを追加する。

修正対象:

- `README.md`
- `README.ja.md`
- `README.zh-CN.md`
- `README.zh-TW.md`
- 同じ top section / platform section に同等表記がある `docs/USAGE*`
- `native/README.md`
- `native/native-bin/README.md`

### 1.3 GitHub Actions の最適化検証

現状の恒久的な最適化:

- Rust release profile: `opt-level = 3`、`lto = "fat"`、`codegen-units = 1`、`strip = true`
- panic: `unwind`（PyO3 の例外変換のため必須）
- `rayon` による並列化
- `ignore` による並列ディレクトリ walk
- `blake3` の `rayon` 利用
- linux-x86_64 GIL artifact への PGO
- windows-x86_64 GIL artifact への PGO

現状の未実施・保留:

- `target-cpu=native` は未使用
- x86-64 v2/v3/v4 などの CPU 特化ビルドは未配布
- linux-aarch64 PGO は未実施
- macOS arm64 単独 PGO は未実施
- free-threaded / abi3t の PGO は未実施
- Windows ARM64 artifact 自体がない
- SHA-256 の `sha2` feature 選択を ISA 固定で出荷していない

### 1.4 内部計画・内部表記

ユーザー向け README / USAGE / SECURITY は一次スキャンで内部計画固有語を検出しなかった。
一方、次の領域には広く残っている。

- `Agent/Plan.md` / `Agent/MEMO.md`
- `docs/BENCH.md`
- `native/README.md`
- `native/native-bin/README.md`
- `.github/workflows/*`
- `py/*`
- `native/crates/mm-core/src/*`
- `native/crates/znn-codec/src/*`
- `tests/*`
- `scripts/bench/*`
- `scripts/cross_validation/*`
- `.gitignore`
- `requirements.txt`
- `pyproject.toml`
- `eslint.config.js`
- `__init__.py`
- `src/*`

ファイル名／モジュール名にも内部段階名が残っている。

- `tests/` 配下の段階番号つきテストファイル群
- `scripts/bench/front/` 配下のタスク番号つき計測器
- `native/crates/mm-core/src/` の段階番号つき bindings 群

したがって、文書の文章から語を消すだけでは「一つ残らず修正・削除」を満たさない。
ファイル名、import、CI 名称、package scripts、文書リンク、成果物名、参照テストまでを連鎖して正規化する。

### 1.5 MEMO §7

`Agent/MEMO.md` §7 は現在も「ユーザー専任」「参照機待ち」「手動 QA 待ち」「キャッシュ方針保留」など、古くなった表示を残す。
2026-11-27 のユーザー回答により、これらは**未更新なだけで、すべて済んでいる**。

この回答を、手動 QA・非公開作業・ユーザー専任作業についての完了判断の根拠として用いる。
ただし、コード／CI／ログから検証可能な主張は、MEMO を書き換える前に実測・照会する。

---

## 2. 実施順序

依存関係に従い、次の順で進める。

```text
┌─────────────────────────────┐
│ 1. 現状スナップショット取得 │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│ 2. 一時 Actions で最適化実測 │
│    - Windows ARM64 toolchain │
│    - PGO / target-cpu / ISA  │
└───────┬──────────────┬──────┘
        ↓              ↓
┌───────────────┐  ┌────────────────────────┐
│ 3. Windows    │  │ 4. 最適化採否を確定    │
│    ARM64 実装 │  │    一時ワークフロー廃止 │
└───────┬───────┘  └────────────────────────┘
        ↓
┌─────────────────────────────┐
│ 5. README / artifact 表記   │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│ 6. 内部計画・内部表記の全除去 │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│ 7. MEMO §7 の完了同期       │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│ 8. 最終スキャン・CI・報告    │
└─────────────────────────────┘
```

### 順序を守る理由

- ARM64 を先に実装すると、最適化 probe と成果物の再検証が二重になる。
- Windows ARM64 が本当に構築可能かを先に実測すれば、不可能な計画を README や成果数へ先に書かなくて済む。
- 内部表記の全除去を最後に集中すると、README・ファイル名変更後の再走査漏れを防げる。
- MEMO の完了同期は、実装と検証が終わった最終状態を記録するため、最後に近い位置で実施する。

---

## 3. 作業 1: Windows ARM64 専用ネイティブバイナリの配布＆完全サポート

### 3.1 目的

Windows on ARM 上で、x86/x64 エミュレーションに頼らず、次の prebuilt extension をネイティブ実行できる状態にする。

- GIL build 用 Stable ABI
  - タグ: `windows-arm64`
  - 成果物: `native/native-bin/windows-arm64/mm_core.pyd`
- free-threaded 3.15+ 用 Stable ABI（PEP 803）
  - タグ: `windows-arm64t`
  - 成果物: `native/native-bin/windows-arm64t/mm_core.pyd`

PEP 803 による Windows filename は plain `.pyd` のままで、tag directory が ABI 系統を区別する。
したがって、裸の `mm_core.pyd` だけを artifact として保存・分類しない。

### 3.2 成功条件

Windows ARM64 サポートは、以下をすべて満たしたときだけ完了とする。

1. Windows ARM64 runner 上で GIL artifact をネイティブ build できる
2. Windows ARM64 runner 上で、対応が確認できた free-threaded artifact をネイティブ build できる
3. `scripts/verify_native_binary.py` が ARM64 PE machine を正しく検証する
4. `py/native.py` が Windows ARM64 を正しい tag へマップする
5. loader の ABI / floor / flavour 判定が x86_64 と同じ規程で動作する
6. Windows ARM64 integration test が実 runner で green
7. `publish-native-bin` が 10 本の成果物を欠落・誤分類なく stage できる
8. size gate、total guideline、native-bin verification が新 artifact 数に同期する
9. README / USAGE ×4 / native README / native-bin README が新成果物を説明する
10. 新鮮 clone で Windows ARM64 artifact だけを使って import できる
11. PR の CI 実 run の run ID が記録される
12. 失敗時は、未完成 artifact をコミット・公開しない

### 3.3 タグ設計

採用表記:

| 用途                        | タグ             | ファイル                                       |
| --------------------------- | ---------------- | ---------------------------------------------- |
| Windows ARM64 GIL           | `windows-arm64`  | `native-bin/windows-arm64/mm_core.pyd`         |
| Windows ARM64 free-threaded | `windows-arm64t` | `native/native-bin/windows-arm64t/mm_core.pyd` |

命名根拠:

- Windows Python が報告する machine は `ARM64`
- Windows ABI の convention に合わせて `arm64` を使う
- 既存 loader が Linux を `aarch64`、Apple Silicon を `arm64` として翻訳しているため、Windows 以上には既存の `windows-x86_64` 命名規約に合わせた `windows-arm64` を使う
- `aarch64` と `arm64` の二重表記を増やさない

禁止:

- `windows-aarch64`
- `windows-universal`
- `windows-x86_64` 配下への ARM64 バイナリ配置
- 裸の `mm_core.pyd` だけを upload して artifact 分類を content sniff 任せにする構成

### 3.4 実装ステップ

#### 3.4.1 Runner / toolchain capability probe

一時ワークフロー（作業 3）で、少なくとも次を `windows-11-vs2026-arm` で実行する。
結果が `windows-11-arm` の方が安定する場合のみ、永続 job へ採用してよい。

```yaml
runs-on: windows-11-vs2026-arm
```

確認項目:

- `$env:PROCESSOR_ARCHITECTURE` / `python -c "import platform; print(platform.machine())"`
- `rustc -vV`
- `rustup target list --installed`
- `aarch64-pc-windows-msvc` の stable 対応
- MSVC ARM64 toolchain / linker / SDK の存在
- `actions/setup-python` で ARM64 Python 3.12、3.14、3.15 を install 可能か
- 3.15 GIL と free-threaded の両方で `platform.machine() == 'ARM64'`
- PE machine が ARM64 になる wheel を maturin が生成できるか
- `zenwebp` / `blake3` / `sha2` / `jiter` / `memmap2` が ARM64 で compile 可能か
- `cargo tree` に x86_64-only crate がないか
- CPython free-threaded ARM64 の runner manifest と `freethreaded: true` の挙動

capability probe が失敗した項目は、実装を進めずに「未対応」とする。
特に 3.15 free-threaded ARM64 が runner で利用できない場合、abi3 GIL のみを出荷し、`windows-arm64t` を「対応済み」と表示しない。

#### 3.4.2 `scripts/verify_native_binary.py`

次の期待値を追加する。

- `windows-arm64` / `windows-arm64t` の base tag は `windows-arm64`
- PE machine は `IMAGE_FILE_MACHINE_ARM64 = 0xAA64`
- x86_64 の `IMAGE_FILE_MACHINE_AMD64 = 0x8664` と分離
- PE の唯一の許容 Python import は従来どおり `python3.dll`
- バージョン付き Python DLL への参照は従来どおり失敗
- Mach-O / ELF の既存検証は変更しない
- `--glibc-floor` は無関係、ただし既存 CLI 互換維持
- JSON report に `machine: "0xaa64"` と ARM64 tag が出ること
- 既存 x86_64 PE のロジックを別関数へ無理に分岐せず、共通化できる箇所だけ整理

必要な pytest:

- synthetic PE AMD64 = pass
- synthetic PE ARM64 = pass for ARM tag only
- synthetic PE wrong-machine = fail
- PE import が `python312.dll` 等なら fail
- `windows-arm64t` は format check では GIL 版と同様に扱う

#### 3.4.3 `scripts/build-native.sh`

新しい target を追加する。

```bash
windows-arm64
windows-arm64t
```

処理:

- Windows host 判定を維持
- `build_windows arm64` / `build_windows arm64 ft` 相当の分岐を追加
- wheel glob は `*win_arm64.whl` 系を使用
- `--pgo-train` は既定無効のまま開始
- workload probe の結果で PGO 採用可否を決める
- abi3t は従来規約どおり `--no-default-features --features ft`
- stable-abi と `ft` の feature 混在禁止を維持
- output はそれぞれ `windows-arm64/mm_core.pyd`、`windows-arm64t/mm_core.pyd`
- `extract_from_wheel`、`finish`、loss gate は x86_64 path を雛形にする
- 中間 wheel 名の検証を ARM64 専用に絞る
- host が ARM64 でない場合は明示エラー。Linux 上のクロス build を暗黙許可しない

#### 3.4.4 `py/native.py`

Windows 分岐を次へ変更する。

```text
machine in ("arm64", "aarch64") -> windows-arm64
```

既存の GIL / free-threaded 判定はそのまま流用:

- GIL 3.12+ → `<tag>`
- free-threaded 3.15+ → `<tag>t`
- floor 未満 → 従来どおり `None` + 理由
- loader の user-visible 例外文言から内部計画語を除去済みであることを再確認

更新する文書:

- supported tag 列挙
- 未対応 architecture rejection reason
- architecture verification tests
- README / USAGE ×4
- `native/README.md` の loader 説明

#### 3.4.5 loader / routing tests

pytest を追加・更新する。

- `("Windows", "ARM64")` → `windows-arm64`
- `("Windows", "arm64")` → `windows-arm64`
- `("Windows", "AARCH64")` のように報告文字列が変わった場合の扱いを固定
- GIL → `windows-arm64`
- free-threaded → `windows-arm64t`
- 低い Python / 非 ARM64 runner では適切に rejection
- `.pyd` の tag directory 分離
- 既存 x86_64 case の回帰テスト

段階名つきの従来テストファイルは、内部表記除去の過程で意味ベース名へ rename する。

#### 3.4.6 CI permanent jobs

##### build job

`native-build-windows` を x86_64 のまま壊さず、次のいずれかに分ける。

案 A: job を分割

- `native-build-windows-x86_64`
- `native-build-windows-arm64`

案 B: 単一 job 内で matrix 化

- runner、artifact name、wheel glob、size gate を matrix 値で渡す

推奨は案 A、または案 B の `include` matrix。
同一 job 名に混ぜる場合でも、各 step が x86_64 assumptions を持たないことを確認する。

各 job の要件:

- `runs-on: windows-11-vs2026-arm`
- stable Rust は host toolchain を採用（cross-compile しない）
- Python 3.12 / 3.15 を ARM64 で setup
- maturin install は `UV_MALWARE_CHECK=1` を維持
- build command は `scripts/build-native.sh --target ...`
- PE verifier を必ず実行
- CPython ARM64 で import smoke
- artifact upload は `<tag>/mm_core.pyd` の directory structure を維持
- upload artifact だけ bare `mm_core.pyd` にしない
- x86_64 artifact と命名衝突させない
- 7日 retention は検証専用、main は `publish-native-bin` が正

##### abi3t smoke

- CPython 3.15 GIL ARM64
- CPython 3.15 free-threaded ARM64

両方が利用できない場合、abi3 GIL のみを完了対象にし、abi3t は作業 3 の probe 結果に従う。

##### integration

最低限の matrix:

| runner                  | Python             | artifact         |
| ----------------------- | ------------------ | ---------------- |
| `windows-11-vs2026-arm` | 3.12 GIL           | `windows-arm64`  |
| `windows-11-vs2026-arm` | 3.15 GIL           | `windows-arm64t` |
| `windows-11-vs2026-arm` | 3.15 free-threaded | `windows-arm64t` |

実行内容:

- artifact staging
- loader smoke
- 完全 pytest suite
- integration import assertion
- artifact size
- optional official zipnn 互換セルは x86_64 integration のカバレッジと重複するため、Windows ARM64 ではまず full pytest + import contract を必須とする

##### size budget

現状の 8-binary shape contract を 10-binary へ変更する。

- `size-budget` job の missing artifact list
- total bytes 集計
- 40 MB guideline
- 1 binary 5 MiB hard gate
- size report の baseline count

Windows ARM64 バイナリを先に測り、仮に total が 40 MB を超える場合:

1. 1 binary 5 MiB gate は維持
2. total guideline は advisory なので、勝手に失敗条件にはしない
3. 40 MB guideline を改訂する場合は、測定結果と影響をユーザーへ示してから文書・workflow を変更する
4. Windows ARM64 artifact を出さないことを「container budget」のためだけに選ばない

##### publish-native-bin

- `needs` に ARM64 build job を追加
- staging target table を 10 本へ拡張
- `windows-arm64` / `windows-arm64t` は directory tag により分類
- bare `.pyd` の fallback 拒否は維持
- `git add -f native/native-bin`
- verify all ten paths
- commit message は「8 本」から「10 本」へ更新
- publish bot message も plan 固有語・古い artifact count を使わない
- GitHub Release の asset 生成はユーザー専任

#### 3.4.7 prebuilt artifact の取り扱い

この計画では、ARM64 artifact をバイナリ手編集で混入させない。

- source を変更して PR を作る
- CI build が唯一の build 根拠
- ユーザーが `dev` → `main` をマージ
- main push の `publish-native-bin` が artifact を再生成しコミット
- それまでの PR は verification artifact のみ、fresh clone 配布は完成扱いしない

Windows ARM64 に対応したローダーだけ先に main へ入れても、artifact が未 publish の場合は利用できない。
そのため、README には「Windows ARM64 artifact が main の `native-bin` に入った時点」で対応開始、と明記する。

### 3.5 文書更新

最低限、次を同一 PR で更新する。

- `README.{md,ja.md,zh-CN.md,zh-TW.md}`
  - platform badge
  - artifact table 2 rows
  - supported CPython note
  - loader / platform tag description
- `docs/USAGE.{md,ja.md,zh-CN.md,zh-TW.md}`
  - artifact table
  - Windows ARM64 の clone 後の確認手順
- `native/README.md`
  - build target 一覧
  - Windows ARM64 の構築条件
  - PE / Python ARM64 / PGO 方針
- `native/native-bin/README.md`
  - tree / publish list / 10-binary contract
- `SECURITY.md`
  - 必要なら Windows ARM64 をサポート範囲へ追加。脆弱性の報告方法自体は変更しない
- `py/native.py` docstring
- Rust / PyO3 自身、Cargo target 注記が不要か確認。ここでは `aarch64-pc-windows-msvc` は dependencies feature ではないため、通常追加不要

### 3.6 Windows ARM64 の詳細リスクと処理

| リスク                                         | 判定方法                      | 処理                                                                     |
| ---------------------------------------------- | ----------------------------- | ------------------------------------------------------------------------ |
| runner image の VS2026 が x86_64 binaries 前提 | capability probe              | `windows-11-vs2026-arm` 固定。migration 中の `windows-11-arm` は使わない |
| `setup-python` が x64 Python を入れる          | `python -c platform`          | ARM64 interpreter を明示。結果が `AMD64` なら失敗                        |
| Python 3.15 FT ARM64 が未提供                  | manifest + setup-python probe | abi3 GIL のみ出荷。abi3t 非対応を文書化                                  |
| Cargo dependency が x86_64-only                | `cargo tree`, build log       | 境界実装を ARM64 互換へ変更、または採否判断から除外                      |
| maturin wheel tag 不一致                       | wheel name assertion          | build script で fail-fast                                                |
| PE machine が AMD64                            | verifier                      | hard fail                                                                |
| wheel が裸 `.pyd` で分類できない               | upload layout                 | `<tag>/mm_core.pyd` を directory-first 保存                              |
| GIL / FT 両方の成果物を誤配布                  | tag + interpreter matrix      | abi3 と abi3t を別ディレクトリでゲート                                   |
| PGO 未検証                                     | 作業 3                        | PGO 採用前に別 PR、初回は非 PGO                                          |
| 40 MB guideline 超過                           | size report                   | 実測をユーザーへ提示。5 MiB gate は維持                                  |
| publish job が ARM64 を分類不能                | `.pyd` fallback 拒否          | directory tag 必須化。誤分類は fail-fast                                 |
| 既存 fresh clone が壊れる                      | distribution test             | x86_64 互換テストと ARM64 追加テストを同時に実行                         |

### 3.7 作業 1 完了条件（チェックリスト）

- [ ] capability probe の run ID が記録された
- [ ] `windows-arm64` GIL artifact が native build できた
- [ ] `windows-arm64t` の可否が binary 付き CI で実証された
- [ ] ARM64 PE verifier の pytest が green
- [ ] loader routing tests が green
- [ ] `scripts/build-native.sh` が ARM64 を受理し、x86_64/macOS/Linux を壊さない
- [ ] `native-build-windows-arm64` または matrix job が PR run で green
- [ ] artifact upload が `<tag>/mm_core.pyd` を保持
- [ ] `size-budget` が 10 artifact contract で green
- [ ] integration matrix が Windows ARM64 で green
- [ ] `publish-native-bin` staging target が 10 本に同期
- [ ] README / USAGE ×4 / native docs が同期
- [ ] merge 後、main publish で `native-bin` が更新された
- [ ] fresh clone で ARM64 artifact import できた
- [ ] 実行できない項目は「対応済み」と書かず、理由と再開条件を記録した

---

## 4. 作業 2: README 冒頭タグ群の x86 表記修正と ARM64 追加

### 4.1 目的

README の最上部を見た利用者が、Windows の bitness と ABI を誤解しない状態にする。

### 4.2 必須変更

4 言語すべてで、platform badge section に次の 2 行を置く。

```markdown
![Windows x86_64](...)
![Windows ARM64](...)
```

推奨 badge URL:

```markdown
![Windows x86_64](https://img.shields.io/badge/Windows-x86__64-0078D6.svg?logo=windows&logoColor=white)
![Windows ARM64](https://img.shields.io/badge/Windows-ARM64-0078D6.svg?logo=windows&logoColor=white)
```

必要であれば、既存の `Windows x64` を残さず `Windows x86_64` へ統一する。
`x64` は口語的な別名であり、 artifact 名 (`x86_64`) との一貫性を優先する。

### 4.3 併せて必須の整合

トップタグだけ直して、下部の artifact 表・install 説明・platform support が x86_64-only のままでは不完全。
次も同一変更で直す。

- Artifact table:
  - `Windows x86_64`
  - `Windows x86_64 (free-threaded)`
  - `Windows ARM64`
  - `Windows ARM64 (free-threaded)`（出荷する場合のみ）
- platform requirements
- supported interpreter note
- fresh clone / import 説明
- 各 GitHub Actions badge の label、対象 workflow、major version が現行と一致すること
- `README.{ja,zh-CN,zh-TW}.md` の表現を日本語／簡体字／繁体字へ完全同期
- `docs/USAGE*` の platform table
- `native/README.md` の target 一覧

### 4.4 表記規約

| 対象              | 標準表記                        | 備考                                             |
| ----------------- | ------------------------------- | ------------------------------------------------ |
| Linux             | `x86_64`, `aarch64`             | Rust target triple に一致                        |
| Windows           | `x86_64`, `ARM64`               | ファイルタグは `windows-x86_64`, `windows-arm64` |
| Windows wheel ABI | `win_amd64`, `win_arm64`        | 表示用語ではなく実装用語                         |
| Apple             | `universal2`, `arm64`, `x86_64` | macOS は従来どおり fat binary                    |
| 32-bit            | `x86` / `i686`                  | サポートしない。README でこの語を出さない        |

### 4.5 検証

次のコマンドで残存を確認する。

```bash
rg -n -e 'Windows.{0,30}x86([^_0-9]|$)' README*.md docs/USAGE*.md native -g '*.md'
rg -n -e 'Windows.{0,30}x86_64' README*.md docs/USAGE*.md native -g '*.md'
rg -n -e '[Ww]indows.{0,20}ARM64|windows-arm64' README*.md docs/USAGE*.md native -g '*.md'
```

acceptance:

- 裸の `x86` として Windows を表す行は 0
- Windows x86_64 の artifact 名と badge が完全一致
- Windows ARM64 の artifact 名と badge が完全一致
- 4 言語で言い回しだけでなく行構成・リンク・artifact 数が一致
- x86_64 以外の既存 platform 表記に不要な drift を作らない

---

## 5. 作業 3: 一時 GitHub Actions で各種最適化を実測し、採否を決定する

### 5.1 目的

「最適化を入れるかどうか」をコードレビューの印象で決めず、このリポジトリの Actions で測定し、
各オプションについて**採用／不採用／保留**の明示的決定を出す。

検証は一時ワークフローで実施し、終了後は削除する。結果は MEMO / BENCH / PR 説明へ転記する。

### 5.2 一時ワークフローの設計

#### 基本 policy

- ファイル名: `.github/workflows/optimization-probe.yml`（temporary）
- trigger: `workflow_dispatch` のみ
- `pull_request_target` は使わない
- `permissions: contents: read`
- job timeout: 原則 30〜90 分
- 外部 action は既存 pinned actions だけを再利用
- token・secret は不要
- 計測成果物は runner 内で削除。必要な JSON / markdown report だけ short-retention artifact または Actions log に出す
- probe 終了後、この workflow は merge せず削除するか、ユーザーの許可がある場合だけ「disabled のまま」残す

#### 標準 matrix

| probe                    | runner                           | 目的                           |
| ------------------------ | -------------------------------- | ------------------------------ |
| Windows ARM64 GIL        | `windows-11-vs2026-arm`          | build/import/performance       |
| Windows ARM64 FT         | 同上                             | ABI3t build/import/performance |
| Windows x64 PGO baseline | `windows-latest`                 | 既存 PGO の再検証              |
| Linux x86_64 baseline    | `ubuntu-latest`                  | existing PGO / target-cpu      |
| Linux ARM64 native       | ARM64 Ubuntu runner があれば使用 | aarch64 PGO                    |
| macOS arm64              | `macos-latest`                   | arm64-only / universal2 PGO    |

Windows ARM64 runner の 2026 年 9 月 VS2026 移行中/後の挙動は [GitHub Changelog](https://github.blog/changelog/2026-08-20-windows-11-arm64-vs2026-image-generally-available/) を一次確認に使い、`windows-11-arm` ではなく `windows-11-vs2026-arm` を初期値とする。

#### 計測 workload

`scripts/pgo/train.py` を再利用し、A/B bench は runner 上で交互実行する。

- compress / decompress（bf16 low-entropy + random）
- f32 / f16 / fp8
- SHA-256 verification
- delta compress / decompress
- scan cold / warm
- hygiene scan
- `walk_models`
- hash file five notations
- WebP still / animation encode/decode
- safetensors header parse
- tensor tree fold

設定:

- 5 rounds 以上（可能なら 7 / 9 rounds）
- 判定は**側別中央値**
- `ratio`, `ratioMed`, `ratioBest` を併記
- 指標のベースラインは同一 runner・同一 commit・同一 profile
- CPU 周波数差・runner capacity を記録
- artifact size / peak RSS / job duration を記録
- すべての測定 JSON は `/tmp` または runner temp に出力し、`scripts/bench/results/` を汚染しない

### 5.3 検証する最適化候補

#### 5.3.1 Windows ARM64 GIL PGO

| 項目     | 内容                                                                           |
| -------- | ------------------------------------------------------------------------------ |
| 実装有無 | Windows ARM64 artifact 自体がなければ先に非 PGO で実装                         |
| 検証方法 | instrumented wheel → temp venv で `pgo-command` → optimized rebuild            |
| 測定     | GIL 3.12/3.15 build で compress/hash/WebP/scan                                 |
| 合否条件 | build 成功 + import + full tests + median ≥ 3% + size ≤ 5 MiB + verifier green |
| 採用形態 | 採用なら artifact の GIL 側だけ `--pgo-train`。abi3t は別途判定                |

#### 5.3.2 Windows ARM64 free-threaded PGO

| 項目     | 内容                                                                                          |
| -------- | --------------------------------------------------------------------------------------------- |
| 前提     | Python 3.15 FT ARM64 を native runner で実装済み                                              |
| 検証方法 | LLVM profile runtime が FT host で動作することをまず確認                                      |
| 合否条件 | profile generate / merge / rebuild / import / full tests / crash 0 / median gain              |
| 採否     | 未検証の組み合せを恒久導入しない。macOS fat dylib での前例を根拠に、必ず measured gate を置く |

#### 5.3.3 Linux aarch64 PGO

| 項目      | 内容                                                                                           |
| --------- | ---------------------------------------------------------------------------------------------- |
| 前提      | ARM64 Linux runner（GitHub-hosted ARM64）が `ubuntu-*arm` で利用可能                           |
| 禁止      | x86_64 profile を aarch64 へ流用すること                                                       |
| 検証方法  | native ARM64 runner で instrument → profile merge → zigbuild または同等 cross route で rebuild |
| 出荷判断  | size/glibc floor/import/integration/performance がすべて green の場合のみ                      |
| otherwise | 現状どおり非 PGO                                                                               |

#### 5.3.4 macOS arm64-only PGO

| 項目       | 内容                                                                                                          |
| ---------- | ------------------------------------------------------------------------------------------------------------- |
| 既知リスク | 既存記録で instrumented universal2 dylib が終了時 SIGSEGV                                                     |
| 検証方法   | arm64-only dylib + arm64 Python + PGO                                                                         |
| 出荷判断   | pass しても、直ちに universal2 を arm64-only へ置き換えない。Intel Mac 対応を維持するかユーザー判断が必要     |
| 選択肢     | (a) 現状 universal2 非 PGO 維持、(b) universal2 のまま profile 試行、(c) arm64-only 追加 artifact、(d) 非 PGO |

#### 5.3.5 free-threaded Linux / macOS / Windows PGO

すべての `<tag>t` を同時変更しない。runner 別に個別判定する。

- LLVM profile runtime の availability
- FT interpreter の起動安定性
- profile の total count > 0
- missing-function 比率が gate 内
- import smoke GIL + FT
- full pytest
- performance median

一つでも不成立なら非 PGO を維持し、理由を matrix で残す。

#### 5.3.6 target-cpu validation

次のビルドを `release` で生成し、サイズ・import・bench を測る。出荷は別途判断。

| target                 | runner                         | 目的                      |
| ---------------------- | ------------------------------ | ------------------------- |
| baseline               | ubuntu-latest / windows-latest | 現行比較基準              |
| `x86-64-v2`            | ubuntu-latest                  | 広い64-bit互換維持の限界  |
| `x86-64-v3`            | ubuntu-latest                  | AVX2 級                   |
| `x86-64-v4`            | 対応 runner があれば           | AVX-512 級                |
| Windows x64 baseline   | windows-latest                 | Windows compiler macro 差 |
| Windows ARM64 baseline | windows-11-vs2026-arm          | ARM64 baseline            |

判定指標:

- size（5 MiB gate）
- import success
- `__AVX2__` / `__ARM_NEON` 相当の codegen evidence
- compress/hash/WebP median
- illegal instruction の有無は runner hardware に依存するため、配布意味論と組み合せて判断
- `target-cpu=native` は**計測値が出ても出荷しない**。CPU 特化 artifact の product decision が別途必要

#### 5.3.7 target-feature validation

Cargo.toml へ無条件 feature を足す前に、runner で build-only probe を実施する。

- SHA-256 path の ISA feature
- BLAKE3 path
- ZenWebP encode/decode
- AAarch64 NEON / dotprod 系（利用可能なら）
- Windows MSVC flag の通り方

`sha2` / `blake3` は runtime ISA detection を既に使うため、必ずしも compile-time ISA 固定の方が速いとは限らない。
追加小幅改善しかない場合は採用しない。

#### 5.3.8 codegen-units / LTO alternatives

現状の `fat` + `codegen-units=1` はリリース最適化の上限に近い。
検証は「これを下げて速く／小さくなるか」ではなく、次に限定する。

- thin-local / thin LTO の size と build time 比較
- `panic="abort"` は PyO3 と相容れないため計測候補に入れない
- `incremental=true` は release 出荷には無関係なので候補外

thin LTO が大幅に小さく同等性能でない限り、fat LTO を維持する。

### 5.4 probe result の記録形式

各候補について、次の 8 列で decision table を作る。

| 候補 | runner | build | tests | median gain | size | risk | decision |
| ---- | ------ | ----- | ----- | ----------- | ---- | ---- | -------- |

decision は必ず次のいずれか。

- **採用**: 恒久 CI / build script / docs / artifact へ反映する follow-up が必要
- **不採用**: 現状維持。理由を MEMO に残す
- **保留**: 必要なハードウェアまたは上流対応が不足。再評価条件を明記
- **条件付き採用**: 特定 flavor / artifact のみ採用。対象を厳密に限定

### 5.5 decision thresholds

絶対閾値は次を初期値とする。ユーザーが変更した場合は、変更前後の理由を decision log に残す。

- median gain が **< 3%**: 原則不採用
- median gain が **3% 以上 5% 未満**: build/size/risk がすべて良好なら採用候補
- median gain が **≥ 5%**: 実装コストと互換性リスクを明示したうえで採用候補
- size が 5 MiB を超える: 不採用（gate は緩めない）
- import/full tests が 1 件でも fail: 不採用
- illegal instruction の可能性がある: baseline upload では不採用
- median 改善が runner noise 以下: 不採用
- min だけ改善・median 悪化: 不採用

### 5.6 一時ワークフローの終了処理

採否決定後に必ず実施する。

1. probe workflow を `dev` から削除するか、ユーザーの明示許可で保管する
2. `scripts/bench/results/` へ probe JSON を無断コピーしない
3. `BENCH.md` に採否表と run ID を記録する
4. `MEMO.md` に関係者向け要約を追記する
5. 採用した候補は、それぞれの実装 PR へ分割する
6. 同一 PR で大量の最適化を導入しない
7. 採用しなかった候補は、再評価条件を明記して閉じる

### 5.7 作業 3 完了条件

- [ ] Windows ARM64 GIL build/import probe green
- [ ] Windows ARM64 FT の可否 probe green または明確に BLOCKED
- [ ] linux-aarch64 PGO probe の採否が記録された
- [ ] macOS arm64-only PGO probe の採否が記録された
- [ ] free-threaded PGO の採否が artifact/profile ごとに記録された
- [ ] target-cpu v2/v3/v4 probe の採否が記録された
- [ ] target-feature probe の採否が記録された
- [ ] thin LTO / codegen-units probe の採否が記録された
- [ ] 一時 workflow が削除された、またはユーザー許可に従う形で停止された
- [ ] decision table が BENCH / MEMO / final report に転記された
- [ ] 「たぶん速い」という記述が残っていない

---

## 6. 作業 4: 残留する内部計画・内部表記を一つ残らず修正・削除する

### 6.1 目的

このリポジトリの tracked files から、内部実装フェーズ・内部タスク番号・内部受入条件・内部 gate label を検出可能な形で除去する。

対象は「文章だけ」ではない。次をすべて含む。

- コメント
- docstring
- error message / log / panic message
- test ID / assertion message
- file name
- module name
- directory name
- workflow 名 / job 名 / step 名 / summary
- package scripts
- bench harness 名
- CI cache key / concurrency key
- docs heading / link / path
- JSON field / JSON note
- binary artifact が参照する source path / panic location（該当する場合）
- generated bundle
- `.gitignore` 注記

### 6.2 先に確定する処理方針

「内部情報を残さない」と「証跡を保存する」を同時に満たすため、次を採る。

1. 測定値・成果物 hash・日付・run ID は残す
2. 内部計画固有語だけを、内容を変えずに意味ベース語へ置換する
3. ファイル名を変える場合は `git mv` を使い、参照を同一コミットで更新する
4. historical BENCH JSON も同様に正規化する。値を変えない。元ファイルは Git history に残る
5. `Agent/MEMO.md` は履歴として残すが、内部計画固有語は意味ベースの表現へ正規化する
6. `Agent/Plan.md` 自身も最終スキャン時に内部識別子なしへ正規化する
7. `node_modules`, `native/target`, `.fallow` cache など、tracked でない生成キャッシュは対象外。tracked なら修正または `.gitignore` 対象に移す

### 6.3 機械的 inventory

まず全 tracked files を走査し、次の 2 段階を実行する。

```bash
git ls-files -z |
  xargs -0 rg -n -i \
    -e '[p]hase[ -]?[0-9]' \
    -e 'P[l]an[ -]?[0-9]' \
    -e '[K][0-9]{1,2}([^0-9]|$)' \
    -e '[L][0-9]{1,2}([^0-9]|$)' \
    -e '[T][0-9]{1,2}([^0-9]|$)' \
    -e '[A-C][0-9]{1,2}([^0-9]|$)'
```

次に `git ls-files` に含まれる path 名自体を確認する。

```bash
git ls-files | rg -i '[p]hase|[k][0-9]|[t][0-9]|[l][0-9]'
```

最後に各 hit を、誤検出／意味保持が必要／削除対象に分類する 3 列 table を作る。
分類が曖昧なものを正規表現で一括置換してはならない。

### 6.4 代表的な置換規則

具体語ではなく、意味で置換する。以下は必須ルールの例。

| 意味                           | 置換先の表現                         |
| ------------------------------ | ------------------------------------ |
| 初期 loader handshake          | availability / version handshake     |
| safetensors job API            | safetensors パイプライン             |
| デルタ圧縮                     | デルタ圧縮                           |
| dtype extension work           | dtype 拡張                           |
| scan / index / hash            | スキャン系実装                       |
| tensor tree fold               | display tensor tree                  |
| file watcher                   | library watcher                      |
| WebP preview codec             | preview WebP codec                   |
| inline download hash           | inline download verification         |
| multi-notation hash            | one-pass multi-notation hashing      |
| 8 MB MoE header parse          | large MoE safetensors header parse   |
| fresh-clone distribution       | self-contained prebuilt distribution |
| reference-machine verification | reference-machine verification       |
| interoperability gate          | official interoperability gate       |
| unit gate                      | unit contract                        |
| integration gate               | integration corpus                   |
| benchmark KPI                  | acceptance metric                    |
| task branch / step             | implementation step                  |

採用しない表現:

- 段階番号を別の番号へ言い換えるだけ
- `Stage` や `Step` に番号を残すだけ
- 意味不明な `phase-*` rename
- 外部から見えないから、と無検証で「対象外」としない

### 6.5 ファイル名・モジュール名の正規化

以下は削除／rename の対象に必ず含める。

- `tests/` 配下で `phase` を含むファイル名
- `scripts/bench/front/` のタスク番号つき計測器
- `native/crates/mm-core/src/` の段階番号つき bindings
- `scripts/cross_validation/official_cross.py`（内部ゲート名入りパス）および全参照
  - rename 例: `scripts/cross_validation/official_cross.py`（または同等の意味ベース名）
  - 参照: `.github/workflows/native.yml`（integration / 統合・公式 interoperability 検証 コメント・step 名）、`scripts/bench/README.md`、`docs/BENCH.md`、`native/README.md`、各 `tests/test_*` のコメント
  - ファイル内の `official interoperability gate` / `統合・公式 interoperability 検証` / `l5.*` 一時ファイル名接頭辞も意味ベースへ正規化
- `docs/BENCH.md` の段階番号見出し
- `scripts/bench/results/` の段階番号つき filename / note
- `.github/workflows/` の内部タスク番号つき comment / summary key
- workflow artifact name / cache key に含まれる内部語（ある場合）

rename は次の方針で実施する。

1. 新しいファイル名案を先に table 化
2. `git mv`
3. import / `require` / glob / package scripts / CI references を同一コミットで更新
4. docs link checker で missing link がないことを確認
5. test discovery が rename 後も同じ件数を走らせることを確認

推奨する意味ベース名の例:

- loader contract test
- native pipeline contract test
- delta round-trip test
- dtype coverage test
- scan and header test
- index and hash test
- tensor tree test
- watcher lifecycle test
- preview WebP test
- distribution test
- scan bindings
- tensor tree bindings
- WebP bindings
- grid render benchmark

### 6.6 generated / binary files

#### generated web bundle

`web/manager.js` に build 元の comment や string が混入していても、手編集しない。

1. `src/` 側の内部表記を正規化
2. `pnpm build`
3. generated diff を review
4. source map の change も確認
5. CI の artifact size / smoke を green にする

#### tsbuildinfo / cache

- tracked なら削除または `.gitignore` 化
- tracked でないなら snapshot の偶然として扱い、明示管理しない
- いずれも「1つ残らず」判定は tracked files を基準にする

#### native binaries

- `strip = true` でも source path / panic location が文字列として残る可能性がある
- source の panic message / module path / assert text から内部語を除去した後、main の `publish-native-bin` が再生成した artifact を最終確認する
- PR 内で binary だけ手編集しない
- source-string に内部語がない場合でも、rename が panic location を変えるなら rebuild 対象として扱う

### 6.7 文書体系

#### user-facing

- `README.{md,ja.md,zh-CN.md,zh-TW.md}`
- `docs/USAGE.{md,ja.md,zh-CN.md,zh-TW.md}`
- `SECURITY.md`

これらは既に clean だが、rename / link update 後に再スキャンする。

#### developer-facing

- `native/README.md`
- `native/native-bin/README.md`
- `scripts/*/README.md`
- `docs/BENCH.md`
- `Agent/MEMO.md`
- `Agent/Plan.md`

これらも対象。開発者だけが読むからといって内部段階名を残してよい、とはしない。

#### evidence

- `scripts/bench/results/*.json`
- benchmark snapshot
- run ID 引用
- JSON note

値を変えず、内部語だけ意味ベースへ置換する。
変更前後のファイル一覧と、削除した語の置換表を PR description に記録する。

### 6.8 検証ゲート

必須 gate:

```bash
git ls-files -z | xargs -0 rg -n -i \
  -e '[p]hase[ -]?[0-9]' \
  -e 'P[l]an[ -]?[0-9]' \
  -e 'NEO[-]PLAN' \
  -e '\bIMPLEMENTATION[-]?PLAN\b' \
  -e '[K][0-9]{1,2}([^0-9]|$)' \
  -e '[L][0-9]{1,2}([^0-9]|$)' \
  -e '[T][0-9]{1,2}([^0-9]|$)' \
  -e '[A-C][0-9]{1,2}([^0-9]|$)'

git ls-files | rg -i '[p]hase|[k][0-9]|[t][0-9]|[l][0-9]'
```

期待:

- Exit code 1（hit 0）または、誤検出 review で許可した語のみ
- ただしユーザーの「一つ残らず」を厳密運用するなら、許可語でも意味ベースへ改名できるなら改名する
- `\b` 境界の誤検出も手作業で判定し、判定表を残す

併せて実行:

- `cargo fmt --all -- --check`
- `cargo clippy --workspace --all-targets --all-features -- -D warnings`
- `cargo test --workspace --exclude mm-core`
- `cargo test -p mm-core --no-default-features`
- `pnpm typecheck`
- `pnpm lint`
- `pnpm format:check`
- `pnpm build`
- `python -m ruff check`
- `python -m ruff format --check`
- `mypy`
- `python -m pytest`
- docs link check
- 4 言語 documentation parity check

rename がある場合は、それぞれの test discovery count が rename 前と同じであることを報告する。

### 6.9 作業 4 完了条件

- [ ] tracked file content の内部固有語検索が 0 hit、またはレビュー済みの監査表に理由付きで記録された
- [ ] tracked file path の内部段階名検索が 0 hit
- [ ] docs / tests / workflows / scripts の参照がすべて新名称へ同期
- [ ] generated bundle を再生成済み
- [ ] native binary の source string 起因 residue を確認済み
- [ ] BENCH の内部語が意味ベースへ正規化
- [ ] MEMO の内部語が意味ベースへ正規化
- [ ] Plan（本書）自身が最終スキャンを通過
- [ ] 4 言語 docs の行構成・リンク・artifact count が一致
- [ ] 全テスト・全 lint・全 build が green

---

## 7. 作業 5: MEMO §7 の stale 記述を完了済みへ同期する

### 7.1 user directive の扱い

2026-11-27 のユーザー回答:

> `MEMO §7` に残る本来の残件について、それは未更新なだけであり、すべて済んでいるため適宜更新すること。

この回答は、手動 QA・ユーザー専任作業・非公開の完了確認など、セッションから直接再実施できない項目についての一次判断である。
したがって、次の方針で `Agent/MEMO.md` を更新する。

- 「未解決」と表示されている古い残件を、そのまま残さない
- ユーザー回答で完了扱いになった事項は、完了済みとして更新する
- 既に後続セッションで完了済みと記録されている項目も、古い表示に取り残さない
- 事実を捏造しない。日付・SHA・run ID が不明な項目は、`ユーザー 2026-11-27 回答により完了確認済み` と書く
- 「範囲外」と確定されていた事項は、未完了ではなく**意図的な非対応／対象外として閉じた**と記録する
- 現在の本当に未実施な事項がある場合、それだけを新しい残件として残す

### 7.2 必須の確認表

以下を 1 行ずつ `MEMO.md` の該当表へ転記する。推測で埋めない。

| 古い表示                              | 更新後の状態       | 根拠の扱い                                                                           |
| ------------------------------------- | ------------------ | ------------------------------------------------------------------------------------ |
| 公開作業／タグ／registry              | 完了済み           | ユーザー回答 + MEMO 15 節の `v0.4.0 はユーザーが公開済み` と `tag 00aba50` 記録      |
| demo-assets 差し替え                  | 完了済み           | ユーザー回答。`demo-assets/*` の現状と user 管理領域であることを併記                 |
| CI 実行結果確認の指示                 | 完了済み           | ユーザー回答 + 現在の `MEMO.md` に記録された GitHub API 実測                         |
| 圧縮／解凍の reference-machine 再測定 | 完了済み           | ユーザー回答。BENCH の絶対値と外挿の扱いを最新値へ同期                               |
| 5,000 モデル warm scan の確認         | 完了済み           | ユーザー回答。warm scan の測定結果を BENCH または MEMO で再参照                      |
| request-path spill の endpoints       | 対象外として閉じた | 公開契約を変更するため範囲外という既存判断を、未完了ではなく「意図的な対象外」と明記 |
| 実 UI の手動 QA                       | 完了済み           | ユーザー回答。USAGE の手順と実測手段の参照を更新                                     |
| Python 3.15 final 移行                | 既存どおり完了済み | MEMO 内の完了記録を「残件」から履歴節へ移動                                          |
| fuzz-long の不要 toolchain 削除       | 既存どおり完了済み | MEMO 内の完了記録を「残件」から履歴節へ移動                                          |
| Linux native build cache 方針         | 完了済み           | 現行 `native.yml` に `cache-targets: false` が存在しないこと + ユーザー回答          |

なお、`BENCH.md` または `MEMO.md` の後続節に完成済みの実測値・`run ID`・`tag`・commit SHA がある場合は、それを一次根拠として併記する。
見つからない項目を数値や日付で埋めない。

### 7.3 更新方法

1. `Agent/MEMO.md` §7 の見出しを `残件` のままにするか、`完了した作業` / `完了・再開条件` に改名するかを決める。
   - 旧見出しを残す場合、本文は「現時点で未着手の残件はない。過去に残件と表示していた事項の最終状態は次表のとおり」を先頭に置く。
2. 古い bullet を削除するだけで終わらせず、各項目を次のいずれかへ分類する
   - 完了済み
   - ユーザー専任として完了確認済み
   - 意図的な対象外として close
   - 後続判断が必要（ある場合だけ）
3. `§7` という節番号を参照している文書を検索し、参照先名または新節番号へ同期する
4. 内部段階語を含む項目は、作業 4 と合わせて意味ベースの表現へ正規化する
5. `Plan.md` に §7 を引用している箇所があれば同一コミットで更新する
6. user-facing docs へ「完了」と書かない。これは開発者向け進捗の更新であり、README は実装結果だけを書く

### 7.4 MEMO 内の更新例（表現方針）

良い例:

```text
過去に参照機測定待ちとしていた項目は、ユーザー 2026-11-27 回答により完了扱いとする。
実測値・外部機設定・公開手順の詳細は BENCH に記録し、この節では状態だけを閉じる。
```

悪い例:

```text
5,000 モデル warm scan は 100 ms でした。 # 根拠を確認せずに断定
```

### 7.5 作業 5 完了条件

- [ ] §7 に「待ち」「保留」「未実施」と読める古い表示が残っていない
- [ ] ユーザー回答による完了事項が、一次根拠の有無とともに明記されている
- [ ] 意図的な対象外事項が「未完了」ではなく「対象外として close」と表記されている
- [ ] 後続に渡す本当の残件がある場合だけ、理由と再開条件つきで残されている
- [ ] `MEMO.md` の内部段階語が作業 4 の結果と整合している
- [ ] § 番号または節名の相互参照がすべて有効
- [ ] README / Plan / workflow comments から stale §7 参照がない
- [ ] 変更 diff をユーザーが確認できる形で PR に含める

---

## 8. 最終統合・検証・公開前チェック

### 8.1 必須 gate

作業 1〜5 の変更は、少なくとも次をすべて通す。

#### Rust

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace --exclude mm-core
cargo test -p mm-core --no-default-features
```

Windows ARM64 の成果物が追加された場合、さらに次が CI で必要。

```bash
python scripts/verify_native_binary.py windows-arm64 <artifact>
python scripts/verify_native_binary.py windows-arm64t <artifact>
```

#### Python / loader

```bash
python -m pytest
python -m ruff check
python -m ruff format --check
python -m mypy
```

Windows ARM64 CI では、target tag loader test と integration suite を必ず別 job で実行する。

#### Frontend

```bash
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
```

内部表記除去で `src/` が変わる場合、generated `web/manager.js` を必ず再生成し、
バンドル差分が内部語だけで挙動を壊していないことを確認する。

#### Docs

- 4 言語 README の heading / artifact table / support note が一致
- 4 言語 USAGE の手順と artifact count が一致
- `native/README.md` / `native/native-bin/README.md` が 10-artifact reality に対応
- すべての Markdown リンク resolve
- prettier / format gates green

### 8.2 PR / CI 方針

- `dev` へ commit & push
- PR は `dev` → `main`
- PR description には少なくとも以下を含める
  1. Windows ARM64 のビルド matrix と CI run ID
  2. artifact SHA-256 / size
  3. README 4 言語差分
  4. optimization decision table
  5. temporary workflow の run ID と削除確認
  6. residual notation scan 結果
  7. MEMO §7 の更新方針
- `main` への merge は従来どおりユーザー専任
- merge 後、`publish-native-bin` の bot commit と artifact 再生成を確認する
- release / tag の発行はユーザー専任

### 8.3 最終スキャン

```bash
rg -n -i \
  -e '[p]hase[ -]?[0-9]' \
  -e 'P[l]an[ -]?[0-9]' \
  -e 'NEO[-]?PLAN' \
  -e '[K][0-9]{1,2}([^0-9]|$)' \
  -e '[L][0-9]{1,2}([^0-9]|$)' \
  -e '[T][0-9]{1,2}([^0-9]|$)' \
  --git
```

期待: match 0、またはレビュー済み監査表の許可語のみ。
本計画では「ユーザーの完全除去」指示を優先し、許可語も意味ベース語へ置換できるなら置換する。

追加確認:

```bash
git ls-files | rg -i '[p]hase|[k][0-9]|[t][0-9]|[l][0-9]'
```

期待: path 由来の internal name 0 件。

### 8.4 最終報告テンプレート

最終報告には必ず以下を入れる。

```text
1. Windows ARM64
   - runner / interpreter / artifact / SHA-256 / size / CI run ID
   - abi3t 可否と理由
   - publish 状況

2. README
   - 4 言語の冒頭 tag / artifact table の結果
   - 不足していた x86 表記の実在・修正箇所

3. 最適化採否
   - decision table（採用/不採用/保留）
   - 一時 workflow run ID
   - 削除または保管確認

4. 内部表記
   - 修正ファイル数 / rename 数 / 再生成生成物
   - 最終 scan の結果
   - 誤検出監査表の有無

5. MEMO
   - §7 の全項目と更新後の状態
   - ユーザー回答で完了扱いにした項目
   - 実測／CI／git で裏づけた項目

6. 未完了・制約
   - あれば正確に記載。なければ「なし」と書く
   - 公開作業はユーザー専任であることを明記
```

---

## 9. 失敗・中止・rollback 規程

### 9.1 Windows ARM64 build が失敗した場合

- README に support badge を追加しない
- loader mapping を merge しない
- placeholder artifact をコミットしない
- failure log と missing requirement を MEMO に記録
- 再開条件（例: upstream dependency、runner image、Python ABI）を明記

### 9.2 abi3t が失敗した場合

- GIL artifact だけで完了扱いにしない
- `windows-arm64t` は未サポートとして明記する、または artifact を出さない
- optional artifact として黙って publish しない

### 9.3 optimization probe が不安定な場合

- 採用しない
- ベンチが 1 run だけの改善は採用しない
- runner capacity 差が支配的な場合、判定は「保留」
- 一時 workflow を残したまま議論を打ち切らない

### 9.4 in-place path normalization で参照漏れが出た場合

- path 変更と参照更新は同一コミットに戻す
- `git revert` ではなく、follow-up commit でもよいが、同一 PR 内で解決する
- generated files が古い場合は必ず再生成

### 9.5 user-verified MEMO update と一次ログが衝突した場合

- 数値・成果物・CI run を推測で埋めない
- 衝突内容を PR に列挙し、ユーザーへ次を問う
  - どちらの記録を正とするか
  - 該当項目を完了済み扱いしてよいか
  - MEMO / BENCH のどちらへ詳細を書くか

### 9.6 容量超過

- 1 artifact 5 MiB 超過: 不採用・修正必須
- 10-artifact total が 40 MiB 超過:
  1. 測定値を提示
  2. README / native README / workflow / MEMO の guideline を同時に見直すか、ユーザーに確認する
  3. 無言で 40 MiB を無視しない

---

## 10. 完了定義（definition of done）

この計画の 5 作業は、次をすべて満たしたとき完了する。

1. Windows ARM64 artifacts が設計どおり生成され、fresh clone から import できる
2. Windows ARM64 が README 4 言語・USAGE 4 言語・native docs に記載される
3. README 冒頭の Windows badge が x86_64 / ARM64 を正しく表示し、裸の x86 がない
4. 一時 Actions probe の実 run が完了し、全候補に明示的採否が付く
5. tracked tree に内部計画固有語・内部段階名・内部タスク名の残存がない
6. `MEMO.md` §7 が current state と矛盾しない
7. CI / lint / test / build / docs gate がすべて green
8. `dev` PR が作成され、merge 後 main の publish 成果物が確認される
9. GitHub Release / tag / registry 公開はユーザー専任で、未実施なら「未実施」と明示される

---

## 11. 参照情報

### GitHub Actions / runner

- Windows 11 arm64 VS2026 image generally available  
  <https://github.blog/changelog/2026-08-20-windows-11-arm64-vs2026-image-generally-available/>
- GitHub-hosted runners reference  
  <https://docs.github.com/en/actions/reference/runners/github-hosted-runners>
- setup-python supported architectures  
  <https://github.com/actions/setup-python#supported-architectures>

### この repository の一次ファイル

- `.github/workflows/native.yml`
- `scripts/build-native.sh`
- `scripts/verify_native_binary.py`
- `scripts/pgo/train.py`
- `native/Cargo.toml`
- `py/native.py`
- `native/native-bin/`
- `README.{md,ja.md,zh-CN.md,zh-TW.md}`
- `docs/USAGE.{md,ja.md,zh-CN.md,zh-TW.md}`
- `docs/BENCH.md`
- `Agent/MEMO.md`
