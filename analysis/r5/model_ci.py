"""RAF R5 (coordinator Oct 20): CIs for a single model fit (Mistral m3, gpt-oss m4), never pooled.
Same CI method as augment_r5_numbers.py (bootstrap over tasks, 1000 draws, seed 0; success Wilson),
using its boot, gain and linear_law_ci. Writes prefixed fields into <r5_dir>/r5_numbers.json.
Usage: python model_ci.py <export_dir> <r5_dir> <tag> <prefix>   (prefix: m3 or m4)
"""
import json
import os
import sys

import controller_model as cm
import fit_controller_params as F
from augment_r5_numbers import boot, gain, linear_law_ci, eps


def main(exp, out, tag, px):
    t = F.goal_table(os.path.join(exp, "goals.csv"))
    _, rows = F.cross_validate(t)
    e, sr = eps(rows)
    succ = rows.groupby("method").ok.agg(["sum", "size"])
    w = lambda m: [float(x) for x in cm.wilson(succ.loc[m, "sum"], succ.loc[m, "size"])]
    sav = lambda ref: dict(value=float(100 * (e[ref] - e["model"]) / e[ref]), ci=boot(rows, gain(ref, "model")))
    npath = os.path.join(out, "r5_numbers.json")
    nums = json.load(open(npath))
    law = nums["energyLaw"]
    lin = linear_law_ci(os.path.join(exp, "calls.csv"))
    d_ci = law["ci"]["d"]
    add = {
        f"{px}CtrlSavingVsResume": sav("always_SR_warm"),
        f"{px}CtrlSavingVsRestart": sav("always_FR_warm"),
        f"{px}CtrlSavingVsRollback": sav("always_RB_cold"),
        f"{px}CtrlSavingVsXstarRule": sav("xstar_rule"),
        f"{px}CtrlSavingVsGbr": sav("gbr"),
        f"{px}CtrlSavingVsUncached": sav("tok_uncached_rule"),
        f"{px}CtrlSavingVsBilled": sav("tok_billed_rule"),
        f"{px}CtrlOfflineSucc": dict(value=float(sr["model"]), ci=w("model")),
        f"{px}FrOfflineSucc": dict(value=float(sr["always_FR_warm"]), ci=w("always_FR_warm")),
        f"{px}SrOfflineSucc": dict(value=float(sr["always_SR_warm"]), ci=w("always_SR_warm")),
        f"{px}RbOfflineSucc": dict(value=float(sr["always_RB_cold"]), ci=w("always_RB_cold")),
        f"{px}NBlocks": int(succ.loc["model", "size"]),
        f"{px}NGoals": int(t.goal_id.nunique()),
        f"{px}NTasks": int(t.task.nunique()),
        f"{px}EnergyLawLinear": lin,
        f"{px}QuadSupported": bool(d_ci[0] > 0 or d_ci[1] < 0),
        f"{px}Provenance": dict(data_tag=tag, export=exp, fit=nums.get("provenance"),
                                ci_method="95% percentile bootstrap over tasks, 1000 draws, seed 0; success Wilson",
                                note="single model fit, never pooled with 30B data"),
    }
    nums.update(add)
    json.dump(nums, open(npath, "w"), indent=1)
    for k, v in add.items():
        if isinstance(v, dict) and "value" in v:
            print(f"{k:28s} {v['value']:8.3f} CI {[round(x, 3) for x in v['ci']]}")
    print(px, "blocks", add[f"{px}NBlocks"], "goals", add[f"{px}NGoals"], "tasks", add[f"{px}NTasks"],
          "quadSupported", add[f"{px}QuadSupported"], "linear", lin)


if __name__ == "__main__":
    main(*sys.argv[1:5])
