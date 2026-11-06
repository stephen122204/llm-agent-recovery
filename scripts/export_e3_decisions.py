#!/usr/bin/env python3
"""export_e3_decisions.py: E3 raf.controller annotation payloads to raf_e3/e3_decisions.jsonl (store read only).

For R7's parity test. One line per controller decision with: annotation id, span id, created at,
decider, option, counts used, seed, sampled p per option, calls_done, plus every other payload field kept
verbatim under "payload". The annotation table is found by its columns (annotation_type and payload),
so a table name difference does not break the export.

Cross check: the number of exported decisions is compared with the decisions recorded in the E3 split
ledgers; a difference is printed, never hidden.

Usage (from the sandbox, store window only):
  python3 ./scripts/export_e3_decisions.py
"""
import glob
import json
import os
import re
import sqlite3
import subprocess


def find_annotation_table(c):
    for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')"):
        cols = [r[1] for r in c.execute("PRAGMA table_info(%s)" % name)]
        if "annotation_type" in cols and "payload" in cols:
            return name, cols
    raise SystemExit("no table with annotation_type and payload columns")


def token_context(c, gid, dec_att):
    """Prompt and cached tokens of the last model call in the attempt before the decision (the failed one)."""
    if gid is None or dec_att is None:
        return None, None, None
    att = int(dec_att) - 1
    r = c.execute("SELECT run_id FROM goal_attempt WHERE goal_id = ? AND attempt_number = ?", (gid, att)).fetchone()
    if not r:
        return None, None, att
    calls = c.execute("SELECT prompt_tokens FROM llm_interactions WHERE run_id = ? ORDER BY interaction_id", r).fetchall()
    reuse = c.execute("SELECT tokens_reused FROM state_reuse_events WHERE run_id = ? ORDER BY reuse_id", r).fetchall()
    if not calls:
        return None, None, att
    cached = reuse[-1][0] if len(reuse) == len(calls) else None  # pair by order only when counts match
    return calls[-1][0], cached, att


def main():
    info = subprocess.run(["alems", "sandbox", "info"], capture_output=True, text=True).stdout
    db = re.search(r"^store:\s+(\S+)", info, re.M).group(1)
    art = os.path.join(os.path.dirname(db), "artifacts")
    c = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    table, cols = find_annotation_table(c)
    want = [x for x in ("annotation_id", "span_id", "annotation_type", "annotation_version", "source",
                        "created_at", "payload") if x in cols]
    types = [t for (t,) in c.execute("SELECT DISTINCT annotation_type FROM %s WHERE annotation_type LIKE "
                                     "'raf.controller%%'" % table)]
    print("table %s; types %s" % (table, types))
    rows = c.execute("SELECT %s FROM %s WHERE annotation_type LIKE 'raf.controller%%' ORDER BY %s"
                     % (", ".join(want), table, want[0])).fetchall()
    out_path = os.path.join(art, "raf_e3", "e3_decisions.jsonl")
    n_e3 = 0
    with open(out_path, "w") as f:
        for r in rows:
            rec = dict(zip(want, r))
            try:
                p = json.loads(rec.get("payload") or "{}")
            except ValueError:
                p = {"_unparsed": rec.get("payload")}
            if p.get("study_id") not in (None, "e3"):
                continue  # only E3 decisions; earlier studies stay out of the parity file
            n_e3 += 1
            tctx, tcached, tatt = token_context(c, p.get("goal_id"), p.get("decision_attempt"))
            line = {k: rec.get(k) for k in want if k != "payload"}
            line.update({
                "decider": p.get("decider_used") or p.get("decider"),
                "option": p.get("chosen") or p.get("option"),
                "counts": p.get("counts"),
                "seed": p.get("seed"),
                "sampled_p": {s.get("option"): s.get("p") for s in (p.get("scores") or [])},
                "calls_done": p.get("calls_done"),
                "arm": p.get("arm"),
                "tokens_context": tctx,
                "tokens_cached": tcached,
                "context_attempt": tatt,
                "payload": p,
            })
            f.write(json.dumps(line, sort_keys=True) + "\n")
    # cross check against the ledgers
    n_led = 0
    for path in glob.glob(os.path.join(art, "raf_e3", "raf_e3_items_raf_e3_split_*_ledger.jsonl")):
        for l in open(path):
            d = json.loads(l)
            n_led += len(d.get("decisions") or {})
    print("exported %d E3 decisions to %s; ledgers record %d decisions%s"
          % (n_e3, out_path, n_led, "" if n_e3 == n_led else "  (COUNTS DIFFER, report to coordinator)"))


if __name__ == "__main__":
    main()
