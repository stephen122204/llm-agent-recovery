#!/usr/bin/env python3
"""export_figdata.py: the one store read for all figures (run only in a store window, read only).

Writes data/figdata/goals.csv and calls.csv; figure scripts read only these files.
Goal selection reuses paper_numbers.py rules: latest record wins per (item_id, policy), and per
(item_id, arm, policy) for E3; records with a validity code are excluded.
Energy definitions are paper_numbers.py's Store.energy (board = DC_INPUT minus idle, per run).
Cached tokens: llm_interactions column if present, else state_reuse_events.tokens_reused (one row per call).

Usage (from the sandbox, or on a snapshot with --db and --art):
  python3 scripts/figures/export_figdata.py --out ./data/figdata
  python3 scripts/figures/export_figdata.py --db SNAPSHOT.db --art ARTIFACTS_DIR --out DIR
"""
import argparse
import csv
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import paper_numbers as pn  # noqa: E402  (Store, load_ledger: one definition of energy and selection)

FIG1 = ("multi_turn_base_71", "timeout", "late", ("FR_warm", "SR_warm"))


def columns(c, table):
    return [r[1] for r in c.execute("PRAGMA table_info(%s)" % table)]


def pick(cols, *names):
    for n in names:
        if n in cols:
            return n
    return None


def e3_goals(art):
    """{gid: (task, cls, point, arm label)} from the E3 split ledgers, latest wins, arm in the key."""
    best = {}
    for path in sorted(glob.glob(os.path.join(art, "raf_e3", "raf_e3_items_raf_e3_split_*_ledger.jsonl"))):
        for l in open(path):
            d = json.loads(l)
            if d.get("validity") or not d.get("goal_id"):
                continue
            p = d.get("plan", {})
            arm = p.get("arm") or d.get("arm")
            label = p.get("policy") if arm == "fixed" else arm
            key = (d.get("item_id"), arm, p.get("policy"))
            gid = int(d["goal_id"])
            if key not in best or gid > best[key][0]:
                best[key] = (gid, (p.get("task"), p.get("cls"), p.get("point") or "", label))
    return dict(best.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sandbox", default=os.getcwd())
    ap.add_argument("--db", help="read this store file (snapshot) instead of the live sandbox store")
    ap.add_argument("--art", help="artifacts folder; default is the folder beside the store")
    a = ap.parse_args()
    if a.db:
        db = a.db
    else:
        info = subprocess.run(["alems", "sandbox", "info"], capture_output=True, text=True, cwd=a.sandbox).stdout
        db = re.search(r"^store:\s+(\S+)", info, re.M).group(1)
    art = a.art or os.path.join(os.path.dirname(db), "artifacts")
    st = pn.Store(db)
    c = st.c
    li = columns(c, "llm_interactions")
    cached = pick(li, "tokens_reused", "cached_tokens", "prompt_cached_tokens", "cache_hit_tokens", "cached_prompt_tokens")
    reuse = not cached and bool(c.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'state_reuse_events'").fetchone())
    tok_ok = bool(cached or reuse)
    print("store %s; artifacts %s" % (db, art))
    print("cached tokens from %s" % (cached or ("state_reuse_events.tokens_reused" if reuse else "none")))
    t0 = pick(li, "request_start_ns", "start_ns")
    t1 = pick(li, "last_token_time_ns", "end_ns", "response_end_ns")
    es = columns(c, "energy_sample_domains")
    ts = pick(es, "timestamp_ns", "ts_ns", "sample_ns", "time_ns", "t_ns")
    print("llm_interactions cached=%s start=%s end=%s; energy_sample_domains time=%s" % (cached, t0, t1, ts))

    studies = {}
    e1 = sorted(glob.glob(os.path.join(art, "raf_e1", "raf_e1_run_ledger.jsonl")) +
                glob.glob(os.path.join(art, "raf_e1", "*rerun*ledger*.jsonl")))
    studies["e1"] = pn.load_ledger(e1)
    studies["e1b"] = pn.load_ledger(glob.glob(os.path.join(art, "raf_e1b", "raf_e1b_run_ledger.jsonl")))
    studies["e3"] = e3_goals(art)
    chosen = {}  # goal id -> options the deciding policy took, in decision order (R8 request, Oct 20)
    dec_path = os.path.join(art, "raf_e3", "e3_decisions.jsonl")
    if os.path.exists(dec_path):
        for l in open(dec_path):
            if l.strip():
                d = json.loads(l)
                g = (d.get("payload") or {}).get("goal_id")
                if g is not None and d.get("option"):
                    chosen.setdefault(int(g), []).append(d["option"])
    os.makedirs(a.out, exist_ok=True)
    demo = os.path.join(a.out, "DEMO")
    if os.path.exists(demo):
        os.remove(demo)  # real data replaces the demo marker
    tok_sql = ("SELECT ga.attempt_number, SUM(li.prompt_tokens), SUM(li.prompt_tokens - COALESCE(li.%s, 0)), "
               "COUNT(*) FROM llm_interactions li JOIN goal_attempt ga ON ga.run_id = li.run_id "
               "WHERE ga.goal_id = ? GROUP BY ga.attempt_number" % (cached or "prompt_tokens"))
    ga_cols = columns(c, "goal_attempt")
    att_col = pick(ga_cols, "attempt_number", "attempt", "attempt_index")
    tok_sql = tok_sql.replace("ga.attempt_number", "ga.%s" % att_col)
    n = 0
    with open(os.path.join(a.out, "goals.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["study", "goal_id", "task", "cls", "point", "option", "ok", "board_j", "pkg_j",
                    "tok_uncached", "tok_billed", "calls", "board_j_rec", "tok_uncached_rec", "chosen"])
        for study, goals in studies.items():
            for gid, (task, cls, pt, opt) in sorted(goals.items()):
                ok = st.success(gid)
                eb, ep, _ = st.energy(gid)
                rec_e = 0.0
                for run, pkg, dur, bid, att, num in c.execute(
                        "SELECT r.run_id, r.pkg_energy_uj, r.duration_ns, r.baseline_id, ga.energy_uj, ga.%s "
                        "FROM goal_attempt ga JOIN runs r ON r.run_id = ga.run_id WHERE ga.goal_id = ?"
                        % att_col, (gid,)).fetchall():
                    if (num or 1) >= 2:
                        s = (dur or 0) / 1e9
                        ib = st.idle_w(bid).get("DC_INPUT", 0.0)
                        mw = c.execute("SELECT AVG(energy_uj) FROM energy_sample_domains WHERE run_id = ? "
                                       "AND domain_id = 28", (run,)).fetchone()[0] or 0.0
                        rec_e += (mw / 1000.0 - ib) * s
                billed = unc = calls = unc_rec = 0.0
                ru = dict(c.execute("SELECT ga.%s, SUM(s.tokens_reused) FROM state_reuse_events s JOIN goal_attempt ga "
                                    "ON ga.run_id = s.run_id WHERE ga.goal_id = ? GROUP BY ga.%s" % (att_col, att_col),
                                    (gid,)).fetchall()) if reuse else {}
                for num, b, u, k in c.execute(tok_sql, (gid,)).fetchall():
                    if reuse:
                        u = (b or 0) - (ru.get(num) or 0)
                    billed += b or 0; unc += u or 0; calls += k or 0
                    if (num or 1) >= 2:
                        unc_rec += u or 0
                w.writerow([study, gid, pn_norm(task), cls, pt, opt, ok, "%.3f" % eb, "%.3f" % ep,
                            "%.0f" % unc if tok_ok else "NA", "%.0f" % billed, "%.0f" % calls,
                            "%.3f" % rec_e, "%.0f" % unc_rec if tok_ok else "NA", "+".join(chosen.get(gid, []))])
                n += 1
    # calls of the Figure 1 goals (model calls; energy per call window needs a sample time column)
    task, cls, pt, opts = FIG1
    fig1 = [g for g, v in studies["e1"].items() if pn_norm(v[0]) == task and v[1] == cls and v[2] == pt
            and v[3] in opts]
    m = 0
    with open(os.path.join(a.out, "calls.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["study", "goal_id", "attempt", "step", "kind", "prompt_tokens", "uncached_tokens",
                    "board_j", "failed"])
        for gid in sorted(fig1):
            step = 0
            for run, num, bid in c.execute("SELECT ga.run_id, ga.%s, r.baseline_id FROM goal_attempt ga "
                                           "JOIN runs r ON r.run_id = ga.run_id WHERE ga.goal_id = ? ORDER BY 2"
                                           % att_col, (gid,)).fetchall():
                ib = st.idle_w(bid).get("DC_INPUT", 0.0)
                q = "SELECT prompt_tokens, %s, %s, %s FROM llm_interactions WHERE run_id = ? ORDER BY %s" % (
                    cached or "0", t0 or "0", t1 or "0", t0 or "rowid")
                rows = c.execute(q, (run,)).fetchall()
                if reuse:
                    rr = [x for (x,) in c.execute("SELECT tokens_reused FROM state_reuse_events WHERE run_id = ? "
                                                  "ORDER BY reuse_id", (run,))]
                    rows = [(r[0], rr[i] if len(rr) == len(rows) else None) + tuple(r[2:]) for i, r in enumerate(rows)]
                for i, (pt_, ca, s0, s1) in enumerate(rows):
                    e = "NA"
                    if ts and s0 and s1 and s1 > s0:
                        mw = c.execute("SELECT AVG(energy_uj) FROM energy_sample_domains WHERE run_id = ? AND "
                                       "domain_id = 28 AND %s BETWEEN ? AND ?" % ts, (run, s0, s1)).fetchone()[0]
                        if mw is not None:
                            e = "%.3f" % ((mw / 1000.0 - ib) * (s1 - s0) / 1e9)
                    failed = 1 if (num or 1) == 1 and i == len(rows) - 1 else 0
                    unc_call = (pt_ - (ca or 0)) if cached else ((pt_ - ca) if (reuse and ca is not None) else "NA")
                    w.writerow(["e1", gid, num or 1, step, "model", pt_, unc_call, e, failed])
                    step += 1
                    m += 1
    print("goals %d, figure 1 calls %d, written to %s" % (n, m, a.out))


def pn_norm(t):
    return t[5:] if t and t.startswith("bfcl_") else t


if __name__ == "__main__":
    main()
