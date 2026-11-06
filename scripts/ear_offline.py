#!/usr/bin/env python3
"""ear_offline.py: EAR replayed offline on the second and third model (out of model; coordinator, Oct 23).

EAR = selector v2 routing plus the token rule (params v2), the platform's own code (ear.py, token_rule.py).
For each item (task, failure type, point) of a study, EAR's inputs are the failure class and the calls done
in attempt 1 (model plus tool calls of the attempt 1 run of the restart goal; attempt 1 is identical for every
option at temperature 0). EAR's pick is restricted to the options the study ran (FR_warm, SR_warm, RB_cold);
its outcome is the recorded goal of that option on the same item. earRestrictedShare counts items where the
unrestricted pick (all options) is an option the study never ran.
Savings: board J per successful goal, paired bootstrap over tasks (paper_numbers.boot_saving), positive = EAR lower.

Run in the platform environment (writes one JSON, nothing else):
  cd ./scripts && \\
  PYTHONPATH=experiments/platform/alems-plugin-bfcl python3 ear_offline.py \\
    --db FROZEN_DB --art /tmp/raf_art_frozen --params ../data/r5sel/controller_params_v2.json \\
    --selector ../data/r5sel/selector_lr_v2.json --out ../data/r4/ear_offline.json
"""
import argparse
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paper_numbers as pn  # noqa: E402

RUN = ("FR_warm", "SR_warm", "RB_cold")
STUDIES = (("Mistral", "raf_m3/raf_m3_run_ledger.jsonl", ()),
           ("Gptoss", "raf_m4/raf_m4_run_ledger.jsonl", ("multi_turn_base_105",)))
NAME = {"FR_warm": "Restart", "SR_warm": "Resume", "RB_cold": "Rollback"}


def attempt1_calls(st, gid):
    """Model plus tool calls of the goal's attempt 1 run."""
    c = st.c
    ga = [r[1] for r in c.execute("PRAGMA table_info(goal_attempt)")]
    att = next(x for x in ("attempt_number", "attempt", "attempt_index") if x in ga)
    rc = [r[1] for r in c.execute("PRAGMA table_info(runs)")]
    tool = "r.tool_calls" if "tool_calls" in rc else "0"
    row = c.execute("SELECT r.llm_calls, %s FROM goal_attempt ga JOIN runs r ON r.run_id = ga.run_id "
                    "WHERE ga.goal_id = ? AND ga.%s = 1" % (tool, att), (gid,)).fetchone()
    return (row[0] or 0) + (row[1] or 0) if row else None


def observable(cls):
    c = (cls or "none").replace("persistent_", "")
    return "silent_detected" if c in ("silent_tool_output", "wrong_model_step", "silent_detected") else c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--art", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--selector", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.environ["ALEMS_RAF_CTRL_PARAMS"] = os.path.abspath(a.params)
    E = importlib.import_module("alems_plugin_bfcl.decider.ear")
    tr = importlib.import_module("alems_plugin_bfcl.decider.token_rule")
    tok = tr.TokenRule()
    sel, sel_sha = E.load_selector(os.path.abspath(a.selector))
    if sel is None:
        raise SystemExit("selector refused by ear.load_selector")
    thr = sel.get("threshold", 0.5)
    st = pn.Store(a.db)
    out = {"inputs": {"db_sha256": pn.sha256(a.db), "params_sha256": pn.sha256(a.params), "selector_sha256": sel_sha},
           "values": {}, "provenance": {}}

    def put(k, v, s):
        out["values"][k] = v
        out["provenance"][k] = s

    for key, led, drop in STUDIES:
        goals = {g: v for g, v in pn.load_ledger([os.path.join(a.art, led)]).items() if pn.norm_task(v[0]) not in drop}
        items = {}
        for g, (task, cls, pt, pol) in goals.items():
            items.setdefault((pn.norm_task(task), cls, pt), {})[pol] = g
        ear_goals, restricted, cost_route, n_items = {}, 0, 0, 0
        for (task, cls, pt), opts in sorted(items.items()):
            if not all(o in opts for o in RUN):
                continue  # an item without all three options cannot be scored
            n_items += 1
            ocls = observable(cls)
            calls = attempt1_calls(st, opts["FR_warm"])
            p = E.probability(sel, E.features(sel, ocls, calls))
            if not p > thr:
                cost_route += 1  # EAR would use the cost model here; not emulated, counted and reported
                continue
            res = tok.choose(ocls, calls)
            pred = res.get("tokens") or {}
            run_pred = {o: pred[o] for o in RUN if pred.get(o) is not None}
            if not run_pred:
                continue
            pick = min(sorted(run_pred), key=lambda o: run_pred[o])
            if res.get("option") not in RUN:
                restricted += 1
            ear_goals[opts[pick]] = (task, cls, pt, "EAR")
        fixed = {g: v for g, v in goals.items() if v[3] in RUN}
        cc = pn.cells(st, fixed)  # fixed and EAR cells built separately: a goal EAR picks also stays in its fixed cell
        cc.update(pn.cells(st, ear_goals))
        src = ("%s, out of model offline replay of EAR (selector v2 %s, params v2 %s), restricted to FR_warm, SR_warm, "
               "RB_cold; %d items scored, %d routed to the cost model (not scored); board J per successful goal, "
               "paired bootstrap over tasks, positive = EAR lower" % (key, sel_sha[:8], out["inputs"]["params_sha256"][:8],
                                                                     len(ear_goals), cost_route))
        for fx in RUN:
            sit = [(c, p_) for (c, p_, pol) in cc if pol == "EAR" and (c, p_, fx) in cc]
            pt_, lo, hi, nt, nu = pn.boot_saving([(cc[(c, p_, "EAR")], cc[(c, p_, fx)]) for c, p_ in sit])
            flag = "" if (lo > 0 or hi < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
            nm = "ear%sVs%s" % (key, NAME[fx])
            for suf, x in (("", pt_), ("Lo", lo), ("Hi", hi)):
                put(nm + suf, "%.1f" % x, src + ", vs %s, %d tasks%s" % (fx, nt, flag))
        for lab in RUN + ("EAR",):  # EpG and success per policy on the scored items (R8 table, Oct 23)
            vs = [v for (c, p_, pol), v in cc.items() if pol == lab]
            e_, k_, n_ = sum(v["epg_board"] * v["n"] for v in vs), sum(v["ok"] for v in vs), sum(v["n"] for v in vs)
            out.setdefault("table", {}).setdefault(key, {})[lab] = {"j": e_ / k_ if k_ else None, "ok": k_, "n": n_}
        ok = sum(v["ok"] for (c, p_, pol), v in cc.items() if pol == "EAR")
        n = sum(v["n"] for (c, p_, pol), v in cc.items() if pol == "EAR")
        wl, wh = pn.wilson(ok, n)
        put("ear%sOk" % key, "%d of %d" % (ok, n), src + ", correct goals")
        put("ear%sOkLo" % key, "%.0f" % (100 * wl), "Wilson 95, " + src)
        put("ear%sOkHi" % key, "%.0f" % (100 * wh), "Wilson 95, " + src)
        put("ear%sRestrictedShare" % key, "%d of %d" % (restricted, len(ear_goals)),
            src + ", items where the unrestricted pick (all options) is an option this study never ran")
        put("ear%sRestrictedSharePct" % key, "%.1f" % (100.0 * restricted / len(ear_goals) if ear_goals else 0),
            src + ", percent")
        put("ear%sCostRoute" % key, str(cost_route), src + ", items routed to the cost model (not scored)")
        print("%s: %d items, %d scored, %d cost model route, %d restricted, EAR %d of %d correct"
              % (key, n_items, len(ear_goals), cost_route, restricted, ok, n))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)
    print("wrote %d values to %s" % (len(out["values"]), a.out))


if __name__ == "__main__":
    main()
