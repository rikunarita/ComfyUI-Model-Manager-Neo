# ComfyUI-Model-Manager-Neo 脆弱性スキャン体制 総合力計画書

## ― CodeQL（default setup）＋ OSV-Scanner ＋ Gitleaks ＋ zizmor の 4 層ゲート構築と、実測検出（OSV 10 件・zizmor 142 件・gitleaks 誤検知 1 件）の全量対処 ―

| 項目           | 内容                                                                                                                                                                   |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 文書番号       | NEO-PLAN-2026-004                                                                                                                                                      |
| 版数           | 1.0                                                                                                                                                                    |
| 作成日         | 2026-10-07                                                                                                                                                             |
| 対象リポジトリ | `rikunarita/ComfyUI-Model-Manager-Neo`                                                                                                                                 |
| 対象ブランチ   | `dev`（コミット・プッシュはすべて dev — 恒久規程）                                                                                                                     |
| 前提文書       | [`MEMO.md`](MEMO.md)・[`environment-report.md`](environment-report.md)・旧計画書（NEO-PLAN-2026-001/002/003 — git 履歴参照: `git show bd1bb97^:Agent/Plan-3.md` ほか） |
| 状態           | **Step 0（ユーザ設定）待ち ＋ コード側 Step 1 以降は着手可 — 進捗 0/11 Step・最終更新 2026-10-07（v1.0 策定）**                                                        |

### 版数履歴

| 版  | 日付       | 変更                                                                                                                                                                                                                                                                                                                   |
| --- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.0 | 2026-10-07 | 初版。2026-10-07 セッションの徹底調査（Web 一次ソース 24 点 — 付録 B）とツール実測（osv-scanner 2.6.0 / gitleaks 8.30.1 / zizmor 1.30.1 / ruff 0.16.9 — §1.2）に基づき策定。ユーザが採用ツール全部（CodeQL・OSV-Scanner・Gitleaks・zizmor・uv audit 観察・ruff S・eslint-plugin-security）と実測検出の全量対処を可決。 |

### 進捗マーク凡例

| マーク  | 意味                     |
| ------- | ------------------------ |
| `- [x]` | 完了                     |
| `- [/]` | 進行中                   |
| `- [ ]` | 未着手                   |
| `- [!]` | ブロック（ユーザ待ち等） |

**進捗更新規程**: 各セッションの終了時に、(1) 各 Step のチェックリスト、(2) §9 進捗管理表、(3) ヘッダ表「状態」行の完了 Step 数と最終更新日、(4) §10 進捗ログへの追記 — の 4 点を必ず更新する。完了の定義は §8 検収基準に従い、証跡（run 番号・コミット SHA・実測出力）を §10 に残す。

---

## エグゼクティブサマリー

1. **5 層の脆弱性スキャン体制を構築する**: SAST = **CodeQL**（default setup・Extended クエリスイート・Copilot Autofix）、SCA = **OSV-Scanner**（公式 reusable workflow・PR 差分＋定期フル・SARIF）、シークレット = **Gitleaks**（全履歴＋カスタム設定）、CI/CD 設定 = **zizmor**（SARIF・0.3 秒）、Python ネイティブ監査 = **uv audit**（preview 観察枠・非ブロッキング）。
2. **実測検出を全量対処する**: OSV-Scanner 10 件（source-map-js 修正、braces/bincode/paste は理由付き accept・ignore 記録、requirements.txt 下限シグナル 6 件は uv.lock 権威化でトリアージ）、zizmor 142 件（template-injection 2 error 修正、artipacked・excessive-permissions 是正、unpinned-uses は SHA ピニング移行＋dtolnay 文書化例外）、gitleaks 1 件（誤検知の allowlist 記録）。
3. **GitHub 標準機能をユーザ設定で補完する**（Phase 0 — §5）: CodeQL default setup、Dependency graph、Dependabot alerts ＋ security updates、Private vulnerability reporting。API 実測で Dependabot alerts は現状 **disabled**（= SCA の継続監視が皆無）であるため優先度が高い。
4. **極限活用の方針**: SARIF の単一集約（GitHub Security タブへ CodeQL/OSV/zizmor の 3 ソース）、PR 差分ゲート＋定期フルスキャンの二本立て、**ゲート発火テスト**（mutation 規律 — 「意図的に混ぜて失敗、復元して成功」を全ゲートで実証）、SHA ピニング、uv の OSV マルウェアチェック（`UV_MALWARE_CHECK=1`）試用、既存ツール内強化（ruff S rules・eslint-plugin-security）。
5. **本プロジェクトの CI 制約との完全両立**: 新規ゲートはすべて DB ダウンロード無し・Actions キャッシュ不使用・秒〜分級（実測: OSV 3 秒 / gitleaks 11 秒 / zizmor 0.3 秒）・全ジョブ `timeout-minutes` 設定（6 時間ハング前例への対策規程）・CodeQL default setup はワークフローファイル不要でキャッシュ逼迫履歴（96.5%）と衝突しない。

**主要数値サマリー**

| 指標                                    | 現行（2026-10-07 実測）                              | 本計画後                                                              |
| --------------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------- |
| 脆弱性スキャン CI ゲート                | 0                                                    | 4 系（CodeQL / OSV-Scanner / Gitleaks / zizmor）＋ uv audit 観察      |
| 既知脆弱性（OSV 実測）                  | 10 件（High 5・Medium 3・Unknown 2）                 | 0 件（修正 1＋accept/ignore 記録 3＋下限シグナル 6 はトリアージ記録） |
| Actions セキュリティ検出（zizmor 実測） | 142 件（error: template-injection 2・unpinned 多数） | 0 件（dtolnay/rust-toolchain の floating は文書化例外）               |
| シークレット履歴走査                    | 未実施（実測で誤検知 1 件）                          | 全履歴緑（allowlist 1 件を理由付き記録）                              |
| Dependabot                              | alerts Off・dependency graph Off                     | alerts On＋security updates On＋dependabot.yml（npm/cargo/uv）        |
| CodeQL                                  | 未設定                                               | default setup（Extended＋Autofix・JS/TS＋Vue・Python・Rust・Actions） |
| Python セキュリティ lint                | ruff S 未有効（実測 805 件・生産コード実質 ~22 件）  | S 有効化＋トリアージ済みで緑                                          |
| JS セキュリティ lint                    | なし                                                 | eslint-plugin-security（flat config）有効化＋トリアージ済みで緑       |
| unpinned action 参照                    | 10 参照（すべて tag ピン）                           | 0（dtolnay 2 参照は文書化例外）                                       |

---

## 1. 背景と一次事実

### 1.1 リポジトリ現状（2026-10-07 実測）

- **GitHub API 実測**（PAT・読み取り専用）: `secret_scanning=enabled` / `secret_scanning_push_protection=enabled` / `dependabot_security_updates=disabled` / `secret_scanning_non_provider_patterns=disabled` / `secret_scanning_validity_checks=disabled`。`GET /vulnerability-alerts` → 404、`GET /dependabot/alerts` → 403「Dependabot alerts are disabled for this repository」= **SCA が皆無**。
- **設定画面**（ユーザ提供 PDF・2026-10-07 20:30）: Dependency graph **Off** / Dependabot alerts **Off** / CodeQL analysis **未設定**（「Set up」ボタン）/ Copilot Autofix 節あり / AI Scan（Preview）節あり / Grouped security updates Off / Push protection **On**（Security alert severity level: High or higher・Standard alert severity level: Only errors）。
- **CI**: 4 ワークフロー（`ci.yml` / `native.yml` / `fuzz-long.yml` / `cache-cleanup.yml`）にセキュリティゲート皆無。`.github/dependabot.yml` 無し・`SECURITY.md` 無し。`pull_request_target` 不使用（実測 grep 0 件）。actionlint は検証に導入済み（MEMO §5.4）。
- **ロックファイル 4 本**: `pnpm-lock.yaml`（492 pkg）/ `uv.lock`（60 pkg）/ `native/Cargo.lock`（153 crate）/ `requirements.txt`（4 pin・loose。pyproject と `tests/test_phase8_distribution.py` が機械同期）。
- **シークレット実害面**: API キーは `private.key`（pickle・gitignore 済み）に保存 → 誤コミット時の実害が大きく、履歴走査＋pre-commit 阻止の価値が高い。
- **CI 運用制約**（MEMO §4.1 より継承）: Actions キャッシュは 10 GB/repo 上限で逼迫前例（96.5%）あり・`save-if` 規律と `cache-cleanup.yml` 運用中。apt ステップは 6 時間ハング前例あり（`timeout-minutes: 10` 規律）。runner は `GITHUB_TOKEN` を step env へ自動注入しない（明示 `env:` 必須）。GH Actions の更新は 1 action ずつ別コミット。

### 1.2 ツール実測（2026-10-07・開発サンドボックス 2 vCPU / 1 GiB・本リポジトリ dev tip `022543e` against）

| ツール          | 版数   | 対象                                          | 所要    | 結果                                                                                                                                                                                                     |
| --------------- | ------ | --------------------------------------------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| osv-scanner     | 2.6.0  | 4 lockfile（709 packages）                    | 3.0 秒  | **10 脆弱性**（High 5・Medium 3・Unknown 2・fixable 7）— 詳細は付録 A                                                                                                                                    |
| gitleaks        | 8.30.1 | git 全履歴 333 commits / 47.06 MB             | 11.3 秒 | **1 件 = 誤検知**（`generic-api-key`・`native/crates/znn-codec/src/dtype.rs:49` の //! doc コメントが Python 例外 `KeyError: torch.complex128` を引用したもの）                                          |
| zizmor          | 1.30.1 | `.github/` 4 ワークフロー（--offline）        | 0.27 秒 | **142 件**（high 73 / medium 12 / low 13 / info 6・38 suppressed・29 unsafe fixes）— `template-injection` error ×2、`unpinned-uses` 多数、`artipacked` 複数（auto-fix 可）、`excessive-permissions` 多数 |
| ruff --select S | 0.16.9 | `py/ __init__.py tests/ scripts/ conftest.py` | 0.1 秒  | **805 件**（S101 assert ×783 = tests 由来が支配的、S110 ×10、S106 ×3、S108 ×2、S603 ×2、S301 ×2、S310 ×2、S112 ×1）                                                                                      |

**zizmor の template-injection error 2 件の具体**（実測出力）:

- `cache-cleanup.yml:97` — `days="${{ github.event.inputs.older_than_days || '0' }}"` を run ブロックへ直接展開
- `fuzz-long.yml:91` — `HOURS="${{ github.event.inputs.hours || '3' }}"` を同様に直接展開
- （info ×1: `native.yml:413` — 同パターン系。confidence 低）

いずれも `workflow_dispatch` input（write 権限者しか発火不能）のため実害可能性は低いが、env バインド化が定石修正であり zizmor ゲート緑化に必要。

**OSV API での advisory 個別確認**（実測）:

- `RUSTSEC-2025-0141` = 「Bincode is unmaintained」（修正版なし・informational）
- `RUSTSEC-2024-0436` = 「paste - no longer maintained」（修正版なし・informational）
- `GHSA-vfj7-8cjw-p6xm` = CVE-2026-93687・braces の stack-exhaustion DoS（HIGH・`last_affected: 3.0.3` = **修正版なし**）
- `GHSA-68fv-2mgg-jv7q` = CVE-2026-93749・source-map-js の event-loop DoS（HIGH・**fix 1.2.2**）

**requirements.txt 由来 6 件（httpx2/httpcore2 2.9.1）の正体**: `uv.lock` の実解決は **httpx2/httpcore2 2.13.1（無影響）**であることを実測確認。requirements.txt は loose pin（`huggingface_hub>=1.32.0` 等）のため、OSV-Scanner の manifest 解決が下限近傍の版を報告したもの。公式ドキュメントも「manifest から報告された版は実際にインストールされる版と限らない」と明記（付録 B7）。ユーザー環境の実 `pip install` も最新版へ解決される。**よって 6 件は「宣言レンジが脆弱版を許容している」シグナルであり、実環境の脆弱性ではない** — トリアージ記録（D3）で扱う。

### 1.3 Web 調査の一次事実（2026-10-07 調査・出典は付録 B）

- **CodeQL**: Rust 解析 GA（2025-10-14 changelog・default setup は build mode none = **コンパイル不要**、rust-analyzer が build.rs のみ実行）。`.vue` は JavaScript の公式抽出拡張子。CodeQL 2.26.3（2026-08-19）で **Vue Composition API のフローモデリング追加**（`ref`/`shallowRef`/`toRef`/`reactive`/`computed`・Vue Router `useRoute()` を remote flow source 化）— 本プロジェクトのフロントエンドはまさにこの API 群を使用。GitHub Actions クエリ（cache poisoning・template injection・untrusted checkout 等）は default/advanced 両 setup で利用可（2024-12-17）。**公開リポジトリは無料**（CodeQL CLI・code scanning とも）。default setup は CodeQL 全対応言語に利用可で、クエリスイートは **default / security-extended（UI 表記「Extended」）** から選択可。**Copilot Autofix は公開リポジトリ無料**（2024-09-17）かつ CodeQL 利用リポジトリで既定有効。default setup の対象は**既定ブランチ（main）への push・main 向け PR・週次スケジュール** — dev への直接 push はスコープ外（→ security.yml が dev push で補完、D1）。
- **OSV-Scanner**: `pnpm-lock.yaml` / `uv.lock` / `Cargo.lock` / `requirements.txt` をすべて公式サポート。OSV.dev は GitHub Security Advisories・**RustSec Advisory Database**・PyPI 系等を統合（= cargo audit / pnpm audit / pip-audit の検出源を包含）。公式 reusable workflow 2 種（PR 差分・フル＋SARIF を Security タブへ）。**guided remediation（`fix`）は npm/Maven のみ** → 是正ループは Dependabot と手動が担う。offline mode あり（OSV DB のローカルダウンロード）。Apache-2.0・SLSA 3。最新 v2.6.0（2026-09-14 ビルド）。
- **Gitleaks**: MIT・150+ 正規表現ルール・SARIF/JSON/JUnit 出力・公式 pre-commit フック・baseline 対応。**`gitleaks-action@v2` は個人アカウントのリポジトリならライセンスキー不要**（本リポジトリは `rikunarita` 個人名義 — 実測 API で確認済み）。代替の TruffleHog は AGPL-3.0・800+ detectors・クレデンシャル有効性検証付きだが、検証（サービスへの認証試行）は本用途で過剰かつ SARIF 非対応 → 不採用。GitHub 標準 secret scanning（有効済み）は push 時の provider pattern 検知が主眼 → Gitleaks は**既存履歴の一括走査・カスタムパターン・ローカル pre-commit** で補完関係。
- **zizmor**: MIT・Rust 製・GitHub Actions / Dependabot / pre-commit 設定のセキュリティ静的解析（template injection・過剰権限・unpinned uses・impostor commits・artipacked 等）。公式 `zizmor-action`（SARIF → code scanning・PR チェック表示）。**arXiv:2601.14455**（2026-01 投稿・9 スキャナ × 2,722 ワークフローの実証研究）が「スキャナ間で解析戦略が根本的に異なり検出に大きなギャップ」を実証 → CodeQL actions クエリとの併用に学術的正当性。2026-10 現在も活発（Trail of Bits / Grafana スポンサー）。
- **uv audit**: 2026-06-08 公式発表（Astral・**preview = 不安定宣言あり**）。`uv.lock` をネイティブ読解・OSV バックエンド・pip-audit 比 **4–10×高速**（第三者実測でも「identical findings, much faster」）。`UV_MALWARE_CHECK=1` で sync 時に OSV の MAL advisories（PyPI 検疫済みマルウェア）を照会しインストール前ブロック。requirements.txt / pylock.toml は将来対応（現行は uv.lock）。
- **Dependabot**: **uv エコシステム公式対応**（2025-03-13〜。`uv.lock` の version/security updates・Astral 公式ガイドに `package-ecosystem: uv` の記載）。設定ファイルは**既定ブランチから読まれる** → dev へのコミットだけでは有効化されず、main へのマージ（ユーザ専任）で発効。
- **pnpm audit**: pnpm 11 で npm の legacy audit endpoint 退役に伴い bulk advisories endpoint へ移行（= データ源は GHSA）。OSV-Scanner と同源のため CI ゲートとしては重複 → ローカルのアドホック用途に留める。
- **不採用の根拠**（調査済み・詳細は前セッション回答）: **Semgrep** — CE は Python/TS/JS/Rust とも「単一関数解析限定・Community rules」（公式 CE 言語表）、Vue 対応は 2021 年の basic support（`<script>` 内 JS マッチのみ）で現行言語表に無く、公式 `semgrep-action` は **deprecated**（2024-04）。**Trivy** — 本プロジェクトにコンテナが皆無、lockfile 走査は OSV-Scanner と重複、脆弱性 DB は ~2 GB 級のダウンロードが必要。**OWASP ZAP** — DAST の標的（常駐 web サービス）が存在しない（ローカル ComfyUI 拡張機能）。**pip-audit** — uv.lock を直接読めず、uv audit（公式後継）に置換。**cargo audit** — RustSec は OSV.dev に収録済み（実測で両 RUSTSEC を OSV-Scanner が検出）。**cargo-deny** — ライセンス構成（GPL-3.0 + AGPL zenwebp）は README/native/NOTICE で手動厳密管理済み。grype / syft / bandit / detect-secrets / Socket / Harden Runner — 重複・過剰・商用・外部 SaaS 依存のいずれか。

### 1.4 実測検出の一覧

付録 A に全件を掲載。**すべて本計画の Step 1–4 で対処する**（accept/ignore も「理由付き記録」をもって対処とみなす — 無記録の放置を禁止）。

---

## 2. 方針

### 2.1 層別アーキテクチャ

```
                     Git Repository (public, GPL-3.0)
                              │
      ┌───────────────────────┼────────────────────────┐
      │                       │                        │
  CodeQL                  security.yml            GitHub 標準
  (default setup・        (push main/dev・PR・     (Dependabot alerts・
   ユーザ設定)             週次・dispatch)          secret scanning・
      │                       │                     push protection)
      │           ┌───────────┼───────────┐                │
      │      OSV-Scanner   Gitleaks     zizmor         dependabot.yml
      │      (PR差分+フル   (全履歴+     (Actions設定    (npm/cargo/uv・
      │       SARIF)        allowlist)   SARIF)          target: dev)
      │           │           │           │
      └───────────┴─────┬─────┴───────────┘
                        ▼
              GitHub Security タブ（SARIF 単一集約）
                        │
        開発側補完: uv audit（観察）・UV_MALWARE_CHECK=1（試用）
                    ruff S rules・eslint-plugin-security（既存ゲート内強化）
```

### 2.2 決定表（2026-10-07 ユーザ可決）

| 層                | ツール                   | 判断                     | 備考                                                              |
| ----------------- | ------------------------ | ------------------------ | ----------------------------------------------------------------- |
| SAST              | CodeQL default setup     | **採用**                 | Extended スイート・Autofix・AI Scan は optional（D7）             |
| SCA               | OSV-Scanner              | **採用**                 | PR 差分＋定期フル・SARIF・ignore 設定                             |
| SCA（是正ループ） | Dependabot               | **採用**                 | alerts/security updates（ユーザ設定）＋ dependabot.yml（Step 5）  |
| シークレット      | Gitleaks                 | **採用**                 | CI 全履歴＋allowlist。pre-commit 統合は optional（O2）            |
| CI/CD 設定        | zizmor                   | **採用**                 | SARIF・fix 活用・zizmor.toml で例外の文書化                       |
| Python 監査       | uv audit                 | **観察付き採用**         | preview のため非ブロッキング（D5）。安定化後にゲート昇格を再評価  |
| Python lint       | ruff S rules             | **採用**（既存ツール内） | per-file-ignores＋個別トリアージ（Step 7）                        |
| JS lint           | eslint-plugin-security   | **採用**（既存ツール内） | flat config recommended（Step 8）                                 |
| SAST（代替）      | Semgrep CE               | 不採用                   | CE 単一関数限定・Action deprecated・CodeQL が上位（§1.3）         |
| コンテナ/SBOM     | Trivy                    | 不採用                   | コンテナ皆無・DB ~2 GB 級・重複（§1.3）。Docker 配布時に再評価    |
| DAST              | OWASP ZAP                | 不採用                   | 標的サービス無し（§1.3）。ホスティング提供時に再評価              |
| Python SCA        | pip-audit                | 不採用                   | uv audit に置換（§1.3）                                           |
| JS SCA            | pnpm audit（CI ゲート）  | 不採用                   | OSV と同源重複。ローカル Ad hoc 用としては残置                    |
| Rust SCA          | cargo audit（CI ゲート） | 不採用                   | RustSec は OSV に収録（実測証明）。cargo-auditable は O3 で再評価 |

（O1–O3 = optional 検討事項: O1 AI Scan preview、O2 gitleaks pre-commit フック統合、O3 cargo-auditable による出荷バイナリへの依存情報埋め込み — いずれも本計画の必須範囲外。O3 はサイズ予算 ≤5 MB/本への影響調査を前提とする）

### 2.3 極限活用の原則

1. **SARIF 単一集約**: CodeQL（ネイティブ）・OSV-Scanner・zizmor の 3 ソースを GitHub Security タブへ集約し、アラートのライフサイクル（triage/dismiss 理由付き）を GitHub UI で管理する。
2. **PR 差分＋定期フルの二本立て**: OSV-Scanner は PR 差分（新規混入のみブロック）＋ push/週次フル（SARIF 更新）。CodeQL default setup は PR チェック（High or higher で fail）＋週次。
3. **ゲート発火テスト（mutation 規律）**: 全ゲートで「意図的に脆弱物を混ぜて失敗 → 復元して成功」を実証する（§6 検証プロトコル）。テスト無しゲートは導入とみなさない。
4. **設定のコード化**: ignore/accept/例外はすべて設定ファイル（`osv-scanner.toml` / `zizmor.toml` / `.gitleaks.toml` / `dependabot.yml`）に**理由コメント付き**で記録し、レビュー可能にする。
5. **SHA ピニング**: 新規 action は導入時点から、既存 action は Step 4 で SHA ピンへ移行（サプライチェーン攻撃面削減。dtolnay/rust-toolchain のみ floating 例外 — D2）。

---

## 3. 設計

### 3.0 Step 0 — ユーザ設定（GitHub UI・ユーザ専任）

§5 に詳細手順。**コード変更ゼロ・セッション側で検証可能**（API 再実測: `GET /repos/.../vulnerability-alerts` → 204、CodeQL 初期 run の完了確認）。

### 3.1 Step 1 — ワークフロー加固（zizmor 検出の是正・ゲート導入前）

**順序の根拠**: ゲート（Step 3）を先に導入すると既存検出で CI が赤になる。先に是正し、ゲートは緑の状態で導入する（各 Step 独立緑の規律）。

- [ ] S1.1 `cache-cleanup.yml:97` の template-injection 修正 — `days="${{ github.event.inputs.older_than_days || '0' }}"` を **env バインド**（`env: DAYS: ${{ ... }}` → `days="$DAYS"`）へ。同ファイルの他 input 展開も一括点検。
- [ ] S1.2 `fuzz-long.yml:91` の同修正（`HOURS`）。`native.yml:413`（info）も同型なら修正。
- [ ] S1.3 **artipacked** 是正: 全 `actions/checkout` を棚卸しし、git 認証を要さない step へ `persist-credentials: false` を追加。**例外**: `publish-native-bin`（main・bot が git push するため credentials 必須）は据え置き、zizmor.toml に理由付き例外記録。
- [ ] S1.4 **excessive-permissions** 是正: 4 ワークフローのトップレベルへ `permissions: contents: read`（最小権限）を置き、必要 job のみ昇格（cache-cleanup の cache 削除 = `actions: write`、publish = `contents: write` 等 — 既存の job 級 permissions は実測で native.yml に 1 箇所あり）。
- [ ] S1.5 検証: `actionlint`（既存ツール）＋ `zizmor --offline` 再走で **error 0**（unpinned-uses は Step 4 まで残置可 — zizmor.toml のポリシーは Step 4 で締める）。dev push で ci.yml / native.yml 全緑を確認。
- [ ] S1.6 コミット規約: 修正は関心ごとに分割（template-injection 群 / artipacked 群 / permissions 群）。日本語 conventional commits（`ci: …`）。

### 3.2 Step 2 — 依存是正とトリアージ記録

- [ ] S2.1 **source-map-js → ≥1.2.2**（CVE-2026-93749・HIGH・fix あり）: `pnpm why source-map-js` で経路確認 → `pnpm-workspace.yaml` の `overrides:` へ `source-map-js: ^1.2.2` を追加（既存の typescript override と同じ機構）→ lockfile 再生成。**環境注意**（MEMO §11.3）: pnpm のサプライチェーン検証（minimumReleaseAge 系）で OOM する場合は一時的な `minimumReleaseAge: 0` ＋ `--lockfile-only` → `install --frozen-lockfile` の手順を使い、**設定はコミット前に復元**。1.2.2 の公開日が 24 h 未満ならクールダウンゲートに阻まれるため、その場合は 1 日待つか前記 workaround。
- [ ] S2.2 `pnpm typecheck` ＋ `pnpm exec vite build`（**web/ 再ビルド — コミット前 pnpm build 規程**）＋ K15 ゲート（`node scripts/bench/front/k15.mjs`）＋ `pnpm fallow:dead` / `fallow:dupes` 緑を確認。source-map-js はビルドツールchain のためバンドル内容不変が期待されるが、**ビルド出力の差分を確認**し、変化があれば理由を記録。
- [ ] S2.3 **osv-scanner.toml** 新設（repo root・スキーマは実装時に公式 configuration doc で確認 — 推測禁止）。記録する ignore/accept:
  - `GHSA-vfj7-8cjw-p6xm`（braces・dev-only ビルドツール・DoS 要求入力はビルド時 glob のみ・修正版無し upstream 待ち）— **accept・upstream 監視**
  - `RUSTSEC-2025-0141`（bincode unmaintained・代替不在〔3.0.0 は名前占拠 placeholder — MEMO §4.1〕・audit 対象は永続インデックスの bincode 符号化のみ）— **accept**
  - `RUSTSEC-2024-0436`（paste unmaintained・proc-macro ユーティリティ・実行時リスク無し）— **accept**
  - `PYSEC-2026-3844/3845/3846/3847/3848/3849` ＋ 対応 GHSA（httpx2/httpcore2 2.9.1・requirements.txt 下限解決シグナル。uv.lock = 2.13.1 が権威、実 pip 解決も最新）— **ignore・理由 = D3**
  - 各エントリに**理由コメント必須**（無記録 ignore 禁止）。
- [ ] S2.4 再実測: `osv-scanner scan source --lockfile ...`（4 本）で **検出 0 件**（設定済み ignore 除く）を確認。実測出力を §10 進捗ログへ転記。

### 3.3 Step 3 — セキュリティゲート導入（security.yml ＋ 設定ファイル）

- [ ] S3.1 `.github/workflows/security.yml` 新設。設計:

```yaml
name: Security
on:
  push:
    branches: [main, dev]
  pull_request:
  schedule:
    - cron: '0 3 * * 1' # 月曜 03:00 UTC — 日曜 18:00 fuzz-long・日曜 03:40 cache-sweep と衝突させない
  workflow_dispatch:
permissions: {}
jobs:
  osv-pr: # PR 差分ゲート（新規混入のみ fail）
    if: github.event_name == 'pull_request'
    uses: google/osv-scanner-action/.github/workflows/osv-scanner-reusable-pr.yml@<SHA> # Step 4 で SHA ピン（導入時は v2.6.0 tag → 同 Step 内で SHA 化）
    permissions:
      actions: read
      security-events: write
      contents: read
  osv-full: # push/定期フル（SARIF → Security タブ）
    if: github.event_name != 'pull_request'
    uses: google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml@<SHA>
    with:
      scan-args: |-
        --lockfile=pnpm-lock.yaml
        --lockfile=uv.lock
        --lockfile=native/Cargo.lock
        --lockfile=requirements.txt
    permissions:
      actions: read
      security-events: write
      contents: read
  zizmor: # Actions 設定解析（SARIF）
    ...
  gitleaks: # 全履歴シークレット走査
    ...
```

- 全 job へ `timeout-minutes`（osv: 30 / zizmor: 15 / gitleaks: 15 — 実測は秒級だが 6 時間ハング前例の規律に従い上限を置く）。
- **Actions キャッシュ不使用**（3 ツールとも DB/キャッシュ不要 — OSV は API クエリ、zizmor/gitleaks はバイナリ DL のみ）。cache 逼迫対策（save-if 規律）の影響ゼロ。
- `osv-scanner.toml` は OSV-Scanner が既定で参照する（設定ファイル名・パスは実装時に公式 doc で確認し、必要なら scan-args へ明示）。
- gitleaks job: `gitleaks/gitleaks-action@v2`（個人アカウント = ライセンスキー不要・実証済み）。PR イベント時は差分走査、push/schedule 時は全履歴が既定挙動 — 実装時に action の README で挙動を確認し、full-history を週次で確実に走る形にする。
- zizmor job: `zizmorcore/zizmor-action`（SARIF → `github/codeql-action/upload-sarif`）。online audit 用に `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` を env 明示（runner は自動注入しない — MEMO §4.1）。
- [ ] S3.2 `.gitleaks.toml` 新設: `dtype.rs` 誤検知の allowlist（path ＋ regex 限定・理由コメント付き）。allowlist は**最小スコープ**（ファイル全体ではなく該当行パターン）にする。
- [ ] S3.3 `zizmor.toml` 新設: unpinned-uses ポリシー（Step 4 完了後は strict）、publish-native-bin の persist-credentials 例外（S1.3）、その他の accepted finding を理由付き記録。
- [ ] S3.4 検証: dev push で security.yml 全 job 緑 → **Security タブへ SARIF 3 ソース（OSV/zizmor/CodeQL〔Step 0 済みなら〕）が反映**されたことを確認（スクリーンショット or API: `GET /repos/.../code-scanning/analyses`）。actionlint 緑。
- [ ] S3.5 1 ワークフロー 1 コミット原則: security.yml＋3 設定ファイルは「ゲート導入」として 1 コミットにまとめる（分割すると中間コミットで CI が赤くなるため。bisect 単位 = ゲート全体）。

### 3.4 Step 4 — SHA ピニング移行

- [ ] S4.1 対象 10 参照を棚卸し（実測リスト）: `actions/checkout@v7` / `actions/setup-node@v7` / `actions/setup-python@v7` / `actions/upload-artifact@v7` / `actions/download-artifact@v8` / `pnpm/action-setup@v6` / `astral-sh/setup-uv@v10.2.0` / `Swatinem/rust-cache@v2` / `dtolnay/rust-toolchain@stable` / `dtolnay/rust-toolchain@nightly`。＋ Step 3 で追加した 3 action（osv reusable ×2・zizmor-action・gitleaks-action・upload-sarif）。
- [ ] S4.2 **dtolnay/rust-toolchain の 2 参照は floating のまま**（`@stable`/`@nightly` は意図的に最新版を追うプロジェクト方針 — MEMO「dtolnay/rust-toolchain@stable・バージョンピン無しの方針どおり」）。`zizmor.toml` に例外＋理由を記録し、tag の後ろに `# ...` コメントで**当該 tag の現時点 SHA を併記**する運用（GitHub 公式推奨表記）にする。
- [ ] S4.3 其余の全参照を**コミット SHA ピン**へ（`@v7 # v7.x.x` 形式で tag をコメント併記）。**1 action 1 コミット**（恒久規程）。SHA は実装時に GitHub API で解決（推測禁止）。
- [ ] S4.4 zizmor.toml の unpinned-uses ポリシーを strict 化し、`zizmor` 再走で unpinned 検出 0（例外 2 参照のみ）を確認。dev push で ci/native/fuzz-smoke 全緑。

### 3.5 Step 5 — dependabot.yml

- [ ] S5.1 `.github/dependabot.yml` 新設:

```yaml
version: 2
updates:
  - package-ecosystem: npm # pnpm-lock.yaml（directory: /）
    directory: '/'
    schedule: { interval: weekly }
    target-branch: dev
    groups:
      { production: { dependency-type: production }, development: { dependency-type: development } }
    ignore:
      - dependency-name: typescript # ユーザ決定 2026-09-29: TypeScript 7 はプロジェクト全体で除外（pnpm-workspace.yaml override と二重の番人）
        versions: ['>=7']
  - package-ecosystem: cargo
    directory: '/native'
    schedule: { interval: weekly }
    target-branch: dev
  - package-ecosystem: uv # pyproject.toml + uv.lock（Astral 公式ガイド準拠）
    directory: '/'
    schedule: { interval: weekly }
    target-branch: dev
```

- [ ] S5.2 **pip エコシステムは追加しない**（理由: `requirements.txt` は pyproject と test_phase8_distribution.py が機械同期するランタイム契約。Dependabot に requirements.txt を単独更新させると parity 規律が壊れる。uv エコシステムが pyproject+uv.lock を更新し、requirements.txt への反映は既存の手動同期規律に従う）。
- [ ] S5.3 zizmor は dependabot.yml も解析対象（設定追加時に再走）。actionlint 対象外ファイルなので prettier ゲートのみ（YAML）。
- [ ] S5.4 **有効化は main マージ後**（設定は既定ブランチから読まれる — §1.3）。dev push 後は「ファイル存在・構文有効・zizmor 緑」までを確認し、発効確認はユーザのマージ後（§10 に記録）。
- [ ] S5.5 初回 Dependabot PR の挙動確認（target: dev・groups・ignore が効いているか）を main マージ後に実施し記録。

### 3.6 Step 6 — uv audit ＋ UV_MALWARE_CHECK（観察枠）

- [ ] S6.1 package.json へ `"py:audit": "uv audit"` を追加（ローカル用。preview 版のため CI ゲート化しない — D5）。
- [ ] S6.2 ci.yml の Python 依存インストール後段に**非ブロッキング** step（`uv audit`・`continue-on-error: true`・job summary へ出力転記）。preview 安定後にブロッキング化を再評価（§10 に評価記録）。
- [ ] S6.3 `UV_MALWARE_CHECK=1` を ci.yml の uv step env へ試用追加（OSV MAL advisory 照会。**ロールバック基準**: uv sync が失敗/遅延する事象が 1 回でも出たら即削除し記録）。native.yml への展開は ci.yml で 2 週無事故を確認してから。
- [ ] S6.4 uv audit の実測出力（検出 0 件期待 — uv.lock は httpx2 2.13.1 等でクリーン）を §10 へ記録。

### 3.7 Step 7 — ruff S rules（flake8-bandit）有効化

- [ ] S7.1 `pyproject.toml` の `[tool.ruff.lint] select` へ `"S"` を追加。`per-file-ignores`: `"tests/*" = ["S101"]`（assert は pytest の作法）、必要なら `"scripts/**"` へ限定 ignore。
- [ ] S7.2 生産コード ~22 件のトリアージ表を作成し、**修正 / 個別 `# noqa: Sxxx`（理由コメント付き）/ 設定 ignore** の 3 択で全件を決定:
  - S110（try-except-pass）×10 — 既存 ignore の SIM105 と同根の「意図的な防御的ガード」（pyproject コメントに前例あり）→ 個別 noqa ＋理由、または SIM105 と同じ哲学で限定 ignore
  - S301（pickle）×2 — `private.key` は設計上の pickle（.gitignore 済み・ローカル専用）→ noqa＋理由
  - S106 ×3 / S108 ×2 / S603 ×2 / S310 ×2 / S112 ×1 — 実コードを確認し個別判断（S603 は build スクリプトの subprocess 想定）
- [ ] S7.3 `pnpm py:lint` 緑・`pnpm py:format:check` 緑・pytest 全緑（225 件水準）を確認。mypy 影響なし（型変更を伴う場合のみ再走）。
- [ ] S7.4 トリアージ表を §10 進捗ログへ転記（次セッションの参照用）。

### 3.8 Step 8 — eslint-plugin-security 導入

- [ ] S8.1 devDependency 追加（4.0.1 以上・2026-06-12 に flat config 既定化済み。pnpm のサプライチェーン検証は §3.2 S2.1 と同じ workaround 規程）。
- [ ] S8.2 `eslint.config.js`（flat）へ recommended を追加。検出をトリアージ（修正 / rule-level off ＋理由コメント）。
- [ ] S8.3 `pnpm lint` / `pnpm typecheck` / `pnpm fallow:dead` / `pnpm fallow:dupes` / `pnpm format:check` 緑。**web/ に影響する変更が出た場合は pnpm build ＋ K15 再走**（rule 追加のみならバンドル不変が期待される — 差分確認を記録）。

### 3.9 Step 9 — SECURITY.md・Private vulnerability reporting・ドキュメント同期

- [ ] S9.1 `SECURITY.md` 新設（英語・簡潔）: サポート版数、private vulnerability reporting の手順（Step 0 でユーザが有効化）、報告時の期待応答。README×4 の Documentation 節からリンク。
- [ ] S9.2 README×4 の Development / Quality gates 節へ**セキュリティゲート段落**を追加（CodeQL default setup・security.yml の 4 ジョブ・Dependabot・ruff S / eslint-plugin-security。既存の「Quality is enforced by a five-level test pyramid」段落の隣接に配置）。ツールチェーン表・バッジの追加は既存様式に従う（過剰なバッジ追加はしない — 既存の選別様式を尊重）。
- [ ] S9.3 MEMO へ本セッション記録（新設 §11）＋ §1.2 開発ワークフロー規程へ「security.yml の運用（SARIF 集約・ignore は理由付き設定ファイル）」を追加。
- [ ] S9.4 prettier 緑（md は lint-staged が自動整形）。

### 3.10 Step 10 — ゲート発火テスト（mutation 規律）と総合検収

- [ ] S10.1 **OSV-Scanner PR ゲート発火**: 一時ブランチで既知脆弱ピン（例: devDependency へ `source-map-js@1.2.1`）を追加 → PR 作成 → osv-pr ジョブが **fail ＋ PR アノテーション表示**を確認 → ブランチ削除（main へはマージしない）。
- [ ] S10.2 **Gitleaks 発火**: 一時ブランチで**擬似シークレット**（高エントロピー乱数文字列を `api_key = "..."` 形式で配置。provider pattern を使うと push protection に阻まれるため generic パターンのみ）をコミット → push → gitleaks ジョブ fail を確認 → revert コミットで削除し、**履歴に残った擬似シークレットは allowlist せず「テスト用の無効文字列」である旨を .gitleaks.toml に理由付き記録**（または発火テスト専用ブランチを push 後に削除して履歴ごと除去 — どちらを採るかは実装時に gitleaks-action のブランチ走査挙動を確認して決定）。
- [ ] S10.3 **zizmor 発火**: 一時ブランチで `${{ github.event.issue.title }}` を run ブロックへ意図的に配置 → fail 確認 → revert。
- [ ] S10.4 **CodeQL 発火（optional・時間許せば）**: テスト PR で意図的に脆弱な Python スニペット（例: `eval(request.params)` 型）を配置 → code scanning PR チェックが High+ で fail することを確認 → revert。default setup の PR 解析は main 向け PR のみである点に注意（dev 同士の PR では発火しない — D1）。
- [ ] S10.5 総合検収（§8）を全項目チェックし、証跡（run 番号・コミット SHA・実測出力）を §10 進捗ログと MEMO へ記録。

---

## 4. 実施計画（Step 総覧）

| Step | 名称                     | 主成果物                                                                                                    | 完了条件（要約）                                                     | 担当               |
| ---- | ------------------------ | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------ |
| 0    | ユーザ設定               | CodeQL default setup・Dependency graph・Dependabot alerts/security updates・Private vulnerability reporting | Security タブに CodeQL 初期解析・Dependabot 有効（API 再実測で確認） | **ユーザ**         |
| 1    | ワークフロー加固         | cache-cleanup/fuzz-long/native の修正・permissions 最小化                                                   | actionlint＋zizmor error 0（unpinned 除く）・dev CI 全緑             | セッション         |
| 2    | 依存是正＋トリアージ記録 | pnpm override・web/ 再ビルド・osv-scanner.toml                                                              | OSV 実測 0 件（記録済み ignore 除く）・K15/fallow/build 緑           | セッション         |
| 3    | セキュリティゲート導入   | security.yml・.gitleaks.toml・zizmor.toml                                                                   | dev push 緑・SARIF 3 ソースが Security タブへ反映                    | セッション         |
| 4    | SHA ピニング             | 全 action 参照の SHA ピン（dtolnay 例外）                                                                   | zizmor unpinned 0（例外 2 のみ）・1 action 1 コミット・CI 全緑       | セッション         |
| 5    | dependabot.yml           | .github/dependabot.yml（npm/cargo/uv・target dev・TS7 ignore）                                              | dev push 緑・main マージ後に発効（ユーザ）                           | セッション＋ユーザ |
| 6    | uv audit 観察枠          | py:audit・ci.yml 非ブロッキング step・UV_MALWARE_CHECK=1 試用                                               | 実測出力記録・ロールバック基準明記                                   | セッション         |
| 7    | ruff S 有効化            | pyproject・トリアージ                                                                                       | py:lint 緑・pytest 全緑・トリアージ表記録                            | セッション         |
| 8    | eslint-plugin-security   | package.json・eslint.config.js                                                                              | lint/typecheck/fallow/format 緑                                      | セッション         |
| 9    | SECURITY.md＋文書同期    | SECURITY.md・README×4・MEMO                                                                                 | prettier 緑・リンク解決                                              | セッション         |
| 10   | 発火テスト＋総合検収     | 発火証跡・検収表                                                                                            | 全ゲート「混ぜて失敗・復元して成功」実証・§8 全項目 ✓                | セッション         |

各 Step は独立コミット・独立 revert（Plan §6.3 継承）。**Step 1 → 2 → 3 → 4 は順序必須**（ゲート緑導入のため）。Step 6–9 は相互独立で並行可。Step 0 はいつでも先行可能（コード変更に依存しない）。

---

## 5. ユーザ設定手順（Step 0 詳細 — Settings → Advanced Security）

対象ページ: `https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/settings/security_analysis`（添付 PDF と同一ページ）

1. **Code scanning → Tools → CodeQL analysis** → 「**Set up**」→「**Default**」を選択。ダイアログで:
   - **Languages**: 自動検出された言語をすべて有効のまま（想定: JavaScript/TypeScript・Python・**Rust**〔build mode none = コンパイル不要〕。GitHub Actions 解析はワークフロー存在時に default setup へ含まれる）。
   - **Query suites**: 「**Extended**」を選択（= security-extended 級。default より深いセキュリティクエリ。実行時間は延びるが公開リポジトリは分無制限）。
   - 「**Enable CodeQL**」で確定。初回解析は数分〜十数分で完了し、Security → Code scanning に結果が出る。
2. **Copilot Autofix**: トグルがあれば **On** を確認（公開リポジトリ無料・CodeQL 有効化で既定有効のはず — 2024-09-17 changelog）。
3. **AI Scan for pull requests（Preview）**: トグル可能なら **On**（PR 限定の AI 検出・CodeQL の補完。preview のためノイズが出たら Off でよい）。
4. **Dependency scanning → Dependency graph**: **On**（Dependabot alerts の前提）。
5. **Dependabot alerts**: **On**。
6. **Dependabot security updates**: **On**（アラートにパッチがある場合の自動 PR）。
7. **Grouped security updates**: **Off のまま**（Step 5 の dependabot.yml でグループ化を管理する — ページの説明文自身も「advanced configuration には dependabot.yml を使え」と案内）。
8. **Private vulnerability reporting**: 「**Enable**」（コミュニティからの非公開脆弱性報告。Step 9 で SECURITY.md を整備）。
9. **Secret Protection**: Push protection は **On 済みのまま**（しきい値「Security alert severity level: High or higher / Standard alert severity level: Only errors」は据え置き — これが CodeQL PR チェックの fail 基準になる）。同節に「非 provider パターンの検出」や「validity checks」のトグルが**表示される場合は On**、表示されない（プラン制限）場合はスキップ — Gitleaks がその隙間を補完する。
10. **やらないこと**: 「Check runs failure threshold」節の branch ruleset は**作成しない**（main への publish-native-bin bot の直接 push を阻害するおそれ — D6）。
11. **Dependabot version updates**: 設定不要（Step 5 で `dependabot.yml` をコミット。**既定ブランチから読まれるため dev→main マージ後に発効**）。

**完了後の検証**（セッション側で実施可能）: GitHub API 再実測（vulnerability-alerts → 204・repo の security_and_analysis 変化なし〔CodeQL は別 API〕）＋ CodeQL 初期 run の完了確認 ＋ Security タブのスクリーンショット or `GET /repos/.../code-scanning/analyses`。

---

## 6. 検証プロトコル（ゲート発火テスト = mutation 規律）

「テストは mutation testing で捕捉力まで証明する」（MEMO §1.2）をセキュリティゲートへ適用する。各ゲートで:

1. **陽性プローブ**: 意図的な脆弱物（§3.10 S10.1–S10.4 の素材）を一時ブランチへ混ぜ、ゲートが **fail すること**を確認する。
2. **復元**: 脆弱物を除去し、ゲートが **success へ戻ること**を確認する。
3. **証跡**: run 番号・fail したジョブ名・検出メッセージを §10 進捗ログへ逐語記録する。

発火テストを行っていないゲートは「導入済み」とみなさない（検収基準 §8 に反映）。

---

## 7. 決定事項（D1–D10）

| #   | 事項                                         | 決定（2026-10-07）                                                                                                                                                                                                                                                                                                                               |
| --- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| D1  | CodeQL の setup 形態                         | **default setup で開始**。dev 直接 push は default setup のスコープ外だが、security.yml（OSV/zizmor/gitleaks）が dev push をカバーするため実質の空白は生じない。CodeQL を dev push でも回したくなった場合のみ advanced setup への移行を再評価する（移行時は codeql-action の Actions キャッシュ使用に注意 — 本 repo はキャッシュ逼迫履歴あり）。 |
| D2  | SHA ピニングの例外                           | `dtolnay/rust-toolchain@stable` / `@nightly` の 2 参照は **floating のまま**（プロジェクトのツールチェーン方針 = バージョンピン無し・rustc 1.99 ドリフトは CI が捕捉する実績）。zizmor.toml に理由付き例外として記録し、tag コメントへ現時点 SHA を併記する。                                                                                    |
| D3  | requirements.txt 下限解決シグナルの扱い      | **ignore（理由付き記録）**。Python 依存の権威ソースは uv.lock（実測 2.13.1 = 無影響）であり、requirements.txt の loose pin 由来の報告は「宣言レンジが脆弱版を許容」のシグナルに過ぎない。将来 huggingface_hub 側の floor 引き上げ（`>=` の下限版数更新）時に自然解消する — その時点まで ignore 記録で監視。                                      |
| D4  | braces / bincode / paste                     | **accept（理由付き記録）**。braces = dev-only ビルドツール・DoS 入力は信頼できるビルド時 glob のみ・修正版無し。bincode = 代替不在（3.0.0 は名前占拠）・用途は永続インデックス符号化。paste = proc-macro ユーティリティ・実行時リスク無し。いずれも upstream 修正/代替出現時に再評価。                                                           |
| D5  | uv audit の CI 位置づけ                      | **非ブロッキング（観察枠）**。preview = 「unstable・breaking changes あり得る」の公式宣言のため、CI を赤にし得るゲート化は安定版まで保留。`UV_MALWARE_CHECK=1` は試用（ロールバック基準: 失敗/遅延 1 回で即削除）。                                                                                                                              |
| D6  | branch ruleset（code scanning 必須チェック） | **作成しない**。publish-native-bin bot の main 直接 push（`git add -f`・bot コミット）を阻害するおそれがあり、main へのマージはユーザ専任の PR フローなので PR チェック（CodeQL results check・OSV PR 差分）で十分。                                                                                                                             |
| D7  | AI Scan（Preview）                           | **optional**。設定ページに表示があれば試用可（PR 限定検出・CodeQL 非対応領域の補完）。ノイズが多ければ Off。本計画の必須範囲外。                                                                                                                                                                                                                 |
| D8  | Grouped security updates トグル              | **Off のまま**。グループ化は dependabot.yml の `groups:` で管理（設定の単一ソースを yml に保つ）。                                                                                                                                                                                                                                               |
| D9  | security.yml の schedule                     | **月曜 03:00 UTC**。既存の週次ジョブ（fuzz-long 日曜 18:00 UTC・cache-sweep 日曜 03:40 UTC）と時間帯をずらし、Actions 混雑とキャッシュ sweep の直後を避ける。                                                                                                                                                                                    |
| D10 | Dependabot の pip エコシステム               | **設定しない**。requirements.txt は pyproject と機械同期されたランタイム契約であり、uv エコシステム（pyproject+uv.lock）の更新を手動同期規律で requirements.txt へ反映する既存フローを壊さないため。                                                                                                                                             |

---

## 8. 検収基準（総合）

- [ ] A1. Step 0 のユーザ設定が API/run で確認できる（CodeQL 初期解析完了・Dependabot alerts 有効・private vulnerability reporting 有効）。
- [ ] A2. dev push で `security.yml` 全 job 緑（osv-full / zizmor / gitleaks）＋ ci.yml / native.yml の既存ゲート全緑。
- [ ] A3. PR（dev→main）で osv-pr 差分ゲートと CodeQL results check が動作（S10 の発火テストで実証）。
- [ ] A4. GitHub Security タブへ SARIF 3 ソース（CodeQL・OSV-Scanner・zizmor）が反映。
- [ ] A5. OSV-Scanner 実測 0 件（osv-scanner.toml の理由付き ignore/accept のみ残存）。
- [ ] A6. zizmor 実測 0 件（zizmor.toml の文書化例外のみ残存: dtolnay ×2・publish persist-credentials）。
- [ ] A7. gitleaks 全履歴緑（.gitleaks.toml allowlist 1 件 = dtype.rs 誤検知のみ）。
- [ ] A8. 全 action 参照が SHA ピン（例外 2 参照はコメントに SHA 併記）。
- [ ] A9. `pnpm py:lint`（ruff S 込み）・`pnpm lint`（eslint-plugin-security 込み）・typecheck・format:check・fallow dead/dupes・pytest・K15・rs 系ゲートすべて緑。
- [ ] A10. dependabot.yml が main マージ後に発効し、初回 PR が target-branch dev・groups・TS7 ignore どおりに出ることの確認（ユーザのマージ後 — §10 に記録）。
- [ ] A11. SECURITY.md・README×4・MEMO の同期が完了し prettier 緑。
- [ ] A12. 発火テスト 4 系（OSV PR・gitleaks・zizmor・CodeQL〔optional〕）の「混ぜて失敗・復元して成功」証跡が §10 に揃う。

**計画完了時の後始末**（Plan 1–3 の前例継承）: 本計画書は全 Step 完了後にツリーから削除し、git 履歴を一次記録とする（MEMO 冒頭注記の様式に合わせる）。削除前に成果サマリーを MEMO へ転記する。

---

## 9. 進捗管理表

| Step | 名称                   | 状態  | 証跡（commit / run / 実測） | 更新日     |
| ---- | ---------------------- | ----- | --------------------------- | ---------- |
| 0    | ユーザ設定             | `[!]` | —（ユーザ操作待ち）         | 2026-10-07 |
| 1    | ワークフロー加固       | `[ ]` | —                           | 2026-10-07 |
| 2    | 依存是正＋トリアージ   | `[ ]` | —                           | 2026-10-07 |
| 3    | セキュリティゲート導入 | `[ ]` | —                           | 2026-10-07 |
| 4    | SHA ピニング           | `[ ]` | —                           | 2026-10-07 |
| 5    | dependabot.yml         | `[ ]` | —                           | 2026-10-07 |
| 6    | uv audit 観察枠        | `[ ]` | —                           | 2026-10-07 |
| 7    | ruff S 有効化          | `[ ]` | —                           | 2026-10-07 |
| 8    | eslint-plugin-security | `[ ]` | —                           | 2026-10-07 |
| 9    | SECURITY.md＋文書同期  | `[ ]` | —                           | 2026-10-07 |
| 10   | 発火テスト＋総合検収   | `[ ]` | —                           | 2026-10-07 |

---

## 10. 進捗ログ（セッション別・最新在上）

### 2026-10-07 — 計画策定（v1.0）

- 前提セッションでツール選定調査を完了し、ユーザが**採用ツール全部＋実測検出の全量対処を可決**。
- 本計画書を策定・コミット（docs(agent)）。Step 0 のユーザ設定手順を回答として提示（§5 と同一内容）。
- 実測証跡（本計画の根拠・再実行可能）:
  - osv-scanner 2.6.0: `osv-scanner scan source --lockfile pnpm-lock.yaml --lockfile uv.lock --lockfile native/Cargo.lock --lockfile requirements.txt` → 3.0 秒・10 件（付録 A）。
  - gitleaks 8.30.1: `gitleaks git . --redact` → 11.3 秒・333 commits・1 件（dtype.rs:49 誤検知）。
  - zizmor 1.30.1: `zizmor --offline .github` → 0.27 秒・142 件（template-injection error ×2: cache-cleanup.yml:97 / fuzz-long.yml:91）。
  - ruff 0.16.9: `ruff check --select S --statistics py __init__.py tests scripts conftest.py` → 805 件（S101 ×783 ほか）。
  - GitHub API: secret_scanning/push_protection = enabled・Dependabot alerts = disabled（403 メッセージ逐語: 「Dependabot alerts are disabled for this repository.」）。
  - OSV API: RUSTSEC-2025-0141 = unmaintained・RUSTSEC-2024-0436 = unmaintained・GHSA-vfj7-8cjw-p6xm = CVE-2026-93687（braces・fix 無し）・GHSA-68fv-2mgg-jv7q = CVE-2026-93749（source-map-js・fix 1.2.2）。
  - uv.lock 実測: httpx2 = 2.13.1 / httpcore2 = 2.13.1（requirements.txt 由来検出 6 件は下限解決シグナル — D3）。

（次回以降のセッションは、実施内容・run 番号・コミット SHA・実測出力をここへ追記する）

---

## 付録 A: 実測検出の詳細（2026-10-07・dev tip 022543e）

### A.1 OSV-Scanner（10 件）

| Advisory                              | CVSS | Ecosystem | Package       | Version | Fix    | 対処（Step）                     |
| ------------------------------------- | ---- | --------- | ------------- | ------- | ------ | -------------------------------- |
| PYSEC-2026-3844 / GHSA-7mj9-2mp8-4m2p | 8.1  | PyPI      | httpcore2     | 2.9.1   | 2.10.0 | D3 ignore（S2.3）                |
| PYSEC-2026-3845 / GHSA-7mj9-2mp8-4m2p | 8.1  | PyPI      | httpx2        | 2.9.1   | 2.10.0 | D3 ignore（S2.3）                |
| PYSEC-2026-3846 / GHSA-8xx6-hgc6-gc2m | 7.5  | PyPI      | httpx2        | 2.9.1   | 2.12.0 | D3 ignore（S2.3）                |
| PYSEC-2026-3847 / GHSA-f2fp-rgf2-35cp | 5.9  | PyPI      | httpx2        | 2.9.1   | 2.10.0 | D3 ignore（S2.3）                |
| PYSEC-2026-3848 / GHSA-h4x7-gw46-3wm6 | 5.3  | PyPI      | httpx2        | 2.9.1   | 2.11.0 | D3 ignore（S2.3）                |
| PYSEC-2026-3849 / GHSA-pf96-p4fj-6566 | 5.6  | PyPI      | httpx2        | 2.9.1   | 2.11.0 | D3 ignore（S2.3）                |
| RUSTSEC-2025-0141                     | —    | crates.io | bincode       | 2.0.1   | 無し   | D4 accept（S2.3）                |
| RUSTSEC-2024-0436                     | —    | crates.io | paste         | 1.0.15  | 無し   | D4 accept（S2.3）                |
| GHSA-vfj7-8cjw-p6xm（CVE-2026-93687） | 8.7  | npm       | braces        | 3.0.3   | 無し   | D4 accept・upstream 監視（S2.3） |
| GHSA-68fv-2mgg-jv7q（CVE-2026-93749） | 8.7  | npm       | source-map-js | 1.2.1   | 1.2.2  | **修正**（S2.1）                 |

### A.2 zizmor（142 件の内訳・主要カテゴリ）

| カテゴリ              | 件数（実測概数） | 重症度        | 対処                                         |
| --------------------- | ---------------- | ------------- | -------------------------------------------- |
| template-injection    | error 2 + info 1 | high          | S1.1–S1.2 で env バインド化                  |
| unpinned-uses         | 多数             | high/medium   | S4（SHA ピニング・dtolnay は D2 例外）       |
| artipacked            | 複数             | medium        | S1.3（persist-credentials: false＋例外記録） |
| excessive-permissions | 多数             | medium/low    | S1.4（最小権限化）                           |
| adhoc-packages ほか   | info 級          | informational | S3.3 で zizmor.toml に記録・必要なら是正     |

### A.3 Gitleaks（1 件）

| Rule            | File                                 | Line | 実体                                                                        | 対処           |
| --------------- | ------------------------------------ | ---- | --------------------------------------------------------------------------- | -------------- |
| generic-api-key | native/crates/znn-codec/src/dtype.rs | 49   | //! doc コメント内の Python 例外引用 `KeyError: torch.complex128`（誤検知） | S3.2 allowlist |

### A.4 ruff --select S（805 件 → 実質トリアージ対象 ~22 件）

S101 ×783（tests — per-file-ignore）、S110 ×10、S106 ×3、S108 ×2、S603 ×2、S301 ×2、S310 ×2、S112 ×1（S7.2 のトリアージ表で全件決定）。

---

## 付録 B: 一次ソース一覧（2026-10-07 調査）

| #   | 出典                                                                                                                                                                                            | 用いた事実                                                                       |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| B1  | https://github.blog/changelog/2025-10-14-codeql-scanning-rust-and-c-c-without-builds-is-now-generally-available/                                                                                | CodeQL Rust GA・default setup = build mode none                                  |
| B2  | https://docs.github.com/en/code-security/reference/code-scanning/codeql/build-options-for-compiled-languages                                                                                    | Rust build mode none は rust-analyzer 使用・ビルド不要                           |
| B3  | https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/                                                                                                              | `.vue` が JS 抽出対象・Rust edition 2021/2024・TS 2.6–7.0・Python ≤3.14・Actions |
| B4  | https://github.blog/changelog/2026-08-19-codeql-2-26-3-improves-github-actions-queries-and-javascript-modeling/                                                                                 | Vue Composition API フローモデリング・Actions クエリ改善                         |
| B5  | https://docs.github.com/code-security/code-scanning/enabling-code-scanning/configuring-default-setup-for-code-scanning                                                                          | default setup は公開 repo 無料・全対応言語・クエリスイート選択可                 |
| B6  | https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-query-suites                                                                                                      | default setup のスイート = default / security-extended（UI「Extended」）         |
| B7  | https://google.github.io/osv-scanner/supported-languages-and-lockfiles/                                                                                                                         | 対応 lockfile 表（pnpm/uv/Cargo/requirements）・manifest 版数の best-effort 注記 |
| B8  | https://google.github.io/osv-scanner/github-action/                                                                                                                                             | reusable workflow 2 種・permissions ブロック・scan-args                          |
| B9  | https://github.com/google/osv-scanner（README）                                                                                                                                                 | RustSec/GHSA 集約・guided remediation は npm/Maven のみ・offline・SLSA 3         |
| B10 | https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-cli                                                                                                               | CodeQL CLI は公開リポジトリで無料                                                |
| B11 | https://github.blog/changelog/2024-12-17-find-and-fix-actions-workflows-vulnerabilities-with-codeql-public-preview/                                                                             | Actions クエリは default/advanced setup で利用可                                 |
| B12 | https://github.blog/changelog/2024-09-17-now-available-for-free-on-all-public-repositories-copilot-autofix-for-codeql-code-scanning-alerts/                                                     | Copilot Autofix 公開リポジトリ無料                                               |
| B13 | https://astral.sh/blog/uv-audit                                                                                                                                                                 | uv audit（preview・OSV バックエンド・4–10×）・UV_MALWARE_CHECK                   |
| B14 | https://dev.to/curioustore_48788631d0e2e/uv-audit-vs-pip-audit-and-a-gate-narrower-than-it-looks-30nf                                                                                           | uv audit vs pip-audit 第三者実測（同一検出・高速）                               |
| B15 | https://pnpm.io/blog/releases/11.0                                                                                                                                                              | pnpm audit の bulk advisories endpoint 移行（legacy endpoint 退役）              |
| B16 | https://appsecsanta.com/secret-scanning-tools/gitleaks-vs-trufflehog                                                                                                                            | Gitleaks（MIT・SARIF・pre-commit）vs TruffleHog（AGPL・検証機能）2026 比較       |
| B17 | https://github.com/gitleaks/gitleaks-action                                                                                                                                                     | 個人アカウントは GITLEAKS_LICENSE 不要                                           |
| B18 | https://github.com/zizmorcore/zizmor ＋ https://github.com/zizmorcore/zizmor-action ＋ https://docs.zizmor.sh/integrations/                                                                     | zizmor MIT・audit 群・公式 action（SARIF）                                       |
| B19 | https://arxiv.org/abs/2601.14455                                                                                                                                                                | Actions スキャナ 9 種の体系比較（検出ギャップ = 併用の正当性）                   |
| B20 | https://docs.github.com/code-security/secret-scanning/about-secret-scanning ＋ https://blog.gitguardian.com/github-push-protection-enhancing-open-source-security-with-limitations-to-consider/ | 公開 repo の secret scanning 無料自動・push protection 既定有効                  |
| B21 | https://docs.astral.sh/uv/guides/integration/dependabot/ ＋ https://github.com/dependabot/dependabot-core/issues/10478                                                                          | Dependabot の uv 公式対応（uv.lock 更新）                                        |
| B22 | https://docs.semgrep.dev/semgrep-ce-languages ＋ https://github.com/semgrep/semgrep-action ＋ https://github.com/semgrep/semgrep/pull/3497                                                      | Semgrep CE 単一関数限定・action deprecated・Vue basic support                    |
| B23 | https://trivy.dev/docs/v0.54/scanner/vulnerability/ ＋ https://tech-insider.org/trivy-tutorial-2026/                                                                                            | Trivy の DB ダウンロード機構・ディスク実需 ~2 GB                                 |
| B24 | https://github.com/eslint-community/eslint-plugin-security/blob/main/CHANGELOG.md ＋ https://docs.astral.sh/ruff/rules/                                                                         | eslint-plugin-security 4.0.1（flat 既定）・ruff 900+ rules（S 系含む）           |

**リポジトリ内一次ソース**: `Agent/MEMO.md` §1.2（CI 規律）・§4.1（キャッシュ/token/apt ハング）・§4.3（bincode 2.0.1 名前占拠）・§11.3（pnpm OOM workaround）・`Agent/environment-report.md` §11（環境の癖）・`.github/workflows/*.yml`（実測 grep）・`pnpm-workspace.yaml`（overrides 機構）。
