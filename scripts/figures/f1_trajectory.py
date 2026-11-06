#!/usr/bin/env python3
"""F1 one failure, two recoveries (E1, road trip task 71, timeout, late failure, repetition 1).

Each row is one goal drawn on a common axis of cumulative board energy (J).
Model calls are boxes whose length is the call's measured board dynamic energy; tool calls are small dots.
Attempt 1 is gray up to the injected failure (red cross); attempt 2 is colored by the recovery.
Restart repays the work before the failure; resume continues from it.
Right side: attempt 2 board energy and uncached prompt tokens, and the checker verdict.
"""
import argparse

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

import figlib as L
import style as S

TASK, CLS, PT = "multi_turn_base_71", "timeout", "late"
ROWS = (("FR_warm", "Restart"), ("SR_warm", "Resume"))


def pick(goals, opt):
    """Lowest goal id of the cell (repetition 1)."""
    m = [g for g in goals if g["study"] == "e1" and g["task"].endswith(TASK) and g["cls"] == CLS
         and g["point"] == PT and g["option"] == opt]
    return min(m, key=lambda g: int(g["goal_id"])) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--out", default="figures")
    a = ap.parse_args()
    d = L.data_dir(a.data)
    goals = L.load_goals(d, studies=("e1",))
    calls = L.load_calls(d)
    S.apply()
    fig, ax = plt.subplots(figsize=(S.FULL, 1.25))
    out = {"task": TASK, "cls": CLS, "point": PT, "rows": {}}
    xmax = 0.0
    for i, (opt, name) in enumerate(ROWS):
        g = pick(goals, opt)
        if not g:
            continue
        y = len(ROWS) - 1 - i
        x = 0.0
        cs = calls.get(int(g["goal_id"]), [])
        col, _ = S.opt_color(opt)
        a2_j = a2_tok = 0.0
        # per call energy needs sample timestamps; without them each attempt's measured energy is
        # split evenly over its calls (segment length stays the measured attempt energy)
        if cs and all(c["board_j"] is None for c in cs):
            rec = float(g.get("board_j_rec") or 0.0)
            tot = float(g["board_j"] or 0.0)
            per_att = {1: tot - rec, 2: rec}
            n_att = {k: sum(1 for c in cs if min(c["attempt"], 2) == k) for k in (1, 2)}
            for c in cs:
                k = min(c["attempt"], 2)
                c["board_j"] = per_att[k] / n_att[k] if n_att[k] else 0.0
            out["per_call_energy"] = "attempt energy split evenly over calls (no sample timestamps)"
        for c in cs:
            e = c["board_j"] or 0.0
            fc = S.lighten(S.C["B0"], 0.45) if c["attempt"] == 1 else col
            if c["kind"] == "model":
                ax.add_patch(FancyBboxPatch((x, y - 0.22), max(e - 2, 1), 0.44,
                                            boxstyle="round,pad=0,rounding_size=3", fc=fc, ec="none",
                                            mutation_aspect=0.02))
            else:
                ax.scatter([x + e / 2], [y], s=6, color=fc, zorder=3)
            if c["failed"]:
                ax.scatter([x + e], [y], marker="x", s=30, color=S.C["FAIL"], linewidth=1.4, zorder=4)
            if c["attempt"] >= 2:
                a2_j += e
                a2_tok += c["uncached_tokens"] or 0.0
            x += e
        xmax = max(xmax, x)
        ax.text(-8, y, name, ha="right", va="center", fontsize=7, fontweight="bold", color=col)
        out["rows"][opt] = {"goal_id": int(g["goal_id"]), "attempt2_board_j": a2_j,
                            "attempt2_uncached_tokens": a2_tok, "ok": g["ok"], "total_board_j": x}
    if xmax <= 0:
        print("F1: no drawable goal (rows found: %s); check goals.csv for e1 %s %s %s"
              % (list(out["rows"]), TASK, CLS, PT))
        xmax = 1.0
    for opt, name in ROWS:
        r = out["rows"].get(opt)
        if not r:
            continue
        y = len(ROWS) - 1 - [o for o, _ in ROWS].index(opt)
        verdict = "checker: correct" if r["ok"] else "checker: wrong"
        tok = ("" if not r["attempt2_uncached_tokens"] else
               ", %s uncached tokens" % "{:,.0f}".format(r["attempt2_uncached_tokens"]))
        ax.text(xmax * 1.03, y, "attempt 2: %s J%s\n%s" % ("{:,.0f}".format(r["attempt2_board_j"]), tok, verdict),
                va="center", fontsize=6.5)
    ax.set_xlim(0, xmax * 1.42)
    ax.set_ylim(-0.6, len(ROWS) - 0.4)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Cumulative board energy of the goal (J); gray = attempt 1, red cross = injected timeout")
    S.save(fig, "F1_trajectory", a.out, out, L.is_demo(d))


if __name__ == "__main__":
    main()
