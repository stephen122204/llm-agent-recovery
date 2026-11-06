#!/usr/bin/env bash
# Redraw the earlier winner-map and cache figures from saved goal measurements.
set -euo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
P="$(cd "$S/../../.." && pwd)"
OUT="${1:-$P/output/earlier-figures}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
"${RAF_PYTHON:-python3}" "$S/make_f3.py" "$P/data/figdata/goals.csv" "$OUT/F3_winner_map"
"${RAF_PYTHON:-python3}" "$S/make_f5.py" "$P/data/figdata/goals.csv" "$OUT/F5_cache"
