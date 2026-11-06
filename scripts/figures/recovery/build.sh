#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
OUT="${1:-$REPO_ROOT/analysis/recovery/generated/figures}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
PYTHON="${RAF_PYTHON:-python3}"
"$PYTHON" "$SCRIPT_DIR/draw_published_data_figures.py" "$OUT"
"$PYTHON" "$SCRIPT_DIR/draw_mechanisms.py" "$OUT"
