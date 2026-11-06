#!/usr/bin/env python3
"""F8: energy per successful goal against success, one point per policy (online study, held-out tasks).

Reads data/figdata/e3_points.csv (R4): policy, label, ach_j, ok, n, succ_lo, succ_hi.
Writes output/earlier-figures/F8_e3_arms.pdf (one column).

Reading: lower is cheaper per successful goal, further right is more often correct;
the best place is the lower right corner.
"""
import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
SRC = os.path.join(ROOT, "data/figdata/e3_points.csv")
OUT = os.path.join(ROOT, "output/earlier-figures/F8_e3_arms.pdf")

# option colours fixed for the whole paper; deciding policies in black or grey
COLOURS = {
    "restart": "#D55E00",
    "resume": "#0072B2",
    "roll back": "#009E73",
}
MARKERS = {"restart": "o", "resume": "o", "roll back": "o"}


def style_for(label):
    """Colour and marker by the option a policy always takes; EAR stands out."""
    low = label.lower()
    if low.startswith("ear"):
        return "#000000", "*", 13
    for key, col in COLOURS.items():
        if key in low:
            return col, MARKERS[key], 7
    return "#555555", "s", 6  # online controller, threshold rule


def load(path):
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            n = float(r["n"])
            rows.append({
                "label": r["label"],
                "x": 100.0 * float(r["ok"]) / n,
                "y": float(r["ach_j"]),
                "lo": 100.0 * float(r["succ_lo"]),
                "hi": 100.0 * float(r["succ_hi"]),
            })
    return rows


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if not os.path.exists(SRC):
        sys.exit("missing " + SRC)
    rows = load(SRC)
    plt.rcParams.update({
        "font.family": "serif", "font.size": 7.5, "axes.linewidth": 0.8,
        "xtick.major.width": 0.8, "ytick.major.width": 0.8,
    })
    fig, ax = plt.subplots(figsize=(3.25, 2.3))
    for r in rows:
        col, mk, ms = style_for(r["label"])
        # Wilson interval on success as a horizontal whisker
        ax.errorbar(r["x"], r["y"], xerr=[[r["x"] - r["lo"]], [r["hi"] - r["x"]]],
                    fmt=mk, color=col, ms=ms, mec="black", mew=0.6,
                    elinewidth=0.8, capsize=2, zorder=3)
        ax.annotate(r["label"], (r["x"], r["y"]), xytext=(5, 3),
                    textcoords="offset points", fontsize=7)
    ax.set_xlabel("Correct goals (%), Wilson 95% CI")
    ax.set_ylabel("Board J per successful goal")
    ax.grid(True, lw=0.4, color="#dddddd", zorder=0)
    for s in ax.spines.values():
        s.set_color("black")
    fig.tight_layout(pad=0.3)
    fig.savefig(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
