#!/usr/bin/env python3
"""e2b_numbers.py: E2b macros and table (accepted wrong steps), store read only.

Rules (coordinator, Oct 18):
  records   outcome numbers use the latest valid record per (item_id, policy, arm);
            validity counts use first records
  scope     wrong_model_step goals whose injected step the tool accepted
            (attempt_meta.1.corruption.accepted is true)
  excluded  six cells, all arms: task 94 early and late, 194 early and late, 1 early, 110 late
  arms      if the ledger has arms, option comparisons use the fixed arm only
  self corr detail.self_corrected, reported as its own rate (etwobSelfCorrect, Wilson 95);
            self corrected goals are excluded from every option comparison
  savings   early only: FR_warm vs SR_warm and RB_cold vs SR_warm, board energy per successful goal,
            paired bootstrap by task (2000 resamples, seed 20261013), with etwobCellMin and etwobCellMax
  late      success counts with Wilson only (etwobLate*Ok), no saving percent
  excluded  nEtwobExcluded = cells in the list; nEtwobExcludedGoals = latest valid goals inside them

Standalone, on a snapshot (writes e2b_numbers.json and tables/e2b_table.tex in --out):
  python3 e2b_numbers.py --db SNAPSHOT.db --art ARTIFACTS_DIR --out OUT_DIR
Inside paper_numbers.py:
  e2b_numbers.add(st, art, put, NOTE, a.paper)
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paper_numbers as pn  # noqa: E402  (Store, cells, wilson, boot_saving, fmt0, sha256)

EXCLUDED = {("94", "early"), ("94", "late"), ("194", "early"), ("194", "late"), ("1", "early"), ("110", "late")}
LABEL = "E2B ACCEPTED WRONG STEPS (raf_e2b_r2)"
COMPARE = (("FR_warm", "SR_warm", "FrVsSr"), ("RB_cold", "SR_warm", "RbVsSr"))


def task_no(t):
    m = re.search(r"(\d+)$", t or "")
    return m.group(1) if m else None


def accepted(d):
    co = ((d.get("attempt_meta") or {}).get("1") or {}).get("corruption")
    return isinstance(co, dict) and co.get("accepted") is True


def ledger_paths(art):
    return sorted(glob.glob(os.path.join(art, "raf_e2b_r2", "*ledger*.jsonl")))


def load(art):
    paths = ledger_paths(art)
    recs = []
    for p in paths:
        recs += [json.loads(l) for l in open(p) if l.strip()]
    recs = [d for d in recs if d.get("goal_id")]
    recs.sort(key=lambda d: int(d["goal_id"]))

    def key(d):
        p = d.get("plan", {})
        return (d.get("item_id"), p.get("policy"), p.get("arm") or d.get("arm"))

    first, latest_valid = {}, {}
    for d in recs:
        first.setdefault(key(d), d)
        if not d.get("validity"):
            latest_valid[key(d)] = d
    return paths, recs, first, latest_valid


def add(st, art, put, NOTE, paper_dir=None):
    paths, recs, first, lv = load(art)
    if not recs:
        put("etwobSelfCorrect", "\\pending{etwobSelfCorrect}", "pending: no E2b ledger under " + art)
        return
    src = "%s; %s, goals %d to %d" % (LABEL, ",".join(os.path.basename(p) for p in paths),
                                      int(recs[0]["goal_id"]), int(recs[-1]["goal_id"]))

    def P(name, val, s):
        put(name, val, s)
        NOTE[name] = LABEL

    # validity counts: first records
    codes = collections.Counter(c for d in first.values() for c in (d.get("validity") or []))
    for code, nm in (("PRE_INJECTION", "PreInjection"), ("CORRUPTION_NOT_APPLIED", "CorruptionNotApplied"),
                     ("DETECTION_MISSED", "DetectionMissed"), ("FALSE_DETECTION", "FalseDetection")):
        P("etwobInv" + nm, str(sum(v for c, v in codes.items() if c.startswith(code))),
          src + ", first records, codes starting with " + code)

    # scope: latest valid, wrong_model_step, not in the six cells, corruption accepted
    scope, n_excl, n_rej = {}, 0, 0
    for k, d in lv.items():
        p = d.get("plan", {})
        if p.get("cls") != "wrong_model_step":
            continue
        if (task_no(p.get("task")), p.get("point") or "") in EXCLUDED:
            n_excl += 1
            continue
        if not accepted(d):
            n_rej += 1
            continue
        scope[k] = d
    s2 = src + ", latest valid per (item, policy, arm), accepted corruptions, six cells excluded"
    P("nEtwobGoals", str(len(scope)), s2)
    seen = collections.Counter((task_no((d.get("plan") or {}).get("task")), (d.get("plan") or {}).get("point") or "")
                               for d in recs)
    empty = sorted("%s %s" % c for c in EXCLUDED if not seen.get(c))
    P("nEtwobExcluded", str(len(EXCLUDED)), src + ", excluded cells (coordinator list); cells with no ledger records: "
      + (", ".join(empty) or "none"))
    P("nEtwobExcludedGoals", str(n_excl), src + ", latest valid goals inside the excluded cells "
      "(others there are invalid or absent)")
    P("nEtwobNotAccepted", str(n_rej), src + ", latest valid goals whose corruption was not accepted")

    # self corrected: own rate
    sc = [d for d in scope.values() if (d.get("detail") or {}).get("self_corrected")]
    P("etwobSelfCorrectN", "%d of %d" % (len(sc), len(scope)), s2 + ", detail.self_corrected")
    if scope:
        lo, hi = pn.wilson(len(sc), len(scope))
        P("etwobSelfCorrect", "%.0f" % (100.0 * len(sc) / len(scope)), s2 + ", percent")
        P("etwobSelfCorrectLo", "%.0f" % (100 * lo), "Wilson 95, " + s2)
        P("etwobSelfCorrectHi", "%.0f" % (100 * hi), "Wilson 95, " + s2)

    # option cells: self corrected excluded; fixed arm only if arms exist
    has_arm = any(k[2] for k in scope)
    goals = {}
    for (item, pol, arm), d in scope.items():
        if (d.get("detail") or {}).get("self_corrected"):
            continue
        if has_arm and arm != "fixed":
            continue
        p = d.get("plan", {})
        goals[int(d["goal_id"])] = (p.get("task"), "wrong_model_step", p.get("point") or "", pol)
    cc = pn.cells(st, goals) if goals else {}
    s3 = s2 + ", self corrected excluded" + (", fixed arm only" if has_arm else ", ledger has no arms")
    print("E2B cells (point, option, n, ok):",
          sorted((p_, pol, v["n"], v["ok"]) for (c, p_, pol), v in cc.items()))

    # success counts with Wilson for the compared options, early and late (late: counts only, no saving)
    for pt in ("early", "late"):
        for opt, cam in (("FR_warm", "FrWarm"), ("RB_cold", "RbCold"), ("SR_warm", "SrWarm")):
            v = cc.get(("wrong_model_step", pt, opt))
            name = "etwob%s%sOk" % (pt.capitalize(), cam)
            if not v:
                P(name, "\\pending{%s}" % name, "pending: cell missing; " + s3)
                continue
            P(name, "%d of %d" % (v["ok"], v["n"]), s3 + ", %s %s" % (opt, pt))
            wl, wh = pn.wilson(v["ok"], v["n"])
            P(name + "Lo", "%.0f" % (100 * wl), "Wilson 95, %s, %s %s" % (s3, opt, pt))
            P(name + "Hi", "%.0f" % (100 * wh), "Wilson 95, %s, %s %s" % (s3, opt, pt))
    early_n = [cc[("wrong_model_step", "early", o)]["n"] for o in ("FR_warm", "RB_cold", "SR_warm")
               if ("wrong_model_step", "early", o) in cc]
    if early_n:
        P("etwobCellMin", str(min(early_n)), s3 + ", goals per cell, early FR_warm, RB_cold, SR_warm")
        P("etwobCellMax", str(max(early_n)), s3 + ", goals per cell, early FR_warm, RB_cold, SR_warm")

    for pt in ("early",):  # coordinator: late states counts only, no saving percent
        for a_, b_, nm in COMPARE:
            name = "etwob%sSave%s" % (nm, pt.capitalize())
            ca, cb = cc.get(("wrong_model_step", pt, a_)), cc.get(("wrong_model_step", pt, b_))
            if not ca or not cb or not ca["ok"] or not cb["ok"]:
                for suf in ("", "Lo", "Hi"):
                    P(name + suf, "\\pending{%s}" % (name + suf), "pending: cell missing or no success; " + s3)
                continue
            p, l, h, nt, nu = pn.boot_saving([(ca, cb)])
            ss = ("%s; %s below %s, %s, board per achieved, paired bootstrap over %d tasks, %d resamples, "
                  "seed %d, %d undefined draws" % (s3, a_, b_, pt, nt, pn.BOOT_REPS, pn.BOOT_SEED, nu))
            for suf, v in (("", p), ("Lo", l), ("Hi", h)):
                P(name + suf, "%.1f" % v, ss)

    # table: every option run, per point
    rows = []
    for pt in ("early", "late"):
        pc = {pol: v for (c, p_, pol), v in cc.items() if p_ == pt}
        best = min((v["ach_board"] for v in pc.values() if v["ach_board"]), default=None)
        for pol in sorted(pc):
            v = pc[pol]
            wl, wh = pn.wilson(v["ok"], v["n"])
            a_txt = pn.fmt0(v["ach_board"]) if v["ach_board"] else "none"
            if v["ach_board"] and v["ach_board"] == best:
                a_txt = "\\textbf{%s}" % a_txt
            rows.append("%s & %s & %d/%d & %.0f to %.0f & %s & %s \\\\" % (
                pt, pol.replace("_", " "), v["ok"], v["n"], 100 * wl, 100 * wh, pn.fmt0(v["epg_board"]), a_txt))
        if pt == "early" and rows:
            rows.append("\\midrule")
    if paper_dir:
        os.makedirs(os.path.join(paper_dir, "tables"), exist_ok=True)
        with open(os.path.join(paper_dir, "tables", "e2b_table.tex"), "w") as f:
            f.write("% GENERATED by e2b_numbers.py; do not edit by hand. " + LABEL +
                    ", board J, self corrected excluded.\n" + "\n".join(rows) + "\n\\bottomrule\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="store snapshot, opened read only")
    ap.add_argument("--art", required=True, help="artifacts folder holding raf_e2b_r2/")
    ap.add_argument("--out", required=True, help="folder for e2b_numbers.json and tables/e2b_table.tex")
    a = ap.parse_args()
    st = pn.Store(a.db)
    M, prov, NOTE = {}, {}, {}

    def put(n, v, s):
        M[n] = v
        prov[n] = s

    add(st, a.art, put, NOTE, a.out)
    os.makedirs(a.out, exist_ok=True)
    out = {"db": a.db, "db_sha256": pn.sha256(a.db),
           "ledgers": {p: pn.sha256(p) for p in ledger_paths(a.art)},
           "values": M, "provenance": prov}
    with open(os.path.join(a.out, "e2b_numbers.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("db sha256", out["db_sha256"])
    for k in sorted(M):
        print("  %-28s %s" % (k, M[k]))


if __name__ == "__main__":
    main()
