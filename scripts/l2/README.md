# `scripts/l2/` — L2 ゴールデン差分（移行期ゲート・Phase 8 で退役）

移行期（Phase 1–7）の L2 ゲートは、vendored C コア
（`third_party/zipnn-core-bin/linux-x86_64/`）をゴールデン生成器に、Rust
（`znn-cli`）の出力を**バイト単位**で照合する `golden_diff.py` でした
（フル 10,500 ケース: 長さクラス × エントロピ 8 種 × パラメータ 8 組 +
付録 C の SEGFAULT クラス 495 ケースの安全処理 + 圧縮率/速度ゲート）。

Phase 8 が `third_party/` を撤去したため、**スクリプトと CI ジョブ
（native.yml `native-diff`・fuzz-long.yml `l2-full`）は退役**しました。

- `results/golden_diff.json` — フルスイート GATE PASS の証跡（コミット済み。
  `docs/BENCH.md` が引用する数値の一次ソース。**再生成しない** — MEMO 規程）。
- `results/speed.json` — 圧縮率/速度ゲートの証跡（同上）。
- スクリプト本体は git 履歴（Phase 7 tip 以前、例: `git show
d35cbf3:scripts/l2/golden_diff.py`）から復元できます。

退役後の公式 ZipNN 互換の機械証明は **L5 クロス検証**が担います
（native.yml `integration`・ubuntu セルで pip の公式 zipnn 0.5.4 を
ソースビルドし、双方向解凍 + テンソルブロブ parity を毎 push 実行 —
`scripts/l5/official_cross.py`）。
