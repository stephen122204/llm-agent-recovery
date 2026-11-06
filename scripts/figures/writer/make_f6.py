#!/usr/bin/env python3
"""F6: the restart threshold as a decision map, with the evidence behind it.

Rows: failure types, grouped by side. Left of x* (red) restart is cheaper per successful goal, right (blue) resume.
Pale band: bootstrap 95% CI of x*. Hollow diamond: estimate from failures placed in the middle of tasks, where measured.
Right columns: success of restart and of resume (why the threshold differs) and x* as energy of work done.
Inputs: R5 main JSON (xstar.<cls>: x_star_calls, x_star_calls_ci, p_restart, p_resume, x_star_joules, W_range)
        R5 middle slice JSON (xstarMid... fields, optional: use - to skip).
Usage: python3 make_f6.py r5_numbers.json r5_mid.json OUTSTEM
"""
import json, sys
import figstyle as S
from matplotlib.transforms import blended_transform_factory as BT

main = json.load(open(sys.argv[1]))["xstar"]
mid = {}
if sys.argv[2] != "-":
    m = json.load(open(sys.argv[2]))
    src = m.get("xstarMid", m)
    for c in ("rate_limit", "tool_error"):
        v = src.get(c)
        if isinstance(v, dict) and "x_star_calls" in v:
            mid[c] = (v["x_star_calls"], v.get("x_star_calls_ci", [None, None]))
ORDER = (("rate_limit", "model"), ("json_parse", "model"), ("tool_error", "tool"), ("timeout", "tool"))
S.apply()
fig = S.plt.figure(figsize=(S.COL, 2.25))
S.frame(fig, "Restart if little work is done, otherwise resume", head=0.11)
ax = fig.add_axes([0.25, 0.25, 0.42, 0.52]); S.clean(ax)
X = max(main[c]["W_range"][1] for c, _ in ORDER)
n = len(ORDER)
for i, (c, side) in enumerate(ORDER):
    v = main[c]; y = n - 1 - i - (0.35 if side == "tool" else 0)
    x, (lo, hi) = v["x_star_calls"], v["x_star_calls_ci"]
    ax.add_patch(S.Rectangle((0, y - 0.32), x, 0.64, fc=S.OPT["FR"], alpha=0.85, lw=0))
    ax.add_patch(S.Rectangle((x, y - 0.32), X - x, 0.64, fc=S.OPT["SR"], alpha=0.85, lw=0))
    ax.add_patch(S.Rectangle((lo, y - 0.32), hi - lo, 0.64, fc="white", alpha=0.55, lw=0))
    ax.plot([x, x], [y - 0.32, y + 0.32], color=S.INK, lw=1.4)
    ax.text(x, y + 0.36, "%.1f" % x, ha="center", va="bottom", fontsize=6, color=S.INK, fontweight="bold")
    if c in mid:
        mx, (ml, mh) = mid[c]
        ax.scatter([mx], [y], marker="D", s=16, facecolor="white", edgecolor=S.INK, lw=0.9, zorder=4)
    ax.text(-0.04 * X, y, S.CLS[c], ha="right", va="center", fontsize=6.4, color=S.INK, clip_on=False)
    ax.text(1.05, y, "%.2f / %.2f" % (v["p_restart"], v["p_resume"]), ha="left", va="center", fontsize=6.2, color=S.INK, clip_on=False, transform=BT(ax.transAxes, ax.transData))
    ax.text(1.5, y, "%.0f" % v["x_star_joules"], ha="left", va="center", fontsize=6.2, color=S.INK, clip_on=False, transform=BT(ax.transAxes, ax.transData))
ax.text(1.05, n - 0.45, "success\nrestart / resume", ha="left", va="bottom", fontsize=5.4, color=S.MUT, clip_on=False, transform=BT(ax.transAxes, ax.transData))
ax.text(1.5, n - 0.45, "x* (J)", ha="left", va="bottom", fontsize=5.4, color=S.MUT, clip_on=False, transform=BT(ax.transAxes, ax.transData))
ax.set_xlim(0, X); ax.set_ylim(-0.85, n - 0.45); ax.set_yticks([])
ax.set_xlabel("Calls finished when the failure happened", fontsize=6.2, color=S.INK, labelpad=1)
h = [S.plt.Rectangle((0, 0), 1, 1, fc=S.OPT["FR"], label="restart cheaper"),
     S.plt.Rectangle((0, 0), 1, 1, fc=S.OPT["SR"], label="resume cheaper"),
     S.plt.Line2D([], [], marker="D", ls="", mfc="white", mec=S.INK, ms=4, label="middle of task")]
fig.legend(handles=h, loc="lower center", ncol=3, fontsize=5.6, frameon=False, bbox_to_anchor=(0.5, 0.0))
S.save(fig, sys.argv[3])
