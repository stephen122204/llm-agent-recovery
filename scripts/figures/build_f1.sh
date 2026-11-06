#!/usr/bin/env bash
# Export the recorded recovery trace from a supplied database and redraw F1.
# Usage: bash scripts/figures/build_f1.sh FROZEN_DB [OUTPUT_DIRECTORY]
set -euo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
P="$(cd "$S/../.." && pwd)"
DB="${1:?Usage: build_f1.sh FROZEN_DB [OUTPUT_DIRECTORY]}"
OUT="${2:-$P/output/trace}"
PYTHON="${RAF_PYTHON:-python3}"
mkdir -p "$OUT/data"
OUT="$(cd "$OUT" && pwd)"
"$PYTHON" "$S/export_f1_trace.py" "$DB" "$OUT/data" \
  1295:FR_warm 1294:FR_cold 2240:RB_cold 1297:SR_warm
"$PYTHON" "$S/make_f1_trace.py" "$OUT/data/f1_attempts.csv" \
  "$OUT/data/f1_calls.csv" "$OUT/F1_trajectory" "$P/data/figdata/goals.csv"
