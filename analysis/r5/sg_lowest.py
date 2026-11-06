"""RAF R5 (coordinator Oct 19): sgLowestCount and sgSituations.
A situation is (failure class, failure point) on the clean E1b classes and points.
In each situation, energy per successful goal per option = sum of goal energy / successes,
pooling E1 and E1b goals (E1 measures FR and SR, E1b measures RB and SG; O1).
sgLowestCount = situations where SG_warm or SG_cold has the lowest value.
Also reported by (side, point), the four cells of O1.
Usage: python sg_lowest.py <export_dir> <r5_numbers.json> <tag>
"""
import json
import os
import sys

import pandas as pd

import fit_controller_params as F

STUDIES = ["raf_e1", "raf_e1b"]


def lowest(g):
    s = g.groupby("option").agg(e=("epg", "sum"), k=("ok", "sum"), n=("ok", "size"))
    s = s[s.k > 0]
    s["J"] = s.e / s.k
    return s.sort_values("J")


def main(exp, npath, tag):
    gp = os.path.join(exp, "goals.csv")
    g = pd.read_csv(gp).sort_values(["goal_id", "attempt"])
    a1 = g[g.attempt == 1].set_index("goal_id")
    agg = g.groupby("goal_id").agg(epg=("e_board_j", "sum"), ok=("pass_fail", "last"))
    t = a1[["study", "cls", "point", "option", "fired_phase"]].join(agg)
    t = t[t.study.isin(STUDIES) & (t.option != "B0")]
    t["ok"] = t.ok.fillna(0).astype(int)
    b_cls = sorted(t[t.study == "raf_e1b"].cls.unique())
    b_pts = sorted(t[t.study == "raf_e1b"].point.unique())
    t = t[t.cls.isin(b_cls) & t.point.isin(b_pts)]
    t["side"] = t.fired_phase.map({"llm": "model", "tool": "tool"}).fillna("other")
    by_cls, by_side = {}, {}
    for key, grp, out in [(["cls", "point"], None, by_cls), (["side", "point"], None, by_side)]:
        for k, s in t.groupby(key):
            r = lowest(s)
            out["|".join(map(str, k))] = dict(lowest=r.index[0] if len(r) else None,
                                              J={o: float(v) for o, v in r.J.items()},
                                              succ={o: f"{int(r.k[o])}/{int(r.n[o])}" for o in r.index})
    count = sum(1 for v in by_cls.values() if v["lowest"] in ("SG_warm", "SG_cold"))
    nums = json.load(open(npath))
    nums.update(sgLowestCount=int(count), sgSituations=int(len(by_cls)),
                sgLowestDetail=dict(by_class_point=by_cls, by_side_point=by_side),
                sgLowestProvenance=dict(data_tag=tag, export=exp, goals_sha256=F._sha(gp),
                                        definition="situation = (failure class, failure point) on E1b classes and points; "
                                                   "options pooled from E1 and E1b; energy per successful goal"))
    json.dump(nums, open(npath, "w"), indent=1)
    for name, d in [("class|point", by_cls), ("side|point", by_side)]:
        for k, v in d.items():
            print(f"{name:12s} {k:22s} lowest {v['lowest']:9s} " +
                  " ".join(f"{o}={j:.0f}" for o, j in v["J"].items()))
    print("sgLowestCount", count, "sgSituations", len(by_cls))


if __name__ == "__main__":
    main(*sys.argv[1:4])
