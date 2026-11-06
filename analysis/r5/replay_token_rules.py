"""RAF R5, coordinator Oct 18 jobs (a) and (b): offline replay of the uncached
token rule and the billed token rule on the same 5 fold by task blocks as O3.
energy per successful goal; paired bootstrap by task (same blocks for both methods).
Adds fields to <r5_dir>/r5_numbers.json; writes <r5_dir>/r5_token_rules.json.

Usage: python replay_token_rules.py <export_dir> <r5_dir> <tag>
"""
import json
import os
import sys

import numpy as np
import pandas as pd

import controller_model as cm
import fit_controller_params as F

BOOT, SEED = 2000, 0
RULES = ["tok_uncached_rule", "tok_billed_rule"]
REFS = ["model", "always_SR_warm", "always_FR_warm", "always_RB_cold", "xstar_rule"]
KEY = ["task", "cls", "point"]


def _eps(epg, ok):
    return epg.sum() / max(ok.sum(), 1)


def paired(r, rule, ref, rng):
    """Saving of ref against rule, percent: 100 (J_rule - J_ref) / J_rule, on blocks
    where both acted; 95% CI from resampling tasks."""
    m = r[r.method == rule].merge(r[r.method == ref], on=KEY, suffixes=("_r", "_x"))
    if m.empty:
        return None
    def stat(x):
        jr, jx = _eps(x.epg_r, x.ok_r), _eps(x.epg_x, x.ok_x)
        return 100 * (jr - jx) / jr
    tasks = m.task.unique()
    by = {t: m[m.task == t] for t in tasks}
    draws = [stat(pd.concat([by[t] for t in rng.choice(tasks, len(tasks))])) for _ in range(BOOT)]
    return dict(saving_pct=float(stat(m)),
                ci=[float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
                blocks=int(len(m)), tasks=int(len(tasks)))


def main(exp, out, tag):
    t = F.goal_table(os.path.join(exp, "goals.csv"))
    cv, r = F.cross_validate(t)
    rng = np.random.default_rng(SEED)
    n_blocks = int((r.method == "oracle").sum())
    res = dict(data_tag=tag, boot=BOOT, n_blocks=n_blocks,
               billed_definition="prompt plus completion tokens of all attempts after the failure, "
                                 "no cache discount, predicted per (class, option) as a + b W on the training folds",
               tie_rule="on equal predicted tokens the warm option is chosen",
               summary={}, paired={}, disagree={})
    for m in RULES + REFS + ["oracle"]:
        if m in cv.index:
            k, n = int(cv.loc[m, "succ"]), int(cv.loc[m, "blocks"])
            res["summary"][m] = dict(EpS=float(cv.loc[m, "EpS"]), regret_pct=float(cv.loc[m, "regret_pct"]),
                                     success=k / n, succ_ci=[float(v) for v in cm.wilson(k, n)],
                                     blocks=n, blocks_skipped=n_blocks - n)
    orc = r[r.method == "oracle"][KEY + ["option"]].rename(columns={"option": "oracle"})
    for rule in RULES:
        res["paired"][rule] = {ref: paired(r, rule, ref, rng) for ref in REFS}
        d = r[r.method == rule].merge(orc, on=KEY)
        d["side"] = np.where(d.cls == "silent_detected", "contaminating", "clean")
        dis = {f"{p}_{s}": float((g.option != g.oracle).mean()) for (p, s), g in d.groupby(["point", "side"])}
        dis["all"] = float((d.option != d.oracle).mean()) if len(d) else None
        res["disagree"][rule] = dis
    json.dump(res, open(os.path.join(out, "r5_token_rules.json"), "w"), indent=1)

    npath = os.path.join(out, "r5_numbers.json")
    nums = json.load(open(npath)) if os.path.exists(npath) else {}
    pu, pb = res["paired"]["tok_uncached_rule"]["model"], res["paired"]["tok_billed_rule"]["model"]
    nums.update(
        ctrlSavingVsUncached=pu and pu["saving_pct"], ctrlSavingVsUncachedCI=pu and pu["ci"],
        ctrlSavingVsBilled=pb and pb["saving_pct"], ctrlSavingVsBilledCI=pb and pb["ci"],
        uncachedRuleSucc=res["summary"].get("tok_uncached_rule", {}).get("success"),
        billedRuleSucc=res["summary"].get("tok_billed_rule", {}).get("success"),
        uncachedRuleRegret=res["summary"].get("tok_uncached_rule", {}).get("regret_pct"),
        billedRuleRegret=res["summary"].get("tok_billed_rule", {}).get("regret_pct"),
        tokenRuleDisagree=res["disagree"],
        tokenRulesProvenance=dict(data_tag=tag, export=exp, boot=BOOT, seed=SEED,
                                  label="offline calibrated rule (R5 decide, fixed parameters per fold, posterior mean)"))
    json.dump(nums, open(npath, "w"), indent=1)
    for k, v in res["summary"].items():
        print(f"{k:20s} EpS {v['EpS']:8.0f} regret {v['regret_pct']:5.1f}% succ {v['success']:.3f} "
              f"blocks {v['blocks']} skipped {v['blocks_skipped']}")
    for rule, d in res["paired"].items():
        for ref, p in d.items():
            if p:
                print(f"{ref} vs {rule}: {p['saving_pct']:.1f}% [{p['ci'][0]:.1f}, {p['ci'][1]:.1f}] n={p['blocks']}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
