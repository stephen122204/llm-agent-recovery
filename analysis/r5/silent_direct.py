"""RAF R5 (coordinator Oct 19): direct comparison of silent_detected cells, no fit.
Per position (early, middle): energy per successful goal of SR_warm (resume) against
FR_warm (restart) and against RB_cold (roll back), paired bootstrap by task over
tasks that have both options measured at that position.
saving_pct = 100 (J_other - J_SR_warm) / J_other; positive means resume is lower.
silentResumeLowerAllPos = true only if resume is lower than FR_warm at every position
with the 95% CI excluding zero (lower bound > 0); comparisons against RB_cold are reported.
Usage: python silent_direct.py <export_dir> <r5_numbers.json> <tag>
"""
import json
import os
import sys

import numpy as np

import fit_controller_params as F

BOOT, SEED = 2000, 0
POS = ["early", "middle"]
RESUME, OTHERS = "SR_warm", ["FR_warm", "RB_cold"]


def j(s):
    k = s.ok.sum()
    return s.epg.sum() / k if k > 0 else np.nan


def compare(c, other, rng):
    a, b = c[c.option == RESUME], c[c.option == other]
    tasks = sorted(set(a.task) & set(b.task))
    if not tasks:
        return None
    a, b = a[a.task.isin(tasks)], b[b.task.isin(tasks)]
    ga, gb = {t: a[a.task == t] for t in tasks}, {t: b[b.task == t] for t in tasks}

    def stat(ts):
        import pandas as pd
        ja = j(pd.concat([ga[t] for t in ts])); jb = j(pd.concat([gb[t] for t in ts]))
        return 100 * (jb - ja) / jb
    draws = np.array([stat(rng.choice(tasks, len(tasks))) for _ in range(BOOT)])
    ci = [float(np.nanpercentile(draws, 2.5)), float(np.nanpercentile(draws, 97.5))]
    return dict(saving_pct=float(stat(tasks)), ci=ci, tasks=len(tasks),
                n_resume=int(len(a)), n_other=int(len(b)),
                succ_resume=f"{int(a.ok.sum())}/{len(a)}", succ_other=f"{int(b.ok.sum())}/{len(b)}",
                J_resume=float(j(a)), J_other=float(j(b)), nan_draws=int(np.isnan(draws).sum()))


def main(exp, npath, tag):
    gp = os.path.join(exp, "goals.csv")
    t = F.goal_table(gp)
    s = t[t.cls == "silent_detected"]
    rng = np.random.default_rng(SEED)
    res = {p: {o: compare(s[s.point == p], o, rng) for o in OTHERS} for p in POS}
    flag = all(res[p]["FR_warm"] is not None and res[p]["FR_warm"]["ci"][0] > 0 for p in POS)
    prov = dict(data_tag=tag, export=exp, goals_sha256=F._sha(gp), boot=BOOT, seed=SEED,
                definition="silentResumeLowerAllPos is true only if SR_warm has lower energy per successful goal "
                           "than FR_warm at early and at middle, each with the 95% CI of the saving above zero; "
                           "paired bootstrap by task; RB_cold comparisons reported, not part of the flag")
    nums = json.load(open(npath))
    nums.update(silentDirect=res, silentResumeLowerAllPos=bool(flag), silentDirectProvenance=prov)
    json.dump(nums, open(npath, "w"), indent=1)
    for p in POS:
        for o in OTHERS:
            r = res[p][o]
            if r is None:
                print(f"{p:6s} SR_warm vs {o}: no paired tasks")
                continue
            print(f"{p:6s} SR_warm vs {o}: saving {r['saving_pct']:.1f}% CI [{r['ci'][0]:.1f}, {r['ci'][1]:.1f}] "
                  f"tasks {r['tasks']} J {r['J_resume']:.0f} vs {r['J_other']:.0f} "
                  f"succ {r['succ_resume']} vs {r['succ_other']} nan_draws {r['nan_draws']}")
    print("silentResumeLowerAllPos", flag)


if __name__ == "__main__":
    main(*sys.argv[1:4])
