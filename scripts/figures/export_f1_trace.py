#!/usr/bin/env python3
"""Export the data behind F1 from the store (read only). Run only when no measured run is active.

Board energy per attempt uses the paper's rule: mean DC_INPUT (domain 28, mW) minus the
DC_INPUT idle of the run's baseline, times the run duration. Success is the latest
output_quality.pass_fail of the goal.

Usage:
  python3 export_f1_trace.py STORE.db OUTDIR GOAL:POLICY [GOAL:POLICY ...]
  e.g. python3 export_f1_trace.py experiments.db data/figdata 1295:FR_warm 2240:RB_cold 1297:SR_warm
Writes OUTDIR/f1_attempts.csv and OUTDIR/f1_calls.csv.
"""
import csv, os, re, sqlite3, sys

db = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True)
out = sys.argv[2]
os.makedirs(out, exist_ok=True)
pairs = [a.split(":") for a in sys.argv[3:]]


def idle_w(bid):
    r = db.execute("SELECT power_watts FROM v_idle_baseline_domains "
                   "WHERE baseline_id=? AND domain_name='DC_INPUT'", (bid,)).fetchone()
    return r[0] if r else 0.0


att = csv.writer(open(os.path.join(out, "f1_attempts.csv"), "w"))
att.writerow(["goal", "policy", "attempt", "run", "board_j", "ok"])
cal = csv.writer(open(os.path.join(out, "f1_calls.csv"), "w"))
cal.writerow(["run", "step", "time_ms", "prompt_tok", "completion_tok", "tools"])
TOOL = re.compile(r'"name"\s*:\s*"([A-Za-z_][A-Za-z0-9_]*)"')  # tool calls the model asked for, from its response
for goal, pol in pairs:
    ok = (db.execute("SELECT pass_fail FROM output_quality WHERE goal_id=? "
                     "ORDER BY quality_id DESC LIMIT 1", (goal,)).fetchone() or [0])[0]
    for n, run in db.execute("SELECT attempt_number, run_id FROM goal_attempt WHERE goal_id=? "
                             "ORDER BY attempt_number", (goal,)).fetchall():
        dur, bid = db.execute("SELECT duration_ns, baseline_id FROM runs WHERE run_id=?", (run,)).fetchone()
        mw = db.execute("SELECT AVG(energy_uj) FROM energy_sample_domains "
                        "WHERE run_id=? AND domain_id=28", (run,)).fetchone()[0] or 0.0
        att.writerow([goal, pol, n, run, round((mw / 1000.0 - idle_w(bid)) * dur / 1e9, 1), ok])
        for st, tm, pt, ct, resp in db.execute("SELECT step_index, total_time_ms, prompt_tokens, completion_tokens, response "
                                               "FROM llm_interactions WHERE run_id=? ORDER BY interaction_id", (run,)):
            cal.writerow([run, st, tm, pt, ct, ";".join(TOOL.findall(resp or ""))])
print("wrote", out)
