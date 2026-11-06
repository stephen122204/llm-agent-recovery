#!/bin/bash
# RAF R5: rerun every R5 output on the frozen snapshot (Oct 23 to 25), v2 rules, and write a manifest.
# Run on a grace compute node after: module load GCC/12.3.0 SciPy-bundle/2023.07 scikit-learn/1.3.1 matplotlib/3.7.2
# Code: analysis/r5 (platform files at commit 0203d7c plus the analysis scripts).
# Usage: bash analysis/r5/rerun_frozen.sh
set -euo pipefail
FZ=${RAF_FROZEN_DIR:?Set RAF_FROZEN_DIR to the directory containing the frozen database and ledgers}
OUT=${RAF_OUTPUT_DIR:?Set RAF_OUTPUT_DIR to a new output directory}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
RUN="$OUT/code"
mkdir -p "$RUN"
cp "$REPO"/experiments/fitting/scripts/raf/*.{py,sh} "$RUN/"
cp "$REPO"/analysis/r5/*.py "$RUN/"
cd "$RUN"

SNAP=$(ls "$FZ"/*.db)
[ "$(echo "$SNAP" | wc -l)" -eq 1 ] || { echo "expected exactly one .db in $FZ"; exit 1; }
echo "snapshot $SNAP"; sha256sum "$SNAP"

# place ledgers: folder, then one glob per expected ledger; abort if a glob does not match exactly one file
place() {
  local dir=$1; shift
  mkdir -p "$OUT/$dir"
  for pat in "$@"; do
    local m; m=$(find "$FZ" -name "$pat" ! -name "*smoke*")
    [ "$(echo "$m" | grep -c .)" -eq 1 ] || { echo "ledger pattern $pat for $dir matched: $m"; exit 1; }
    ln -sf "$m" "$OUT/$dir/"
  done
  echo "$dir:"; ls -l "$OUT/$dir"/*ledger*.jsonl
}
E1="raf_e1_run_ledger.jsonl"; R1="raf_e1_items_raf_e1_rerun_512_513_ledger.jsonl"; R2="raf_e1_items_raf_e1_rerun_512_513_platform_ledger.jsonl"
E1B="raf_e1b_run_ledger.jsonl"; E2="raf_e2_run_ledger.jsonl"; E2B="raf_e2b_r2_items*ledger.jsonl"; MID="raf_mid_run_ledger.jsonl"
place main  "$E1" "$R1" "$R2" "$E1B" "$E2"
place clean "$E1" "$R1" "$R2" "$E1B"
place mid   "$E1" "$R1" "$R2" "$E1B" "$E2" "$E2B" "$MID"
place m3    "raf_m3_run_ledger.jsonl" "raf_m3_b0_run_ledger.jsonl"
place m4    "raf_m4_run_ledger.jsonl" "raf_m4_b0_run_ledger.jsonl"
place sweep "raf_sweep_qwen_run_ledger.jsonl" "raf_sweep_m4_run_ledger.jsonl"
place samp  "raf_samp_s1_run_ledger.jsonl" "raf_samp_s2_run_ledger.jsonl" "raf_samp_s3_run_ledger.jsonl"

echo "== NULL both ways check"
python null_check.py "$SNAP" "$OUT/mid" "$OUT/m3" "$OUT/m4" "$OUT/sweep" "$OUT/samp"

echo "== clean sub tag (e1_e1b), needed by augment"
bash run_recovery_controller.sh "$OUT/clean" "$SNAP" e1_e1b
mv "$OUT/clean/export_e1_e1b" "$OUT/main/" ; mv "$OUT/clean/r5_e1_e1b" "$OUT/main/"

echo "== main (frozen_main)"
bash run_recovery_controller.sh "$OUT/main" "$SNAP" frozen_main
python replay_token_rules.py "$OUT/main/export_frozen_main" "$OUT/main/r5_frozen_main" frozen_main
python add_law_ctx.py "$OUT/main/export_frozen_main" "$OUT/main/r5_frozen_main/r5_numbers.json" frozen_main
python sg_lowest.py "$OUT/main/export_frozen_main" "$OUT/main/r5_frozen_main/r5_numbers.json" frozen_main
python augment_r5_numbers.py --main "$OUT/main" --clean "$OUT/main" --tag frozen_main
python -c "import json, fit_controller_params as F; p='$OUT/main/r5_frozen_main/r5_numbers.json'; t=F.goal_table('$OUT/main/export_frozen_main/goals.csv'); cv,r=F.cross_validate(t); d=json.load(open(p)); d['gbrBlocksActed']=int((r.method=='gbr').sum()); d['nCtrlBlocksTotal']=int((r.method=='oracle').sum()); json.dump(d,open(p,'w'),indent=1); print('gbr', d['gbrBlocksActed'], 'of', d['nCtrlBlocksTotal'])"

echo "== mid slice (frozen_mid)"
bash run_recovery_controller.sh "$OUT/mid" "$SNAP" frozen_mid
python refit_xstar_mid.py "$OUT/mid/export_frozen_mid" "$OUT/mid/r5_frozen_mid" frozen_mid
python silent_direct.py "$OUT/mid/export_frozen_mid" "$OUT/mid/r5_frozen_mid/r5_numbers.json" frozen_mid

echo "== Mistral and gpt-oss"
bash run_recovery_controller.sh "$OUT/m3" "$SNAP" frozen_m3
python model_ci.py "$OUT/m3/export_frozen_m3" "$OUT/m3/r5_frozen_m3" frozen_m3 m3
bash run_recovery_controller.sh "$OUT/m4" "$SNAP" frozen_m4
python model_ci.py "$OUT/m4/export_frozen_m4" "$OUT/m4/r5_frozen_m4" frozen_m4 m4

echo "== GB10 sweep"
python export_recovery_store.py --db "$SNAP" --ledger "$OUT/sweep/raf_sweep_qwen_run_ledger.jsonl" --ledger "$OUT/sweep/raf_sweep_m4_run_ledger.jsonl" --out "$OUT/sweep/export_sweep"
python sweep_fit.py "$OUT/sweep/export_sweep" "$OUT/sweep" "$OUT/sweep/r5_sweep" frozen_sweep

echo "== raf_samp"
python export_recovery_store.py --db "$SNAP" --ledger "$OUT/samp/raf_samp_s1_run_ledger.jsonl" --ledger "$OUT/samp/raf_samp_s2_run_ledger.jsonl" --ledger "$OUT/samp/raf_samp_s3_run_ledger.jsonl" --out "$OUT/samp/export_samp"
python samp_analysis.py "$OUT/samp/export_samp" "$OUT/samp" "$OUT/main/export_frozen_main" "$OUT/samp/r5_samp" frozen_samp raf_samp

echo "== compare with the delivered files (flags must be read before sending)"
D=inputs
python compare_numbers.py "$D/e2/r5_e1_e1b_e2_v2/r5_numbers.json" "$OUT/main/r5_frozen_main/r5_numbers.json" > "$OUT/compare_main.txt"
python compare_numbers.py "$D/mid/r5_e1_e1b_e2_e2b_mid/r5_numbers.json" "$OUT/mid/r5_frozen_mid/r5_numbers.json" > "$OUT/compare_mid.txt"
python compare_numbers.py "$D/m3/r5_m3_v2/r5_numbers.json" "$OUT/m3/r5_frozen_m3/r5_numbers.json" > "$OUT/compare_m3.txt"
python compare_numbers.py "$D/m4/r5_m4_v2/r5_numbers.json" "$OUT/m4/r5_frozen_m4/r5_numbers.json" > "$OUT/compare_m4.txt"
python compare_numbers.py "$D/sweep/r5_sweep/r5_numbers.json" "$OUT/sweep/r5_sweep/r5_numbers.json" > "$OUT/compare_sweep.txt"
python compare_numbers.py "$D/samp/r5_samp/r5_numbers.json" "$OUT/samp/r5_samp/r5_numbers.json" > "$OUT/compare_samp.txt"
grep -h "^flags\|^SIGN\|^SIGNIFICANCE\|^BOOL" "$OUT"/compare_*.txt || true

echo "== manifest"
{
  echo "# R5 manifest, frozen snapshot $(basename "$SNAP") $(sha256sum "$SNAP" | cut -c1-64)"
  echo "# code: platform commit 0203d7c plus ./analysis/r5"
  for f in main/r5_frozen_main mid/r5_frozen_mid m3/r5_frozen_m3 m4/r5_frozen_m4 sweep/r5_sweep samp/r5_samp; do
    sha256sum "$OUT/$f/r5_numbers.json"
  done
} > "$OUT/R5_MANIFEST_SHA256.txt"
cat "$OUT/R5_MANIFEST_SHA256.txt"
