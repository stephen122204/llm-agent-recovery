#!/usr/bin/env python3
"""F2 measurement setup and boundary, F7 controller design: schematics drawn in code.

No data. Drawn with the same style so fonts and colors match the data figures; the SVG keeps live text
for finishing in Figma or Inkscape.
"""
import argparse

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

import style as S


def box(ax, x, y, w, h, text, fc, ec=None, bold=False, size=6.5, tc=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.025",
                                fc=fc, ec=ec or "none", lw=0.7))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size,
            fontweight="bold" if bold else "normal", color=tc or S.C["INK"], linespacing=1.15)


def arrow(ax, a, b, color=None, style="-|>", ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=7, lw=0.8, ls=ls,
                                 color=color or S.C["MUTED"], connectionstyle="arc3,rad=%s" % rad,
                                 shrinkA=1, shrinkB=1))


def f2(out):
    fig, ax = plt.subplots(figsize=(S.COL, 2.15))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_axis_off()
    soft = S.lighten(S.C["SR"], 0.88)
    sz = 5.8
    box(ax, 0.00, 0.74, 0.19, 0.17, "Study\ndriver", S.C["PANEL"], size=sz)
    box(ax, 0.25, 0.74, 0.22, 0.17, "Pre attempt\nhook", S.lighten(S.C["CTRL"], 0.85), size=sz)
    box(ax, 0.53, 0.74, 0.18, 0.17, "Agent", soft, size=sz)
    box(ax, 0.79, 0.74, 0.21, 0.17, "vLLM\nprefix cache", soft, size=sz)
    box(ax, 0.53, 0.50, 0.18, 0.13, "Failure\ninjector", S.lighten(S.C["FAIL"], 0.82), size=sz)
    box(ax, 0.79, 0.50, 0.21, 0.13, "A-LEMS\nsampler", S.lighten(S.C["RB"], 0.85), size=sz)
    box(ax, 0.00, 0.50, 0.19, 0.13, "Store", S.C["PANEL"], size=sz)
    arrow(ax, (0.19, 0.825), (0.25, 0.825))
    arrow(ax, (0.47, 0.825), (0.53, 0.825))
    arrow(ax, (0.71, 0.845), (0.79, 0.845))
    arrow(ax, (0.79, 0.805), (0.71, 0.805))
    arrow(ax, (0.62, 0.63), (0.62, 0.74))
    ax.add_patch(plt.Polygon([[0.895, 0.50], [0.895, 0.44], [0.095, 0.44]], closed=False, fill=False,
                             ec=S.C["MUTED"], lw=0.8))
    arrow(ax, (0.095, 0.44), (0.095, 0.50))
    # timeline of one goal: shaded = measurement window, unshaded = outside (resets, restore, decision)
    y0, h = 0.12, 0.13
    ax.text(0.0, 0.33, "One goal", fontsize=6.5, fontweight="bold")
    ax.add_patch(plt.Rectangle((0.02, y0), 0.44, h, fc=S.lighten(S.C["RB"], 0.75), ec="none"))
    ax.add_patch(plt.Rectangle((0.58, y0), 0.40, h, fc=S.lighten(S.C["RB"], 0.75), ec="none"))
    ax.text(0.24, y0 + h / 2, "attempt 1", ha="center", va="center", fontsize=6)
    ax.text(0.78, y0 + h / 2, "attempt 2", ha="center", va="center", fontsize=6)
    ax.scatter([0.455], [y0 + h / 2], marker="x", s=26, color=S.C["FAIL"], linewidth=1.3, zorder=3)
    ax.text(0.52, y0 + h / 2, "reset\nrestore\ndecide", ha="center", va="center", fontsize=5.2,
            color=S.C["MUTED"], linespacing=1.0)
    ax.plot([0.02, 0.98], [y0 - 0.02, y0 - 0.02], color=S.C["MUTED"], lw=0.6)
    ax.text(0.98, y0 - 0.075, "time", ha="right", fontsize=5.5, color=S.C["MUTED"])
    ax.text(0.02, 0.02, "Shaded: measurement window; idle power subtracted",
            fontsize=5.5, color=S.C["MUTED"])
    S.save(fig, "F2_setup", out, {"schematic": True})


def f7(out):
    fig, ax = plt.subplots(figsize=(S.COL, 1.6))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_axis_off()
    m = S.lighten(S.C["CTRL"], 0.85)
    box(ax, 0.00, 0.58, 0.20, 0.30, "Failure:\nclass,\nwork done", S.C["PANEL"], size=5.6)
    box(ax, 0.26, 0.58, 0.22, 0.30, "Success:\nBeta posterior\nfrom the store", m, size=5.6)
    box(ax, 0.54, 0.58, 0.20, 0.30, "Energy:\nlinear per\ncall law", m, size=5.6)
    box(ax, 0.80, 0.58, 0.20, 0.30, "Pick: lowest\nenergy per\nsuccess\n(Thompson)", m, size=5.6)
    arrow(ax, (0.20, 0.73), (0.26, 0.73))
    arrow(ax, (0.48, 0.73), (0.54, 0.73))
    arrow(ax, (0.74, 0.73), (0.80, 0.73))
    labels = (("FR", "restart"), ("SR", "resume"), ("RB", "roll back"))
    for i, (fam, name) in enumerate(labels):
        x = 0.30 + i * 0.24
        box(ax, x, 0.12, 0.20, 0.18, "%s\nwarm or cold" % name, S.lighten(S.C[fam], 0.80), size=5.6)
        arrow(ax, (0.90, 0.58), (x + 0.10, 0.30), rad=0.0)
    box(ax, 0.00, 0.12, 0.24, 0.18, "abandon", S.C["PANEL"], size=5.6)
    arrow(ax, (0.90, 0.58), (0.12, 0.30), ls="--")
    ax.text(0.5, 0.97, "Runs in the pre attempt hook, outside the measurement window", ha="center",
            fontsize=5.8, color=S.C["MUTED"])
    S.save(fig, "F7_controller", out, {"schematic": True})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="figures")
    a = ap.parse_args()
    S.apply()
    f2(a.out)
    f7(a.out)


if __name__ == "__main__":
    main()
