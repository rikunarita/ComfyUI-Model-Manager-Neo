# 実行環境 詳細レポート

**調査日時:** 2026-09-14 13:41–13:46 UTC (= 2026-09-14 21:41 Asia/Shanghai)
**調査方法:** 実際にシェルコマンド / Python を実行して観測した一次情報のみ（推測は「推定」と明記）

---

## 1. 要約（ひと目でわかる版）

| 項目           | 値                                                                                   |
| -------------- | ------------------------------------------------------------------------------------ |
| 仮想化         | **Kata Containers**（KVM 上の軽量 VM）+ Docker 互換レイヤ                            |
| OS             | Debian GNU/Linux 12 "bookworm"                                                       |
| ホストカーネル | Linux 4.19.91-c8dfc93.al7.x86_64（Alibaba Cloud Linux 系, 2023-09-26 ビルド）        |
| アーキテクチャ | x86_64                                                                               |
| CPU            | Intel Xeon @ 2.50GHz（family 6 / model 85 = **Skylake-SP**, stepping 7）、**2 vCPU** |
| メモリ         | **1 GiB**（cgroup 制限 1073741824 bytes）                                            |
| ディスク       | overlay rootfs **9.9 GB**（空き 9.3 GB）/ inode 655,360                              |
| 実行ユーザ     | **root**（uid=0, gid=0）                                                             |
| ネットワーク   | アウトバウンド **あり**（egress IP `47.236.158.65`）                                 |
| 主要ランタイム | Python 3.11.2（venv）、Node.js v20.20.2、npm 10.8.2、yarn 1.22.22、git 2.39.5        |
| クラウド       | **Alibaba Cloud**（DNS 100.100.2.x、ossfs マウント、aliyun ミラー）                  |
| GPU            | なし                                                                                 |

---

## 2. システム / カーネル

```
uname -a
Linux c-6aa7f983-019e4feb-642de7d05c39 4.19.91-c8dfc93.al7.x86_64
      #1 SMP Tue Sep 26 10:25:51 UTC 2023 x86_64 GNU/Linux

/proc/version
Linux version 4.19.91-c8dfc93.al7.x86_64 (root@b36943c9f7f9)
      (gcc version 4.8.5 20150623 (Red Hat 4.8.5-39) (GCC)) #1 SMP
```

- `.al7` サフィックス → ホストは **Alibaba Cloud Linux (Alinux) 7** 系カーネル。
- コンテナ内 rootfs は Debian 12 だが、**カーネルはホスト由来の 4.19**（ゲスト VM のカーネル）。
- ホスト名 `c-6aa7f983-019e4feb-642de7d05c39` はコンテナ ID 形式。`/etc/hosts` に `21.0.2.247` として登録。
- `/.dockerenv` が存在 → Docker 互換コンテナとして起動。

### 仮想化

```
Hypervisor vendor:   KVM
Virtualization type: full
```

マウント情報から **Kata Containers** が確定：

```
kataShared on /.dockerenv type virtio_fs (ro,relatime,...,dax=inode)
lowerdir=/run/kata-containers/shared/containers/passthrough/c-.../rootfs_lower
```

→ 通常の runc コンテナではなく、**KVM 上のマイクロ VM 内で動くコンテナ**。ホストカーネルを直接共有しないため、分離は強い。

### CPU 詳細

```
Architecture:        x86_64        CPU op-mode(s): 32-bit, 64-bit
Address sizes:       46 bits physical, 48 bits virtual
CPU(s):              2             On-line CPU(s) list: 0,1
Vendor ID:           GenuineIntel  Model name: Intel(R) Xeon(R) Processor @ 2.50GHz
CPU family: 6  Model: 85  Stepping: 7   BogoMIPS: 5000.00
Thread(s) per core: 1   Core(s) per socket: 2   Socket(s): 1
L1d 64 KiB (2) / L1i 64 KiB (2) / L2 2 MiB (2) / L3 35.8 MiB (1)
NUMA node(s): 1
```

主な命令セットフラグ: `avx512f avx512dq avx512cd avx512bw avx512vl avx512_vnni avx2 fma aes pclmulqdq rdrand rdseed bmi1 bmi2 f16c adx sha 系は無し`

- Family 6 / Model 85 / Stepping 7 = **Skylake-SP**（AVX-512 + VNNI 対応）。Alibaba Cloud の第6世代相当インスタンス（推定）。
- 脆弱性緩和状況: Meltdown / L1TF / MDS / TSX-AA = _Not affected_、Spectre v1/v2 = _Mitigated_（Enhanced IBRS, IBPB conditional, RSB filling）、Spec Store Bypass = _Mitigated_（prctl + seccomp）。

### メモリ

```
MemTotal:      1,083,460 kB  (≈1.03 GiB)
MemFree:         910,880 kB
MemAvailable:    922,364 kB
Cached:           70,580 kB
Swap: なし（SwapCached 0）
cgroup memory.limit_in_bytes = 1073741824  (1 GiB)
```

→ **メモリ 1 GiB がハード上限**。swap なし。大きな DataFrame やビルドは OOM になりやすい。

### cgroup / rlimit

```
/sys/fs/cgroup/cpu/cpu.cfs_quota_us = -1   (CPU クォータ無制限、ただし 2 vCPU  visible)
/sys/fs/cgroup/pids/pids.max        = max
cgroup v1 階層（memory / cpu,cpuacct / pids / cpuset / freezer / blkio / devices / net_cls / hugetlb / perf_event / systemd）
```

```
ulimit -a
core file size          0          open files            100000
data seg size           unlimited  max user processes    100000
file size               unlimited  stack size            8192 kB
max locked memory       64 kB      virtual memory        unlimited
cpu time                unlimited  pending signals       564
```

### セキュリティコンテキスト

```
uid=0(root) gid=0(root) groups=0(root)
CapPrm/CapEff/CapBnd = 00000000a80425fb
NoNewPrivs: 0     Seccomp: 0（無効）
```

実効ケーパビリティ（Docker デフォルトセット相当）:
`chown, dac_override, fowner, fsetid, kill, setgid, setuid, setpcap, net_bind_service, net_raw, sys_chroot, mknod, audit_write, setfcap`

**無いもの:** `sys_admin`, `net_admin`, `sys_ptrace`, `sys_module`, `sys_rawio`, `sys_time`, `dac_read_search` ほか
→ root だが **VM 脱出や名前空間操作は不可能**な構成。Kata VM 自体が最終的な隔離境界。

`/dev` の中身は `null zero full random urandom tty console ptmx pts shm mqueue fd stdin stdout stderr kcore` のみ（ブロックデバイス・GPU デバイスなし）。

---

## 3. ストレージ / マウント

```
Filesystem                              Type        Size  Used Avail Use% Mounted on
c-...-rootfs                            overlay     9.9G   55M  9.3G   1% /
tmpfs                                   tmpfs        64M     0   64M   0% /dev
tmpfs                                   tmpfs       530M     0   530M  0% /sys/fs/cgroup
shm                                     tmpfs        64M     0   64M   0% /dev/shm
kataShared                              virtio_fs   189G  720M  188G   1% /.dockerenv
tmpfs                                   tmpfs        72M    28K   72M   0% /etc/hosts
ossfs                                   fuse.ossfs   16E     0   16E    0% /mnt/oss
```

- **rootfs**: overlay（`volatile` 付き＝書き込みの耐久性を犠牲に高速化）。lower は Kata の passthrough 共有、upper/work は `/run/builtin_wlayer/<container>/`。
- **/mnt/oss**: Alibaba Cloud **OSS を ossfs (FUSE) でマウント**。中にセッションスナップショットの tar.gz が並ぶ（観測時 11 個、最大 850 MB、合計約 2.2 GB）。これがワークスペース永続化の実体と推定。
- **/dev/shm は 64 MB のみ**（並列ビルドや Chromium 系には厳しい）。
- `/etc/hosts`, `/etc/hostname`, `/etc/resolv.conf` は tmpfs（起動時に注入）。
- inode 上限: rootfs **655,360**（残り 655,304）。node_modules を大量展開すると枯渇しうる。

### I/O 実測

```
dd if=/dev/zero of=/home/user/.iotest bs=1M count=200 oflag=direct
209715200 bytes (200 MiB) copied, 0.334556 s, 627 MB/s
```

### CPU 実測

```
python3: for i in range(2_000_000): x += i*i   →  0.22 s
```

---

## 4. ワークスペースの構造（重要）

`/home/user` は **バインドマウント** で、セッション管理領域と同一 inode：

```
/tmp/arena/tenants/6acc009e-668a-4d2f-9f51-3f7ed5839ee4/sessions/e0605820-e4dd-4360-a19c-6cd3d0d83683/workspace
  → stat すると File: /home/user  /  st_dev=39, st_ino=893
  → /home/user と st_dev,st_ino 完全一致（SAME OBJECT: True）
  → 片方に書いたファイルをもう片方から読めることを実測確認済み
```

セッション管理領域の中身：

```
/tmp/arena/tenants/<tenantId>/sessions/<sessionId>/
├── artifacts/          (空)
├── workspace/          ← /home/user と同一
├── session.json        (378 B)
├── history.json        ({metadata, messages})
├── llm-calls.jsonl     (mode 600)
└── undo/checkpoint.json + undo/workspace/   ← 巻き戻し用スナップショット
```

`session.json` の中身（機微値はマスク）：

```
version            = 1
id                 = e0605820-e4dd-4360-a19c-6cd3d0d83683
tenantId           = 6acc009e-668a-4d2f-9f51-3f7ed5839ee4
currentDate        = 2026-09-14
timezone           = Asia/Shanghai
tokenHash          = <REDACTED>
tokenExpiresAt     = 1789396884376  → 2026-09-14 14:41:24 UTC (22:41:24 +08)
createdAt          = 1789393284376  → 2026-09-14 13:41:24 UTC (21:41:24 +08)
pendingInterruption= False
interruptionGeneration = 0
```

→ **セッションの有効期限は発行から 1 時間**。

`HOME` は `/tmp`（`/root` ではない）。`ARENA_WORKSPACE=/home/user`。

---

## 5. 環境変数

```
ARENA_WORKSPACE=/home/user
HOME=/tmp
LANG=C.UTF-8
LC_ALL=C.UTF-8
PATH=/opt/arena-python/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
PWD=/home/user
PYTHONNOUSERSITE=1
SHLVL=1
TERM=xterm
TMPDIR=/tmp
VIRTUAL_ENV=/opt/arena-python
```

- **プロキシ変数なし**、**API キー・トークン系の環境変数は一切注入されていない**（認証はホスト側で処理）。
- `pip.conf` / `.npmrc` も存在せず（ミラー設定は apt のみ）。

---

## 6. ネットワーク

### 名前解決・経路

```
/etc/resolv.conf:
  nameserver 100.100.2.136
  nameserver 100.100.2.138      ← Alibaba Cloud 内部 DNS

/etc/hosts:
  127.0.0.1  localhost
  ::1        localhost ip6-localhost ip6-loopback
  fe00::0    ip6-localnet / ip6-mcastprefix
  fe00::1    ip6-allnodes      fe00::2  ip6-allrouters
  21.0.2.247 c-6aa7f983-019e4feb-642de7d05c39
```

`ip` / `ifconfig` / `ss` / `netstat` / `ping` は**未インストール**のため、IF 一覧・ルーティングテーブル・LISTEN ソケットは観測不能（ツールが無いため空表示になる）。

### 疎通実測（Python socket / urllib）

| 宛先                 | 結果                                                                        |
| -------------------- | --------------------------------------------------------------------------- |
| `pypi.org`           | DNS 151.101.128.223 → **HTTPS 200**、TCP connect **8 ms**                   |
| `registry.npmjs.org` | DNS 104.16.7.34 → `npm view react version` = **19.3.0**（成功）             |
| `github.com`         | DNS 20.205.243.166 → TCP connect **5 ms**                                   |
| `deb.debian.org`     | DNS 199.232.114.132 → **HTTPS 200**                                         |
| `www.google.com`     | DNS 142.251.150.119（解決可）                                               |
| `mirrors.aliyun.com` | DNS 43.109.150.114 → TCP 5 ms、ルートは **403 Forbidden**（apt パスは正常） |
| `api.ipify.org`      | egress IP = **47.236.158.65**、往復 **303 ms**                              |

### ブロック確認（タイムアウト）

| 宛先                                       | 結果                     |
| ------------------------------------------ | ------------------------ |
| `100.100.100.200:80`（Alibaba メタデータ） | **TimeoutError**（遮断） |
| `169.254.169.254:80`（クラウド IMDS）      | **TimeoutError**（遮断） |
| `10.0.0.1:22`（内部 SSH）                  | **TimeoutError**（遮断） |

→ 一般インターネットは開いているが、**クラウドメタデータサービスと内部ネットワークは到達不能**（クレデンシャル窃取対策）。

### egress IP の所属

`47.236.0.0/16` は Alibaba Cloud International のレンジで、地理的にはシンガポール地域（推定）。内部 DNS が aliyun、apt ミラーが aliyun という点と整合。

### curl / wget が無い件

`/usr/bin/curl` も `/usr/bin/wget` も**存在しない**。最初の疎通テストが全て FAIL に見えたのはこれが原因で、ネットワーク自体は生きている。HTTP は Python `urllib`、または `python3 -m pip` / `npm` 経由で扱う必要がある。

---

## 7. インストール済みソフトウェア

### パッケージ総数

- dpkg: **135 パッケージ**（最小構成）
- PATH 上のバイナリ総数: **924**

### Python

```
/opt/arena-python/bin/python3 → Python 3.11.2
pyvenv.cfg:
  home = /usr/bin
  include-system-site-packages = false
  version = 3.11.2
  executable = /usr/bin/python3.11
  command = /usr/bin/python3 -m venv /opt/arena-python
sys.path = ['', '/usr/lib/python311.zip', '/usr/lib/python3.11',
            '/usr/lib/python3.11/lib-dynload',
            '/opt/arena-python/lib/python3.11/site-packages']
サイズ: /opt/arena-python = 110 MB
```

`pip list`（15 パッケージ）:

| パッケージ         | バージョン | 用途              |
| ------------------ | ---------- | ----------------- |
| charset-normalizer | 3.5.1      | 文字コード判定    |
| defusedxml         | 0.7.1      | 安全な XML パース |
| et_xmlfile         | 2.0.0      | openpyxl 依存     |
| fonttools          | 4.64.0     | フォント操作      |
| **fpdf2**          | 2.8.8      | PDF 生成          |
| lxml               | 6.1.2      | XML/HTML          |
| **openpyxl**       | 3.1.5      | .xlsx 読み書き    |
| **pillow**         | 12.3.0     | 画像処理          |
| pip                | 26.2.1     |                   |
| **python-docx**    | 1.2.0      | .docx 生成        |
| **python-pptx**    | 1.0.2      | .pptx 生成        |
| **reportlab**      | 5.0.1      | PDF 生成          |
| setuptools         | 66.1.1     |                   |
| typing_extensions  | 4.16.0     |                   |
| **xlsxwriter**     | 3.2.9      | .xlsx 生成        |

→ **Office ドキュメント生成スタックに特化**。

**入っていない主要モジュール（`importlib.util.find_spec` で確認）:**
`numpy` ✗ / `pandas` ✗ / `matplotlib` ✗ / `scipy` ✗ / `requests` ✗ / `bs4` ✗ / `httpx` ✗ / `jinja2` ✗ / `yaml` ✗ / `playwright` ✗ / `selenium` ✗ / `tkinter` ✗

**入っているもの:** `sqlite3` ✓ / `venv` ✓ / `ssl` ✓ / `zlib` ✓ / `ctypes` ✓ / `tomllib` ✓ / `asyncio` ✓ / `multiprocessing` ✓

※ `pip install --dry-run requests` は成功（exit 0）、`apt-get update` も成功 → **必要なら都度インストール可能**（ただし永続しない）。

### Node.js

```
node  v20.20.2      (/usr/local/bin/node, nodejs)
npm   10.8.2
yarn  1.22.22       (+ /opt/yarn-v1.22.22, yarnpkg)
corepack 0.34.6
グローバル: corepack@0.34.6, npm@10.8.2 のみ（サイズ 18 MB）
/usr/local/bin: corepack docker-entrypoint.sh node nodejs npm npx yarn yarnpkg
node ビルド日: 2026-03-24
```

### その他ツール

**あり:** `git 2.39.5`（グローバル設定なし）, `perl`, `tar`, `gzip`, `openssl`, `apt/apt-get/dpkg`, `python3.11`

**なし（重要）:** `curl`, `wget`, `gcc`/`g++`/`make`/`cmake`（**ネイティブビルド不可**）, `java`, `go`, `rustc`/`cargo`, `ruby`, `php`, `jq`, `rg`(ripgrep), `fd`, `vim`, `nano`, `less`, `htop`, `ip`/`ifconfig`/`ss`/`netstat`/`ping`/`dig`/`nslookup`/`nc`/`socat`, `zip`/`unzip`, `sqlite3` CLI, `psql`/`mysql`, `ffmpeg`, `imagemagick`(convert/magick), `pandoc`, `libreoffice`(soffice), `docker`, `kubectl`, `uv`, `poetry`, `pipx`, `conda`

### フォント・ロケール

```
fontconfig: 未インストール（fc-list なし）
/usr/share/fonts: 存在しない
LANG = LC_ALL = C.UTF-8
```

→ **CJK フォントも fontconfig も無い**。reportlab / fpdf2 で日本語 PDF を作る場合は、TTF を自前で用意して埋め込む必要がある。Pillow の日本語描画も同様。HTML→PDF 系の変換ツール（pandoc / wkhtmltopdf / Chromium）も皆無。

### apt ソース（イメージの再現性確保）

```
/etc/apt/sources.list.d/debian.sources
Types: deb
# http://snapshot.debian.org/archive/debian/20260421T000000Z
URIs: http://mirrors.aliyun.com/debian
Suites: bookworm bookworm-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
# http://snapshot.debian.org/archive/debian-security/20260421T000000Z
URIs: http://mirrors.aliyun.com/debian-security
Suites: bookworm-security
Components: main
```

- Debian **snapshot 2026-04-21T00:00:00Z** 固定 + aliyun ミラー。`main` のみ（`contrib`/`non-free` なし）。
- イメージビルド痕跡: `/etc/localtime` = 2026-04-21、`/opt/yarn` = 2026-04-22、`debian.sources` 更新 = 2026-09-01。

### キャッシュ

```
/root/.cache          25 MB（pip http-v2 キャッシュ）
/usr/lib/python3.11   29 MB
/usr/share            34 MB
```

---

## 8. 日時・タイムゾーン

```
コンテナ内 TZ:  Etc/UTC  (/etc/localtime -> /usr/share/zoneinfo/Etc/UTC)
date:           Mon Sep 14 13:41:35 UTC 2026
セッション設定: currentDate=2026-09-14, timezone=Asia/Shanghai
```

→ **シェルは UTC、ユーザー向け表示は Asia/Shanghai (+08:00)**。時刻計算時はこの 8 時間差に注意。

---

## 9. 運用上の制約と実務ノウハウ

1. **メモリ 1 GiB / 2 vCPU**。大規模データのメモリ内処理は不可。ストリーミング処理・チャンク分割が必須。
2. **ネイティブコンパイラが無い** → C 拡張が必要な pip パッケージは wheel があるもののみ。無ければ `apt-get install build-essential` を実行する必要がある（rootfs 9.3 GB 空きがあるので容量は足りる）。
3. **`pip install` / `apt-get install` / `npm install` は可能**だが、**永続しない**。スナップショット対象は `/home/user` 配下の通常ファイルのみで、`node_modules`, `.venv`, `dist`, `build`, `__pycache__`, `.cache` 等の生成物は除外される。パッケージは会話ごとに再インストール前提。
4. **swap なし**。OOM は即 kill。
5. **/dev/shm 64 MB**。 multiprocessing の共有メモリやブラウザ系に制約。
6. **inode 655,360**。`node_modules` を巨大プロジェクトで展開すると枯渇の危険。
7. **curl/wget が無い** → HTTP は `python3 -c "import urllib.request..."` で。
8. **ps / ip / ss が無い** → プロセスやソケットの内省は `/proc` を直接読む。
9. **日本語フォントが無い** → 日本語を含む PDF/画像生成は TTF の調達・埋め込みが前提。
10. **メタデータサービス遮断済み** → クラウドのロール資格情報は取得不能（設計通り）。
11. **root 実行**だがケーパビリティは Docker デフォルト相当で、Kata VM が外側の壁。

---

## 10. 観測できなかったもの

- ネットワークインターフェース一覧・ルーティングテーブル・LISTEN ポート（`ip`/`ss`/`netstat` 未インストール）
- 実行中プロセス一覧（`ps` 未インストール。`/proc` 経由なら可能）
- ホスト側の物理リソース総量（VM には 2 vCPU / 1 GiB しか見えない）
- GPU（デバイスなし = 非搭載）

---

_本レポートはすべて実際にコマンドを実行して得た出力に基づいています。_
