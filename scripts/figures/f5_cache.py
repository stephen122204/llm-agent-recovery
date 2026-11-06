#!/usr/bin/env python3
"""F5 keeping the prefix cache saves far more tokens than joules (E1 plus E1b, recovery attempts).

Per recovery depth (restart, resume, roll back): percent reduction warm versus cold of the same option,
in uncached prompt tokens and in board energy, each with a paired bootstrap 95 percent CI over tasks.
Uses the recovery attempt columns (attempt 2 onward) when the export has them, else the whole goal.
"""
import argparse
import collections
import random

import matplotlib.pyplot as plt

import figlib as L
import style as S

FAMS = (("FR", "Restart"), ("SR", "Resume"), ("RB", "Roll back"))


def reduction(rows, fam, col):
    """Percent reduction warm vs cold of per goal mean, pooled over situations, paired by task."""
    t = collections.defaultdict(lambda: {"warm": [0.0, 0], "cold": [0.0, 0]})
    for r in rows:
        if r["option"] not in (fam + "_warm", fam + "_cold") or r.get(col) is None:
            continue
        v = t[r["task"]][r["option"].split("_")[1]]
        v[0] += r[col]; v[1] += 1
    tasks = sorted(k for k, v in t.items() if v["warm"][1] and v["cold"][1])
    if not tasks:
        return None  # no task has both a warm and a cold goal with this column

    def red(draw):
        w = sum(t[k]["warm"][0] for k in draw) / sum(t[k]["warm"][1] for k in draw)
        c = sum(t[k]["cold"][0] for k in draw) / sum(t[k]["cold"][1] for k in draw)
        return 100 * (1 - w / c)

    rng = random.Random(L.BOOT_SEED)
    vals = sorted(red([rng.choice(tasks) for _ in tasks]) for _ in range(L.BOOT_REPS))
    return red(tasks), vals[int(0.025 * (len(vals) - 1))], vals[int(round(0.975 * (len(vals) - 1)))], len(tasks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--out", default="figures")
    a = ap.parse_args()
    d = L.data_dir(a.data)
    rows = L.load_goals(d, studies=("e1", "e1b"))
    e_col = "board_j_rec" if rows and rows[0].get("board_j_rec") not in (None, "") else "board_j"
    t_col = "tok_uncached_rec" if rows and rows[0].get("tok_uncached_rec") not in (None, "") else "tok_uncached"
    for r in rows:
        for k in (e_col, t_col):
            r[k] = float(r[k]) if r.get(k) not in (None, "", "NA") else None
    S.apply()
    fig, ax = plt.subplots(figsize=(S.COL, 1.45))
    out = {"energy_column": e_col, "token_column": t_col, "families": {}}
    for i, (fam, name) in enumerate(FAMS):
        y = len(FAMS) - 1 - i
        col = S.C[fam]
        for dy, metric, colname, marker in ((0.15, "tokens", t_col, "s"), (-0.15, "joules", e_col, "o")):
            if not any(r.get(colname) is not None for r in rows):
                out["families"].setdefault(fam, {})[metric] = "not available (no cached token column)"
                continue
            r_ = reduction(rows, fam, colname)
            if r_ is None:
                print("F5: no warm and cold pairs for %s %s" % (fam, colname))
                out["families"].setdefault(fam, {})[metric] = "no warm and cold pairs"
                continue
            p, lo, hi, nt = r_
            ax.plot([lo, hi], [y + dy, y + dy], color=col, lw=0.9)
            fc = "white" if metric == "joules" else col
            ax.scatter([p], [y + dy], marker=marker, s=22, facecolor=fc, edgecolor=col, linewidth=1.0, zorder=3)
            ax.text(hi + 1.5, y + dy, "%.0f%%" % p, va="center", fontsize=6, color=S.C["INK"])
            out["families"].setdefault(fam, {})[metric] = {"reduction_pct": p, "lo": lo, "hi": hi, "tasks": nt}
    ax.axvline(0, color=S.C["MUTED"], lw=0.6)
    ax.set_yticks(range(len(FAMS)))
    ax.set_yticklabels([n for _, n in reversed(FAMS)])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Reduction from keeping the cache warm (%)")
    ax.set_xlim(min(-5, ax.get_xlim()[0]), max(100, ax.get_xlim()[1]))
    ax.scatter([], [], marker="s", s=18, color=S.C["MUTED"], label="uncached tokens")
    ax.scatter([], [], marker="o", s=18, facecolor="white", edgecolor=S.C["MUTED"], label="board joules")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.33), ncol=2, handletextpad=0.2, columnspacing=1.2)
    S.direction(ax, "Saving from a warm cache: tokens versus joules")
    S.save(fig, "F5_cache", a.out, out, L.is_demo(d))


if __name__ == "__main__":
    main()
