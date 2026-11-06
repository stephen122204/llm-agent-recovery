"""R5 read only check (Oct 19): supersede key with and without study; validity codes.
Usage: python check_keys.py <ledger_dir>"""
import collections, glob, json, sys
import pandas as pd

rows = []
for f in sorted(glob.glob(sys.argv[1] + "/*ledger*.jsonl")):
    if "smoke" in f:
        continue
    for l in open(f):
        if not l.strip():
            continue
        r = json.loads(l); pl = r.get("plan", {})
        rows.append(dict(file=f.split("/")[-1], goal_id=r["goal_id"], study=r.get("study"),
                         block=r.get("item_id"), option=pl.get("policy"), rep=pl.get("rep"),
                         rerun=r.get("rerun", 0), validity=str(r.get("validity") or [])))
d = pd.DataFrame(rows).sort_values("goal_id").drop_duplicates("goal_id", keep="last")
print("goals after goal_id dedupe", len(d))
print("per file: study, rerun, invalid")
for f, g in d.groupby("file"):
    print(" ", f, dict(collections.Counter(g.study)), "rerun", int((g.rerun != 0).sum()), "invalid", int((g.validity != "[]").sum()))
print("validity codes:", dict(collections.Counter(d.validity[d.validity != "[]"])))
for name, key in [("3 key", ["block", "option", "rep"]), ("4 key", ["study", "block", "option", "rep"])]:
    sup = d.duplicated(key, keep="last")
    kept = d[~sup]
    print(name, "kept", len(kept), "superseded", int(sup.sum()), "kept per study", dict(collections.Counter(kept.study)))
k3 = d.duplicated(["block", "option", "rep"], keep="last")
k4 = d.duplicated(["study", "block", "option", "rep"], keep="last")
x = d[k3 & ~k4]
print("dropped only because study was ignored:", len(x), dict(collections.Counter(x.study)))
