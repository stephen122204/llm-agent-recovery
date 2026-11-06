#!/usr/bin/env python3
"""F8: online study on held-out tasks. Left: saving per successful goal against always restart (warm),
paired bootstrap 95% CI over tasks, read from e3_savings.csv (same function as the text macros).
Right: which recovery each deciding policy chose first, after early and after late failures, from goals.csv "chosen".
Usage: python3 make_f8.py e3_savings.csv goals.csv OUTSTEM
"""
import csv, sys, collections
import figstyle as S

NAME = {"ctrl_beta": "EAR, learning mode", "xstar_rule": "Threshold rule", "token_rule": "Token rule (EAR)",
        "SR_warm": "Always resume (warm)", "RB_cold": "Always roll back (cold)", "FR_warm": "Always restart (warm)"}
COL = {"ctrl_beta": "#000000", "xstar_rule": "#8C510A", "token_rule": "#6A3D9A", "SR_warm": S.OPT["SR"], "RB_cold": S.OPT["RB"]}
sav = {r["policy"]: r for r in csv.DictReader(open(sys.argv[1]))}
order = [p for p in ("token_rule", "ctrl_beta", "xstar_rule", "RB_cold", "SR_warm") if p in sav]
share = collections.defaultdict(collections.Counter)
for r in csv.DictReader(open(sys.argv[2])):
    if r["study"] == "e3" and r["option"] in ("ctrl_beta", "xstar_rule", "token_rule") and r.get("chosen"):
        share[(r["option"], r["point"])][r["chosen"].split("+")[0][:2]] += 1
S.apply()
fig = S.plt.figure(figsize=(S.COL * 2.05, 1.75))
S.frame(fig, "Online study on held-out tasks: saving and the choices behind it", head=0.12)
ax = fig.add_axes([0.2, 0.2, 0.22, 0.62]); S.clean(ax)
fig.text(0.01, 0.9, "(a)", fontsize=7.5, fontweight="bold")
n = len(order)
for i, p in enumerate(order):
    y = n - 1 - i; r = sav[p]; v, lo, hi = float(r["saving"]), float(r["lo"]), float(r["hi"])
    ax.plot([lo, hi], [y, y], color=COL[p], lw=1.4, solid_capstyle="round")
    ax.scatter(v, y, s=26, color=COL[p], zorder=3, edgecolor="white", lw=0.7)
    ax.text(ax.get_xlim()[0], y, "", )
    ax.text(-0.02, y, NAME[p], transform=S.blend(ax), ha="right", va="center", fontsize=6.3, color=S.INK,
            fontweight="bold" if p == "ctrl_beta" else "normal")
    if r.get("ok"):
        ax.text(1.02, y, "%s/%s" % (r["ok"], r["n"]), transform=S.blend(ax), ha="left", va="center", fontsize=5.8, color=S.MUT)
ax.axvline(0, color=S.OPT["FR"], lw=0.9)
ax.text(0.5, -0.9, "always restart", color=S.OPT["FR"], fontsize=5.6)
ax.set_ylim(-1.1, n - 0.4); ax.set_yticks([])
ax.text(1.02, n - 0.4, "correct", transform=S.blend(ax), fontsize=5.4, color=S.MUT, va="bottom")
ax.set_xlabel("Saving per successful goal vs always restart (%)", fontsize=6.2, color=S.INK, labelpad=1)
bx = fig.add_axes([0.66, 0.2, 0.32, 0.55]); S.clean(bx)
fig.text(0.52, 0.9, "(b)", fontsize=7.5, fontweight="bold")
rows = [(p, pt) for p in ("ctrl_beta", "xstar_rule", "token_rule") for pt in ("early", "late")]
for i, (p, pt) in enumerate(rows):
    y = len(rows) - 1 - i - (0.4 * (i // 2)); c = share[(p, pt)]; tot = sum(c.values()) or 1; left = 0
    for d in ("FR", "SR", "RB", "SG"):
        w = 100.0 * c.get(d, 0) / tot
        if w:
            bx.barh(y, w, left=left, height=0.7, color=S.OPT[d], lw=0)
            if w >= 14:
                bx.text(left + w / 2, y, "%.0f" % w, ha="center", va="center", fontsize=5.4, color="white")
            left += w
    bx.text(-2, y, pt, ha="right", va="center", fontsize=5.9, color=S.INK)
    if pt == "early":
        bx.text(-14, y - 0.5, {"ctrl_beta": "EAR, learning mode", "xstar_rule": "Threshold rule", "token_rule": "Token rule"}[p],
                ha="right", va="center", fontsize=6.3, color=S.INK, fontweight="bold")
bx.set_xlim(0, 100); bx.set_yticks([]); bx.set_ylim(-1.2, len(rows) - 0.4)
bx.set_xlabel("First recovery chosen (% of goals)", fontsize=6.2, color=S.INK, labelpad=1)
h = [S.plt.Rectangle((0, 0), 1, 1, fc=S.OPT[d], label=S.NAME[d]) for d in ("FR", "SR", "RB", "SG")]
fig.legend(handles=h, loc="upper right", ncol=4, columnspacing=0.8, handlelength=1.2, fontsize=5.6, frameon=False, bbox_to_anchor=(0.985, 0.875))
S.save(fig, sys.argv[3])
