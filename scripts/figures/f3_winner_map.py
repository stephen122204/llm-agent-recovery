#!/usr/bin/env python3
"""F3 winner map: which recovery wins in each situation (E1 plus E1b, board energy per successful goal).

Rows: model side failures (JSON parse, rate limit) and tool side failures (tool error, timeout), pooled (O2).
Columns: early and late failure point.
Each tile: winning option, its saving versus the runner up with a paired bootstrap 95 percent CI,
and a strip with every option's per achieved energy relative to the winner.
"""
import argparse

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

import figlib as L
import style as S

OPTS = ("FR_warm", "FR_cold", "SR_warm", "SR_cold", "RB_warm", "RB_cold")
SIDES = (("model", ("json_parse", "rate_limit"), "Model side failure"),
         ("tool", ("tool_error", "timeout"), "Tool side failure"))


def pooled(cs, classes, pt, opt):
    """One task keyed cell pooled over the classes of a side."""
    out = {}
    for c in classes:
        for t, v in cs.get((c, pt, opt), {}).items():
            o = out.setdefault(t, [0.0, 0, 0])
            o[0] += v[0]; o[1] += v[1]; o[2] += v[2]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--out", default="figures")
    a = ap.parse_args()
    d = L.data_dir(a.data)
    rows = L.load_goals(d, studies=("e1", "e1b"))
    cs = L.cells(rows)
    S.apply()
    fig, axes = plt.subplots(2, 2, figsize=(S.COL, 2.55))
    out = {}
    for i, (side, classes, slabel) in enumerate(SIDES):
        for j, pt in enumerate(("early", "late")):
            ax = axes[i][j]
            ax.set_axis_off()
            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            cell = {o: pooled(cs, classes, pt, o) for o in OPTS}
            ach = {o: L.per_achieved(c) for o, c in cell.items() if c}
            ach = {o: v for o, v in ach.items() if v}
            rank = sorted(ach, key=ach.get)
            win, second = rank[0], rank[1]
            p, lo, hi, nt = L.boot_saving([(cell[win], cell[second])])
            k = sum(v[1] for v in cell[win].values()); n = sum(v[2] for v in cell[win].values())
            col, hatch = S.opt_color(win)
            ax.add_patch(FancyBboxPatch((0.02, 0.04), 0.96, 0.92, boxstyle="round,pad=0,rounding_size=0.06",
                                        fc=S.lighten(col, 0.86), ec="none"))
            ax.text(0.08, 0.80, S.OPT_LABEL[win], fontsize=7.5, fontweight="bold", color=S.C["INK"], va="center")
            ax.add_patch(plt.Rectangle((0.08, 0.63), 0.03, 0.08, fc=col, ec="none", hatch=hatch))
            sig = "" if lo > 0 else " (n.s.)"
            ax.text(0.14, 0.67, "%.0f%% below %s%s" % (p, S.OPT_SHORT[second], sig), fontsize=6.5, va="center")
            ax.text(0.14, 0.55, "95%% CI %.0f to %.0f%%" % (lo, hi), fontsize=6, color=S.C["MUTED"], va="center")
            ax.text(0.14, 0.44, "correct %d of %d" % (k, n), fontsize=6, color=S.C["MUTED"], va="center")
            # strip: every option relative to the winner (1.0 = winner), axis 1.0 to 1.6
            x0, x1, lo_r, hi_r = 0.10, 0.92, 1.0, 1.6
            ax.plot([x0, x1], [0.22, 0.22], color=S.C["GRID"], lw=1.2, solid_capstyle="round")
            for o in rank:
                r = min(ach[o] / ach[win], hi_r)
                x = x0 + (r - lo_r) / (hi_r - lo_r) * (x1 - x0)
                c2, h2 = S.opt_color(o)
                ax.scatter([x], [0.22], s=16, color=c2, hatch=h2, edgecolor="white", linewidth=0.6, zorder=3)
            ax.text(x0, 0.07, "1.0", fontsize=5.5, color=S.C["MUTED"], ha="center")
            ax.text(x1, 0.07, "1.6×", fontsize=5.5, color=S.C["MUTED"], ha="center")
            out["%s_%s" % (side, pt)] = {"winner": win, "runner_up": second, "saving": p, "lo": lo, "hi": hi,
                                         "tasks": nt, "ok": k, "n": n, "per_achieved_j": ach}
    for j, pt in enumerate(("Early failure", "Late failure")):
        axes[0][j].set_title(pt, fontweight="bold", pad=2)
    for i, (_, _, slabel) in enumerate(SIDES):
        axes[i][0].text(-0.04, 0.5, slabel, rotation=90, ha="right", va="center", fontsize=7,
                        fontweight="bold", transform=axes[i][0].transAxes)
    fig.text(0.5, -0.01, "Dots: every option's energy per successful goal relative to the winner (lower is better)",
             ha="center", fontsize=6, color=S.C["MUTED"])
    fig.subplots_adjust(wspace=0.06, hspace=0.12)
    S.save(fig, "F3_winner_map", a.out, out, L.is_demo(d))


if __name__ == "__main__":
    main()
