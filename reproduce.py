"""Redraw recovery figures from the saved summaries without a GPU or database."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=root / "output",
                        help="output directory (default: output/ beside this script)")
    args = parser.parse_args()
    out = args.out.resolve()
    jobs = [
        ("scripts/figures/recovery/draw_published_data_figures.py", out / "figures"),
        ("scripts/figures/recovery/draw_mechanisms.py", out / "figures"),
        ("analysis/recovery/scripts/draw_data_figures.py", out / "analysis"),
    ]
    for script, destination in jobs:
        subprocess.run([sys.executable, str(root / script), str(destination)], check=True)
    print(f"Wrote five figure pairs to {out / 'figures'}")
    print(f"Wrote three alternative analysis figure pairs to {out / 'analysis'}")


if __name__ == "__main__":
    main()
