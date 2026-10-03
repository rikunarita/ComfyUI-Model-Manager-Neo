# ComfyUI‑Model‑Manager‑Neo Python 下限 3.12 化と abi3t（フリースレッド対応 Stable ABI）バイナリ追加計画書

## ― abi3‑py312 への floor 引き上げと、CPython 3.15+ フリースレッド向け abi3t 成果物の全プラットフォーム追加 ―

| 項目           | 内容                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 文書番号       | NEO‑PLAN‑2026‑003                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 版数           | 1.5                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| 作成日         | 2026‑10‑02（v1.0）/ 2026‑10‑03（v1.1 改訂）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 対象リポジトリ | `rikunarita/ComfyUI-Model-Manager-Neo`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| 対象ブランチ   | `dev`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| 前提文書       | [`Plan.md`](Plan.md)（NEO‑PLAN‑2026‑001）・[`Plan-2.md`](Plan-2.md)（NEO‑PLAN‑2026‑002）・[`MEMO.md`](MEMO.md)                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 状態           | **実装完了 + CI 全緑 + 公開パイプライン完了（2026‑10‑03 — dev push #135/#224・PR #29 の #136/#225・main push #137/#226 の 4 run すべて success〔native 18/18〕、publish‑native‑bin の bot コミット `208a3ff` で `native/native-bin/` に 8 本 = 合計 34.98 MiB〔D1 の 40 MB 目安内・FAT 2 本も 10 MB 予算内〕。残りは D4 のラベル振替〔3.15 final の manifest 着弾待ち — PEP 790 の final 予定 2026‑10‑09〕と Plan‑2 R5 のみ。実装記録は MEMO 第 26・修正記録は第 27–28・CI 全緑確認と Actions キャッシュ対策は第 29 セッション）** |

### 版数履歴

| 版  | 日付       | 変更                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| --- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.0 | 2026‑10‑02 | 初版。一次ソース調査完了（下記付録 B）。Step 1–4 の設計とゲート・未決事項（D1–D4）を定義                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 1.1 | 2026‑10‑03 | ユーザ決定の反映: floor を **3.12**（`abi3-py312`）へ変更（3.11 案から改訂）・**D1 = 合計 40 MB の「目安」化**（絶対条件ではない）。D2–D4 は提案の採用を決定（根拠を §6 に明記）。再検証（PyO3 `abi3-py312` と host ≥ target 制約・ruff `py312` 実測・python‑versions manifest の rc.2 ft 網羅・3.15 final 未着）と、インベントリ追加（mypy `python_version`・`uv.lock`・ci.yml の解釈系・I001 1 件・wheel glob・ローダー下限ガード）を実施。§3.5 の K16 記述を実査に合わせて訂正                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 1.2 | 2026‑10‑03 | 状態更新（計画内容の変更なし）: **Steps 1–5 実装完了** — commits c5ffa7e（Step 1 floor 3.12）/ fcdf540（Step 2 ft 構成+ビルド経路）/ 07a4d05（Step 3 ローダー）/ 0ca9847（Step 4 CI 拡張）/ Step 5（文書・バッジ・記録 = 本コミット）。ローカル検証: ruff 0.16.9（py312）・mypy 3.12・pytest 3.12.15 = 85 passed/135 skipped・publish staging simulation 5 シナリオ PASS・build‑native.sh cargo スタブ実測・実解釈系 3.15.0rc2 GIL/ft でローダールーティング実測（EXTENSION_SUFFIXES が PEP 803 予告どおりであることを実測確認）。CI 実走確認は次ターン（ユーザ）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 1.3 | 2026‑10‑03 | 状態更新（計画内容の変更なし）: **dev run（native）37113439219 の 3 失敗を根因解析して修正** — ① linux t ビルドの「Failed to find zig」（py315 切替で cargo‑zigbuild の python 経路が喪失・ziglang wheel に `zig` shim 無し）→ ツールチェイン導入時の `CARGO_ZIGBUILD_ZIG_COMMAND` pin（`$GITHUB_ENV`）、② macOS GIL ビルドの `feat[*]: unbound variable`（bash 3.2 は空配列がダブルクォート内でも unbound）→ log 3 箇所を `${feat[*]+"${feat[*]}"}` ガードへ統一（実機 bash 3.2.57 自ビルドで再現+検証）、③ toggle ゲート ft 軸の `cargo metadata -p`（同コマンドにセレクタ無し）→ `mm-core/…` 修飾 feature へ + cargo stderr の surface。**あわせて潜在誤検出を修正**: pyo3 0.29.2 の abi3‑pyXY は上向きチェーン（floor = 有効化された最小 pyXY・pyo3‑build‑config 一次確認）のため、v1.2 ゲートの「default に abi3‑py313+ が居たら BUG」は ③ を直し次第必ず誤発火した → 「最小有効 minor == 12 / == 15」形へ置換（ゲート実走 PASS + 負例 9 ケースで検出力実証）。同 run で windows t ビルド + 3.15 GIL/ft import smoke は全緑 = R4 実証解消。詳細は MEMO 第 27 セッション / §4.1。CI 再走確認は次ターン（ユーザ）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 1.4 | 2026‑10‑03 | 状態更新（計画内容の変更なし）: **dev run（native）37121494488 = 18 ジョブ中 17 success で v1.3 の 3 修正が実走解消**（native‑test ×3・native‑build‑linux/macos/windows・abi3‑import 4 セル・size‑budget・fuzz‑smoke・integration の GIL 3 セルが緑）。**残る 1 失敗 = integration t セルの pytest 1 本**（`test_load_finds_prebuilt_and_handshakes`・`1 failed, 218 passed, 1 skipped`）を根因解析して修正 — 根因はテスト側で、ローダーも abi3t 成果物も無罪（同セルの他 218 本は実ローダ経由で `linux-x86_64t/mm_core.abi3t.so` を使用）。連鎖: autouse ピン（GIL 3.12 偽装）が `platform_tag()` を `linux-x86_64` にし、ハードコードのプローブ名 `mm_core.abi3.so` が **4 tag 丸ごと展開されたステージング先で実在**して skip ガードをすり抜け、free-threaded 3.15 の `EXTENSION_SUFFIXES` に `.abi3.so` が無い（`Python/dynload_shlib.c` の `#ifndef Py_GIL_DISABLED`）ため `import mm_core` が `ModuleNotFoundError` → `load()` False = **正しく拒否したのは load()**。CI と同一材料（同一 SHA の git archive + artifact 11273309005 の実バイナリ + 3.15.0rc2t + pytest 9.1.1 + 同一依存）で `1 failed, 218 passed, 1 skipped` を完全再現し、reason() を実測。修正は 2 独立コミット（実ホスト解釈系での handshake 検証 + flavour 準拠プローブ + 回帰テスト `test_extension_suffixes_enforce_the_flavour_split`〔5 flavour 実測〕／ピンが aiohttp の import 時分岐に漏れる地雷の除去）。修正後 220 passed / 1 skipped（3.15.0rc2t・3.12.15 双方）。**D3 の予備方針（t セル縮小）は不要**と判明 — sdist 依存（aiohttp/pyyaml）は runner 上で 13.19 s ビルド完了。R1（rc ピン）は据え置き: upstream に `v3.15.0rc3` は実在するが `actions/python-versions` manifest は `3.15.0-rc.2` が最新で rc.3 は setup‑python 不可。詳細は MEMO 第 28 セッション / §4.3 / §4.5。CI 再走確認は次ターン（ユーザ）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 1.5 | 2026‑10‑03 | 状態更新（計画内容の変更なし）+ **D4 の振替対象を精密化**。① **CI 全緑と公開パイプライン完了を確認** — dev push #135/#224・PR #29 の #136/#225・main push #137/#226 の 4 run すべて success（native 18/18）で v1.4 の 2 修正が実走解消、publish‑native‑bin の bot コミット `208a3ff` が `native/native-bin/` に **8 本（abi3 4 + abi3t 4・合計 34.98 MiB）*_をコミット = **D1 の 40 MB 目安内・本別 5 MB / FAT 10 MB のハード予算内・`found = 8` の形状契約を満たす**（Step 4 の公開側が完了）。② **D4 の実施条件を再実測** — CPython の最新タグは `v3.15.0rc3`（**PEP 790: rc3 = 2026‑10‑02 実績 / final = 2026‑10‑09 予定**）、`actions/python-versions` の versions‑manifest.json は今も `3.15.0-rc.2`（`stable=False`・ft ファイル 13 本）が最新で **rc3 も final も未着 = D4 は引き続き実行不可**（R1 の rc ピンは正解のまま）。③ **D4 の振替対象を実ファイルで精密化**（§6 D4 に反映）— native.yml の `python-version: "3.15.0-rc.2"` **9 箇所**（L353/377/459/470/538/546/586/589/721）とコメント 5 箇所（L10/347/453/531/571）だけ。**ft セルは setup‑python の `freethreaded: true` 側で切替わるので `3.15t` という文字列は書かない**（v1.0 以来の「`3.15`/`3.15t` へ振替」という記述より実装は単純）。バイナリの再ビルドは不要（rc1 の ABI 凍結）。④ **計画外の後始末: Actions キャッシュ逼迫（9.65 GiB / 96.5 %）を根因解析して対策** — Step 4 で増えたセルと dev→PR→main の納品形により、キャッシュが ref 単位スコープに 3 重保存されていた（PR の `refs/pull/N/merge` とタグ run のスコープは公式ドキュメント上ほかから復元できず、PR #29 分 2.505 GiB が死蔵・LRU eviction で fuzz‑long のキャッシュが既に消失）。rust‑cache 7 箇所への `save-if`（main/dev の非 PR イベントのみ保存）・`cache-cleanup.yml` + `scripts/actions_cache_sweep.py`（PR クローズ時 + 週次 sweep）・native‑bin‑_ の `retention-days: 7` を 3 独立コミットで入れ、即時 prune 16 件 / 4.566 GiB で **5.083 GiB（50.8 %）**へ。**この 4 コミットの CI 実走確認まで完了**（push `4e92a4d` → native #138 = 16 success + 2 skipped・CI #227 = success。native‑test (ubuntu) のログで `save-if: true` / `Cache hit for: v0-rust-native-test-Linux-x64-…-412e313b`（624 MB・full match）/ post step `Cache up-to-date.` を確認し、**run 後も 22 件 / 5.083 GiB = 新規エントリ 0**）。詳細は MEMO §4.1 末尾 / 第 29 セッション。 |

### 進捗マーク凡例

| マーク  | 意味   |
| ------- | ------ |
| `- [x]` | 完了   |
| `- [/]` | 進行中 |
| `- [ ]` | 未着手 |

---

## エグゼクティブサマリー

1. **Python 下限を 3.10 → 3.12 へ引き上げる**（abi3 フロア `abi3-py312` —
   ユーザ決定 2026‑10‑03）。根拠: CPython 3.10 は **2026‑10‑01 に EOL 到達済み**
   （devguide「Status of Python versions」— 2026‑10‑03 確認）。ComfyUI 公式の
   サポート表記は 3.12（フォールバック）/3.13（推奨）/3.14（動作）で、下限 3.12
   は **ComfyUI の文書化サポート下限と完全一致**する（3.11 は同表記に無い）。
   3.12 の EOL は 2028‑10 で、下限は 2 年の保全窓を持つ。
2. **CPython 3.15 の Stable ABI for Free‑Threaded Builds（`abi3t`、PEP 803）
   成果物を 4 プラットフォームタグすべてに追加**する（`linux-x86_64t` /
   `linux-aarch64t` / `macos-universal2t` / `windows-x86_64t`）。abi3t は
   **3.15 以上のフリースレッド build と GIL build の両方**にロード可能
   （CPython 3.15 howto「Migrating to Stable ABI for free threading」）。
   GIL 環境向けには既存の `abi3` 成果物（フロア 3.12）を維持する
   （3.15 GIL は abi3 も abi3t も読めるが、成果物の二重出荷を避ける）。
3. **ローダーはインタープリタ flavour とバージョンを検出して成果物を選ぶ**
   （フリースレッド 3.15+ ⇒ `<tag>t`、GIL 3.12+ ⇒ `<tag>`、それ以外は理由付き
   デグレード）。フリースレッド 3.13/3.14（abi3t 未定義のため成果物を出せない）
   と GIL 3.10/3.11（フロア未満）は理由を明示してデグレードする
   （現行の「対応外プラットフォーム」契約と同じ失敗のしかた）。
4. ユーザ環境での自動ビルドは**導入しない**（設計哲学「no compiler, no
   network at setup」と衝突。§5 の質問回答参照。手動ビルド手順は既存文書の
   まま有効）。

**主要数値サマリー**

| 指標                 | 現行                                 | 本計画後                                                                                                                                   |
| -------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| abi3 フロア          | `abi3-py310`（CPython 3.10+）        | `abi3-py312`（CPython 3.12+）                                                                                                              |
| 成果物本数           | 4（abi3）                            | 8（abi3 ×4 + abi3t ×4）                                                                                                                    |
| フリースレッド対応   | なし（3.13t/3.14t/3.15t は理由報告） | CPython 3.15+（t/GIL 両 build）を abi3t で対応                                                                                             |
| サイズ合計上限（R6） | ≤ 20 MB（ハード）                    | ≤ 40 MB（**目安** — D1 決定: 超過は warning、run はブロックしない）                                                                        |
| abi3t の PGO         | —                                    | **非 PGO**（D2 決定 — GIL 側の PGO は Plan‑2 のまま維持）                                                                                  |
| CI の t 解釈系ピン   | —                                    | `3.15.0-rc.2` / `3.15.0-rc.2t`（D4: final 着弾後に別コミットで振替。実装は全セル `3.15.0-rc.2` + `freethreaded: true` の組 = §3.4 の注記） |

---

## 1. 背景と一次事実（2026‑10‑02/03 調査・付録 B 出典）

### 1.1 Python 3.10 / 3.11 / 3.12 の位置（floor 3.12 の決定）

- CPython 3.10 は devguide のバージョン状態表で **end-of-life（EOL
  2026‑10‑01）**（2026‑10‑03 確認）。3.11 / 3.12 は security フェーズで、
  EOL はそれぞれ **2027‑10 / 2028‑10** → 下限 3.12 は 2 年の保全窓を持つ。
- ComfyUI 公式ドキュメントの Python 表記は「3.13 推奨 / 3.14 動作（カスタム
  ノード次第）/ 3.12 フォールバック」で、**3.10・3.11 は記載無し**
  （docs.comfy.org — 2026‑10‑02 確認）。下限 3.12 なら本拡張の動作集合は
  ComfyUI の文書化サポート集合の下限と**一致**し、「本拡張は対応するが
  ComfyUI 本体が対応表記を持たない」隙間が無い（v1.0 の 3.11 案はこの隙間を
  残すため、ユーザ決定 2026‑10‑03 で 3.12 へ改訂）。
- 副次的な整合: 現行 `requires-python >= 3.10` は実装と**矛盾**している —
  `tests/test_phase8_distribution.py` は `tomllib`（3.11+ stdlib）を無条件
  import し、`py/utils.py` も `tomllib` を使う（try/except ガード付き）。
  floor 3.12 化はこの矛盾を解消する（ガード自体は残置可 — 無害）。
- `abi3-py312` は PyO3 0.29.2 の feature ラダー（`abi3-py38` …
  `abi3-py315`）に実在する（docs.rs の feature 一覧で実測 — 付録 B8）。

### 1.2 CPython 3.15 と abi3t（PEP 803）

- 3.15.0 final は 2026‑10‑01 予定に対し **2026‑10‑03 現在も 3.15.0rc3**
  （python.org Source Releases。ダウンロードページの最新 stable 表示は
  **3.14.8** のまま、devguide の 3.15 状態は prerelease = final 未着）。
  **ABI は rc1 時点で凍結**（rc ページの宣言「no ABI changes from this point
  forward in the 3.15 series」）のため、rc 版での abi3t ビルドは final に対しても
  ABI 安全。
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

- **PyO3 0.29.2**（現ピン）: `abi3-py312` は feature ラダー内（付録 B8）。
  `abi3t` および `abi3t-py315` feature も持つ（features reference:
  「abi3t, supported on Python 3.15 and newer for both the GIL-enabled and
  free-threaded builds」）。**host 制約**（building-and-distribution、
  2026‑10‑03 確認）: 「PyO3 is only able to link your extension module to
  abi3 version up to and including your host Python version」→ GIL 成果物の
  ビルド host は **≥ 3.12** が必須（現行 CI の 3.11 host では**ビルドが
  fail する**ため、Step 1 で Cargo feature と CI 解釈系を同一コミットで
  bump する）。t 成果物は host **≥ 3.15** が必須（t ビルドセルは
  `3.15.0-rc.2` を host にする — §3.2/§3.4）。同ページに「The free-threaded
  build of CPython cannot load abi3 wheels but both builds can load abi3t
  wheels」= §2‑2 のローダー分離（t に abi3 成果物を渡さない）の一次根拠。
  **注意**: `abi3` と `abi3t` を同時有効化すると成果物 flavour がホスト解釈系に
  依存する（3.15+ ホストで abi3t 化）ため、**成果物ごとに排他的な feature
  構成**でビルドする。
- **maturin 1.15.0**（現ピン）: abi3t サポートは 1.14.0 で merge 済み
  （changelog「Support pyo3 abi3t features on Python3.15 and PyO3 0.29
  (#3113)」、issue #3064 は 2026‑07‑20 close）。macOS/Windows の abi3t
  成果物も maturin 経路で生成可能（wheel 内モジュール名は howto の命名に
  追従 = POSIX `.abi3t.so` / Windows `.pyd`）。実装時に wheel 内文件名を
  実測で確認し、逸脱していれば cargo 直接経路へフォールバック（§3.2）。
- **actions/setup-python**: フリースレッドは `'3.13t'` 形の suffix 構文
  （setup-python #973）。actions/python-versions マニフェストを
  **2026‑10‑03 再検証**: 3.15 系の最新は **3.15.0‑rc.2**（rc.3 の ft ビルド
  は未掲載）で、ft ファイルは darwin（arm64/x64）・linux（22.04/24.04/
  26.04 の arm64/x64）・rhel（9/10）・**win32（x64/arm64/x86）**に実在
  （付録 B10）→ CI は `'3.15.0-rc.2'` / `'3.15.0-rc.2t'` でピンし、final が
  マニフェストへ着弾したら `'3.15'` / `'3.15t'` へ別コミットで振り替える
  （ABI 凍結済みのため成果物の再ビルドは不要 — D4）。
- **ruff 0.16.9**（CI ピン）: `target-version = "py312"` は有効値
  （`ruff check --help` の possible values = py37 … py315 で実測）。
  **実測**: リポジトリ全体を py312 target で再検査した新規違反は
  **1 件のみ** — `tests/test_phase8_distribution.py` の I001（`tomllib` が
  py311+ で stdlib 分類になり、stdlib import ブロックへ移動が必要）。
  機械的修正を Step 1 に含める。`ruff format --check` は py312 でも
  43 files 緑（実測）。
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
   GIL-flavour を t へ渡さない — PyO3 文書も「free-threaded build は abi3
   wheel をロードできない」と明記、§1.3）。
3. **feature 構成の排他性**: GIL 成果物 = `abi3-py312` のみ、abi3t 成果物 =
   `abi3t-py315` のみ（同時有効化のホスト依存 flavour 化を構造的に禁止）。
   PyO3 の host ≥ target 制約（§1.3）は CI 解釈系の bump（3.12）と t セルの
   `3.15.0-rc.2` host で満たす。
4. **abi3t は v1 非 PGO**（D2 決定 — 根拠は §6）: トレーニングワークロード
   （`scripts/pgo/train.py`）の t 解釈系での挙動・プロファイル_runtime の
   検証が未了のため。GIL 成果物の PGO パイプライン（Plan‑2）は無変更。
5. **サイズ予算**（D1 決定）: 本数 8 化により合計 ≤ 20 MB（R6 ハード上限）
   は物理的に不成立（現行 4 本で 18.1 MB = 90.6 %）。**合計上限を ≤ 40 MB
   へ改定し、位置づけを「目安」へ降格**する（ユーザ指示 2026‑10‑03:
   絶対条件ではない）→ size-budget の合計チェックは**超過時に warning
   （`::warning::` + job summary）を出すが run をブロックしない**。
   本別 ≤ 5 MB / fat 10 MB のハード予算と `found = 8`（成果物欠落）の
   ハード検査は**不変**（本別予算はサイズ方針であると同時に成果物の形状
   契約のため）。
6. **3.10 / 3.11 の切り捨ては互換破壊だが配布契約の範囲内**: pyproject
   `requires-python` を 3.12 へ上げ、3.10/3.11 環境（ComfyUI の文書化
   サポート範囲外・3.10 は EOL 済み）では拡張の import 自体が pip 解決で
   降りない形にする。ローダーにも下限ガードを追加し（§3.3）、フロア未満の
   解釈系では理由を報告してデグレードする。

---

## 3. 設計

### 3.1 ビルド構成（feature 再編）

- `native/Cargo.toml`: workspace 依存 `pyo3 = { version = "0.29.2" }`
  （feature なしへ — 現行の workspace 層 `features = ["abi3-py310"]` は
  撤去。header コメントの `abi3-py310` 言及も同期）。`mm-core` の features:
  - `default = ["extension-module", "stable-abi"]`
  - `stable-abi = ["pyo3/abi3-py312"]`
  - `ft = ["pyo3/abi3t-py315"]`（`stable-abi` と同時有効化を CI ゲートで禁止）
- `mm-core` の description（`abi3-py310` 言及）も `abi3-py312` へ同期。
- 現行の「`--no-default-features` で extension-module を外す」テスト契約は
  維持（version-specific ABI + libpython リンクで単体テスト）。
  native-test の「feature toggle 検証」ステップは新 feature 名へ更新
  （default に `abi3-py312`・`ft` モードに `abi3t-py315`・両立しないこと）。
- GIL 成果物: 現行経路不変（linux zigbuild + PGO / mac・win maturin + PGO）。
  **host 解釈系のみ 3.12 へ bump**（PyO3 の host ≥ target 制約 — §1.3。
  Cargo の feature 変更と CI 解釈系 bump は同一コミットで行い、一時的な赤を
  作らない）。
- abi3t 成果物: 同一ランナーで `--no-default-features --features extension-module,ft`
  としてビルドする（linux は zigbuild、mac は maturin `--features ft` の
  universal2、win は maturin `--features ft`）。**host 解釈系は
  `3.15.0-rc.2`（GIL）**（host ≥ 3.15 制約。maturin/PyO3 が abi3t wheel
  生成に ft host を要求する実測結果が出た場合のみ ft host へ切り替える —
  推測で本番化しない原則）。出力文件名: POSIX `mm_core.abi3t.so` /
  Windows `mm_core.pyd`（howto 命名）。配置先: `native-bin/<tag>t/`。

### 3.2 build-native.sh

- ターゲット追加: `linux-x86_64t` / `linux-aarch64t` / `macos-universal2t` /
  `windows-x86_64t`（`= <tag>t`）。`--size-gate` は t でも同一本別予算。
- GIL wheel の glob を実測値に合わせて更新: `mm_core-*-cp310-abi3-*` →
  `mm_core-*-cp312-abi3-*`（macOS universal2 / Windows の 2 箇所）。t wheel
  の glob は maturin の実タグ命名を実測して決める（PEP 803 の圧縮タグ
  `cp315-abi3.abi3t` から `cp315-abi3t-*` 系が予想 — 実測で確定）。
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
- **GIL 側の下限ガード（v1.1 新設）**: GIL かつ `sys.version_info < (3, 12)`
  は `None` + reason「native core requires CPython 3.12+ (abi3-py312
  floor)」— 3.10/3.11 host では 3.12 stable ABI バイナリの import 試行が
  undefined symbol 系の読みにくい失敗になるため、試行前に可読な理由へ
  変換する（デグレード契約の継承）。loader テストへ該当ケース
  （3.11 → None+reason / 3.12 → tag）を追加（§3.5）。
- モジュール名: t ディレクトリでは POSIX `mm_core.abi3t.so` / Windows
  `mm_core.pyd` を import（`importlib` の suffix 解決に委ねる — t build の
  EXTENSION_SUFFIXES は `.abi3t.so` / `.pyd` を含むことを howto が保証）。
- origin ガード・api_version ハンドシェーク・diagnostics は不変
  （diagnostics に `freeThreaded: bool` を追加）。

### 3.4 CI（native.yml / ci.yml）

> **表記の注記（v1.5 で追加）**: 以下で `3.15.0-rc.2t` / `3.15t` と書くのは
> 「free‑threaded ビルド」の意味。実装は setup‑python の `t` サフィックスが rc 版で
> 非対応のため（付録 B10）、**全セルが `python-version: "3.15.0-rc.2"` +
> `freethreaded: true` の組**で表現されている（run 名も `…, 3.15.0-rc.2, true`）。
> よって D4 の振替は 9 箇所すべてを `"3.15"` に置くだけで済み、`3.15t` という
> 文字列は登場しない（§6 D4‑5）。

- **解釈系 bump（Step 1）**: ci.yml verify の `python-version: "3.11"` ×1 と
  native.yml の ×6（native-test / native-build-linux ×2 /
  native-build-macos / native-build-windows / integration）を **3.12** へ。
  t ビルド・t smoke・t integration のセルは **`3.15.0-rc.2` /
  `3.15.0-rc.2t`**（D4 ピン）。
- `native-build-linux`: t 2 ターゲットの zigbuild を追加（非 PGO・host
  `3.15.0-rc.2`）。glibc 床ゲートは t 成果物にも適用（readelf ループを
  4 本へ）。
- `native-build-macos` / `-windows`: maturin `--features ft` で t wheel を
  追加ビルド（非 PGO・host `3.15.0-rc.2`）。lipo/extract は §3.2 どおり。
  t 成果物の import smoke は `3.15.0-rc.2`（GIL）と `3.15.0-rc.2t`（ft）の
  両解釈系で実走（D3 の「他 OS は import smoke まで」の実体）。
- `abi3-import`: マトリクスを
  `{3.12, abi3}` `{3.14, abi3}` `{3.15.0-rc.2, abi3t}` `{3.15.0-rc.2t, abi3t}`
  へ拡張。abi3 列は**フロア 3.12 + 現行 stable 3.14** での単一バイナリ主張の
  証明（現行 3.10/3.13 の設計理由「最古 + 現行」を継承 — 3.14.8 は
  manifest の最新 stable）。abi3t 列は GIL 3.15 と t 3.15 の両方で import
  証明 = howto の表の両列を実測。final 公開後は `3.15` / `3.15t` へ表記
  振替（別コミット — D4）。
- `size-budget`: 8 本へ（`found -lt 8` は**ハードのまま**）。合計は
  **40 MB 目安**（D1）: 超過時は `::warning::` annotation + job summary へ
  実測合計と超過率を記録し、**run は緑のまま**。本別 5 MB / FAT 10 MB の
  ハード予算は不変。FAT 検出は内容判定のまま（t fat も cafebabe）。
- `publish-native-bin`: ターゲット辞書 8 エントリ。Windows は GIL/t とも
  `mm_core.pyd` のため、**ディレクトリタグ優先 + 内容分類フォールバック**
  へステージングロジックを改修（upload-artifact の LCA 挙動を考慮し、
  両 windows タグをディレクトリ構造込みで upload）。
- `integration`: ubuntu セルに **t 解釈系（3.15.0-rc.2t）+ linux-x86_64t
  成果物**のフル pytest を追加（フリースレッド soak = 当コアの並行耐性の
  機械証明）。**D3 決定: v1 は ubuntu のみ** — mac/win の t は各 build job の
  import smoke（GIL + ft）でカバーする（根拠は §6）。
- native-test の feature toggle 検証: assert を `abi3-py310` →
  `abi3-py312` へ更新し、`ft` モード（`abi3t-py315`）と排他性の検証を
  追加（§3.1）。
- `ci.yml`: 解釈系 bump 以外は変更不要（成果物なしセルはローダー skip の
  まま）。
- `fuzz-smoke` / `fuzz-long`: 変更不要（codec 表面不変・純 Rust ワーク
  スペースは Python host を使わない）。

### 3.5 Python/フロント/配布メタ

- `pyproject.toml`: `requires-python = ">=3.12"`・ruff `target-version = "py312"`・
  **mypy `python_version = "3.12"`**（現行 "3.11" — v1.0 インベントリの
  見落とし、v1.1 の実査で追加）。`requirements.txt` との同期テストは不変
  （依存リスト無変更）。
- **`uv lock` 再生成**: uv.lock 冒頭の `requires-python = ">=3.10"` と
  resolution-markers は pyproject に連動する（lock の新鮮さを検査する CI
  ゲートは無いことを確認済みだが、整合のためコミットに含める）。
- **ruff target bump の伴生修正（実測済み）**:
  `tests/test_phase8_distribution.py` の I001 のみ — `import tomllib` を
  stdlib ブロック（`import re` の隣）へ移動する。
- `tests/test_phase0_native_loader.py`: タグ表へ t 4 種と ft 検出の
  monkeypatch ケース（`Py_GIL_DISABLED` / `sys.abiflags` / version 境界
  3.14t→None+reason / 3.15t→tag+t）+ **GIL 下限ガードのケース**
  （3.11→None+reason / 3.12→tag）を追加。
- `tests/test_phase8_distribution.py`: **v1.0 §3.5 の「K16 スモークの解釈系
  下限を 3.11 へ更新」は訂正する — 実査の結果、同ファイルに解釈系下限の
  アサートは存在しない**（K16 の言及は .gitignore / publish 文言のテキスト
  ピンのみ）。本計画での変更は上記 I001 修正のみ。
- `scripts/verify_native_binary.py`: t タグの ELF/Mach-O/PE 検査を許可
  （判定ロジックはタグ直交）。
- `py/utils.py` の `tomllib` try/except ガードは残置（floor 3.12 で無条件
  利用可能になるが、ガードは無害 — 変更しない）。
- web/・i18n・ロケール: 影響なし（ビルド不要）。

### 3.6 ドキュメント

- README×4 / USAGE×4: 「CPython 3.10 and newer」→「CPython 3.12 and newer
  (GIL builds); free-threaded builds are served by the abi3t artifacts on
  CPython 3.15+」へ。「proven against 3.10 and 3.13 in CI」→「proven
  against 3.12 and 3.14 (abi3) + 3.15 / 3.15t (abi3t) in CI」。ruff target
  の記述 `py310` → `py312`。エンジン表へ t 4 行を追加（成果物名・要件）。
  トラブルシューティングへ t‑3.13/3.14 の理由行を追加。
- バッジ: `Python-3.10%2B` → `Python-3.12%2B`・PyO3 バッジを
  `0.29 · abi3-py312 + abi3t-py315` へ・プラットフォーム行へ
  `CPython 3.15+ free-threaded (abi3t)` バッジを 1 本追加。
- `native/README.md`: `abi3-py310` 言及 ×3（feature 節・requires-python
  整合行・検証表）の更新、feature 構成・t ビルド手順・検証表（8 本）を
  追記。`native/Cargo.toml` header コメントと `mm-core` description の
  言及も同期（§3.1）。
- `scripts/pgo/README.md`: abi3t は v1 非 PGO の旨を追記（D2 決定済み）。

---

## 4. 実施計画（Step 総覧）

| Step | 名称                                              | 主成果物                                                     | 完了条件（要約）                                                       |
| ---- | ------------------------------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------- |
| 1    | floor 3.12 化（abi3-py312）                       | Cargo/pyproject/ruff/mypy/uv.lock/CI 解釈系+マトリクス/文書  | 全ゲート緑 + abi3-import 3.12/3.14 緑 + ruff py312 緑（I001 修正込み） |
| 2    | abi3t feature 構成とビルド経路                    | mm-core features・build-native.sh・maturin 経路（host rc.2） | 4 t 成果物のローカル/CI ビルド緑 + サイズゲート                        |
| 3    | ローダー ft 検知・下限ガードと t タグ配信         | py/native.py・loader テスト                                  | 3.15/3.15t import smoke 緑 + 境界 reason テスト緑（3.11/3.14t）        |
| 4    | CI 拡張（abi3-import/size/publish/integration-t） | native.yml                                                   | 8 本配信 + t integration 緑 + publish 8 エントリ実証                   |
| 5    | 文書・バッジ・記録                                | README×4/USAGE×4/native/README/MEMO                          | prettier 緑 + dev CI 緑 + ユーザマージ後 publish 確認                  |

各 Step は独立コミット・独立 revert（Plan §6.3 継承）。**D1–D4 はすべて
決定済み（§6）**のため、各 Step はユーザ決定待ちなしで着手できる。

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

## 6. 決定事項（D1–D4 — 決定済み）

| #   | 事項                                    | 決定（2026‑10‑03）                                                |
| --- | --------------------------------------- | ----------------------------------------------------------------- |
| D1  | native-bin 合計サイズ上限（R6）         | **≤ 40 MB・「目安」**（ユーザ決定 — 絶対条件ではない）            |
| D2  | abi3t 成果物の PGO（v1）                | **非 PGO**（提案採用 — 根拠は下記。GIL 側は PGO 維持）            |
| D3  | t integration セルの OS 範囲（v1）      | **ubuntu のみ**＋他 OS は import smoke（提案採用 — 根拠は下記）   |
| D4  | CI の 3.15 表記（rc ピン → final 振替） | **manifest への final 着弾確認後の別コミット**（提案採用 — 下記） |

### D1 — サイズ合計 40 MB・目安化（ユーザ決定）

8 本体制では現行の合計 ≤ 20 MB ハード上限は物理的に不成立（現行 4 本で
18.1 MB = 90.6 %）。ユーザ指示により **≤ 40 MB へ改定し、位置づけは
「目安」（絶対条件ではない）**。CI 実装（Step 4）:

- size-budget の**合計チェック**: 40 MB 超過時に `::warning::` annotation と
  job summary 行（実測合計・超過率）を出す — **run は緑のまま**。
- **本別ハード予算は不変**: 1 本 ≤ 5 MB / FAT（universal2・t 含む）≤ 10 MB
  の超過は従来どおり赤（単一成果物の暴走・LTO 構成壊れを検出する本来の面）。
- `found = 8`（成果物欠落）も従来どおり赤（サイズ目安ではなく形状契約）。
- 合計実測値は毎 run の job summary へ記録し、MEMO でトレンドを追う
  （R5 緩和）。

### D2 — abi3t v1 非 PGO（根拠）

1. **検証基盤が未了**: 現行 PGO パイプライン（train.py 30 セクション +
   G1/G2 ゲート）の実証はすべて GIL 解釈系でのもの（runs #106–#109・
   G2 の決定論的形状 7,618/1,052/13.81 %/877 が 3 run 完全再現）。
   t 解釈系での LLVM profile runtime の挙動（profraw 生成・merge・G2 形状の
   再現性）は未実測であり、未実測のまま組み込むと「間違ったプロファイルで
   焼いた成果物」を出荷するリスクがある。macOS fat dylib × 計装ビルドの
   終了時 SIGSEGV 前例（Plan‑2 §4.4 判断 (c) = macOS 非 PGO 化）は、
   「未検証の PGO 組み合わせが出荷を壊す」の実例。
2. **プロファイルの移植性が低く、利得が不確実**: フリースレッド CPython は
   GIL build とオブジェクトヘッダ/参照計数の実装が異なる（3.13t で導入され
   3.15 で再び変更）。GIL 側ですら実測利得は定常 ×1.10–1.13 と中程度
   （BENCH §13.7）で、t build ではまず「動くこと・並行耐性の証明」を固める
   のが優先（R3）。性能最適化は ft エコシステムの成熟後（R2）でも遅くない。
3. **マトリクス時間**: t ビルドは 3 プラットフォーム分追加される。PGO
   （計装ビルド + train + 最適化リビルド）を重ねると native.yml の実走時間が
   およそ倍増し、G4（run ≤ 20 分）の運用目標と衝突する。
4. **後追いのコストが低い**: 3.15 の ABI は rc1 で凍結済み、成果物は
   ディレクトリ分離（`<tag>t/`）のため、後の PGO 化は別計画でビルドステップ
   を差し替えるだけでアーキテクチャ変更を要しない。

→ **v1 は非 PGO・GIL 側の PGO は不変**。`scripts/pgo/README.md` に明記する。

### D3 — t integration は ubuntu のみ（根拠）

1. **証明対象が OS 非依存**: t フル pytest の目的は、フリースレッド下での
   mm_core の API 挙動・並行耐性の機械証明（R3）。同一 Rust ソース・同一
   スイートなので 1 セルで証明は足りる — プラットフォーム差は PyO3/CPython
   層が吸収する部分が本体で、それは次の 2 がカバーする。
2. **プラットフォーム固有リスクは smoke で網羅**: OS 毎に違うのはロード面
   （POSIX `.abi3t.so` / Windows `.pyd` の命名、loader の flavour 検出、
   Mach-O/PE 形式）だけ。mac/win の t は各 build job の import smoke
   （`3.15.0-rc.2` + `3.15.0-rc.2t` の両 flavour）+ linux 成果物を使う
   abi3-import 4 セルで実証される。
3. **コストと flake 面**: mac/win t のフル pytest は 2 セル追加（torch/L5 の
   ubuntu 専用基盤は t に流用できず別途 setup が必要）で、非決定性の露出が
   増える（run #98 の fresh-boot watcher flake 前例 = セル数と flake 遭遇率は
   比例）。ubuntu セルは既存の torch/L5 基盤の隣に 1 セル足すだけで済む。
4. **後から拡張可能**: manifest 上 mac/win にも ft ビルドは実在する
   （win32 x64/arm64/x86 — 2026‑10‑03 再検証、付録 B10）。ユーザ報告や
   flake が出た時点でセル追加でき、アーキテクチャ変更は不要。

### D4 — rc ピン → final 振替は別コミット（根拠）

1. **final を待てない**: 2026‑10‑03 現在、3.15.0 final は未着
   （python.org の最新 stable = 3.14.8・3.15 = rc3・devguide の状態は
   prerelease、first release 予定 2026‑10‑01 は過ぎている）。python-versions
   manifest の ft ビルドも **rc.2 まで**（rc.3 の ft は未掲載 — 付録 B10）。
   final 公開まで実装をブロックすると日程が不定になる。
2. **ABI 凍結により rc 成果物は final に対して有効**: rc1 の宣言「no ABI
   changes from this point forward in the 3.15 series」→ 振替時に t 成果物の
   再ビルドは不要で、振替は **CI の表記だけの変更**になる。
3. **別コミット原則**: 表記振替と機能実装を分けると履歴がクリーンで、
   独立 revert ができる（Plan §6.3 継承）。振替条件は「manifest に
   `3.15.0`（stable）+ ft ファイルが出現」で機械的に判定でき、Step 4 の
   フォローアップ規程として明文化する。
4. **実行者**: final 公開の確認後にユーザが実施、またはエージェントへ指示
   （GitHub Actions / 公開状況の確認はターン制でユーザが担う現行運用どおり）。
5. **振替の実体（2026‑10‑03 に実ファイルで精密化 — v1.5）**: 対象は native.yml の
   `python-version: "3.15.0-rc.2"` **9 箇所**（L353 native‑build‑linux の t ホスト /
   L377 その py315t smoke / L459・L470 macOS の 2 ホスト / L538・L546 Windows の
   2 ホスト / L586・L589 abi3‑import の abi3t 2 セル / L721 integration の t セル）と、
   それを参照するコメント 5 箇所（L10 / L347 / L453 / L531 / L571）。
   **`3.15t` という文字列は書かない** — ft セルは setup‑python の
   `freethreaded: true` 入力で切替わる（rc 版は `t` サフィックス非対応、付録 B10）ので、
   9 箇所を `"3.15"` に置くだけで両 flavour をカバーする。ci.yml / fuzz‑long.yml に
   対象なし（grep 実測 0 件）。行番号は v1.5 時点のもの。
6. **実施条件の機械判定（2026‑10‑03 実測の手順）**:
   `actions/python-versions` の `versions-manifest.json` に `version: "3.15.0"` かつ
   `stable: true` かつ freethreaded ファイルを含むエントリが出現したら実行可。
   当日時点は `3.15.0-rc.2`（`stable=False`・ft 13 本）が最新で、upstream のタグは
   `v3.15.0rc3` まで（**PEP 790: rc3 = 2026‑10‑02 実績 / final = 2026‑10‑09 予定**）。
   振替コミットは `save-if` 等の CI 変更と混ぜず単独で（独立 revert のため）。

---

## 7. リスク管理

| #   | リスク                                               | 確率 | 影響 | 緩和策                                                                                                                                                                      | Step |
| --- | ---------------------------------------------------- | ---- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| R1  | 3.15 final 遅延による CI 表記揺れ                    | 中   | 小   | rc ピン（ABI 凍結宣言済み・rc.2 が manifest 最新）+ D4 の振替コミット規程                                                                                                   | 4    |
| R2  | ComfyUI 本体の t 環境未成熟（依存が GIL を再有効化） | 高   | 小   | abi3t は t/GIL 両 build で import 可能＝環境が整った瞬間に機能。デグレード契約は不変                                                                                        | 全   |
| R3  | フリースレッド下での当コア並行耐性                   | 中   | 中   | PyO3 0.29 の ft サポート（Send/Sync 強制）+ t integration セルのフル pytest（D3 = ubuntu）で機械証明。flake 時は t セルを smoke へ降格し別計画へ移管                        | 4    |
| R4  | maturin の abi3t wheel 命名が howto と不一致         | 低   | 中   | 実測確認 → 不一致なら cargo 直接経路（§3.2 フォールバック）                                                                                                                 | 2    |
| R5  | サイズ合計目安（40 MB）超過の見逃し                  | 中   | 小   | D1 決定済み: size-budget が毎 run の job summary へ実測合計 + 超過時 warning を記録（run はブロックしない）。本別ハード予算が単一成果物の暴走を防止。トレンドは MEMO へ記録 | 4    |
| R6  | feature 同時有効化による flavour のホスト依存化      | 中   | 中   | 排他 feature 構成 + native-test の toggle ゲートを 3 feature 軸へ拡張（§3.1）                                                                                               | 1–2  |
| R7  | Windows の t/GIL 同文件名（`mm_core.pyd`）の取り違え | 中   | 中   | ディレクトリタグ優先の staging（§3.4）+ publish の重複検出（現行の `duplicate artifact for tag` 系）を 8 タグへ拡張                                                         | 4    |
| R8  | floor 3.12 による 3.10/3.11 ユーザの排除             | 低   | 小   | 両版は ComfyUI の文書化サポート範囲外（3.10 は EOL 済み）。`requires-python` が pip 解決層で防止 + ローダー下限ガード（§3.3）が理由付きデグレードへ変換 + 文書で下限を明記  | 1・3 |

---

## 付録 A: 現行資産の影響面インベントリ（2026‑10‑02/03 実査）

- `native/Cargo.toml`（workspace pyo3 `features = ["abi3-py310"]` + header コメントの言及）/ `native/crates/mm-core/Cargo.toml`（description の `abi3-py310`）
- `pyproject.toml`（requires-python `">=3.10"` / ruff target `"py310"` / **mypy `python_version = "3.11"`**）/ **`uv.lock`**（冒頭 requires-python + resolution-markers → `uv lock` 再生成）/ `py/native.py`（platform_tag / reason / diagnostics — 下限ガード追加）
- `.github/workflows/ci.yml`（**`python-version: "3.11"` ×1**）/ `.github/workflows/native.yml`（**`python-version: "3.11"` ×6**・abi3-import マトリクス 3.10/3.13・size-budget 4 本/20 MB ハード・publish 4 タグ辞書・toggle ゲートの abi3-py310 assert・glibc ループ 2 本）
- `scripts/build-native.sh`（4 ターゲット case / extract_from_wheel / **wheel glob `cp310-abi3` ×2**）/ `scripts/verify_native_binary.py`（タグ表）
- `tests/test_phase0_native_loader.py`（タグ/パス）/ `tests/test_phase8_distribution.py`（**I001: `import tomllib` の位置 — ruff target py312 で実測した唯一の新規違反**。解釈系下限アサートは存在しない = v1.0 §3.5 の記述を訂正済み）
- README×4（バッジ Python 3.10+ / PyO3 abi3 / エンジン表「CPython 3.10 and newer」/「proven against 3.10 and 3.13」/ ruff `py310` 言及 / PGO 文）/ USAGE×4（エンジン表・トラブルシューティング）/ `native/README.md`（abi3‑py310 ×3・検証表）/ `scripts/pgo/README.md`
- 履歴文書（Plan.md / Plan-2.md / BENCH.md / MEMO.md）と bench 結果 JSON（`python: 3.11.2` 等の記録）は**改訂しない**（時点記録のため）。

## 付録 B: 一次ソース一覧（2026‑10‑02 調査・B8–B11 は 2026‑10‑03 再検証）

| #   | 対象                                                   | ソース                                                                                                                                                                                                                                                                                                                                   |
| --- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1  | Python 3.10 EOL（2026‑10‑01 到達）・3.12 EOL 2028‑10   | devguide.python.org「Status of Python versions」（2026‑10‑03 再確認: 3.10 = end-of-life 2026‑10‑01 / 3.11・3.12 = security / 3.15 = prerelease）                                                                                                                                                                                         |
| B2  | ComfyUI の Python サポート集合                         | docs.comfy.org「System Requirements」（3.13 推奨 / 3.14 動作 / 3.12 フォールバック / ft は「完全サポートではない」）                                                                                                                                                                                                                     |
| B3  | 3.15.0rc3（final 未着）・ABI 凍結                      | python.org/downloads/source（rc3 = Oct. 2, 2026）・3.15.0rc2 ページの「no ABI changes from this point forward」・python.org/downloads の最新 stable 表示 = 3.14.8（2026‑10‑03 確認）                                                                                                                                                     |
| B4  | abi3t の定義・命名・対応範囲                           | PEP 803・CPython 3.15 howto「Migrating to Stable ABI for free threading (abi3t)」（`.abi3t.so` / Windows `.pyd` / 3.15+ t+GIL）                                                                                                                                                                                                          |
| B5  | PyO3 0.29.2 の abi3t feature                           | pyo3.rs/v0.29.2/features（`abi3t` / `abi3t-py315`・両 feature 同時有効化のホスト依存挙動）                                                                                                                                                                                                                                               |
| B6  | maturin の abi3t サポート（≥1.14）                     | maturin.rs changelog（#3113）・PyO3/maturin#3064（2026‑07‑20 close）                                                                                                                                                                                                                                                                     |
| B7  | setup-python の t 構文                                 | actions/setup-python #973                                                                                                                                                                                                                                                                                                                |
| B8  | PyO3 0.29.2 の `abi3-py312`・host ≥ target 制約        | pyo3.rs/v0.29.2/features（ラダー `abi3-py38 … abi3-py314` 明記）・docs.rs/crate/pyo3/0.29.2/features（feature 一覧に `abi3-py312` / `abi3t-py315` 実測）・pyo3.rs/v0.29.2/building-and-distribution（「only able to link … up to and including your host Python version」「free-threaded build … cannot load abi3 wheels」）— 2026‑10‑03 |
| B9  | ruff 0.16.9 の py312 target 有効性と repo への実測影響 | `ruff check --help` possible values = py37…py315（CI ピン版で実測）+ リポジトリ全対象の py312 再実行 = 新規違反 I001 の 1 件のみ / `ruff format --check` 43 files 緑 — 2026‑10‑03                                                                                                                                                        |
| B10 | python-versions manifest の 3.15.0‑rc.2 ft 網羅        | actions/python-versions versions-manifest.json（2026‑10‑03: 3.15 系最新 = rc.2。ft = darwin arm64/x64・linux 22.04/24.04/26.04 arm64/x64・rhel 9/10・win32 x64/arm64/x86。rc.3 ft 未掲載）                                                                                                                                               |
| B11 | uv.lock / mypy / ci.yml の現状値                       | 本リポジトリ実査（uv.lock 冒頭 `requires-python = ">=3.10"`・pyproject `[tool.mypy] python_version = "3.11"`・ci.yml `python-version: "3.11"` ×1・native.yml ×6）— 2026‑10‑03                                                                                                                                                            |

---

_本計画書は 2026‑10‑02/03 の一次ソース調査と本リポジトリの実査に基づく
（v1.1 = 2026‑10‑03 のユーザ決定〔floor 3.12・D1 目安化〕と D2–D4 の根拠
提示を反映）。実装着手はユーザ承認後とし、各 Step の完了条件を満たさない
状態で次へ進まない（Plan §6.3 継承）。_
