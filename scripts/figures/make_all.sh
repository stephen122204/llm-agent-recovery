#!/usr/bin/env bash
# Draw the earlier failure-position figure from the saved goal export.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT="${1:-$REPO_ROOT/output/earlier-figures}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
"${RAF_PYTHON:-python3}" "$SCRIPT_DIR/f4_position.py" --data "$REPO_ROOT/data/figdata" --out "$OUT"
