#!/usr/bin/env python3
"""F4 the cost of each recovery moves with the failure point (E1 plus E1b, board energy per successful goal).

Two panels (model side, tool side, pooled classes per O2). Lines connect early and late for restart warm,
resume warm and roll back cold; whiskers are bootstrap 95 percent CIs over tasks. Line ends are labelled
directly, so no legend is needed.
"""
import argparse

import matplotlib.pyplot as plt

import figlib as L
import style as S
from f3_winner_map import SIDES, pooled

OPTS = ("FR_warm", "SR_warm", "RB_cold")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--out", default="figures")
    a = ap.parse_args()
    d = L.data_dir(a.data)
    cs = L.cells(L.load_goals(d, studies=("e1", "e1b")))
    S.apply()
    fig, axes = plt.subplots(1, 2, figsize=(S.COL, 1.75), sharey=True)
    out = {}
    all_ends = []
    for ax, (side, classes, slabel) in zip(axes, SIDES):
        ends = []
        for k, o in enumerate(OPTS):
            pts = []
            for x, pt in enumerate(("early", "late")):
                p, lo, hi = L.boot_cell(pooled(cs, classes, pt, o))
                xo = x + (k - 1) * 0.06  # small dodge so whiskers never overlap
                pts.append((xo, p))
                col = S.C[o.split("_")[0]]  # full hue for whiskers; dashes mark cold on the line
                ax.plot([xo, xo], [lo, hi], color=col, lw=0.8, alpha=0.9)
                out.setdefault(side, {}).setdefault(o, {})[pt] = {"per_achieved_j": p, "lo": lo, "hi": hi}
            col, hatch = S.opt_color(o)
            col = S.C[o.split("_")[0]]  # dashes, not tint, mark cold here (tint is unreadable as a line)
            ax.plot([q[0] for q in pts], [q[1] for q in pts], color=col, lw=1.6, marker="o", ms=4,
                    markeredgecolor="white", markeredgewidth=0.6, ls="--" if hatch else "-")
            ends.append([pts[1][1], o, col])
        all_ends.append((ax, ends))
        ax.set_xticks([0, 1]); ax.set_xticklabels(["early", "late"])
        ax.set_xlim(-0.25, 2.15)
        ax.set_xlabel("Failure point, %s" % slabel.lower().replace(" failure", ""))
    lo_y, hi_y = axes[0].get_ylim()
    for ax, ends in all_ends:  # direct labels at the late end, nudged apart after the shared axis is final
        ends.sort()
        last = -1e18
        for y, o, col in ends:
            y = max(y, last + 0.10 * (hi_y - lo_y))
            last = y
            ax.text(1.12, y, S.OPT_LABEL[o].replace(" warm", "").replace(" cold", ""),
                    color=col, fontsize=6, va="center")
    axes[0].set_ylabel("Board J per successful goal ↓")
    fig.subplots_adjust(left=0.15, right=0.97, top=0.96, bottom=0.22, wspace=0.08)
    from matplotlib.patches import Rectangle
    fig.add_artist(Rectangle((0.003, 0.003), 0.994, 0.994, transform=fig.transFigure, fill=False,
                             lw=0.8, edgecolor="black"))  # thin black box, as every paper figure (R8)
    S.save(fig, "F4_position", a.out, out, L.is_demo(d))


if __name__ == "__main__":
    main()
