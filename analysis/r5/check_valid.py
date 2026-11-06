"""R5 read only check (Oct 19): validity among kept goals (4 key) and E2b excluded cells.
Usage: python check_valid.py <ledger_dir>"""
import collections, glob, json, sys
import pandas as pd
rows = []
for f in sorted(glob.glob(sys.argv[1] + "/*ledger*.jsonl")):
    if "smoke" in f:
        continue
    for l in open(f):
        if l.strip():
            r = json.loads(l); pl = r.get("plan", {})
            rows.append(dict(goal_id=r["goal_id"], study=r.get("study"), block=r.get("item_id"),
                             option=pl.get("policy"), rep=pl.get("rep"), task=pl.get("task"),
                             cls=pl.get("cls"), point=pl.get("point"), validity=str(r.get("validity") or [])))
d = pd.DataFrame(rows).sort_values("goal_id").drop_duplicates("goal_id", keep="last")
d = d[~d.duplicated(["study", "block", "option", "rep"], keep="last")]
bad = d[d.validity != "[]"]
print("kept", len(d), "invalid among kept", len(bad))
print(bad.groupby(["study", "validity"]).size().to_string())
e = bad[bad.study == "raf_e2b_r2"]
print("E2b invalid cells (task, cls, point): goals")
print(e.groupby(["task", "cls", "point"]).size().to_string())
