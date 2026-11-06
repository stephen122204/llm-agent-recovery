#!/usr/bin/env python3
"""export_sweep.py: GB10 context sweep, one JSON line per measured call, for R8's sweep figure (store read only).

Writes OUT (default data/sweep/gb10_sweep.jsonl) with: model, cache ("cached" or "uncached"), size, context_tokens,
joules_net, goal_id, hits_delta, gate_ok.
  records       raf_sweep_m4 (gpt-oss 20B) and raf_sweep_qwen (Qwen3 30B) run ledgers; smoke folders never read;
                latest valid record per item (paper_numbers rule); each goal is one B0 run with one measured call
  size, mode    detail.size and detail.mode (R2, Oct 21)
  context       attempt_meta["1"].sweep_usage.prompt_tokens
  joules_net    paper_numbers Store.energy board value: DC_INPUT minus the run's idle baseline, all attempts
  hits_delta    cache_metrics_after.prefix_cache_hits minus prepare["1"].cache_metrics.prefix_cache_hits
  gate_ok       uncached: hits_delta 0; cached: hits_delta at least 90 percent of the prompt (R2: prompt minus 16)
Usage (store window, from anywhere):
  python3 export_sweep.py --out ./data/sweep/gb10_sweep.jsonl
  python3 export_sweep.py --db SNAPSHOT.db --art ARTIFACTS_DIR --out FILE
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import paper_numbers as pn  # noqa: E402

SWEEPS = (("raf_sweep_m4", "gpt-oss 20B"), ("raf_sweep_qwen", "Qwen3 30B"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--db")
    ap.add_argument("--art")
    ap.add_argument("--sandbox", default=os.path.expanduser("~/sandboxes/raf-mlsys-2027"))
    a = ap.parse_args()
    db = a.db
    if not db:
        info = subprocess.run(["alems", "sandbox", "info"], capture_output=True, text=True, cwd=a.sandbox).stdout
        db = re.search(r"^store:\s+(\S+)", info, re.M).group(1)
    art = a.art or os.path.join(os.path.dirname(db), "artifacts")
    st = pn.Store(db)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    n = bad = 0
    with open(a.out, "w") as f:
        for study, model in SWEEPS:
            path = os.path.join(art, study, "%s_run_ledger.jsonl" % study)
            if not os.path.exists(path):
                print("missing %s, skipped" % path)
                continue
            best = {}
            for l in open(path):
                d = json.loads(l) if l.strip() else {}
                if d.get("validity") or not d.get("goal_id"):
                    continue
                if d.get("item_id") not in best or int(d["goal_id"]) > int(best[d["item_id"]]["goal_id"]):
                    best[d.get("item_id")] = d
            for d in sorted(best.values(), key=lambda x: int(x["goal_id"])):
                gid = int(d["goal_id"])
                det = d.get("detail") or {}
                use = ((d.get("attempt_meta") or {}).get("1") or {}).get("sweep_usage") or {}
                before = (((d.get("prepare") or {}).get("1") or {}).get("cache_metrics") or {}).get("prefix_cache_hits")
                after = (d.get("cache_metrics_after") or {}).get("prefix_cache_hits")
                hits = (after - before) if isinstance(after, (int, float)) and isinstance(before, (int, float)) else None
                pt = use.get("prompt_tokens")
                mode = det.get("mode")
                ok = hits is not None and pt and ((mode == "uncached" and hits == 0) or (mode == "cached" and hits >= 0.9 * pt))
                bad += not ok
                f.write(json.dumps({"model": model, "cache": mode, "size": det.get("size"), "context_tokens": pt,
                                    "joules_net": round(st.energy(gid)[0], 3), "goal_id": gid, "hits_delta": hits,
                                    "gate_ok": bool(ok)}) + "\n")
                n += 1
    print("wrote %d calls to %s; %d fail the cache gate%s" % (n, a.out, bad, "  (ALERT: report to the coordinator)" if bad else ""))
    print("sha256 %s" % pn.sha256(a.out))


if __name__ == "__main__":
    main()
