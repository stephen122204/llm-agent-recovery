"""R5 read only check (Oct 20): rows of state_reuse_events with both tokens_reused and
tokens_recomputed NULL, per study, first call of an attempt (lowest reuse_id) vs later.
Also rows per run vs llm calls per run, to test one row per call.
Usage: python null_check.py <snapshot.db> <ledger_dir> [<ledger_dir> ...]"""
import collections, glob, json, sqlite3, sys
import pandas as pd

db, dirs = sys.argv[1], sys.argv[2:]
study = {}
for d in dirs:
    for f in glob.glob(d + "/*ledger*.jsonl"):
        if "smoke" in f:
            continue
        for l in open(f):
            if l.strip():
                r = json.loads(l); study[r["goal_id"]] = r.get("study")
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
s = pd.read_sql("select reuse_id, attempt_id, run_id, tokens_reused, tokens_recomputed from state_reuse_events", c)
a = pd.read_sql("select attempt_id, goal_id, attempt_number from goal_attempt", c)
n = pd.read_sql("select run_id, count(*) as n_calls from llm_interactions group by run_id", c)
s = s.merge(a, on="attempt_id", how="left")
s["study"] = s.goal_id.map(study).fillna("no ledger")
s["first"] = s.reuse_id == s.groupby("attempt_id").reuse_id.transform("min")
s["both_null"] = s.tokens_reused.isna() & s.tokens_recomputed.isna()
s["one_null"] = s.tokens_reused.isna() ^ s.tokens_recomputed.isna()
t = s.groupby("study").agg(rows=("reuse_id", "size"), both_null=("both_null", "sum"),
                            both_null_first=("both_null", lambda x: int((x & s.loc[x.index, "first"]).sum())),
                            one_null=("one_null", "sum"))
t["both_null_not_first"] = t.both_null - t.both_null_first
print(t.to_string())
print("rows with no attempt_id match:", int(s.goal_id.isna().sum()))
rp = s.groupby("run_id").size().rename("rows").to_frame().join(n.set_index("run_id"))
print("runs:", len(rp), "rows == calls:", int((rp.rows == rp.n_calls).sum()),
      "rows < calls:", int((rp.rows < rp.n_calls).sum()), "rows > calls:", int((rp.rows > rp.n_calls).sum()))
