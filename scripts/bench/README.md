# `scripts/bench/` — KPI ベースライン計測スイート（Phase 0）

`Agent/Plan.md` §2.2 の KPI に対する**現行実装（vendored ZipNN C コア + Python バックエンド）の
ベースライン**を計測するためのスクリプト群です。結果は [`docs/BENCH.md`](../../docs/BENCH.md)
に記録され、以降のフェーズの達成判定（「KPI 未達のフェーズは完了としない」）の比較原点になります。

## 設計原則

- **実コードを計測する**: `py/compress.py`・`py/manager.py`・`py/utils.py`・`py/identify.py`・
  `py/download.py` の本物の関数を、ComfyUI 側モジュール（`folder_paths` / `comfy.utils` /
  `server`）の忠実なスタブ（`common.py`）経由で呼ぶ。計測対象を書き換えない。
  `comfy.utils.safetensors_header` のスタブは ComfyUI 本体 master からの逐語移植。
- **ピーク RAM はプロセスごとに隔離**: 各計測は fork されたサブプロセスで実行し、
  カーネル記録の `VmHWM`（/proc/self/status）を報告する。OOM や SEGFAULT（K5 の再現は
  **クラッシュが期待値**）は親を道連れにしない。
- **再現可能**: フィクスチャはすべてシード固定の合成生成（`gen_synthetic.py`）。
  1 GiB RAM のコンテナでも回るサイズ設計で、参照機（8C/16T NVMe）では環境変数で
  サイズを上げて再実行できる。
- **ネットワーク不使用**: 実モデルは各自ローカルに用意（`REAL_MODEL=/path/...`）。
  2026‑09‑23 の初回実行では ModelScope の `unsloth/all-MiniLM-L6-v2`
  （model.safetensors、90,868,376 B、f32×104 テンソル）を使用した。

## 実行

```bash
pip install numpy safetensors torch blake3   # torch は CPU 版で可
FIXTURES=/tmp/mm-bench REAL_MODEL=/path/model.safetensors ./scripts/bench/run_all.sh
```

| スクリプト            | KPI             | 内容                                                                                                                  |
| --------------------- | --------------- | --------------------------------------------------------------------------------------------------------------------- |
| `gen_synthetic.py`    | —               | フィクスチャ生成: 8 MB 級 MoE ヘッダー / Gaussian テンソルバイト / モデル / ペア / 5,000 モデルツリー                 |
| `bench_zipnn.py`      | K1/K2/K3/K5/K13 | C コア直呼び（dtype 別スループット・ピーク RAM）、Neo e2e（圧縮→解凍→SHA‑256 一致）、付録 C SEGFAULT 再現、起動系計測 |
| `bench_delta.py`      | K4/K5           | デルタ圧縮/解凍（ピーク RAM・byte‑exact 検証）+ **生産経路での SEGFAULT 到達性実証**                                  |
| `bench_c_defects.py`  | K5              | Plan 付録 C.3 の**全 22 ケース行列**（dtype32 クラッシュ 8・対照 9・dtype16 境界/奇数長 5）を一括再実行               |
| `bench_scan.py`       | K9/K10          | `scan_models` 冷間/暖間（現行は毎回全面走査）+ `scan_hygiene`                                                         |
| `bench_header.py`     | K11/K12         | `get_model_tensors` / `get_model_metadata`（8 MB MoE ヘッダー、内訳: read / json.loads / list 構築）                  |
| `bench_hash.py`       | K7/K8           | `compute_hashes` 5 算法 1 パス / `_sha256_of` フル再読込 / 素の sha256 参照（相互検証付き）                           |
| `native/…/json-bench` | （選定）        | jiter vs simd-json vs serde_json（8 MB ヘッダー、ダイジェスト一致検証付き）                                           |

結果 JSON は `scripts/bench/results/` に保存されます（コミット対象 = 初回実行の証跡。
再実行時は上書きされるため、`docs/BENCH.md` の表が正）。

## 既知の環境依存

- `drop_caches` はコンテナ内で Read‑only のことがあり、その場合「冷間」は
  **データキャッシュのみ冷間**（dentry キャッシュは暖）。結果 JSON の `coldNote` に記録される。
- スレッド数は vendored ZipNN と同じ `min(cpu_count, 16)`。2 vCPU 機と 16 スレッド機では
  スループットが線形に異なる（結果 JSON の `threads` に記録）。
- CPU に SHA 拡張がない場合 sha256 は AVX2 経路（`env` に CPU 情報を記録すること）。
