#!/usr/bin/env python3
"""F8 online learning controller versus baselines on held out tasks (E3, board energy per successful goal).

ONLINE LEARNING CONTROLLER (E3). Bars: energy per successful goal with a bootstrap 95 percent CI over tasks;
right column: correct goals with Wilson 95 percent interval. Dashed line: best fixed policy.
"""
import argparse
import collections

import matplotlib.pyplot as plt

import figlib as L
import style as S

ARMS = ("ctrl_beta", "xstar_rule", "token_rule", "RB_cold", "SR_warm", "FR_warm")
FIXED = ("RB_cold", "SR_warm", "FR_warm")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--out", default="figures")
    a = ap.parse_args()
    d = L.data_dir(a.data)
    rows = L.load_goals(d, studies=("e3",))
    by = collections.defaultdict(list)
    for r in rows:
        by[r["option"]].append(r)
    arms = [x for x in ARMS if by.get(x)]
    S.apply()
    fig, ax = plt.subplots(figsize=(S.COL, 1.75))
    out = {"label": "ONLINE LEARNING CONTROLLER (E3)", "arms": {}}
    vals = {}
    for i, arm in enumerate(arms):
        cell = L.by_task(by[arm])
        p, lo, hi = L.boot_cell(cell)
        k = sum(v[1] for v in cell.values()); n = sum(v[2] for v in cell.values())
        wl, wh = L.wilson(k, n)
        vals[arm] = p
        y = len(arms) - 1 - i
        col, hatch = S.opt_color(arm)
        if arm == "token_rule":
            col = S.lighten(S.C["MUTED"], 0.5)
        ax.barh(y, p, height=0.62, color=col, hatch=hatch, edgecolor="white", linewidth=0.6)
        ax.plot([lo, hi], [y, y], color=S.C["INK"], lw=0.8)
        ax.text(p * 0.03, y, "%.0f J" % p, va="center", ha="left", fontsize=6,
                color=S.C["INK"] if hatch or arm == "token_rule" else "white", fontweight="bold")
        out["arms"][arm] = {"per_achieved_j": p, "lo": lo, "hi": hi, "ok": k, "n": n, "wilson": [wl, wh]}
        out["arms"][arm]["_succ_y"] = y
    xmax = max(out["arms"][x]["hi"] for x in arms) * 1.22
    for arm in arms:
        v = out["arms"][arm]
        ax.text(xmax * 0.86, v["_succ_y"], "%d/%d" % (v["ok"], v["n"]), va="center", fontsize=6,
                color=S.C["MUTED"])
        del v["_succ_y"]
    best = min((x for x in FIXED if x in vals), key=vals.get, default=None)
    if best:
        ax.axvline(vals[best], color=S.C["MUTED"], lw=0.6, ls=(0, (3, 2)), zorder=0)
        out["best_fixed"] = best
    ax.text(xmax * 0.86, len(arms) - 0.45, "correct", fontsize=6, color=S.C["MUTED"], va="bottom")
    ax.set_yticks(range(len(arms)))
    ax.set_yticklabels([S.OPT_LABEL[x] for x in reversed(arms)])
    for t in ax.get_yticklabels():
        if t.get_text() == S.OPT_LABEL["ctrl_beta"]:
            t.set_fontweight("bold"); t.set_color(S.C["INK"])
    ax.set_xlim(0, xmax)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Board energy per successful goal (J)")
    S.direction(ax, "energy per successful goal, held out tasks ↓")
    S.save(fig, "F8_e3_arms", a.out, out, L.is_demo(d))


if __name__ == "__main__":
    main()
