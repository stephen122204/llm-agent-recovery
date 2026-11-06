#!/usr/bin/env python3
"""export_dataset.py: open dataset of the RAF paper from a frozen store snapshot (read only).

Writes, in --out:
  goals.csv   one row per valid goal: study, goal_id, task, class, position, option, arm, rep,
              outcome (checker pass 1 or 0), board_j, package_j, attempts
  calls.csv   one row per model call of those goals: study, goal_id, attempt, step, prompt_tokens,
              cached_tokens, completion_tokens, board_j (only when the run holds exactly one call)
  README.md   column definitions, rules, input sha256
No prompts or responses are exported.

Rules (same as the paper, reusing paper_numbers.py):
  valid goal   latest record per (item_id, policy, arm) within one study, records with a validity code dropped
  outcome      output_quality.pass_fail of the latest row (Store.success)
  energy       Store.energy: board = DC_INPUT (domain 28) mean minus idle of runs.baseline_id, times duration,
               summed over attempts; package likewise from runs.pkg_energy_uj
  cached       state_reuse_events.tokens_reused, paired to calls by order inside a run only when the counts match
  per call J   R5 rule: board J of the samples (energy_samples_v2.timestamp_ns) inside the call window
               [request_start_ns, last_token_time_ns or start + total_time_ms], minus idle over the window; empty if no sample
  fit inputs   attempt 1: calls_total = runs.llm_calls + runs.tool_calls, calls_model = runs.llm_calls,
               last_prompt_tokens = prompt_tokens of the last call by step_index, fired_phase = detail.fired_phase
               (llm, tool or empty), tok_uncached_rest = ledger prefix cache queries minus hits, attempt 2 to goal end
  class        plan.cls as injected; observable_class = what the controller saw (R5 mapping)

Usage (Oct 23, on the frozen snapshot):
  python3 export_dataset.py --db SNAPSHOT.db --art ARTIFACTS_DIR --out OUT_DIR
  extra or changed studies: --study name=relative/glob/pattern.jsonl (repeatable; smoke ledgers are always skipped)
"""
import argparse
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paper_numbers as pn  # noqa: E402  (Store, norm_task, sha256)
import e2b_numbers  # noqa: E402  (EXCLUDED cells and accepted(): the paper's E2b scope)

STUDIES = {
    "e1": ["raf_e1/raf_e1_run_ledger.jsonl", "raf_e1/*rerun*ledger*.jsonl"],
    "e1b": ["raf_e1b/raf_e1b_run_ledger.jsonl"],
    "e2": ["raf_e2/raf_e2_run_ledger.jsonl"],
    "e2b": ["raf_e2b_r2/*ledger*.jsonl"],
    "e3": ["raf_e3/raf_e3_items_raf_e3_split_*_ledger.jsonl"],
    "m3": ["raf_m3/*ledger*.jsonl"],
}


def observable(cls):
    """R5 mapping: what the controller saw (persistent_ stripped; silent classes to silent_detected)."""
    c = (cls or "none").replace("persistent_", "")
    return "silent_detected" if c in ("silent_tool_output", "wrong_model_step", "silent_detected") else c


def uncached_after_a1(d):
    """R5 recovery_features._uncached_after_a1: prefix cache queries delta minus hits delta, attempt 2 to goal end."""
    a = d.get("cache_metrics_after") or {}
    b = (((d.get("prepare") or {}).get("2") or {}).get("cache_metrics")) or {}
    keys = ("prefix_cache_queries", "prefix_cache_hits")
    if not all(isinstance(x.get(k), (int, float)) for x in (a, b) for k in keys):
        return ""
    return int((a["prefix_cache_queries"] - b["prefix_cache_queries"]) - (a["prefix_cache_hits"] - b["prefix_cache_hits"]))


def ledger_goals(paths):
    """{gid: dict} latest valid record per (item_id, policy, arm), one study only."""
    folders = {os.path.basename(os.path.dirname(os.path.abspath(p))) for p in paths}
    if len(folders) > 1:
        raise SystemExit("ledgers from more than one study folder in one study: %s" % sorted(folders))
    best = {}
    for path in paths:
        for line in open(path):
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("validity") or not d.get("goal_id"):
                continue
            p = d.get("plan", {})
            arm = p.get("arm") or d.get("arm")
            key = (d.get("item_id"), p.get("policy"), arm, p.get("rep", d.get("rep")))  # R5 key includes rep
            gid = int(d["goal_id"])
            if key not in best or gid > best[key][0]:
                best[key] = (gid, {"task": pn.norm_task(p.get("task")), "cls": p.get("cls") or "none",
                                   "point": p.get("point") or "", "policy": p.get("policy"), "arm": arm or "",
                                   "rep": p.get("rep", d.get("rep", "")),
                                   "fired_phase": (d.get("detail") or {}).get("fired_phase") or "",
                                   "e2b_scope": (p.get("cls") == "wrong_model_step" and e2b_numbers.accepted(d) and
                                                 (e2b_numbers.task_no(p.get("task")), p.get("point") or "")
                                                 not in e2b_numbers.EXCLUDED),
                                   "tok_rest": uncached_after_a1(d)})
    return dict(best.values())


def pilot_goals(art):
    p = os.path.join(art, "raf_pilot", "s7_goals.csv")
    if not os.path.exists(p):
        return {}, []
    out = {}
    for r in csv.DictReader(open(p)):
        out[int(r["goal_id"])] = {"task": pn.norm_task(r["task"]), "cls": r["cls"] or "none", "fired_phase": "", "tok_rest": "",
                                  "point": r["point"] or "", "policy": r["policy"], "arm": "", "rep": r.get("rep", "")}
    return out, [p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="frozen store snapshot, opened read only")
    ap.add_argument("--art", required=True, help="artifacts folder of that snapshot")
    ap.add_argument("--out", required=True)
    ap.add_argument("--study", action="append", default=[], help="name=glob relative to --art (adds or replaces)")
    ap.add_argument("--pilot-board-baseline", default="baseline_1792100195_39554")
    a = ap.parse_args()

    studies = {k: list(v) for k, v in STUDIES.items()}
    for s in a.study:
        name, pat = s.split("=", 1)
        studies.setdefault(name, [])
        if name in STUDIES and studies[name] == STUDIES[name]:
            studies[name] = []
        studies[name].append(pat)

    st = pn.Store(a.db)
    c = st.c
    shas = {a.db: pn.sha256(a.db)}
    att_col = next(x for x in ("attempt_number", "attempt", "attempt_index")
                   if x in [r[1] for r in c.execute("PRAGMA table_info(goal_attempt)")])
    has_reuse = bool(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'state_reuse_events'").fetchone())
    run_cols = [r[1] for r in c.execute("PRAGMA table_info(runs)")]
    li_cols = [r[1] for r in c.execute("PRAGMA table_info(llm_interactions)")]
    has_ts = bool(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'energy_samples_v2'").fetchone())

    def call_j(run, s0, s1, idle_w):
        """R5 rule: board J of samples whose timestamp falls in [s0, s1], minus idle over the window; empty if none."""
        if not has_ts or s0 is None or s1 is None or s1 <= s0:
            return ""
        r = c.execute("SELECT COUNT(*), SUM(e.energy_uj / 1000.0 * s.interval_ns / 1e9) FROM energy_sample_domains e "
                      "JOIN energy_samples_v2 s ON s.sample_id = e.sample_id WHERE e.run_id = ? AND e.domain_id = 28 "
                      "AND s.timestamp_ns BETWEEN ? AND ?", (run, s0, s1)).fetchone()
        return "%.3f" % (r[1] - idle_w * (s1 - s0) / 1e9) if r[0] else ""

    sets = {}
    g, files = pilot_goals(a.art)
    if g:
        sets["pilot"] = g
        for f in files:
            shas[f] = pn.sha256(f)
    for name, pats in studies.items():
        paths = sorted({p for pat in pats for p in glob.glob(os.path.join(a.art, pat)) if "smoke" not in os.path.basename(p)})
        if not paths:
            print("study %s: no ledger found for %s, skipped" % (name, pats))
            continue
        for p in paths:
            shas[p] = pn.sha256(p)
        sets[name] = ledger_goals(paths)

    if "m4" in sets:  # the paper removes task 105 from the third model
        sets["m4"] = {g: v for g, v in sets["m4"].items() if v["task"] != "multi_turn_base_105"}
    if "e2b" in sets:  # the paper's E2b goals: accepted wrong steps outside the six excluded cells
        sets["e2b"] = {g: v for g, v in sets["e2b"].items() if v.get("e2b_scope")}
    os.makedirs(a.out, exist_ok=True)
    counts = {}
    with open(os.path.join(a.out, "goals.csv"), "w", newline="") as fg, \
            open(os.path.join(a.out, "calls.csv"), "w", newline="") as fc:
        wg, wc = csv.writer(fg), csv.writer(fc)
        wg.writerow(["study", "goal_id", "task", "class", "observable_class", "position", "option", "arm", "rep",
                     "outcome", "board_j", "package_j", "attempts",
                     "calls_total", "calls_model", "last_prompt_tokens", "fired_phase", "tok_uncached_rest"])
        wc.writerow(["study", "goal_id", "attempt", "step", "prompt_tokens", "cached_tokens",
                     "completion_tokens", "board_j"])
        for study, goals in sets.items():
            n_calls = 0
            board_bid = a.pilot_board_baseline if study == "pilot" else None
            for gid in sorted(goals):
                v = goals[gid]
                eb, ep, _ = st.energy(gid, board_bid)
                runs = c.execute("SELECT ga.run_id, ga.%s, r.duration_ns, r.baseline_id FROM goal_attempt ga "
                                 "JOIN runs r ON r.run_id = ga.run_id WHERE ga.goal_id = ? ORDER BY 2" % att_col,
                                 (gid,)).fetchall()
                ctot = cmod = lpt = ""
                if runs:
                    r1 = runs[0][0]  # attempt 1 (runs ordered by attempt); R5's fits use attempt 1
                    if "llm_calls" in run_cols:
                        lc, tc = c.execute("SELECT llm_calls, %s FROM runs WHERE run_id = ?"
                                           % ("tool_calls" if "tool_calls" in run_cols else "0"), (r1,)).fetchone()
                        cmod, ctot = (lc or 0), (lc or 0) + (tc or 0)
                    q = c.execute("SELECT prompt_tokens FROM llm_interactions WHERE run_id = ? ORDER BY %s DESC LIMIT 1"
                                  % ("step_index" if "step_index" in li_cols else "interaction_id"), (r1,)).fetchone()
                    lpt = q[0] if q else ""
                wg.writerow([study, gid, v["task"], v["cls"], observable(v["cls"]), v["point"], v["policy"], v["arm"],
                             v["rep"], st.success(gid), "%.3f" % eb, "%.3f" % ep, len(runs),
                             ctot, cmod, lpt, v["fired_phase"], v["tok_rest"]])
                for run, att, dur, bid in runs:
                    rows = c.execute("SELECT prompt_tokens, completion_tokens, request_start_ns, last_token_time_ns, "
                                     "total_time_ms FROM llm_interactions WHERE run_id = ? ORDER BY interaction_id",
                                     (run,)).fetchall()
                    reuse = [x for (x,) in c.execute("SELECT tokens_reused FROM state_reuse_events WHERE run_id = ? "
                                                     "ORDER BY reuse_id", (run,))] if has_reuse else []
                    ib = st.idle_w(board_bid or bid).get("DC_INPUT", 0.0)
                    for i, (pt, ct, s0, s1, tms) in enumerate(rows):
                        if s1 is None and s0 is not None and tms:
                            s1 = s0 + int(tms * 1e6)  # R5: end = last_token_time_ns, else start + total_time_ms
                        cached = reuse[i] if len(reuse) == len(rows) else ""
                        wc.writerow([study, gid, att, i, pt, cached, ct, call_j(run, s0, s1, ib)])
                        n_calls += 1
            counts[study] = {"goals": len(goals), "calls": n_calls}
            print("study %-6s goals %6d calls %7d" % (study, len(goals), n_calls))

    for fn in ("goals.csv", "calls.csv"):
        shas[os.path.join(a.out, fn)] = pn.sha256(os.path.join(a.out, fn))
    with open(os.path.join(a.out, "README.md"), "w") as f:
        f.write(__doc__.split("Usage")[0])
        f.write("\nCounts per study:\n\n")
        for s, v in counts.items():
            f.write("- %s: %d goals, %d calls\n" % (s, v["goals"], v["calls"]))
        f.write("\nsha256 of inputs and outputs:\n\n")
        for p, h in sorted(shas.items()):
            f.write("- %s  %s\n" % (h, p))
    print("wrote goals.csv, calls.csv, README.md to %s" % a.out)


if __name__ == "__main__":
    main()
