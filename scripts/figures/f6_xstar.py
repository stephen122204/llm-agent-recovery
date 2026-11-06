#!/usr/bin/env python3
"""F6 restart threshold x* per clean failure class (OFFLINE CALIBRATED RULE, R5 r5_numbers.json).

Below x* calls of completed work restarting is cheaper per successful goal; above it resuming is.
Dot = x*, bar = bootstrap 95 percent CI (R5 ci_method), light band = range of work observed.
The silent class has no identified x* (O8) and is never drawn.
"""
import argparse
import json
import os

import matplotlib.pyplot as plt

import style as S

ORDER = ("rate_limit", "tool_error", "json_parse", "timeout")


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--r5", default=os.path.join(here, "..", "..", "data", "r5", "r5_numbers.json"))
    ap.add_argument("--out", default="figures")
    a = ap.parse_args()
    r5 = json.load(open(a.r5))
    if r5.get("provenance", {}).get("data_tag") != "e1_e1b_e2":
        raise SystemExit("r5 data_tag mismatch")
    xs = r5["xstar"]
    S.apply()
    fig, ax = plt.subplots(figsize=(S.COL, 1.55))
    out = {"label": "OFFLINE CALIBRATED RULE (R5, data_tag e1_e1b_e2)", "classes": {}}
    xmax = 24
    for i, c in enumerate(ORDER):
        x = xs[c]
        lo, hi = x["x_star_calls_ci"]
        wlo, whi = x["W_range"]
        side = S.SIDE[c]
        col = S.C["SR"] if side == "tool" else S.C["FR"]
        y = len(ORDER) - 1 - i
        ax.plot([wlo, whi], [y, y], color=S.C["GRID"], lw=6, solid_capstyle="round", zorder=1)
        ax.plot([lo, hi], [y, y], color=S.C["INK"], lw=1.0, zorder=2)
        ax.plot([lo, lo], [y - 0.12, y + 0.12], color=S.C["INK"], lw=0.8)
        ax.plot([hi, hi], [y - 0.12, y + 0.12], color=S.C["INK"], lw=0.8)
        ax.scatter([x["x_star_calls"]], [y], s=26, color=S.C["CTRL"], edgecolor="white", linewidth=0.8, zorder=3)
        ax.text(hi + 0.5, y, "%.1f" % x["x_star_calls"], va="center", fontsize=6.5, color=S.C["INK"])
        out["classes"][c] = {"x_star_calls": x["x_star_calls"], "ci": [lo, hi], "work_range": [wlo, whi]}
    ax.set_yticks(range(len(ORDER)))
    ax.set_yticklabels([S.CLS_LABEL[c] for c in reversed(ORDER)])
    ax.set_xlim(0, xmax)
    ax.set_ylim(-1.1, len(ORDER) - 0.5)
    ax.set_xlabel("Work completed at failure (model plus tool calls)")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.text(0.3, -0.85, "← restart cheaper", fontsize=6, color=S.C["MUTED"], va="center")
    ax.text(xmax - 0.3, -0.85, "resume cheaper →", fontsize=6, color=S.C["MUTED"], va="center", ha="right")
    S.direction(ax, "Restart threshold x* per failure class")
    S.save(fig, "F6_xstar", a.out, out)


if __name__ == "__main__":
    main()
