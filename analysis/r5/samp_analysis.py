"""RAF R5 (coordinator Oct 20): raf_samp analysis, FR_warm vs SR_warm per (class, point),
temperature 0.7, seeds as repeats, paired bootstrap by task (2000 draws, seed 0).
Greedy comparison: the same cells at temperature 0 from a reference export (E1 in tag e1_e1b_e2_v2).
Usage: python samp_analysis.py <samp_export_dir> <samp_ledger_dir> <greedy_export_dir> <out_dir> <tag> [study]
study: the study label of the sampling slice in the ledgers (default raf_samp).
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

import controller_model as cm
import fit_controller_params as F

BOOT, SEED = 2000, 0
CAMEL = {"json_parse": "JsonParse", "rate_limit": "RateLimit", "timeout": "Timeout", "tool_error": "ToolError"}
FR, SR = "FR_warm", "SR_warm"


def J(s):
    k = s.ok.sum()
    return s.epg.sum() / k if k > 0 else np.nan


def saving(c, rng):
    """100 (J_FR - J_SR) / J_FR on tasks with both options; positive: resume cheaper."""
    tasks = sorted(set(c[c.option == FR].task) & set(c[c.option == SR].task))
    if not tasks:
        return None
    by = {t: c[c.task == t] for t in tasks}
    def stat(ts):
        x = pd.concat([by[t] for t in ts])
        jf, js = J(x[x.option == FR]), J(x[x.option == SR])
        return 100 * (jf - js) / jf
    d = np.array([stat(rng.choice(tasks, len(tasks))) for _ in range(BOOT)])
    return dict(value=float(stat(tasks)), ci=[float(np.nanpercentile(d, 2.5)), float(np.nanpercentile(d, 97.5))],
                tasks=len(tasks), nan_draws=int(np.isnan(d).sum()))


def main(exp, ledir, gexp, out, tag, study="raf_samp"):
    os.makedirs(out, exist_ok=True)
    rep = {}
    for f in glob.glob(ledir + "/*ledger*.jsonl"):
        for l in open(f):
            if l.strip():
                r = json.loads(l)
                if str(r.get("study")).startswith(study) and "smoke" not in str(r.get("study")):
                    pl = r.get("plan", {})
                    rep[r["goal_id"]] = (pl.get("rep"), str(r.get("seeds")))
    t = F.goal_table(os.path.join(exp, "goals.csv"))
    t = t[t.goal_id.isin(rep) & t.option.isin([FR, SR])].copy()
    t["seedkey"] = t.goal_id.map(lambda g: rep[g][1])
    rng = np.random.default_rng(SEED)
    g = F.goal_table(os.path.join(gexp, "goals.csv"))
    g = g[g.option.isin([FR, SR])]
    res, nums, match, cells = {}, {}, 0, 0
    for (cls, pt), c in t.groupby(["cls", "point"]):
        k = CAMEL.get(cls)
        if k is None:
            continue
        P = str(pt).capitalize()
        sv = saving(c, rng)
        succ = {o: (int(c[c.option == o].ok.sum()), int((c.option == o).sum())) for o in (FR, SR)}
        gc = g[(g.cls == cls) & (g.point == pt) & g.task.isin(c.task.unique())]
        gw = None
        if len(gc):
            jf, js = J(gc[gc.option == FR]), J(gc[gc.option == SR])
            gw = SR if js < jf else FR
        sw = None if sv is None else (SR if sv["value"] > 0 else FR)
        if gw is not None and sw is not None:
            cells += 1
            match += int(gw == sw)
        res[f"{cls}|{pt}"] = dict(saving=sv, succ=succ, winner_samp=sw, winner_greedy=gw)
        nums[f"samp{k}{P}ResumeVsRestart"] = sv
        nums[f"samp{k}{P}SrSucc"] = dict(value=succ[SR][0] / max(succ[SR][1], 1), ci=[float(x) for x in cm.wilson(*succ[SR])])
        nums[f"samp{k}{P}FrSucc"] = dict(value=succ[FR][0] / max(succ[FR][1], 1), ci=[float(x) for x in cm.wilson(*succ[FR])])
    # Per point, classes pooled (coordinator Oct 21): does the early restart, late resume split hold?
    split = {}
    for pt, c in t.groupby("point"):
        sv = saving(c, rng)
        nums[f"samp{str(pt).capitalize()}ResumeVsRestart"] = sv
        split[str(pt)] = sv
    e, l = split.get("early"), split.get("late")
    nums["sampSplitHolds"] = bool(e is not None and l is not None and e["ci"][1] < 0 and l["ci"][0] > 0)
    grp = t.groupby(["task", "cls", "point", "option"]).ok
    pairs = same = 0
    per_task = {}
    for key, s in grp:
        v = s.values
        n = len(v)
        p = n * (n - 1) // 2
        q = sum(int(v[i] == v[j]) for i in range(n) for j in range(i + 1, n))
        pairs += p; same += q
        a = per_task.setdefault(key[0], [0, 0]); a[0] += q; a[1] += p
    tk = [k for k in per_task if per_task[k][1]]
    def so(ts):
        q = sum(per_task[k][0] for k in ts); p = sum(per_task[k][1] for k in ts)
        return 100 * q / p if p else np.nan
    d = np.array([so(rng.choice(tk, len(tk))) for _ in range(BOOT)]) if tk else np.array([np.nan])
    nums["sampSameOutcome"] = dict(value=float(so(tk)) if tk else None,
                                   ci=[float(np.nanpercentile(d, 2.5)), float(np.nanpercentile(d, 97.5))], pairs=int(pairs))
    nums["sampWinnerMatchesGreedy"] = int(match)
    nums["sampCells"] = int(cells)
    nums["sampNTasks"] = int(t.task.nunique())
    nums["sampProvenance"] = dict(data_tag=tag, export=exp, greedy_export=gexp, study=study, boot=BOOT, seed=SEED,
                                  goals=int(len(t)), goals_sha256=F._sha(os.path.join(exp, "goals.csv")),
                                  definition="ResumeVsRestart = 100 (J_FR_warm - J_SR_warm) / J_FR_warm, energy per achieved "
                                             "goal, seeds pooled as repeats, paired bootstrap by task; SameOutcome = share of "
                                             "seed pairs with the same checker verdict in each (task, class, point, option)")
    json.dump(dict(cells=res, **nums), open(os.path.join(out, "r5_samp_detail.json"), "w"), indent=1)
    json.dump(nums, open(os.path.join(out, "r5_numbers.json"), "w"), indent=1)
    for k, v in res.items():
        s = v["saving"]
        val = "n/a" if s is None else round(s["value"], 1)
        ci = None if s is None else [round(x, 1) for x in s["ci"]]
        print(f"{k:20s} resume vs restart {val} CI {ci} succ SR {v['succ'][SR]} FR {v['succ'][FR]} "
              f"winner {v['winner_samp']} greedy {v['winner_greedy']}")
    print("early pooled", split.get("early"), "late pooled", split.get("late"), "splitHolds", nums["sampSplitHolds"])
    print("sameOutcome", nums["sampSameOutcome"], "winnerMatchesGreedy", match, "of", cells, "tasks", nums["sampNTasks"])


if __name__ == "__main__":
    a = sys.argv[1:]
    main(*a[:5], *(a[5:6] or []))
