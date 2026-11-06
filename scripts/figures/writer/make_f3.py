#!/usr/bin/env python3
"""F3: why the best recovery flips with the failure point (main study, board energy).

Grid: rows are model side and tool side failures (two types pooled per side), columns are early and late.
Each tile: restart, resume and roll back (cheaper cache state of each). Solid bar = energy per goal;
light extension = extra energy charged for goals that ended wrong (energy per successful goal minus energy per goal).
Right: correct goals. Winner (lowest energy per successful goal) in bold.
Usage: python3 make_f3.py goals.csv OUTSTEM
"""
import sys
import figstyle as S, goalsdata as G

rows = G.load(sys.argv[1], studies=("e1", "e1b"))
S.apply()
fig = S.plt.figure(figsize=(S.COL, 2.45))
S.frame(fig, "Why the best recovery depends on the failure point", head=0.095)
DEPTH = ("FR", "SR", "RB")
cells = {}
for side in ("model", "tool"):
    for pt in ("early", "late"):
        for d in DEPTH:
            best = None
            for cache in ("warm", "cold"):
                rs = [r for r in rows if S.SIDE.get(r["cls"]) == side and r["point"] == pt and r["option"] == "%s_%s" % (d, cache)]
                if not rs:
                    continue
                epg, pa, k, n = G.per_achieved(rs)
                key = pa if pa is not None else float("inf")
                if best is None or key < best[0]:
                    best = (key, cache, epg, pa, k, n)
            if best:
                cells[(side, pt, d)] = best
xmax = max(v[3] for v in cells.values() if v[3] is not None) * 1.12
pos = {("model", "early"): (0, 0), ("model", "late"): (0, 1), ("tool", "early"): (1, 0), ("tool", "late"): (1, 1)}
W, H, X0, Y0, GX, GY = 0.37, 0.31, 0.19, 0.125, 0.04, 0.085
for (side, pt), (ri, ci) in pos.items():
    ax = fig.add_axes([X0 + ci * (W + GX), Y0 + (1 - ri) * (H + GY), W, H])
    S.clean(ax)
    present = [d for d in DEPTH if (side, pt, d) in cells]
    win = min(present, key=lambda d: cells[(side, pt, d)][0])
    for j, d in enumerate(present):
        key, cache, epg, pa, k, n = cells[(side, pt, d)]
        y = len(present) - 1 - j
        ax.barh(y, epg, height=0.62, color=S.OPT[d], lw=0)
        if pa is not None:
            ax.barh(y, pa - epg, left=epg, height=0.62, color=S.OPT[d], alpha=0.28, lw=0, hatch="////", edgecolor="white")
        ax.text(epg * 0.04, y, "%d/%d correct" % (k, n), ha="left", va="center", fontsize=5.5, color="white", fontweight="bold")
        ax.text((pa if pa else epg) + xmax * 0.015, y, cache, ha="left", va="center", fontsize=5.4, color=S.MUT, clip_on=False)
        if ci == 0:
            ax.text(-0.06 * xmax, y, S.NAME[d], ha="right", va="center", fontsize=6.3, color=S.INK)
        if d == win:
            ax.scatter([-0.012 * xmax], [y], marker=">", s=14, color=S.INK, clip_on=False)
    ax.set_xlim(0, xmax); ax.set_ylim(-0.6, len(present) - 0.4); ax.set_yticks([])
    ax.tick_params(axis="x", length=2, pad=1)
    if ri == 0:
        ax.set_title("%s failure" % pt.capitalize(), fontsize=7, color=S.INK, pad=3)
        ax.set_xticklabels([])
    else:
        pass
    if ci == 0:
        fig.text(0.015, Y0 + (1 - ri) * (H + GY) + H / 2, "%s side" % side.capitalize(), rotation=90, va="center", fontsize=6.6, color=S.INK)
fig.text(X0 + W + GX / 2, 0.03, "Board energy (J)", ha="center", fontsize=6.4, color=S.INK)
S.save(fig, sys.argv[2])
