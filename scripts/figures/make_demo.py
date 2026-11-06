#!/usr/bin/env python3
"""make_demo.py: synthetic goals.csv and calls.csv with the real column layout.

Only for building and checking figure layouts before the store export exists.
Writes a DEMO marker file; every figure made from it is stamped DEMO DATA.
"""
import argparse
import csv
import os
import random

CLS = ("json_parse", "rate_limit", "tool_error", "timeout")
SUCC = {"FR": (0.94, 0.93), "SR": (0.72, 0.86), "RB": (0.90, 0.95), "SG": (0.80, 0.84)}
EXTRA = {"FR": (1.0, 1.0), "SR": (0.15, 0.15), "RB": (0.45, 0.35), "SG": (0.3, 0.3)}


def goal(rng, opt, pt):
    fam, cache = opt.split("_")
    w = 3 if pt == "early" else 13               # calls done before the failure
    total = 22
    redo = w * EXTRA[fam][0 if pt == "early" else 1]
    calls = total + redo + (2 if fam == "SR" and pt == "early" else 0)
    e = calls * (44 + 0.012 * 9000) * rng.uniform(0.9, 1.1)
    e *= 1.0 if cache == "warm" else 1.06
    tok = calls * (2500 if cache == "warm" else 6500) * rng.uniform(0.9, 1.1)
    ok = int(rng.random() < SUCC[fam][0 if pt == "early" else 1])
    return ok, e, tok, calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rng = random.Random(7)
    rows, gid = [], 1000
    tasks = ["multi_turn_base_%d" % i for i in range(30)] + ["multi_turn_base_71"]
    for study, opts in (("e1", ("FR_warm", "FR_cold", "SR_warm", "SR_cold")),
                        ("e1b", ("RB_warm", "RB_cold", "SG_warm", "SG_cold"))):
        for t in tasks:
            for c in CLS:
                for pt in ("early", "late"):
                    for o in opts:
                        ok, e, tok, n = goal(rng, o, pt)
                        gid += 1
                        rows.append([study, gid, t, c, pt, o, ok, "%.1f" % e, "%.1f" % (e * 0.7),
                                     "%.0f" % tok, "%.0f" % (tok * 3), "%.0f" % n])
    for t in tasks[:28]:
        for c in ("json_parse", "tool_error"):
            for pt in ("early", "late"):
                for arm, base in (("ctrl_beta", None), ("xstar_rule", None), ("token_rule", "SR_warm"),
                                  ("FR_warm", "FR_warm"), ("SR_warm", "SR_warm"), ("RB_cold", "RB_cold")):
                    o = base or ("FR_warm" if pt == "early" else "SR_warm")
                    ok, e, tok, n = goal(rng, o, pt)
                    if arm == "ctrl_beta":
                        e *= 0.93
                    gid += 1
                    rows.append(["e3", gid, t, c, pt, arm, ok, "%.1f" % e, "%.1f" % (e * 0.7),
                                 "%.0f" % tok, "%.0f" % (tok * 3), "%.0f" % n])
    with open(os.path.join(a.out, "goals.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["study", "goal_id", "task", "cls", "point", "option", "ok", "board_j", "pkg_j",
                    "tok_uncached", "tok_billed", "calls"])
        w.writerows(rows)
    # calls of the two Figure 1 goals: task 71, timeout, late, FR_warm and SR_warm
    crow = []
    for r in rows:
        if r[0] == "e1" and r[2] == "multi_turn_base_71" and r[3] == "timeout" and r[4] == "late" \
                and r[5] in ("FR_warm", "SR_warm"):
            kinds = ["model", "tool"] * 9
            step = 0
            for i, k in enumerate(kinds[:13]):
                crow.append(["e1", r[1], 1, step, k, 3000 + 600 * i, 3000 + 600 * i if k == "model" else "",
                             "%.1f" % (rng.uniform(70, 160) if k == "model" else rng.uniform(5, 15)),
                             1 if i == 12 else 0])
                step += 1
            seq = kinds if r[5] == "FR_warm" else kinds[13:]
            for i, k in enumerate(seq):
                ctx = 3000 + 600 * (i if r[5] == "FR_warm" else i + 13)
                crow.append(["e1", r[1], 2, step, k, ctx, (400 if r[5] == "SR_warm" else ctx * 0.3) if k == "model" else "",
                             "%.1f" % (rng.uniform(70, 160) if k == "model" else rng.uniform(5, 15)), 0])
                step += 1
    with open(os.path.join(a.out, "calls.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["study", "goal_id", "attempt", "step", "kind", "prompt_tokens", "uncached_tokens",
                    "board_j", "failed"])
        w.writerows(crow)
    open(os.path.join(a.out, "DEMO"), "w").write("synthetic\n")
    print("demo rows", len(rows), "calls", len(crow))


if __name__ == "__main__":
    main()
