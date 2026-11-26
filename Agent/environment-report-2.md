# 実行環境 詳細レポート（環境2）

**調査日時:** 2026-11-26 16:00–16:06 UTC（Asia/Tokyo と同日 25:00 = 2026-11-27 01:00 JST）
**調査方法:** 実際にシェルコマンド / Python を実行して観測した一次情報のみ（推測は「推定」と明記）
**対象:** 本タスクを実行しているエージェント環境（[environment-report.md](environment-report.md) は別環境 = Kata Containers / Alibaba Cloud）

---

## 1. 要約（ひと目でわかる版）

| 項目           | 値                                                                              |
| -------------- | ------------------------------------------------------------------------------- |
| 仮想化         | **KVM**（`systemd-detect-virt` = `kvm`。カーネル cmdline は Firecracker 風の `virtio_mmio` デバイス構成） |
| OS             | Debian GNU/Linux 13 "trixie"（13.8）                                             |
| ホストカーネル | Linux 6.1.189+（PREEMPT_DYNAMIC, 2026-11-02 ビルド、`root@ip-172-31-73-130`）      |
| アーキテクチャ | x86_64                                                                          |
| CPU            | Intel Xeon @ 2.60GHz（family 6 / model 106 / stepping 6 = **Ice Lake-SP 系**）、**2 vCPU** |
| メモリ         | 約 **1.94 GiB**（`/proc/meminfo` MemTotal = 2,030,416 kB）、user cgroup 実効上限 **1,944,928,256 bytes**（≈1.81 GiB） |
| ディスク       | virtio ディスク `/dev/vda`（ext4）**25 GB**（使用 4.4 GB / 空き 20 GB）            |
| 実行ユーザ     | `user`（uid=1000, gid=1000、**sudo グループ所属・パスワード無し sudo 可**）          |
| ネットワーク   | アウトバウンド **あり**（egress IP `136.86.202.79`、DNS 8.8.8.8）                  |
| 主要ランタイム | Python 3.13.18（/usr/local）、Node.js v20.20.2、npm 10.8.2、corepack 0.34.6、git 2.47.3 |
| プラットフォーム | e2b.dev 系サンドボックス（hostname `e2b.local`、`events.e2b.local` = `192.0.2.1`） |
| GPU            | なし                                                                              |

environment-report.md（環境1 = Kata Containers 上の Debian 12 / Alibaba Cloud / 1 GiB RAM / root）
とは完全に別物です。主な差分: RAM 約 2 倍・sudo 可能な非 root ユーザ・cgroup **v2**・Debian 13・e2b 系サンドボックス。

---

## 2. システム / カーネル

```
uname -a
Linux e2b.local 6.1.189+ #1 SMP PREEMPT_DYNAMIC Mon Nov  2 21:08:28 UTC 2026 x86_64 GNU/Linux

/proc/version
Linux version 6.1.189+ (root@ip-172-31-73-130) (gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, GNU ld (GNU Binutils for Ubuntu) 2.42) #1 SMP PREEMPT_DYNAMIC Mon Nov  2 21:08:28 UTC 2026
```

- ビルドホスト名 `ip-172-31-73-130` は AWS EC2 命名規則（推定: e2b の Firecracker ホストは EC2 上）。
- カーネル cmdline（`/proc/cmdline`）に `clocksource=kvm-clock` `virtio_mmio.device=4K@0x...` `root=/dev/vda` `ip=169.254.0.21::169.254.0.22:255.255.255.252:instance:eth0:off:tap0` が並ぶ → **PCI 無しの virtio-mmio マイクロ VM**（Firecracker の典型構成。`pci=off` が 2 回現れる）。
- DMI テーブル（`/sys/class/dmi/id/*`, `/sys/devices/virtual/dmi/id/*`）は**空** → 仮想ハードウェアが最小限に絞られている証跡。
- `systemd-detect-virt` → `kvm`。`hypervisor` フラグあり。
- `/.dockerenv` / `/run/.containerenv` は**存在しない** → Docker/ Podman コンテナではなく、**マイクロ VM そのもの**。

### CPU 詳細

```
Architecture:        x86_64        CPU op-mode(s): 32-bit, 64-bit
CPU(s):              2             On-line CPU(s) list: 0,1
Vendor ID:           GenuineIntel  Model name: Intel(R) Xeon(R) Processor @ 2.60GHz
cpu family: 6  model: 106  stepping: 6   microcode: 0x1
cache size: 55296 KB（L3, 約 54 MiB）
```

主な命令セットフラグ: `avx avx2 avx512f avx512dq avx512cd avx512bw avx512vl avx512ifma avx512vbmi avx512_vnni avx512_bitalg avx512_vpopcntdq fma aes sha_ni gfni vaes vpclmulqdq bmi1 bmi2 f16c adx`

- Family 6 / Model 106 / Stepping 6 = **Ice Lake-SP（第 3 世代 Xeon Scalable）系**。Skylake-SP（環境1）より新しい。
- AVX-512（VNNI / BF16 系を含む）が使える。bf16 直接変換などは CPU パスでも高速化の余地がある。
- 緩和策: `ssbd ibrs ibpb stibp ibrs_enhanced md_clear arch_capabilities` 等（Meltdown 系はハードウェア/マイクロコード緩和済み相当）。

### メモリ

```
MemTotal:      2,030,416 kB  (≈1.94 GiB)
MemAvailable:  1,480,012 kB  (≈1.41 GiB)
SwapTotal:             0 kB
MemFree:          ≈926 MB（`free -m` 実測）
```

- cgroup は **v2**（`/sys/fs/cgroup/cgroup.controllers` が存在し v1 系ファイルは無し）。
- 自分の cgroup は `0::/user`。`/sys/fs/cgroup/user/` の実効値:
  - `memory.max` = **1,944,928,256 bytes**（≈1.81 GiB）
  - `memory.current` ≈ 538 MB（調査時点）
  - `cpu.max` = `max 100000`（**CPU クォータ無し**）
  - `pids.max` = `max`
- `/dev/shm` は tmpfs で **992 MB**（環境1の 64 MB とは対照的。shm 依存処理も実用域）。
- swap 無し。OOM は 1.8 GiB 前後で発火しうる点は環境1と同様の注意が必要。

### cgroup / rlimit

```
/sys/fs/cgroup/cgroup.controllers = cpu cpuset io memory hugetlb pids rdma misc
ulimit -n  = 1024            （open files — 環境1の 100,000 より大幅に小さい。多数ファイルを開く処理は注意）
ulimit -u  = 7909
ulimit -s  = 8192 kB
NoNewPrivs / Seccomp: 未計測（非 root のため直接読めず）
```

### セキュリティコンテキスト

```
uid=1000(user) gid=1000(user) groups=1000(user),27(sudo)
$ sudo -n true → 成功（パスワード無し sudo 可）
CapEff（非 root デフォルト）
```

- root ではないが **sudo がパスワード無しで通る**。システムパッケージの導入は `sudo apt-get` で可能。
- `events.e2b.local` は `192.0.2.1`（TEST-NET-1 のダミーアドレス）として `/etc/hosts` に登録 — サンドボックスの制御チャネル（外部には出ない）。

---

## 3. ストレージ / マウント

```
Filesystem      Size  Used Avail Use% Mounted on
/dev/root        25G  4.4G   20G  19% /          （ext4, virtio, discard 付き）
tmpfs           992M     0  992M   0% /dev/shm
tmpfs           992M    50M  942M  6% /tmp
```

```
NAME MAJ:MIN RM  SIZE RO TYPE MOUNTPOINTS
vda  254:0    0 26.2G  0 disk /
```

- `/dev/vda` = 54,966,272 セクタ ≈ 26.2 GB。回転数フラグ `rotational` = 0（SSD/NVMe 相当）。
- `/tmp` は tmpfs（992 MB）— 大きな一時ファイルは `/home/user` か `/` へ。
- inode ゆとり: 6,857,760 個（使用 135,429 / 2%）— node_modules 大量展開も問題なし。
- **I/O 実測**（`dd oflag=direct bs=1M count=100`）: **774 MB/s**。
- `/home/user` は通常の ext4 上のディレクトリ（環境1のようなセッション管理領域との同一 inode バインドではない）。ワークスペースのスナップショット/永続化はプラットフォーム側が別途担う（この環境からは透過的）。

---

## 4. ランタイム / ツールチェーン

| ツール     | 状態                                                                 |
| ---------- | ---------------------------------------------------------------------- |
| Python     | **3.13.18**（`/usr/local/bin/python3`、pip 26.2.2）                     |
| Node.js    | **v20.20.2**（CI は 26.10.0 を使用 — ローカルは 20 系な点に注意）          |
| npm        | 10.8.2                                                                  |
| pnpm       | **未インストール**。`corepack` 0.34.6 経由で `corepack pnpm` が使える（初回に 12.8.1 を自動ダウンロード — package.json の `packageManager: pnpm@12.8.1+sha512...` に従う）。恒久化するなら `corepack enable` が必要 |
| yarn       | 無し                                                                   |
| git        | 2.47.3（credential helper 未設定 — HTTPS push には PAT を都度指定、または `git -c credential.helper=...`） |
| gh CLI     | **無し** — GitHub 操作は `curl` + PAT（`GH_TOKEN`）で REST API を叩く       |
| Rust       | **cargo / rustc とも無し** — Rust のビルド・clippy・fmt はこの環境では実行不可（CI の native.yml に委ねる） |
| ffmpeg     | 無し                                                                   |
| uv         | **無し**（`pip install uv` で導入は可能）                                  |
| ruff/mypy  | 事前インストール無し（pip 導入可）                                        |

Python 3.13.18 に導入済みの主なパッケージ（182 個中、タスクに関係するもの）:
`numpy 2.3.5`, `aiohttp 3.14.5`, `pytest 9.0.3`, `PyYAML 6.0.4`, `requests 2.33.0`
※ `requirements.txt`（runtime contract）に載る `huggingface_hub` / `hf_xet` / `modelscope_hub` / `markdownify` などは**未導入** — テストやスモーク前に `pip install -r requirements.txt` が必要。

Node プロジェクト側は**未インストール**（`node_modules` 無し）。フロントエンドの検証には `corepack pnpm install --frozen-lockfile` が必要（初回は数分かかりうる）。

---

## 5. ネットワーク

```
nameserver 8.8.8.8
default via 169.254.0.22 dev eth0   （169.254.0.20/30, 自 IP 169.254.0.21）
IPv4 addr: 169.254.0.21/30（eth0）
```

- egress IP（実測）: **136.86.202.79**
- 疎通確認（2026-11-26 16:0x UTC・HTTP コード）:
  - `https://github.com` → 200
  - `https://pypi.org/simple/` → 200
  - `https://registry.npmjs.org/` → 200（104.16.1.34）
  - `git ls-remote` / REST API（`api.github.com`）→ 正常
- `github.com` 解決: 20.64.190.225（getent）。
- HTTP プロキシ環境変数は**無し**（直接 egress）。
- タイムゾーン: **UTC**。ロケール: `LANG` 未設定・`LC_ALL` 空（POSIX/C 相当） — スクリプトは UTF-8 前提処理で注意（git の i18n メッセージ等）。

---

## 6. リポジトリ / 作業領域

- 作業コピー: `/home/user/repo`（`rikunarita/ComfyUI-Model-Manager-Neo`）。
- ブランチ運用: `dev` を checkout・origin 追跡。`main` はリリース専任（ユーザ操作）。
- この環境での GitHub push は `git -c credential.helper='!f() { echo username=rikunarita; echo "password=$GH_TOKEN"; }; f' push origin dev` で通る（2026-11-26 確認）。credential helper の永続設定はしていない。
- 7 分超のコマンドはこの実行系では Internal Error を誘発する → 長時間処理は分割 or `timeout` 付きで。

---

## 7. 環境1（environment-report.md）との比較

| 項目 | 環境1（別エージェント環境） | 環境2（本環境） |
| ---- | -------------------------- | --------------- |
| 基盤 | Kata Containers（KVM マイクロ VM）+ Docker 互換レイヤ | e2b.dev 系 Firecracker 風マイクロ VM（virtio-mmio、PCI 無し） |
| ホスト | Alibaba Cloud Linux 7 系カーネル 4.19.91 | Linux 6.1.189+（Ubuntu 24.04 ビルド） |
| OS（guest） | Debian 12 bookworm | **Debian 13 trixie** |
| CPU | Xeon (Skylake-SP) @2.50GHz model 85 / 2 vCPU | Xeon (**Ice Lake-SP 系**) @2.60GHz model 106 / 2 vCPU |
| メモリ上限 | 1 GiB（cgroup v1） | **≈1.81 GiB**（cgroup **v2**、`user` スライス） |
| /dev/shm | 64 MB | **992 MB** |
| ディスク | overlay 9.9 GB（617 MB/s 級） | ext4 25 GB（**774 MB/s** read direct） |
| ユーザ | root（uid=0） | **uid=1000 `user` + パスワード無し sudo** |
| cgroup | v1 | **v2** |
| `/home/user` | セッション管理領域と同一 inode のバインドマウント | 通常の ext4 上のディレクトリ |
| ランタイム | Python 3.11.2（venv）/ Node 20.20.2 / yarn あり | Python **3.13.18** / Node 20.20.2 / **corepack pnpm（未 enable）** |
| git | 2.39.5 | 2.47.3 |
| ネットワーク | egress あり（Alibaba Cloud, 47.236.158.65） | egress あり（**136.86.202.79**） |
| GPU | なし | なし |
| タイムゾーン | Asia/Shanghai | **UTC** |

---

## 8. この環境での既知の注意点

1. **Rust ツールチェーンが無い**: `cargo test/clippy/fmt` は実行できない。Rust 側の検証は CI（native.yml）に委ね、ローカルは `pnpm` / `python` 系の検証に留めること。
2. **Node が v20.20.2**: CI（26.10.0）より古い。pnpm 12 系は動作確認済み（corepack 経由）が、CI と完全同一の再現はできない。
3. **`gh` が無い**: GitHub の PR マージ・ブランチ削除・設定変更は REST API + curl で行う（本セッションで実績あり）。
4. **メモリ ≈2 GB**: `pnpm install`・`vite build`・`pytest` は同時実行せず、一つずつ。`/tmp` は tmpfs（小さい）なので大物の一時置き場は `/home/user` へ。
5. **`ulimit -n` = 1024**: watcher 系や多ファイル並列スキャンの検証で `Too many open files` が出たら、これを疑う。
6. **open files 1024・sudo あり**: システム変更は `sudo apt-get` で可能だが、対象は最小限に。
7. **git push の認証**: credential helper 未設定のため、push 毎に `GH_TOKEN` を credential.helper 経由で渡す（`.git/config` に恒久保存しない運用。`.git/config` は秘匿対象のためスナップショット除外でもある）。
8. **CI との差異**: GitHub Actions の runner（`ubuntu-latest`, Node 26.10.0）とこの環境は別物 — 「CI で緑だからローカルでも緑」とは限らない点に注意。逆も同様。
