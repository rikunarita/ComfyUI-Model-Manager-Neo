# ComfyUI‑Model‑Manager‑Neo Python 下限 3.11 化と abi3t（フリースレッド対応 Stable ABI）バイナリ追加計画書

## ― abi3‑py311 への_floor 引き上げと、CPython 3.15+ フリースレッド向け abi3t 成果物の全プラットフォーム追加 ―

| 項目           | 内容                                                                                                           |
| -------------- | -------------------------------------------------------------------------------------------------------------- |
| 文書番号       | NEO‑PLAN‑2026‑003                                                                                              |
| 版数           | 1.0                                                                                                            |
| 作成日         | 2026‑10‑02                                                                                                     |
| 対象リポジトリ | `rikunarita/ComfyUI-Model-Manager-Neo`                                                                         |
| 対象ブランチ   | `dev`                                                                                                          |
| 前提文書       | [`Plan.md`](Plan.md)（NEO‑PLAN‑2026‑001）・[`Plan-2.md`](Plan-2.md)（NEO‑PLAN‑2026‑002）・[`MEMO.md`](MEMO.md) |
| 状態           | **計画（ユーザ承認待ち・実装未着手）**                                                                         |

### 版数履歴

| 版  | 日付       | 変更                                                                                     |
| --- | ---------- | ---------------------------------------------------------------------------------------- |
| 1.0 | 2026‑10‑02 | 初版。一次ソース調査完了（下記付録 B）。Step 1–4 の設計とゲート・未決事項（D1–D3）を定義 |

### 進捗マーク凡例

| マーク  | 意味   |
| ------- | ------ |
| `- [x]` | 完了   |
| `- [/]` | 進行中 |
| `- [ ]` | 未着手 |

---

## エグゼクティブサマリー

1. **Python 下限を 3.10 → 3.11 へ引き上げる**（abi3 フロア `abi3-py311`）。
   根拠: CPython 3.10 は 2026 年 10 月中に EOL（python devguide「Status of Python
   versions」・ユーザ指摘どおり本計画日から約 3 週間以内）。ComfyUI 公式の
   サポート表記も 3.12（フォールバック）/3.13（推奨）/3.14（動作）で、3.10 は
   既にサポート集合に無い（docs.comfy.org「System Requirements」）。
2. **CPython 3.15 の Stable ABI for Free‑Threaded Builds（`abi3t`、PEP 803）
   成果物を 4 プラットフォームタグすべてに追加**する（`linux-x86_64t` /
   `linux-aarch64t` / `macos-universal2t` / `windows-x86_64t`）。abi3t は
   **3.15 以上のフリースレッド build と GIL build の両方**にロード可能
   （CPython 3.15 howto「Migrating to Stable ABI for free threading」）。
   GIL 環境向けには既存の `abi3` 成果物（フロア 3.11）を維持する
   （3.15 GIL は abi3 も abi3t も読めるが、成果物の二重出荷を避ける）。
3. **ローダーはインタープリタ flavour を検出して成果物ディレクトリを選ぶ**
   （フリースレッド ⇒ `<tag>t`、GIL ⇒ `<tag>`）。フリースレッド 3.13/3.14
   （abi3t 未定義のため成果物を出せない）は理由を明示してデグレード
   （現行の「対応外プラットフォーム」契約と同じ失敗のしかた）。
4. ユーザ環境での自動ビルドは**導入しない**（設計哲学「no compiler, no
   network at setup」と衝突。§5 の質問回答参照。手動ビルド手順は既存文書の
   まま有効）。

**主要数値サマリー**

| 指標                       | 現行                                 | 本計画後                                       |
| -------------------------- | ------------------------------------ | ---------------------------------------------- |
| abi3 フロア                | `abi3-py310`（CPython 3.10+）        | `abi3-py311`（CPython 3.11+）                  |
| 成果物本数                 | 4（abi3）                            | 8（abi3 ×4 + abi3t ×4）                        |
| フリースレッド対応         | なし（3.13t/3.14t/3.15t は理由報告） | CPython 3.15+（t/GIL 両 build）を abi3t で対応 |
| サイズ合計ハード上限（R6） | ≤ 20 MB                              | **未決 D1: ≤ 40 MB へ改定提案**                |
| abi3t の PGO               | —                                    | **未決 D2: v1 は非 PGO 提案**                  |

---

## 1. 背景と一次事実（2026‑10‑02 調査・付録 B 出典）

### 1.1 Python 3.10 / 3.11 の位置

- CPython 3.10 のサポート終了は **2026 年 10 月中**（devguide のバージョン
  状態表。サードパーティ整理では 10‑31 とされるが、いずれにせよ本計画日から
  数週間内）。3.11 の EOL は 2027 年 10 月であり、下限 3.11 は 1 年以上の
  保全窓を持つ。
- ComfyUI 公式ドキュメントの Python 表記は「3.13 推奨 / 3.14 動作（カスタム
  ノード次第）/ 3.12 フォールバック」で、**3.10 は記載無し**（= ユーザ前提
  「ComfyUI は 3.10 サポートを終了」を一次ソースが支持）。3.11 も明示は
  無いが、下限 3.11 は ComfyUI の実動集合（3.12+）を完全に内包する。

### 1.2 CPython 3.15 と abi3t（PEP 803）

- 3.15.0 final は 2026‑10‑01 予定に対し **2026‑10‑02 現在は 3.15.0rc3**
  （python.org Source Releases）。**ABI は rc1 時点で凍結**（rc ページの
  宣言「no ABI changes from this point forward in the 3.15 series」）のため、
  rc 版での abi3t ビルドは final に対しても ABI 安全。
- PEP 803（abi3t）: フリースレッド build 向け Stable ABI を 3.15 で導入。
  abi3t 成果物は **3.15 以上の t build と GIL build の両方**でロード可能。
  ファイル名は POSIX が **`.abi3t.so`**、**Windows は通常拡張子と同じ
  `.pyd`**。wheel タグは `cp315-abi3.abi3t`（圧縮タグセット）。
- 前提条件（howto）: マルチフェーズ初期化＋「プロセスごと 1 回まで」の
  非 isolated 許可・可変長型（`tp_itemsize`）不使用 — PyO3 は前者を満たす
  生成を行い、当クレートは `tp_itemsize` を使わない（PyO3 は同型を
  生成しない）。グローバルレジストリ（SiteIndex / hasher cap）は
  「1 プロセス 1 ロード」の範囲で howto が許可する形。
- フリースレッド 3.13/3.14 には abi3t が**存在しない**（PEP 803 は 3.15
  から）。したがって t‑3.13/3.14 には成果物を出せず、ローダーは理由を
  報告してデグレードする（現行の対応外プラットフォーム契約と同型）。

### 1.3 ツールチェーン対応状況（ピン留め版で充足）

- **PyO3 0.29.2**（現ピン）: `abi3t` および `abi3t-py315` feature を持つ
  （features reference: 「abi3t, supported on Python 3.15 and newer for both
  the GIL-enabled and free-threaded builds」）。**注意**: `abi3` と `abi3t`
  を同時有効化すると成果物 flavour がホスト解釈系に依存する（3.15+ ホスト
  で abi3t 化）ため、**成果物ごとに排他的な feature 構成**でビルドする。
- **maturin 1.15.0**（現ピン）: abi3t サポートは 1.14.0 で merge 済み
  （changelog「Support pyo3 abi3t features on Python3.15 and PyO3 0.29
  (#3113)」、issue #3064 は 2026‑07‑20 close）。macOS/Windows の abi3t
  成果物も maturin 経路で生成可能（wheel 内モジュール名は howto の命名に
  追従 = POSIX `.abi3t.so` / Windows `.pyd`）。実装時に wheel 内文件名を
  実測で確認し、逸脱していれば cargo 直接経路へフォールバック（§3.2）。
- **actions/setup-python**: フリースレッドは `'3.13t'` 形の suffix 構文
  （setup-python #973）。actions/python-versions マニフェストに
  **3.15.0‑rc.1 / rc.2 の freethreaded ビルド**（darwin/linux/win32・arm64
  - x64）が存在することを確認済み → CI は今日から `'3.15.0-rc.2t'`（または
    rc.3 公開後はそれ）で t 解釈系を実走でき、final 公開後に `'3.15t'` へ
    振り替える（ABI 凍結済みのため成果物の再ビルドは不要）。
- **cargo-zigbuild 0.23.4 / ziglang 0.16.0**: abi3t はリンカではなく
  PyO3 feature（コンパイル定義）側の話であり、zigbuild 経路は不変
  （glibc 2.28 床も不変）。

### 1.4 ComfyUI 側のフリースレッド成熟度（外部リスク）

公式ドキュメントは 3.14 t について「動作するが依存の一部が GIL を有効化
するため完全サポートではない」と表記し、3.15 は未記載。すなわち
**abi3t 成果物は先回り配布**であり、ComfyUI 本体の t 環境成熟は外部依存
（§7 R2）。当拡張の abi3t バイナリ自体は t/GIL 両 build で import 可能な
ため、ComfyUI が t で動く環境になった瞬間に機能する。

---

## 2. 方針

1. **単一リポジトリ・8 成果物の対称配布**を維持する（K16: fresh clone が
   コンパイラも pip もネットワークも無しで動く）。abi3t を「別配布」に
   せず既存 `native-bin/` ツリーへ `<tag>t/` ディレクトリで追加する。
2. **flavour 検出はローダーの単一関数**に集約（`sys.abiflags` /
   `sysconfig.get_config_var("Py_GIL_DISABLED")`）。GIL 解釈系の解決順序は
   現行どおり（`<tag>`）、t 解釈系は `<tag>t` のみを見る（abi3 の
   GIL-flavour を t へ渡さない — PyO3 の abi3 はフリースレッド非対応）。
3. **feature 構成の排他性**: GIL 成果物 = `abi3-py311` のみ、abi3t 成果物 =
   `abi3t-py315` のみ（同時有効化のホスト依存 flavour 化を構造的に禁止）。
4. **abi3t は v1 非 PGO**（未決 D2 提案）: トレーニングワークロード
   （`scripts/pgo/train.py`）の t 解釈系での挙動・プロファイル_runtime の
   検証が未了のため。GIL 成果物の PGO パイプライン（Plan‑2）は無変更。
5. **サイズ予算**: 本数 8 化により合計 ≤ 20 MB（R6 ハード上限）は物理的に
   不成立（現行 4 本で 18.1 MB）。**D1: 合計 ≤ 40 MB へ改定**を提案
   （Plan §6.3 のサイズ運用はユーザ判断事項）。本別 ≤ 5 MB 目安と fat
   per-slice/ファイル予算は不変。
6. **3.10 の切り捨ては互換破壊だが配布契約の範囲内**: pyproject
   `requires-python` を 3.11 へ上げ、ComfyUI 3.10 環境（実在しない）では
   拡張の import 自体が pip 解決で降りない形にする。ローダーの
   デグレード契約（対応外は理由報告）は維持。

---

## 3. 設計

### 3.1 ビルド構成（feature 再編）

- `native/Cargo.toml`: workspace 依存 `pyo3 = { version = "0.29.2" }`
  （feature なしへ）。`mm-core` の features:
  - `default = ["extension-module", "stable-abi"]`
  - `stable-abi = ["pyo3/abi3-py311"]`
  - `ft = ["pyo3/abi3t-py315"]`（`stable-abi` と同時有効化を CI ゲートで禁止）
- 現行の「`--no-default-features` で extension-module を外す」テスト契約は
  維持（version-specific ABI + libpython リンクで単体テスト）。
  native-test の「feature toggle 検証」ステップは新 feature 名へ更新
  （default に `abi3-py311`・`ft` モードに `abi3t-py315`・両立しないこと）。
- GIL 成果物: 現行経路不変（linux zigbuild + PGO / mac・win maturin + PGO）。
- abi3t 成果物: 同一ランナーで `--no-default-features --features
extension-module,ft`（linux は zigbuild、mac は maturin `--features ft`
  - universal2、win は maturin `--features ft`）。出力文件名:
    POSIX `mm_core.abi3t.so` / Windows `mm_core.pyd`（howto 命名）。
    配置先: `native-bin/<tag>t/`。

### 3.2 build-native.sh

- ターゲット追加: `linux-x86_64t` / `linux-aarch64t` / `macos-universal2t` /
  `windows-x86_64t`（`= <tag>t`）。`--size-gate` は t でも同一本別予算。
- `extract_from_wheel` の suffix 引数は呼び出し側が `.abi3t.so` / `.pyd` を
  渡す形へ一般化（win は GIL と同名 `.pyd` — ビルドディレクトリが異なる
  ため衝突しない）。
- maturin が abi3t wheel のモジュール命名を howto どおりに出さない場合の
  フォールバック: mac = `cargo build` 両 arch + `lipo -create`、win =
  `cargo build`（MSVC ホスト）の直接経路（現行 linux 経路と同型）。
  実装時に wheel 内容を実測して選択する（推測で本番化しない原則の継承）。

### 3.3 ローダー（py/native.py）

- `is_free_threaded()`: `sysconfig.get_config_var("Py_GIL_DISABLED") == 1`
  （3.13+ で定義。未定義は GIL）または `"t" in sys.abiflags` の OR。
- `platform_tag()`: 基底タグ（現行 4 種）を計算後、t かつ
  `sys.version_info >= (3, 15)` なら `tag + "t"`。t かつ < 3.15 は
  `None` + reason「free-threaded CPython < 3.15 has no stable-ABI artifact
  (abi3t requires 3.15+, PEP 803)」。
- モジュール名: t ディレクトリでは POSIX `mm_core.abi3t.so` / Windows
  `mm_core.pyd` を import（`importlib` の suffix 解決に委ねる — t build の
  EXTENSION_SUFFIXES は `.abi3t.so` / `.pyd` を含むことを howto が保証）。
- origin ガード・api_version ハンドシェーク・diagnostics は不変
  （diagnostics に `freeThreaded: bool` を追加）。

### 3.4 CI（native.yml / ci.yml）

- `native-build-linux`: t 2 ターゲットの zigbuild を追加（非 PGO）。
  glibc 床ゲートは t 成果物にも適用（readelf ループを 4 本へ）。
- `native-build-macos` / `-windows`: maturin `--features ft` で t wheel を
  追加ビルド（非 PGO）。lipo/extract は 3.2 どおり。
- `abi3-import`: マトリクスを
  `{3.11, abi3}` `{3.14, abi3}` `{3.15.0-rc.2, abi3t}` `{3.15.0-rc.2t, abi3t}`
  へ拡張（abi3t は GIL 3.15 と t 3.15 の両方で import 証明 = howto の表の
  両列を実測）。final 公開後は `3.15` / `3.15t` へ表記振替（別コミット）。
- `size-budget`: 8 本へ（`found -lt 8`）・合計上限は D1 決定値。FAT 検出は
  内容判定のまま（t fat も cafebabe）。
- `publish-native-bin`: ターゲット辞書 8 エントリ。Windows は GIL/t とも
  `mm_core.pyd` のため、**ディレクトリタグ優先 + 内容分類フォールバック**
  へステージングロジックを改修（upload-artifact の LCA 挙動を考慮し、
  両 windows タグをディレクトリ構造込みで upload）。
- `integration`: ubuntu セルに **t 解釈系（3.15.0-rc.2t）+ linux-x86_64t
  成果物**のフル pytest を追加（フリースレッド soak = 当コアの並行耐性の
  機械証明。D3 提案: v1 は ubuntu のみ、mac/win t セルは import smoke まで）。
- `ci.yml`: 変更不要（成果物なしセルはローダー skip のまま）。
- `fuzz-smoke` / `fuzz-long`: 変更不要（codec 表面不変）。

### 3.5 Python/フロント/配布メタ

- `pyproject.toml`: `requires-python = ">=3.11"`・`[tool.ruff] target-version
= "py311"`。`requirements.txt` との同期テストは不変（依存リスト無変更）。
- `tests/test_phase0_native_loader.py`: タグ表へ t 4 種と ft 検出の
  monkeypatch ケース（`Py_GIL_DISABLED` / `sys.abiflags` / version 境界
  3.14t→None+reason / 3.15t→tag+t）を追加。
- `tests/test_phase8_distribution.py`: K16 スモークの解釈系下限を 3.11 へ
  更新（CI の実行解釈系は 3.11 のまま）。
- `scripts/verify_native_binary.py`: t タグの ELF/Mach-O/PE 検査を許可
  （判定ロジックはタグ直交）。
- web/・i18n・ロケール: 影響なし（ビルド不要）。

### 3.6 ドキュメント

- README×4 / USAGE×4: 「CPython 3.10 and newer」→「CPython 3.11 and newer
  (GIL builds); free-threaded builds are served by the abi3t artifacts on
  CPython 3.15+」へ。エンジン表へ t 4 行を追加（成果物名・要件）。
  トラブルシューティングへ t‑3.13/3.14 の理由行を追加。
- バッジ: `Python-3.10%2B` → `Python-3.11%2B`・PyO3 バッジを
  `0.29 · abi3-py311 + abi3t-py315` へ・プラットフォーム行へ
  `CPython 3.15+ free-threaded (abi3t)` バッジを 1 本追加。
- `native/README.md`: feature 構成・t ビルド手順・検証表（8 本）を追記。
- `scripts/pgo/README.md`: abi3t は v1 非 PGO の旨を追記（D2 承認時）。

---

## 4. 実施計画（Step 総覧）

| Step | 名称                                              | 主成果物                                        | 完了条件（要約）                                      |
| ---- | ------------------------------------------------- | ----------------------------------------------- | ----------------------------------------------------- |
| 1    | floor 3.11 化（abi3-py311）                       | Cargo/pyproject/ruff/CI矩阵/文書                | 全ゲート緑 + abi3-import 3.11/3.14 緑                 |
| 2    | abi3t feature 構成とビルド経路                    | mm-core features・build-native.sh・maturin 経路 | 4 t 成果物のローカル/CI ビルド緑 + サイズゲート       |
| 3    | ローダー ft 検知と t タグ配信                     | py/native.py・loader テスト                     | 3.15/3.15t import smoke 緑 + 境界 reason テスト緑     |
| 4    | CI 拡張（abi3-import/size/publish/integration-t） | native.yml                                      | 8 本配信 + t integration 緑 + publish 8 エントリ実証  |
| 5    | 文書・バッジ・記録                                | README×4/USAGE×4/native/README/MEMO             | prettier 緑 + dev CI 緑 + ユーザマージ後 publish 確認 |

各 Step は独立コミット・独立 revert（Plan §6.3 継承）。Step 4 は D1（サイズ
上限）と D3（t integration の OS 範囲）のユーザ決定を前提とする。

---

## 5. 配布哲学の確認（ユーザ質問への回答記録）

**Q: 対応していない OS/アーキテクチャの場合、ユーザー環境でビルドする
ようになっているか?**
A: **ならない**。現設計は「プリビルドが無いプラットフォームでは
ローダーが正確な理由を報告し、閲覧/ダウンロード/ハッシュは純 Python 経路
へデグレード、ZipNN 操作とプレビュー再エンコードのみ理由付きで失敗」
（py/native.py の load 契約）。自動ビルドは行わない。ただし**手動ビルドは
可能かつ文書化済み**: Rust ソース一式はリポジトリに同梱されており、
`native/README.md` の手順（`cargo build -p mm-core` → `native-bin/<tag>/`
へ配置、または `scripts/build-native.sh` で release 成果物）でユーザーが
自機ビルドできる。

**Q: ComfyUI カスタムノードとして（import 時の自動ビルド等は）可能か?**
A: **技術的には可能、だが採用しない**。カスタムノードは単なる Python
パッケージであり `__init__.py` で任意コード（コンパイル含む）を実行でき、
ComfyUI 本体も requirements.txt を pip 導入する。しかし import 時自動ビルドは
(1) 設計哲学「no compiler / no network at setup」と正面衝突、(2) fat‑LTO
release ビルドは数分級で ComfyUI 起動を阻塞、(3) 低 RAM 機での OOM 実例
（自プロジェクトの release プロファイルは 1 GiB 環境で `CARGO_BUILD_JOBS=1`
必須だった実測あり）、(4) crates.io 到達性とツールチェーンドリフト
（Rust リリース当日の lint ドリフト事故の前例）という失敗面を追加する。
ComfyUI‑Manager も pip 要件しか orchestrate しない。よって**手動ビルド
文書の維持＋トラブルシューティング行**が最適解であり、自動ビルドは
導入しない（本計画でも不変）。

---

## 6. 未決事項（ユーザ判断）

| #   | 事項                                                      | 提案                                   |
| --- | --------------------------------------------------------- | -------------------------------------- |
| D1  | native-bin 合計ハード上限（R6）20 MB → 8 本体制での新上限 | **≤ 40 MB** へ改定                     |
| D2  | abi3t 成果物の PGO（v1）                                  | **非 PGO**（GIL 側は維持）             |
| D3  | t integration セルの OS 範囲（v1）                        | **ubuntu のみ**＋他 OS は import smoke |
| D4  | CI の 3.15 表記（rc ピン → final 振替のタイミング）       | final 公開確認後の別コミット           |

---

## 7. リスク管理

| #   | リスク                                               | 確率 | 影響 | 緩和策                                                                                                                                      | Step |
| --- | ---------------------------------------------------- | ---- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| R1  | 3.15 final 遅延による CI 表記揺れ                    | 中   | 小   | rc ピン（ABI 凍結宣言済み）+ D4 の振替コミット規程                                                                                          | 4    |
| R2  | ComfyUI 本体の t 環境未成熟（依存が GIL を再有効化） | 高   | 小   | abi3t は t/GIL 両 build で import 可能＝環境が整った瞬間に機能。デグレード契約は不変                                                        | 全   |
| R3  | フリースレッド下での当コア並行耐性                   | 中   | 中   | PyO3 0.29 の ft サポート（Send/Sync 強制）+ t integration セルのフル pytest（D3）で機械証明。flake 時は t セルを smoke へ降格し別計画へ移管 | 4    |
| R4  | maturin の abi3t wheel 命名が howto と不一致         | 低   | 中   | 実測確認 → 不一致なら cargo 直接経路（3.2 フォールバック）                                                                                  | 2    |
| R5  | サイズ上限改定の見落とし（8 本で 20 MB 超過）        | 高   | 小   | D1 を Step 4 の前提ゲート化。size-budget ジョブが毎 run 監視                                                                                | 4    |
| R6  | feature 同時有効化による flavour のホスト依存化      | 中   | 中   | 排他 feature 構成 + native-test の toggle ゲートを 3 feature 軸へ拡張（§3.1）                                                               | 1–2  |
| R7  | Windows の t/GIL 同文件名（`mm_core.pyd`）の取り違え | 中   | 中   | ディレクトリタグ優先の staging（§3.4）+ publish の重複検出（現行の `duplicate artifact for tag` 系）を 8 タグへ拡張                         | 4    |

---

## 付録 A: 現行資産の影響面インベントリ（2026‑10‑02 実査）

- `native/Cargo.toml`（pyo3 features `abi3-py310`）/ `native/crates/mm-core/Cargo.toml`（description）
- `pyproject.toml`（requires-python / ruff target）/ `py/native.py`（platform_tag / reason / diagnostics）
- `.github/workflows/native.yml`（abi3-import 3.10/3.13・size-budget 4 本/20 MB・publish 4 タグ辞書・toggle ゲートの abi3-py310 assert・glibc ループ 2 本）
- `scripts/build-native.sh`（4 ターゲット case / extract_from_wheel）/ `scripts/verify_native_binary.py`（タグ表）
- `tests/test_phase0_native_loader.py`（タグ/パス）/ `tests/test_phase8_distribution.py`（K16）
- README×4（バッジ Python 3.10+ / PyO3 abi3 / エンジン表「CPython 3.10 and newer」/ PGO 文）/ USAGE×4（エンジン表・トラブルシューティング）/ `native/README.md` / `scripts/pgo/README.md`
- 履歴文書（Plan.md / Plan-2.md / BENCH.md / MEMO.md）は**改訂しない**（時点記録のため）。

## 付録 B: 一次ソース一覧（すべて 2026‑10‑02 確認）

| #   | 対象                                      | ソース                                                                                                                          |
| --- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| B1  | Python 3.10 EOL（2026‑10）                | devguide.python.org「Status of Python versions」                                                                                |
| B2  | ComfyUI の Python サポート集合            | docs.comfy.org「System Requirements」（3.13 推奨 / 3.14 動作 / 3.12 フォールバック / ft は「完全サポートではない」）            |
| B3  | 3.15.0rc3（final 未）・ABI 凍結           | python.org/downloads/source（rc3 = Oct. 2, 2026）・3.15.0rc2 ページの「no ABI changes from this point forward」                 |
| B4  | abi3t の定義・命名・対応範囲              | PEP 803・CPython 3.15 howto「Migrating to Stable ABI for free threading (abi3t)」（`.abi3t.so` / Windows `.pyd` / 3.15+ t+GIL） |
| B5  | PyO3 0.29.2 の abi3t feature              | pyo3.rs/v0.29.2/features（`abi3t` / `abi3t-py315`・両 feature 同時有効化のホスト依存挙動）                                      |
| B6  | maturin の abi3t サポート（≥1.14）        | maturin.rs changelog（#3113）・PyO3/maturin#3064（2026‑07‑20 close）                                                            |
| B7  | setup-python の t 構文と rc ft ビルド存在 | actions/setup-python #973・actions/python-versions versions-manifest.json（3.15.0-rc.1/rc.2 freethreaded ファイル実在）         |

---

_本計画書は 2026‑10‑02 の一次ソース調査と本リポジトリの実査に基づく。
実装着手はユーザ承認後とし、各 Step の完了条件を満たさない状態で次へ
進まない（Plan §6.3 継承）。_
