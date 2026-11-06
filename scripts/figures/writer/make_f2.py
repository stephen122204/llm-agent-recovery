#!/usr/bin/env python3
"""F2: measurement setup and boundary (appendix). Schematic, no data.
MLSys rules: black lines >= 0.5 pt, no text on grey, no title inside; thin box from figstyle.
Usage: python3 make_f2.py OUTSTEM
"""
import sys
import figstyle as S
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


def box(ax, x, y, w, h, text, ec, size=6.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.02", fc="white", ec=ec, lw=1.0))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=S.INK, linespacing=1.1)


def arrow(ax, a, b):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=7, lw=0.8, color=S.INK, shrinkA=1, shrinkB=1))


S.apply()
fig = S.plt.figure(figsize=(S.COL, 2.0))
S.frame(fig)
ax = fig.add_axes([0.02, 0.02, 0.96, 0.96]); ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.0); ax.set_axis_off()
box(ax, 0.00, 0.74, 0.19, 0.18, "Study\ndriver", S.INK)
box(ax, 0.25, 0.74, 0.22, 0.18, "Decision\nhook", S.INK)
box(ax, 0.53, 0.74, 0.18, 0.18, "Agent", S.OPT["SR"])
box(ax, 0.79, 0.74, 0.21, 0.18, "vLLM with\nprefix cache", S.OPT["SR"])
box(ax, 0.53, 0.48, 0.18, 0.15, "Failure\ninjector", S.OPT["FR"])
box(ax, 0.79, 0.48, 0.21, 0.15, "Energy\nsampler", S.OPT["RB"])
box(ax, 0.00, 0.48, 0.19, 0.15, "Store", S.INK)
arrow(ax, (0.19, 0.83), (0.25, 0.83)); arrow(ax, (0.47, 0.83), (0.53, 0.83))
arrow(ax, (0.71, 0.85), (0.79, 0.85)); arrow(ax, (0.79, 0.81), (0.71, 0.81))
arrow(ax, (0.62, 0.63), (0.62, 0.74))
ax.plot([0.895, 0.895, 0.095], [0.48, 0.42, 0.42], color=S.INK, lw=0.8); arrow(ax, (0.095, 0.42), (0.095, 0.48))
y0, h = 0.10, 0.15
ax.text(0.0, 0.31, "One goal", fontsize=6.5, fontweight="bold", color=S.INK)
for x0, w, lab in ((0.02, 0.43, "attempt 1"), (0.59, 0.39, "attempt 2")):
    ax.add_patch(Rectangle((x0, y0), w, h, fc=S.OPT["RB"], alpha=0.25, ec="none"))
    ax.add_patch(Rectangle((x0, y0), w, h, fc="none", ec=S.OPT["RB"], lw=1.0))
    ax.text(x0 + w / 2, y0 + h / 2, lab, ha="center", va="center", fontsize=6.2, color=S.INK)
ax.scatter([0.45], [y0 + h / 2], marker="x", s=26, color=S.OPT["FR"], linewidth=1.3, zorder=3)
ax.text(0.52, y0 + h / 2, "reset\nrestore\ndecide", ha="center", va="center", fontsize=5.4, color=S.INK, linespacing=1.0)
arrow(ax, (0.02, y0 - 0.04), (0.98, y0 - 0.04))
ax.text(0.98, y0 - 0.1, "time", ha="right", fontsize=5.6, color=S.INK)
S.save(fig, sys.argv[1])
