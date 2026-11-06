#!/usr/bin/env python3
"""paper_numbers.py: every data number in the RAF paper, generated from the store (read only).

Writes, in the paper tex folder:
  numbers_auto.tex    one \\newcommand per value (never edit by hand)
  numbers_auto.json   the same values with provenance
  tables/pilot_table.tex, tables/e1_table.tex   tabular rows, ending with \\bottomrule

Definitions (coordinator, Oct 15):
  success  = output_quality.pass_fail of the goal's final attempt (judge bfcl_state)
  EpG      = energy per goal, summed over all attempts, mean over the goals of a cell
  per ach. = EpG / success rate (none if no success)
  board    = DC_INPUT (domain 28, mW samples): mean W minus idle DC_INPUT W of runs.baseline_id, times duration
  pkg      = runs.pkg_energy_uj minus idle PACKAGE W of runs.baseline_id, times duration
  pilot board idle uses --pilot-board-baseline (its own baseline did not record DC_INPUT)

Usage (from the RAF sandbox, never during a measured run):
  python3 paper_numbers.py --paper ./tex
"""
import argparse, collections, csv, datetime, glob, hashlib, json, math, os, random, re, sqlite3, subprocess

SITUATIONS = [(c, p) for p in ("early", "late") for c in ("json_parse", "rate_limit", "tool_error", "timeout")]
CLS_NAME = {"json_parse": "JSON parse", "rate_limit": "Rate limit", "tool_error": "Tool error", "timeout": "Timeout"}


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt0(x):
    return "{:,.0f}".format(x).replace(",", "{,}")


CLS_CAMEL = {"json_parse": "JsonParse", "rate_limit": "RateLimit", "tool_error": "ToolError", "timeout": "Timeout"}
BOOT_REPS, BOOT_SEED = 2000, 20261013


def norm_task(t):
    """Ledger names carry bfcl_, task files do not (D2.7); pair on the bare name."""
    return t[5:] if t and t.startswith("bfcl_") else t


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def boot_saving(pairs, reps=BOOT_REPS, seed=BOOT_SEED, e=0):
    """Percent by which the first cell of each pair is below the second in energy per successful goal.

    pairs: list of (winner cell, other cell). Per achieved = sum board J / sum successes.
    Paired bootstrap over tasks: one task draw is shared by every pair, so pooled classes stay paired.
    Returns (point, lo, hi, n_tasks, n_undefined_draws).
    """
    tasks = None
    for a, b in pairs:
        s = set(a["tasks"]) & set(b["tasks"])
        tasks = s if tasks is None else tasks & s
    tasks = sorted(tasks)

    def sav(draw):
        ea = oa = eb = ob = 0.0
        for a, b in pairs:
            for t in draw:
                ea += a["tasks"][t][e]; oa += a["tasks"][t][1]  # e = 0 board, 3 package
                eb += b["tasks"][t][e]; ob += b["tasks"][t][1]
        if not oa or not ob:
            return None  # a draw with zero successes has no per achieved value
        return 100 * (1 - (ea / oa) / (eb / ob))

    rng = random.Random(seed)
    vals = sorted(v for v in (sav([rng.choice(tasks) for _ in tasks]) for _ in range(reps)) if v is not None)
    lo = vals[int(round(0.025 * (len(vals) - 1)))]
    hi = vals[int(round(0.975 * (len(vals) - 1)))]
    return sav(tasks), lo, hi, len(tasks), reps - len(vals)


class Store:
    def __init__(self, db):
        self.c = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        self.idle = {}

    def idle_w(self, bid):
        if bid not in self.idle:
            rows = dict(self.c.execute(
                "SELECT domain_name, power_watts FROM v_idle_baseline_domains WHERE baseline_id=?", (bid,)))
            self.idle[bid] = rows
        return self.idle[bid]

    def success(self, gid):
        q = self.c.execute("SELECT pass_fail FROM output_quality WHERE goal_id=? "
                           "ORDER BY quality_id DESC LIMIT 1", (gid,)).fetchone()
        return 1 if q and q[0] == 1 else 0

    def energy(self, gid, board_bid=None):
        """(board J, pkg J, attributed J) of a goal, all attempts."""
        eb = ep = ea = 0.0
        for run, pkg, dur, bid, att in self.c.execute(
                "SELECT r.run_id, r.pkg_energy_uj, r.duration_ns, r.baseline_id, ga.energy_uj "
                "FROM goal_attempt ga JOIN runs r ON r.run_id=ga.run_id WHERE ga.goal_id=?", (gid,)):
            s = (dur or 0) / 1e9
            idle = self.idle_w(bid)
            ip = idle.get("PACKAGE", 0.0)
            ib = self.idle_w(board_bid).get("DC_INPUT", 0.0) if board_bid else idle.get("DC_INPUT", 0.0)
            w = self.c.execute("SELECT AVG(energy_uj) FROM energy_sample_domains "
                               "WHERE run_id=? AND domain_id=28", (run,)).fetchone()[0] or 0.0
            eb += (w / 1000.0 - ib) * s
            ep += (pkg or 0) / 1e6 - ip * s
            ea += (att or 0) / 1e6
        return eb, ep, ea


def cells(store, goals, board_bid=None):
    """goals: {gid: (task, cls, point, policy)} -> {(cls, point, policy): dict}"""
    out = collections.defaultdict(lambda: {"n": 0, "ok": 0, "eb": 0.0, "ep": 0.0, "ea": 0.0, "task_eb": {}, "tasks": {}})
    for gid, (task, cls, pt, pol) in goals.items():
        ok = store.success(gid)
        eb, ep, ea = store.energy(gid, board_bid)
        v = out[(cls, pt, pol)]
        v["n"] += 1; v["ok"] += ok; v["eb"] += eb; v["ep"] += ep; v["ea"] += ea
        v["task_eb"][task] = eb
        t = v["tasks"].setdefault(norm_task(task), [0.0, 0, 0, 0.0])
        t[0] += eb; t[1] += ok; t[2] += 1; t[3] += ep  # repetitions summed; index 3 = package J
    res = {}
    for k, v in out.items():
        n, ok = v["n"], v["ok"]
        e = {"n": n, "ok": ok, "epg_board": v["eb"] / n, "epg_pkg": v["ep"] / n, "epg_attr": v["ea"] / n,
             "wilson": wilson(ok, n), "task_eb": v["task_eb"], "tasks": v["tasks"]}
        e["ach_board"] = e["epg_board"] / (ok / n) if ok else None
        e["ach_pkg"] = e["epg_pkg"] / (ok / n) if ok else None
        res[k] = e
    return res


def load_pilot(csv_path):
    goals = {}
    for r in csv.DictReader(open(csv_path)):
        cls = r["cls"] if r["cls"] not in ("", "none") else "none"
        goals[int(r["goal_id"])] = (r["task"], cls, r["point"] or "", r["policy"])
    return goals


def load_ledger(paths, by_arm=False):
    """Latest record wins per (item_id, policy): the highest goal_id (reruns, superseded goals).

    Guard (coordinator, Oct 19): the latest wins rule is applied within one study only. Studies reuse
    item ids (E2 and E2b do), so mixing study folders in one call would let one study replace another.
    """
    studies = {os.path.basename(os.path.dirname(os.path.abspath(p))) for p in paths}
    if len(studies) > 1:
        raise SystemExit("load_ledger: ledgers from more than one study folder in one call: %s" % sorted(studies))
    best = {}
    for path in paths:
        for l in open(path):
            d = json.loads(l)
            if d.get("validity") or not d.get("goal_id"):
                continue
            p = d.get("plan", {})
            key = (d.get("item_id"), p.get("policy"))
            if by_arm:
                key = key + (p.get("arm") or d.get("arm"),)
            gid = int(d["goal_id"])
            if key not in best or gid > best[key][0]:
                best[key] = (gid, (p.get("task"), p.get("cls") or "none", p.get("point") or "", p.get("policy")))
    return {gid: v for gid, v in best.values()}


def sweep_funnel(sweep_dir):
    rx = re.compile(r"(multi_turn_base_\d+) B0\s+\w+\s+err=\S+\s+llm=(\d+)\s+tool=(\d+).*score=(\d)")
    runs = []
    for i in (1, 2, 3):
        d = {}
        for l in open(os.path.join(sweep_dir, "sweep_r%d.txt" % i)):
            m = rx.search(l)
            if m:
                d[m[1]] = (int(m[2]), int(m[3]), int(m[4]))
        runs.append(d)
    r1, r2, r3 = runs
    solved = [k for k, v in r1.items() if v[2] == 1]
    long_ = [k for k in solved if r1[k][0] >= 8 and r1[k][1] >= 5]
    three = [k for k in long_ if k in r2 and k in r3 and r2[k][2] == 1 and r3[k][2] == 1]
    stable = [k for k in three if r1[k][:2] == r2[k][:2] == r3[k][:2]]
    return {"nBaseTasks": len(r1), "nSolvedOnce": len(solved), "nLongEnough": len(long_),
            "nSolvedThree": len(three), "nStable": len(stable), "nCallsVaried": len(three) - len(stable)}, r1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True, help="paper tex folder")
    ap.add_argument("--sandbox", default=os.getcwd())
    ap.add_argument("--db", help="frozen store file, opened read only (default: the live sandbox store)")
    ap.add_argument("--art", help="ledger folder of that store (default: artifacts beside the live store)")
    ap.add_argument("--pilot-board-baseline", default="baseline_1792100195_39554")
    ap.add_argument("--r5", default=os.path.expanduser("./data/r5/r5_numbers.json"))
    ap.add_argument("--flags", help="R2 E3 flag file: goal_id label (light or heavy), one per line")
    ap.add_argument("--flag-files", nargs="*", default=[], help="every R2 flag file, hashed into provenance")
    ap.add_argument("--flags-e2", help="R2 E2 flag file (block rule applies to E2 headlines)")
    ap.add_argument("--allow-ledger-mismatch", action="store_true",
                    help="on SHA256 mismatch, emit \\pending for R5 values instead of refusing")
    a = ap.parse_args()

    if a.db:
        db = a.db
    else:
        db = subprocess.run(["alems", "sandbox", "info"], capture_output=True, text=True, cwd=a.sandbox).stdout
        db = re.search(r"^store:\s+(\S+)", db, re.M).group(1)
    art = a.art or os.path.join(os.path.dirname(db), "artifacts")
    print("store %s%s; ledgers %s" % (db, " sha256 " + sha256(db) if a.db else " (live)", art))
    st = Store(db)
    M, prov = {}, {}

    def put(name, val, src):
        M[name] = val; prov[name] = src

    NOTE = {}  # trailing comments for numbers_auto.tex (R5 label, significance flags)

    def put_wilson(name, k, n, src):
        """Wilson 95 percent interval of k of n, as percent, macros nameLo and nameHi."""
        lo, hi = wilson(k, n)
        put(name + "Lo", "%.0f" % (100 * lo), "Wilson 95, %d of %d, %s" % (k, n, src))
        put(name + "Hi", "%.0f" % (100 * hi), "Wilson 95, %d of %d, %s" % (k, n, src))

    # ---- R5 file: tag and ledger hashes (coordinator Oct 17 answer 10) ----
    r5, r5_ok, r5_note = None, False, "r5 file absent"
    if os.path.exists(a.r5):
        r5 = json.load(open(a.r5))
        r5_sha = sha256(a.r5)
        tag = r5.get("provenance", {}).get("data_tag")
        if tag not in ("e1_e1b_e2_v2", "frozen_main"):  # frozen_main = R5 rerun on the frozen database (Oct 22)
            raise SystemExit("r5 data_tag is %r, expected frozen_main or e1_e1b_e2_v2" % tag)
        bad = []
        for gpath, h in r5["provenance"].get("ledgers", {}).items():
            base = os.path.basename(gpath)
            local = glob.glob(os.path.join(art, "*", base))
            if not local:
                bad.append("missing " + base)
            elif sha256(local[0]) != h:
                bad.append("sha differs " + local[0])
        if bad and not a.allow_ledger_mismatch:
            raise SystemExit("ledger check failed:\n  " + "\n  ".join(bad))
        r5_ok = not bad
        r5_note = "r5 %s sha256 %s tag %s%s" % (a.r5, r5_sha, tag, "" if r5_ok else ", LEDGER MISMATCH: " + "; ".join(bad))

    # ---- funnel (sweep files) ----
    sd = os.path.join(a.sandbox, "raf_sweep30")
    if os.path.exists(os.path.join(sd, "sweep_r3.txt")):
        fun, r1 = sweep_funnel(sd)
        for k, v in fun.items():
            put(k, str(v), "sweep files " + sd)
    put("minLlmCalls", "8", "selection rule in sweep_funnel")
    put("minToolCalls", "5", "selection rule in sweep_funnel")
    e1_tasks = open(os.path.join(a.sandbox, "raf_e1", "e1_tasks.txt")).read().split()
    if os.path.exists(os.path.join(sd, "sweep_r3.txt")):
        for name, tid in (("trip", "multi_turn_base_71"), ("watch", "multi_turn_base_105")):
            put(name + "Llm", str(r1[tid][0]), "sweep r1 " + tid)
            put(name + "Tool", str(r1[tid][1]), "sweep r1 " + tid)
        tot = [r1[t][0] + r1[t][1] for t in e1_tasks if t in r1]
        put("eoneCallsMin", str(min(tot)), "sweep r1, E1 tasks, model plus tool calls")
        put("eoneCallsMax", str(max(tot)), "sweep r1, E1 tasks, model plus tool calls")
    held = open(os.path.join(a.sandbox, "raf_e1", "e3_heldout_tasks.txt")).read().split()
    put("nEoneTasks", str(len(e1_tasks)), "raf_e1/e1_tasks.txt")
    put("nHeldOut", str(len(held)), "raf_e1/e3_heldout_tasks.txt")
    # latePointPct: the late failure point rule, read from the driver config (coordinator Oct 22)
    cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "r2", "make_pilot_config.py")
    m_late = re.search(r"round\(([0-9.]+) \* n\)", open(cfg).read()) if os.path.exists(cfg) else None
    if m_late:
        put("latePointPct", "%.0f" % (100 * float(m_late.group(1))), "make_pilot_config.py sha256 %s, late(n) = "
            "round(%s n) clamped to 3 through n minus 1" % (sha256(cfg), m_late.group(1)))
        NOTE["latePointPct"] = "late failure at call round(%s n), clamped to 3 through n minus 1" % m_late.group(1)
    else:
        put("latePointPct", "\\pending{latePointPct}", "pending: late(n) rule not found in " + cfg)

    # ---- pilot ----
    pg = load_pilot(os.path.join(art, "raf_pilot", "s7_goals.csv"))
    pc = cells(st, pg, board_bid=a.pilot_board_baseline)
    rec = [g for g in pg.values() if g[3] != "B0"]
    put("nPilotGoals", str(len(pg)), "s7_goals.csv")
    put("nPilotTasks", str(len(set(g[0] for g in pg.values()))), "s7_goals.csv")
    put("nPilotRecov", str(len(rec)), "s7_goals.csv")
    put("nPilotBlocks", str(len(rec) // 4), "s7_goals.csv")
    b0 = pc[("none", "", "B0")]
    put("nPilotBzero", str(b0["n"]), "pilot B0")
    put("bZeroNodeJ", "%.1f" % b0["epg_pkg"], "pilot B0 pkg")
    pb0 = [g for g, v in pg.items() if v[3] == "B0"]
    calls = [st.c.execute("SELECT COUNT(*) FROM llm_interactions li JOIN goal_attempt ga ON ga.run_id=li.run_id "
                          "WHERE ga.goal_id=?", (g,)).fetchone()[0] for g in pb0]
    put("pilotCallsMin", str(min(calls)), "pilot B0 llm_interactions per goal")
    put("pilotCallsMax", str(max(calls)), "pilot B0 llm_interactions per goal")
    ex = 811
    d = dict(st.c.execute("SELECT domain_id, SUM(energy_uj) FROM energy_sample_domains WHERE run_id=? "
                          "AND domain_id IN (5,6,7,20,24) GROUP BY domain_id", (ex,)))
    pkg, dur = st.c.execute("SELECT pkg_energy_uj, duration_ns FROM runs WHERE run_id=?", (ex,)).fetchone()
    bw = st.c.execute("SELECT AVG(energy_uj) FROM energy_sample_domains WHERE run_id=? AND domain_id=28",
                      (ex,)).fetchone()[0] or 0
    d[24] = st.c.execute("SELECT SUM(energy_uj) FROM gpu_samples WHERE run_id=? AND source='dcgm'",
                         (ex,)).fetchone()[0] or 0
    j = lambda k: d.get(k, 0) / 1e6
    exPkg, exBoard = pkg / 1e6, bw / 1000.0 * dur / 1e9
    exRes = exPkg - j(5) - j(6) - j(7) - j(20)
    for k, v in (("exRun", str(ex)), ("exBoardJ", fmt0(exBoard)), ("exPkgJ", fmt0(exPkg)),
                 ("exGpuJ", fmt0(j(7))), ("exCpuJ", fmt0(j(5) + j(6))), ("exDlaJ", fmt0(j(20))),
                 ("exResidJ", fmt0(exRes)), ("exResidPct", "%.0f" % (100 * exRes / exPkg)),
                 ("exDcgmJ", fmt0(j(24)))):
        put(k, v, "run %d, gross" % ex)
    if j(24) and j(7):
        put("gpuDcgmGap", "%.0f" % (100 * (1 - j(24) / j(7))), "run %d, domains 24,7" % ex)
    put("bZeroAttrJ", "%.1f" % b0["epg_attr"], "pilot B0 attributed")
    put("attrShare", "%.1f" % (100 * b0["epg_attr"] / b0["epg_pkg"]), "pilot B0")
    put("bZeroBoardJ", fmt0(b0["epg_board"]), "pilot B0 board, idle " + a.pilot_board_baseline)
    put("boardOverPkg", "%.2f" % (b0["epg_board"] / b0["epg_pkg"]), "pilot B0")
    fr = [v for (c, p, pol), v in pc.items() if pol.startswith("FR")]
    sr = [v for (c, p, pol), v in pc.items() if pol.startswith("SR")]
    put("frCorrect", "%d of %d" % (sum(v["ok"] for v in fr), sum(v["n"] for v in fr)), "pilot FR")
    put("srCorrect", "%d of %d" % (sum(v["ok"] for v in sr), sum(v["n"] for v in sr)), "pilot SR")
    put("srWrong", str(sum(v["n"] - v["ok"] for v in sr)), "pilot SR")
    put_wilson("frCorrect", sum(v["ok"] for v in fr), sum(v["n"] for v in fr), "pilot FR")
    put_wilson("srCorrect", sum(v["ok"] for v in sr), sum(v["n"] for v in sr), "pilot SR")
    worst = min((pc[(c, "early", "SR_warm")] for c in ("timeout", "tool_error")), key=lambda v: v["ok"])
    put("earlySrCorrect", "%d of %d" % (worst["ok"], worst["n"]), "pilot early timeout/tool SR_warm")
    put_wilson("earlySrCorrect", worst["ok"], worst["n"], "pilot early timeout/tool SR_warm")
    put("earlyTimeoutFrJ", fmt0(pc[("timeout", "early", "FR_warm")]["ach_pkg"]), "pilot pkg per achieved")
    put("earlyTimeoutSrJ", fmt0(pc[("timeout", "early", "SR_warm")]["ach_pkg"]), "pilot pkg per achieved")
    sav = [100 * (1 - pc[(c, "late", "SR_warm")]["ach_pkg"] / pc[(c, "late", "FR_warm")]["ach_pkg"])
           for c in CLS_NAME]
    put("lateSrSave", "%.0f to %.0f" % (min(sav), max(sav)), "pilot late, pkg per achieved")
    p_, lo_, hi_, nt_, nu_ = boot_saving([(pc[(c, "late", "SR_warm")], pc[(c, "late", "FR_warm")]) for c in CLS_NAME], e=3)
    psrc = "pilot late, pooled 4 classes, pkg per achieved, paired bootstrap over %d tasks, %d resamples, seed %d" % (nt_, BOOT_REPS, BOOT_SEED)
    put("lateSrSavePooled", "%.0f" % p_, psrc)
    put("lateSrSavePooledLo", "%.0f" % lo_, psrc)
    put("lateSrSavePooledHi", "%.0f" % hi_, psrc)
    rows = []
    for c, p in SITUATIONS:
        f, s = pc[(c, p, "FR_warm")], pc[(c, p, "SR_warm")]
        wf = (f["ach_pkg"] or 1e18) <= (s["ach_pkg"] or 1e18)
        b = lambda x, w: ("\\textbf{%s}" % fmt0(x)) if w else fmt0(x)
        rows.append("%s & %s & %d/%d & %s & %s & %d/%d & %s & %s \\\\" % (
            CLS_NAME[c], p, f["ok"], f["n"], fmt0(f["epg_pkg"]), b(f["ach_pkg"], wf),
            s["ok"], s["n"], fmt0(s["epg_pkg"]), b(s["ach_pkg"], not wf)))
        if (c, p) == SITUATIONS[3]:
            rows.append("\\midrule")
    os.makedirs(os.path.join(a.paper, "tables"), exist_ok=True)
    open(os.path.join(a.paper, "tables", "pilot_table.tex"), "w").write(
        "% GENERATED by paper_numbers.py; do not edit by hand.\n" + "\n".join(rows) + "\n\\bottomrule\n")

    # ---- E1 ----
    led = sorted(glob.glob(os.path.join(art, "raf_e1", "raf_e1_run_ledger.jsonl")) +
                 glob.glob(os.path.join(art, "raf_e1", "*rerun*ledger*.jsonl")))
    if led:
        eg = load_ledger(led)
        ec = cells(st, eg)
        put("nEoneGoals", fmt0(len(eg)), "E1 ledgers")
        eb0 = ec[("none", "", "B0")]
        put("eoneBzeroOk", "%d of %d" % (eb0["ok"], eb0["n"]), "E1 B0")
        put("eoneBzeroBoardJ", fmt0(eb0["epg_board"]), "E1 B0 board")
        for name, tid in (("trip", "multi_turn_base_71"), ("watch", "multi_turn_base_105")):
            gids = [g for g, v in eg.items() if v[0] in (tid, "bfcl_" + tid) and v[3] == "B0"]
            if gids:
                lo, hi = st.c.execute(
                    "SELECT MIN(li.prompt_tokens), MAX(li.prompt_tokens) FROM llm_interactions li "
                    "JOIN goal_attempt ga ON ga.run_id=li.run_id WHERE ga.goal_id IN (%s)"
                    % ",".join("?" * len(gids)), gids).fetchone()
                put(name + "CtxLo", fmt0(round(lo, -2)), "E1 B0 prompt_tokens min, " + tid)
                put(name + "CtxHi", fmt0(round(hi, -2)), "E1 B0 prompt_tokens max, " + tid)
        early_sr = [ec[(c, "early", "SR_warm")] for c in CLS_NAME]
        early_fr = [ec[(c, "early", "FR_warm")] for c in CLS_NAME]
        def rng(vs):
            lo, hi = min(v["ok"] for v in vs), max(v["ok"] for v in vs)
            return ("%d of %d" % (lo, vs[0]["n"])) if lo == hi else ("%d to %d of %d" % (lo, hi, vs[0]["n"]))
        put("eoneEarlySrOk", rng(early_sr), "E1 early SR_warm")
        put("eoneEarlyFrOk", rng(early_fr), "E1 early FR_warm")
        e_save = [100 * (1 - ec[(c, "early", "FR_warm")]["ach_board"] / ec[(c, "early", "SR_warm")]["ach_board"]) for c in CLS_NAME]
        l_save = [100 * (1 - ec[(c, "late", "SR_warm")]["ach_board"] / ec[(c, "late", "FR_warm")]["ach_board"]) for c in CLS_NAME]
        put("eoneEarlyFrSave", "%.0f to %.0f" % (min(e_save), max(e_save)), "E1 board per achieved")
        put("eoneLateSrSave", "%.0f to %.0f" % (min(l_save), max(l_save)), "E1 board per achieved")
        wins = sum(1 for c in CLS_NAME if e_save[list(CLS_NAME).index(c)] > 0) + sum(1 for x in l_save if x > 0)
        put("eoneWinsMatch", "%d of 8" % wins, "E1 board per achieved")
        put_wilson("eoneBzeroOk", eb0["ok"], eb0["n"], "E1 B0")
        put_wilson("eoneEarlySrOk", sum(v["ok"] for v in early_sr), sum(v["n"] for v in early_sr), "E1 early SR_warm pooled")
        put_wilson("eoneEarlyFrOk", sum(v["ok"] for v in early_fr), sum(v["n"] for v in early_fr), "E1 early FR_warm pooled")
        bsrc = "paired bootstrap over tasks, %d resamples, seed %d, board per achieved" % (BOOT_REPS, BOOT_SEED)
        for name, pt, win, lose in (("eoneEarlyFrSave", "early", "FR_warm", "SR_warm"),
                                    ("eoneLateSrSave", "late", "SR_warm", "FR_warm")):
            p, lo, hi, nt, nu = boot_saving([(ec[(c, pt, win)], ec[(c, pt, lose)]) for c in CLS_NAME])
            src = "%s; pooled 4 classes, %d tasks, %d undefined draws" % (bsrc, nt, nu)
            put(name + "Pooled", "%.0f" % p, src)
            put(name + "PooledLo", "%.0f" % lo, src)
            put(name + "PooledHi", "%.0f" % hi, src)
            for c in CLS_NAME:
                p, lo, hi, nt, nu = boot_saving([(ec[(c, pt, win)], ec[(c, pt, lose)])])
                src = "%s; %s, %d tasks, %d undefined draws" % (bsrc, c, nt, nu)
                put(name + CLS_CAMEL[c] + "Lo", "%.0f" % lo, src)
                put(name + CLS_CAMEL[c] + "Hi", "%.0f" % hi, src)
        rows = []
        for c, p in SITUATIONS:
            f, s = ec[(c, p, "FR_warm")], ec[(c, p, "SR_warm")]
            wf = (f["ach_board"] or 1e18) <= (s["ach_board"] or 1e18)
            b = lambda x, w: ("\\textbf{%s}" % fmt0(x)) if w else (fmt0(x) if x else "none")
            rows.append("%s & %s & %d/%d & %s & %s & %d/%d & %s & %s \\\\" % (
                CLS_NAME[c], p, f["ok"], f["n"], fmt0(f["epg_board"]), b(f["ach_board"], wf),
                s["ok"], s["n"], fmt0(s["epg_board"]), b(s["ach_board"], not wf)))
            if (c, p) == SITUATIONS[3]:
                rows.append("\\midrule")
        open(os.path.join(a.paper, "tables", "e1_table.tex"), "w").write(
            "% GENERATED by paper_numbers.py; do not edit by hand.\n" + "\n".join(rows) + "\n\\bottomrule\n")
        b0g = [g for g, v in eg.items() if v[3] == "B0"]
        runs = [r for (r,) in st.c.execute("SELECT run_id FROM goal_attempt WHERE goal_id IN (%s)"
                                           % ",".join("?" * len(b0g)), b0g)]
        tot = collections.Counter()
        for r in runs:
            for dom, s in st.c.execute("SELECT domain_id, SUM(energy_uj) FROM energy_sample_domains "
                                       "WHERE run_id=? AND domain_id IN (5,6,7,20) GROUP BY domain_id", (r,)):
                tot[dom] += s / 1e6
            pkg, dur = st.c.execute("SELECT pkg_energy_uj, duration_ns FROM runs WHERE run_id=?", (r,)).fetchone()
            tot[1] += (pkg or 0) / 1e6
            w = st.c.execute("SELECT AVG(energy_uj) FROM energy_sample_domains WHERE run_id=? AND domain_id=28",
                             (r,)).fetchone()[0] or 0
            tot[28] += w / 1000.0 * dur / 1e9
        if tot[1] and tot[28] and tot[7]:
            put("onDieResid", "%.0f" % (100 * (tot[1] - tot[5] - tot[6] - tot[7] - tot[20]) / tot[1]), "E1 B0 gross, domains 1,5,6,7,20")
            put("offDieShare", "%.0f" % (100 * (tot[28] - tot[1]) / tot[28]), "E1 B0 gross, domains 28,1")
            # gpuDcgmGap stays in numbers.tex: E1 did not record DCGM (domain 24).
        bid = st.c.execute("SELECT r.baseline_id FROM goal_attempt ga JOIN runs r ON r.run_id=ga.run_id "
                           "WHERE ga.goal_id=? LIMIT 1", (next(iter(eg)),)).fetchone()[0]
        idle = st.idle_w(bid)
        put("idleBoardW", "%.1f" % idle.get("DC_INPUT", 0), "E1 baseline " + bid)
        put("idlePkgTodayW", "%.1f" % idle.get("PACKAGE", 0), "E1 baseline " + bid)

    # ---- E1b (item 1) ----
    b_led = glob.glob(os.path.join(art, "raf_e1b", "raf_e1b_run_ledger.jsonl"))
    bg = {}
    if b_led and led:
        bg = load_ledger(b_led)
        bc = cells(st, bg)
        bsrc = "E1b ledger, goals %d to %d" % (min(bg), max(bg))
        opts = ("RB_warm", "RB_cold", "SG_warm", "SG_cold")
        wins_b = collections.Counter()
        rows = []
        for c, p in SITUATIONS:
            vs = [bc.get((c, p, o)) for o in opts]
            achs = [v["ach_board"] if v and v["ach_board"] else 1e18 for v in vs]
            best = min(achs)
            if best < 1e18:
                wins_b[opts[achs.index(best)]] += 1
            parts = []
            for v, ach in zip(vs, achs):
                if not v:
                    parts += ["\\pending{e1b cell}"] * 3
                    continue
                a_txt = "none" if not v["ach_board"] else fmt0(v["ach_board"])
                if ach == best:
                    a_txt = "\\textbf{%s}" % a_txt
                parts += ["%d/%d" % (v["ok"], v["n"]), fmt0(v["epg_board"]), a_txt]
            rows.append("%s & %s & %s \\\\" % (CLS_NAME[c], p, " & ".join(parts)))
            if (c, p) == SITUATIONS[3]:
                rows.append("\\midrule")
        open(os.path.join(a.paper, "tables", "e1b_table.tex"), "w").write(
            "% GENERATED by paper_numbers.py; do not edit by hand.\n" + "\n".join(rows) + "\n\\bottomrule\n")
        for o in opts:
            put("eonebWins" + o.replace("_warm", "Warm").replace("_cold", "Cold").replace("RB", "Rb").replace("SG", "Sg"),
                str(wins_b[o]), bsrc + ", lowest board per achieved of 8 situations")
        put("nEonebGoals", fmt0(len(bg)), bsrc)

        def pool(cs):
            return sum(v["ok"] for v in cs), sum(v["n"] for v in cs)
        late_tool = ("tool_error", "timeout")  # O2: pooled late tool side
        k, n = pool([bc[(c, "late", "RB_cold")] for c in late_tool])
        put("eonebRbLateToolOk", "%d of %d" % (k, n), bsrc + ", RB_cold late tool_error plus timeout")
        put_wilson("eonebRbLateToolOk", k, n, "E1b RB_cold late tool side")
        k, n = pool([ec[(c, "late", "SR_warm")] for c in late_tool])
        put("eonebSrLateToolOk", "%d of %d" % (k, n), "E1 ledgers, SR_warm late tool_error plus timeout")
        put_wilson("eonebSrLateToolOk", k, n, "E1 SR_warm late tool side")

    # ---- background task energies (R8, Oct 21): late timeout block, board J per goal (Store.energy) ----
    if led and bg:
        for name, tid in (("trip", "multi_turn_base_71"), ("watch", "multi_turn_base_105")):
            for cam, opt, cc, study in (("Fr", "FR_warm", ec, "E1"), ("Sr", "SR_warm", ec, "E1"), ("Rb", "RB_cold", bc, "E1b")):
                v = (cc.get(("timeout", "late", opt)) or {}).get("tasks", {}).get(tid)
                nm = "%s%sJ" % (name, cam)
                if not v or not v[2]:
                    put(nm, "\\pending{%s}" % nm, "pending: no %s late timeout %s goal for %s" % (study, opt, tid))
                    continue
                put(nm, fmt0(v[0] / v[2]), "%s ledgers, %s, timeout late %s, board J per goal (Store.energy), mean of %d goals"
                    % (study, tid, opt, v[2]))
                NOTE[nm] = "board energy per goal" + ("; roll back from E1b (other engine and baseline segments)" if study == "E1b" else "")

    # ---- best of six (D4 item 2): FR, SR from E1; RB from E1b ----
    if led and bg:
        six = ("FR_warm", "FR_cold", "SR_warm", "SR_cold", "RB_warm", "RB_cold")
        wins6 = collections.Counter()
        rows, n_sit = [], 0
        for c, p in SITUATIONS:
            src_cells = {o: (ec if o[:2] in ("FR", "SR") else bc).get((c, p, o)) for o in six}
            achs = {o: v["ach_board"] for o, v in src_cells.items() if v and v["ach_board"]}
            if not achs:
                continue
            n_sit += 1
            win = min(achs, key=achs.get)
            wins6[win] += 1
            parts = []
            for o in six:
                v = src_cells[o]
                if not v:
                    parts.append("\\pending{cell}")
                elif not v["ach_board"]:
                    parts.append("none")
                else:
                    t = fmt0(v["ach_board"])
                    parts.append("\\textbf{%s}" % t if o == win else t)
            w = src_cells[win]
            parts.append("%d/%d" % (w["ok"], w["n"]))
            rows.append("%s & %s & %s \\\\" % (CLS_NAME[c], p, " & ".join(parts)))
            if (c, p) == SITUATIONS[3]:
                rows.append("\\midrule")
        open(os.path.join(a.paper, "tables", "best6_table.tex"), "w").write(
            "% GENERATED by paper_numbers.py; do not edit by hand. Board J per successful goal, lowest bold.\n"
            + "\n".join(rows) + "\n\\bottomrule\n")
        s6 = "E1 (FR, SR) and E1b (RB) ledgers, board per achieved, lowest of six per situation"
        for o in six:
            put("bestsixWins" + o.replace("_warm", "Warm").replace("_cold", "Cold").replace("FR", "Fr")
                .replace("SR", "Sr").replace("RB", "Rb"), str(wins6[o]), s6)
        put("nBestsixSituations", str(n_sit), s6)

    # ---- cache savings: warm versus cold of the same option, recovery attempts, E1 plus E1b ----
    ga_cols = [r[1] for r in st.c.execute("PRAGMA table_info(goal_attempt)")]
    att_col = next((x for x in ("attempt_number", "attempt", "attempt_index") if x in ga_cols), None)
    li_cols = [r[1] for r in st.c.execute("PRAGMA table_info(llm_interactions)")]
    cached_col = next((x for x in ("tokens_reused", "cached_tokens", "prompt_cached_tokens", "cache_hit_tokens",
                                   "cached_prompt_tokens") if x in li_cols), None)
    reuse_tbl = not cached_col and bool(st.c.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'state_reuse_events'").fetchone())
    tok_src = cached_col or ("state_reuse_events.tokens_reused" if reuse_tbl else None)

    run_log = {}  # goal id -> recovery attempt runs (for the both ways check)

    def rec_metrics(gid):
        """Board J and uncached prompt tokens of the recovery attempts (attempt 2 onward)."""
        e = tok = 0.0
        for run, dur, bid in st.c.execute("SELECT ga.run_id, r.duration_ns, r.baseline_id FROM goal_attempt ga "
                                          "JOIN runs r ON r.run_id = ga.run_id WHERE ga.goal_id = ? AND ga.%s >= 2"
                                          % att_col, (gid,)).fetchall():
            run_log.setdefault(gid, []).append(run)
            mw = st.c.execute("SELECT AVG(energy_uj) FROM energy_sample_domains WHERE run_id = ? AND domain_id = 28",
                              (run,)).fetchone()[0] or 0.0
            e += (mw / 1000.0 - st.idle_w(bid).get("DC_INPUT", 0.0)) * (dur or 0) / 1e9
            if cached_col:
                tok += st.c.execute("SELECT COALESCE(SUM(prompt_tokens - COALESCE(%s, 0)), 0) FROM llm_interactions "
                                    "WHERE run_id = ?" % cached_col, (run,)).fetchone()[0]
            elif reuse_tbl:
                pt = st.c.execute("SELECT COALESCE(SUM(prompt_tokens), 0) FROM llm_interactions WHERE run_id = ?",
                                  (run,)).fetchone()[0]
                ru = st.c.execute("SELECT COALESCE(SUM(tokens_reused), 0) FROM state_reuse_events WHERE run_id = ?",
                                  (run,)).fetchone()[0]
                tok += pt - ru
        return e, (tok if tok_src else None)

    if led and bg and att_col:
        pairs = collections.defaultdict(dict)  # (task, cls, point, family) -> {warm: (e, tok), cold: (e, tok)}
        pair_gid = collections.defaultdict(dict)  # same key -> {warm: goal id, cold: goal id}
        for gid, (task, cls, pt, opt) in list(eg.items()) + list(bg.items()):
            if opt in ("B0", None) or "_" not in opt:
                continue
            fam, cache = opt.split("_", 1)
            pairs[(norm_task(task), cls, pt, fam)][cache] = rec_metrics(gid)
            pair_gid[(norm_task(task), cls, pt, fam)][cache] = gid
        both = {k: v for k, v in pairs.items() if "warm" in v and "cold" in v}
        csrc = "E1 plus E1b, warm vs cold of the same option paired by block, recovery attempts, %d pairs, " \
               "bootstrap over tasks, %d resamples, seed %d" % (len(both), BOOT_REPS, BOOT_SEED)

        def red_boot(idx):
            tasks = sorted({k[0] for k in both})
            by_t = collections.defaultdict(lambda: [0.0, 0.0])
            for k, v in both.items():
                if v["warm"][idx] is None or v["cold"][idx] is None:
                    return None
                by_t[k[0]][0] += v["warm"][idx]; by_t[k[0]][1] += v["cold"][idx]

            def red(draw):
                w = sum(by_t[t][0] for t in draw); c = sum(by_t[t][1] for t in draw)
                return 100 * (1 - w / c) if c else None
            rng = random.Random(BOOT_SEED)
            vals = sorted(v for v in (red([rng.choice(tasks) for _ in tasks]) for _ in range(BOOT_REPS)) if v is not None)
            return red(tasks), vals[int(round(0.025 * (len(vals) - 1)))], vals[int(round(0.975 * (len(vals) - 1)))]

        for name, idx in (("cacheEnergySave", 0), ("cacheTokSave", 1)):
            r = red_boot(idx)
            if r is None:
                put(name, "\\pending{%s}" % name, "pending: no cached token column in llm_interactions")
                continue
            for suf, val in zip(("", "Lo", "Hi"), r):
                put(name + suf, "%.0f" % val, csrc + ("; board J" if idx == 0 else "; uncached prompt tokens (%s)" % tok_src))

        # ---- cache both ways check (coordinator Oct 20 07:31): NULL as full miss must equal unpaired runs excluded ----
        if reuse_tbl and both:
            def unpaired(run):
                rows = st.c.execute("SELECT tokens_reused, tokens_recomputed FROM state_reuse_events WHERE run_id = ?",
                                    (run,)).fetchall()
                if not any(ru is None and rc is None for ru, rc in rows):
                    return False
                n = st.c.execute("SELECT COUNT(*) FROM llm_interactions WHERE run_id = ?", (run,)).fetchone()[0]
                return len(rows) != n
            bad = {k for k in both if any(unpaired(r) for c in ("warm", "cold") for r in run_log.get(pair_gid[k][c], []))}
            kept_all = both
            both = {k: v for k, v in kept_all.items() if k not in bad}
            if not both:
                raise SystemExit("cache both ways check: every pair holds an unpaired run; nothing written")
            diff = []
            for name, idx in (("cacheEnergySave", 0), ("cacheTokSave", 1)):
                r = red_boot(idx)
                if r is None:
                    continue
                for suf, val in zip(("", "Lo", "Hi"), r):
                    if "%.0f" % val != M.get(name + suf):
                        diff.append("%s full miss %s, excluded %.0f" % (name + suf, M.get(name + suf), val))
            both = kept_all
            if diff:
                raise SystemExit("cache both ways check FAILED (nothing written): " + "; ".join(diff))
            print("cache both ways check: %d pairs, %d with an unpaired run, identical" % (len(both), len(bad)))

    # ---- E2: contaminating failures (Writer request; first records for validity counts) ----
    e2l = glob.glob(os.path.join(art, "raf_e2", "raf_e2_run_ledger.jsonl"))
    if e2l:
        recs = [json.loads(l) for l in open(e2l[0])]
        recs = [d for d in recs if d.get("goal_id")]

        def k2(d):
            p = d.get("plan", {})
            return (d.get("item_id"), p.get("policy"), p.get("arm") or d.get("arm"))
        first, latest = {}, {}
        for d in sorted(recs, key=lambda d: int(d["goal_id"])):
            first.setdefault(k2(d), d)
            latest[k2(d)] = d
        esrc = "E2 run ledger %s; validity counts from first records per (item_id, policy, arm)" % os.path.basename(e2l[0])
        put("nEtwoGoalsRun", fmt0(len(recs)), "E2 run ledger, every record with a goal id")
        valid = {k: d for k, d in latest.items() if not d.get("validity")}
        put("nEtwoValid", fmt0(len(valid)), "E2 latest record per key without a validity code")
        codes = collections.Counter(c for d in first.values() for c in (d.get("validity") or []))
        for code, nm in (("PRE_INJECTION", "PreInjection"), ("CORRUPTION_NOT_APPLIED", "CorruptionNotApplied"),
                         ("FALSE_DETECTION", "FalseDetection"), ("DETECTION_MISSED", "DetectionMissed")):
            n_c = sum(v for c, v in codes.items() if c.startswith(code))
            put("etwoInv" + nm, str(n_c), esrc + ", codes starting with " + code)
        put("etwoPreInjection", M["etwoInvPreInjection"], esrc + ", PRE_INJECTION codes, excluded from every other E2 number")
        codes_all = collections.Counter(c for d in recs for c in (d.get("validity") or []))
        for code, nm in (("PRE_INJECTION", "PreInjection"), ("CORRUPTION_NOT_APPLIED", "CorruptionNotApplied"),
                         ("FALSE_DETECTION", "FalseDetection"), ("DETECTION_MISSED", "DetectionMissed")):
            put("etwoInvAll" + nm, str(sum(v for c, v in codes_all.items() if c.startswith(code))),
                "E2 run ledger, every record including reruns, codes starting with " + code)
        b0_all = [d for d in recs if d.get("plan", {}).get("policy") == "B0"]
        fa_all = sum(1 for d in b0_all if any(c.startswith("FALSE_DETECTION") for c in (d.get("validity") or [])))
        put("etwoFalseAlarmAll", "%d of %d" % (fa_all, len(b0_all)), "E2 B0 records including reruns")
        b0 = [d for d in first.values() if d.get("plan", {}).get("policy") == "B0"]
        fa = sum(1 for d in b0 if any(c.startswith("FALSE_DETECTION") for c in (d.get("validity") or [])))
        put("etwoFalseAlarm", "%d of %d" % (fa, len(b0)), esrc + ", B0 goals with FALSE_DETECTION over all B0 goals")
        put_wilson("etwoFalseAlarm", fa, len(b0), "E2 B0 first records")
        # ePersistentRecurred: persistent goals whose failure fired on attempt 1 and again on attempt 2 (first records)
        pers = [d for d in first.values() if str((d.get("plan") or {}).get("cls", "")).startswith("persistent")]
        rec_ = sum(1 for d in pers if (d.get("detail") or {}).get("fired_a1") and (d.get("detail") or {}).get("fired_a2"))
        put("ePersistentRecurred", "%d of %d" % (rec_, len(pers)), esrc + ", persistent classes, detail.fired_a1 and "
            "detail.fired_a2 both set")
        NOTE["ePersistentRecurred"] = "E2 persistent goals whose failure recurred on attempt 2, first records"
        if rec_ != len(pers):
            print("ALERT: ePersistentRecurred %d of %d, coordinator expected all" % (rec_, len(pers)))
        # etwoSelfCorrect comes from paper_extra.py (E2b); not defined here (duplicate check)
        put("etwoRejectedSelfCorrect", "\\pending{etwoRejectedSelfCorrect}",
            "pending: rule for a rejected corruption not yet defined by the coordinator")
        # per class and option, valid goals; arm kept in the label
        g2 = {}
        for (item, pol, arm), d in valid.items():
            p = d.get("plan", {})
            if pol == "B0":
                continue
            g2[int(d["goal_id"])] = (p.get("task"), p.get("cls"), p.get("point") or "", "%s@%s" % (pol, arm))
        c2 = cells(st, g2)
        rows = []
        for (cls, pt, lab) in sorted(c2):
            v = c2[(cls, pt, lab)]
            pol, arm = lab.split("@")
            rows.append("%s & %s & %s & %s & %d/%d & %s & %s \\\\" % (
                cls.replace("_", " "), pt, pol.replace("_", " "), arm, v["ok"], v["n"], fmt0(v["epg_board"]),
                fmt0(v["ach_board"]) if v["ach_board"] else "none"))
        open(os.path.join(a.paper, "tables", "e2_table.tex"), "w").write(
            "% GENERATED by paper_numbers.py; do not edit by hand. E2 valid goals, board J.\n"
            + "\n".join(rows) + "\n\\bottomrule\n")
        # persistent cells: escalating arm versus fixed arm, same option, paired by task
        prs = [(c2[(c, p, l.replace("@fixed", "@escalate"))], c2[(c, p, l)]) for (c, p, l) in c2
               if c.startswith("persistent") and l.endswith("@fixed") and (c, p, l.replace("@fixed", "@escalate")) in c2]
        if not prs:
            prs = [(c2[(c, p, l2)], c2[(c, p, l)]) for (c, p, l) in c2 for (c3_, p3, l2) in c2
                   if c.startswith("persistent") and l.endswith("@fixed") and c3_ == c and p3 == p
                   and l2.split("@")[0] == l.split("@")[0] and l2.split("@")[1] not in ("fixed",)]
        if prs:
            p_, lo_, hi_, nt_, nu_ = boot_saving(prs)
            s2 = "E2 persistent cells, escalating arm below fixed arm, board per achieved, %d cells, %d tasks" % (len(prs), nt_)
            for suf, val in (("", p_), ("Lo", lo_), ("Hi", hi_)):
                put("etwoEscVsFixedSave" + suf, "%.1f" % val, s2)
        # timing fields, found by name anywhere in the valid records
        def walk(x, acc):
            if isinstance(x, dict):
                for kk, vv in x.items():
                    if isinstance(vv, (int, float)) and re.search(r"turn_check.*_ns$", kk):
                        acc["turn"].append(vv)
                    elif isinstance(vv, (int, float)) and re.search(r"accept.*_ns$", kk):
                        acc["accept"].append(vv)
                    else:
                        walk(vv, acc)
            elif isinstance(x, list):
                for vv in x:
                    walk(vv, acc)
        acc = {"turn": [], "accept": []}
        for d in valid.values():
            walk(d, acc)
        for nm, key in (("perTurnCheckMs", "turn"), ("acceptTestMs", "accept")):
            xs = sorted(acc[key])
            if xs:
                put(nm, "%.1f" % (xs[len(xs) // 2] / 1e6), "E2 ledgers, median of fields matching %s, %d values" % (key, len(xs)))
            else:
                put(nm, "\\pending{%s}" % nm, "pending: no timing field found in the E2 ledger")

    # ---- second and third model (coordinator Oct 20 07:42): same functions as E1, never pooled ----
    sens_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "r2",
                             "raf_m4_marker_goals.txt")
    sens_ids = {int(x) for x in open(sens_path).read().split()} if os.path.exists(sens_path) else None
    MODELS = (("mTwo", "raf_m3", "SECOND MODEL (Mistral Small 3.2 24B, 8 bit; raf_m3)", (), None),
              ("mThree", "raf_m4", "THIRD MODEL (gpt-oss 20B; raf_m4, task 105 removed)", ("multi_turn_base_105",), None),
              ("mThreeSens", "raf_m4", "THIRD MODEL SENSITIVITY (gpt-oss 20B; raf_m4, task 105 and harmony marker goals removed)",
               ("multi_turn_base_105",), sens_ids if sens_ids is not None else set()))
    MODEL_SETS = {}  # pre -> (recovery ledgers, b0 ledgers, dropped tasks, valid goals, cells); main runs only, not the sensitivity
    for pre, study, mlabel, drop, excl in MODELS:
        if excl is not None and not excl:
            put("mThreeSensChanged", "\\pending{mThreeSensChanged}", "pending: no marker goal file " + sens_path)
            continue
        mled = glob.glob(os.path.join(art, study, "%s_run_ledger.jsonl" % study))
        bled = glob.glob(os.path.join(art, study + "_b0", "%s_b0_run_ledger.jsonl" % study))
        if not mled:
            put(pre + "NGoals", "\\pending{%sNGoals}" % pre, "pending: no %s ledger" % study)
            continue
        mall = {g: v for g, v in load_ledger(mled).items() if norm_task(v[0]) not in drop}
        mg = {g: v for g, v in mall.items() if not (excl and g in excl)}
        mc = cells(st, mg)
        if excl is None:
            MODEL_SETS[pre] = (mled, bled, drop, mg, mc)
        msrc = "%s; %s, latest valid per (item, policy)%s" % (
            mlabel, os.path.basename(mled[0]), (", tasks removed: " + ", ".join(drop)) if drop else "")
        if excl:
            msrc += ", %d marker goals removed (%s sha256 %s; %d of %d ids found in the set)" % (
                len(mall) - len(mg), os.path.basename(sens_path), sha256(sens_path), len(set(excl) & set(mall)), len(excl))
            put("mThreeMarkerGoals", str(len(mall) - len(mg)), msrc + ", goals with a harmony marker in a tool name, removed in mThreeSens")
            NOTE["mThreeMarkerGoals"] = mlabel
            put("mThreeMarkerGoals", str(len(mall) - len(mg)), msrc + ", goals with a harmony marker in a tool name, removed in mThreeSens")
            NOTE["mThreeMarkerGoals"] = mlabel

        def MP(n, v, s, note=""):
            put(pre + n, v, s)
            NOTE[pre + n] = mlabel + note

        def MW(n, k, nn, s):
            MP(n, "%d of %d" % (k, nn), s)
            put_wilson(pre + n, k, nn, s)
            NOTE[pre + n + "Lo"] = NOTE[pre + n + "Hi"] = mlabel

        MP("NKept", str(len({norm_task(v[0]) for v in mg.values()})), msrc + ", tasks with recovery goals")
        MP("NGoals", fmt0(len(mg)), msrc + ", recovery goals")
        if bled and not excl:
            first = {}
            for l in open(bled[0]):
                if not l.strip():
                    continue
                d = json.loads(l)
                if d.get("goal_id"):
                    first.setdefault(d.get("item_id"), d)
            nbad = sum(1 for d in first.values() if d.get("validity"))
            brule = "all first records (one per item, all screened tasks); a first record with a validity code counts as unsolved"
            bsrc = "%s; %s, %s (%d such records)" % (mlabel, os.path.basename(bled[0]), brule, nbad)
            MW("BzeroOk", sum(st.success(int(d["goal_id"])) for d in first.values() if not d.get("validity")),
               len(first), bsrc)
            for x in ("", "Lo", "Hi"):
                NOTE[pre + "BzeroOk" + x] = mlabel + "; " + brule
        elif not excl:
            MP("BzeroOk", "\\pending{%sBzeroOk}" % pre, "pending: no %s_b0 ledger" % study)
        for opt, cam in (("FR_warm", "FrWarm"), ("SR_warm", "SrWarm"), ("RB_cold", "RbCold")):
            vs = [v for (c, p, o), v in mc.items() if o == opt]
            MW(cam + "Ok", sum(v["ok"] for v in vs), sum(v["n"] for v in vs), msrc + ", " + opt + ", both points")
            for pt in ("early", "late"):
                vp = [v for (c, p, o), v in mc.items() if o == opt and p == pt]
                k, nn = sum(v["ok"] for v in vp), sum(v["n"] for v in vp)
                MW(pt.capitalize() + cam + "Ok", k, nn, msrc + ", %s %s, 4 classes" % (opt, pt))
                ach = sum(v["epg_board"] * v["n"] for v in vp) / k if k else None
                MP(pt.capitalize() + cam + "J", fmt0(ach) if ach else "none",
                   msrc + ", %s %s, board J per successful goal, 4 classes" % (opt, pt))
        msav = "paired bootstrap over tasks, %d resamples, seed %d, board per achieved, pooled 4 classes" % (BOOT_REPS, BOOT_SEED)
        for nm, pt, win, lose in (("EarlyFrSave", "early", "FR_warm", "SR_warm"), ("LateSrSave", "late", "SR_warm", "FR_warm")):
            pairs = [(mc[(c, pt, win)], mc[(c, pt, lose)]) for c in CLS_NAME if (c, pt, win) in mc and (c, pt, lose) in mc]
            try:
                p, lo, hi, nt, nu = boot_saving(pairs)
                "%.0f %.0f %.0f" % (p, lo, hi)
            except (TypeError, IndexError, ZeroDivisionError):
                for suf in ("", "Lo", "Hi"):
                    MP(nm + suf, "\\pending{%s}" % (pre + nm + suf), "pending: %s %s vs %s has no defined saving" % (study, win, lose))
                continue
            flag = "" if (lo > 0 or hi < 0) else "; not significant: 95 percent CI includes 0"
            s = "%s; %s below %s, %s; %s, %d tasks, %d undefined draws%s" % (msrc, win, lose, pt, msav, nt, nu, flag)
            for suf, x in (("", p), ("Lo", lo), ("Hi", hi)):
                MP(nm + suf, "%.0f" % x, s, flag)
            if pre == "mThree" and nm == "EarlyFrSave":
                for suf in ("", "Lo", "Hi"):
                    NOTE[pre + nm + suf] += "; not a claim, sensitive to marker goals (mThreeSensChanged)"
        wins = m = 0
        for c in CLS_NAME:
            for pt, win, lose in (("early", "FR_warm", "SR_warm"), ("late", "SR_warm", "FR_warm")):
                a_, b_ = mc.get((c, pt, win)), mc.get((c, pt, lose))
                if not a_ or not b_:
                    continue
                m += 1
                if a_["ach_board"] and (not b_["ach_board"] or a_["ach_board"] < b_["ach_board"]):
                    wins += 1
        MP("WinsMatch", "%d of %d" % (wins, m), msrc + ", cells where the E1 split winner (early FR_warm, late SR_warm) "
           "has the lower board J per successful goal (a winner with successes beats an option with none)")


    # ---- m23_table and models_table (R8 Oct 21, coordinator approved): appendix, rows only ----
    datadir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    def raw(paths):
        out = []
        for pth in paths or []:
            out += [json.loads(l) for l in open(pth) if l.strip()]
        return [d for d in out if d.get("goal_id")]

    def ptask(d):
        return norm_task((d.get("plan") or {}).get("task"))

    m23 = []
    for pre, lab in (("mTwo", "Mistral Small 3.2 24B"), ("mThree", "gpt-oss 20B")):
        if pre not in MODEL_SETS:
            continue
        mc_ = MODEL_SETS[pre][4]
        m23.append("\\multicolumn{8}{l}{\\textit{%s}} \\\\" % lab)
        for c, p in SITUATIONS:
            vs = [mc_.get((c, p, o)) for o in ("FR_warm", "SR_warm", "RB_cold")]
            achs = [v["ach_board"] for v in vs if v and v["ach_board"]]
            best = min(achs) if achs else None
            parts = []
            for v in vs:
                if not v:
                    parts += ["none", "none"]
                    continue
                t = fmt0(v["ach_board"]) if v["ach_board"] else "none"
                if v["ach_board"] and v["ach_board"] == best:
                    t = "\\textbf{%s}" % t
                parts += ["%d/%d" % (v["ok"], v["n"]), t]
            m23.append("%s & %s & %s \\\\" % (CLS_NAME[c], p, " & ".join(parts)))
        m23.append("\\midrule")
    if m23:
        open(os.path.join(a.paper, "tables", "m23_table.tex"), "w").write(
            "% GENERATED by paper_numbers.py; do not edit by hand. Second and third model, latest valid per (item, policy), "
            "gpt-oss task 105 removed; correct k/n and board J per successful goal, lowest bold.\n"
            + "\n".join(m23[:-1]) + "\n\\bottomrule\n")

    specs = []  # (label, recovery records, b0 records, valid recovery goals, [(b0 gid, counts, task)], (slope, ci))
    if led:
        e1r = raw(led) + [d for d in raw(b_led) if (d.get("plan") or {}).get("policy") == "RB_cold"]
        law0 = (r5 or {}).get("energyLawLinear") or {}
        valid0 = {gg: v for gg, v in eg.items() if v[3] != "B0"}
        valid0.update({gg: v for gg, v in bg.items() if v[3] == "RB_cold"})  # roll back from E1b
        specs.append(("Qwen3 30B", [d for d in e1r if (d.get("plan") or {}).get("policy") != "B0"],
                      [d for d in e1r if (d.get("plan") or {}).get("policy") == "B0"], valid0,
                      [(gg, True, norm_task(v[0])) for gg, v in eg.items() if v[3] == "B0"],
                      (law0.get("linear_b"), law0.get("linear_b_ci"))))
    for pre, lab, px in (("mTwo", "Mistral Small 3.2 24B", "m3"), ("mThree", "gpt-oss 20B", "m4")):
        if pre not in MODEL_SETS:
            continue
        mled_, bled_, drop_, mg_, _ = MODEL_SETS[pre]
        rr = [d for d in raw(mled_) if ptask(d) not in drop_]
        br = raw(bled_)  # B0: all first records, all screened tasks (same rule as the BzeroOk macros)
        fb = {}
        for d in sorted(br, key=lambda d: int(d["goal_id"])):
            fb.setdefault(d.get("item_id"), d)
        lp = os.path.join(datadir, "r5" + px, "r5_numbers.json")
        lw = (json.load(open(lp)).get(px + "EnergyLawLinear") or {}) if os.path.exists(lp) else {}
        specs.append((lab, rr, br, mg_, [(int(d["goal_id"]), not d.get("validity"), ptask(d)) for d in fb.values()],
                      (lw.get("linear_b"), lw.get("linear_b_ci"))))

    def model_col(spec, tasks=None):
        lab, rr, br, valid, b0, law = spec
        keep = lambda t: tasks is None or norm_task(t) in tasks
        rr = [d for d in rr if keep(ptask(d))]
        br = [d for d in br if keep(ptask(d))]
        valid = {gg: v for gg, v in valid.items() if keep(v[0])}
        b0 = [x for x in b0 if keep(x[2])]
        cc = cells(st, valid)
        okb = [gg for gg, ok_, t in b0 if ok_]
        k0 = sum(st.success(gg) for gg in okb)
        j0 = sum(st.energy(gg)[0] for gg in okb) / len(okb) if okb else None
        out = [str(len({norm_task(v[0]) for v in valid.values()})), fmt0(len(rr) + len(br)), fmt0(len(br)),
               fmt0(len(rr)), fmt0(len(valid)), "%d/%d" % (k0, len(b0)), fmt0(j0) if j0 else "none"]
        for opt in ("FR_warm", "SR_warm", "RB_cold"):
            for pt in ("early", "late"):
                vp = [v for (c, p, o), v in cc.items() if o == opt and p == pt]
                k, n = sum(v["ok"] for v in vp), sum(v["n"] for v in vp)
                out.append("%d/%d" % (k, n) if n else "none")
                out.append(fmt0(sum(v["epg_board"] * v["n"] for v in vp) / k) if k else "none")
        wins = m = 0
        for c in CLS_NAME:
            for pt, win, lose in (("early", "FR_warm", "SR_warm"), ("late", "SR_warm", "FR_warm")):
                a_, b_ = cc.get((c, pt, win)), cc.get((c, pt, lose))
                if not a_ or not b_:
                    continue
                m += 1
                if a_["ach_board"] and (not b_["ach_board"] or a_["ach_board"] < b_["ach_board"]):
                    wins += 1
        out.append("%d of %d" % (wins, m))
        if tasks is None and law[0] is not None and law[1] and len(law[1]) == 2:
            out.append("$%.4f$ ($%.4f$ to $%.4f$)" % (law[0], law[1][0], law[1][1]))
        else:
            out.append("--")
        return out

    if len(specs) == 3:
        lbl = ["Tasks", "Goals run", "Runs without failures", "Recovery goals", "Valid goals used",
               "Correct without failures", "Board J per goal without failures"]
        for opt in ("Restart warm", "Resume warm", "Roll back cold"):
            for pt in ("early", "late"):
                lbl += ["%s, %s, correct" % (opt, pt), "%s, %s, J per successful goal" % (opt, pt)]
        lbl += ["Split count (restart early, resume late)", "Per call slope, J per token (95 percent CI)"]
        shared = None
        for s in specs:
            ts = {norm_task(v[0]) for v in s[3].values()}
            shared = ts if shared is None else shared & ts
        rows = ["\\multicolumn{4}{l}{\\textit{(A) each model on its own kept tasks}} \\\\"]
        cols = [model_col(s) for s in specs]
        rows += ["%s & %s \\\\" % (l, " & ".join(c[i] for c in cols)) for i, l in enumerate(lbl)]
        msrc = "models_table: Qwen3 30B from E1 (restart, resume) and E1b (roll back cold), Mistral raf_m3, gpt-oss raf_m4 " \
               "(task 105 removed); latest valid per (item, policy); slope copied from R5 (eLawLinB, m3 and m4 files)"
        put("modelsSharedTasks", str(len(shared)), msrc + ", tasks with valid recovery goals in all three models")
        if shared:
            rows.append("\\midrule")
            rows.append("\\multicolumn{4}{l}{\\textit{(B) the \\modelsSharedTasks{} tasks shared by all three models; "
                        "descriptive only}} \\\\")
            cols = [model_col(s, shared) for s in specs]
            rows += ["%s & %s \\\\" % (l, " & ".join(c[i] for c in cols)) for i, l in enumerate(lbl)]
            rows.append("\\multicolumn{4}{l}{\\footnotesize Slope fitted on each model's kept tasks, see block A.} \\\\")
        open(os.path.join(a.paper, "tables", "models_table.tex"), "w").write(
            "% GENERATED by paper_numbers.py; do not edit by hand. Columns: Qwen3 30B, Mistral Small 3.2 24B, gpt-oss 20B. "
            "Board J; Qwen roll back from E1b; B0 rules as the BzeroOk macros.\n" + "\n".join(rows) + "\n\\bottomrule\n")
        print("models_table: %d shared tasks; m23_table %d rows" % (len(shared), len(m23)))
    else:
        put("modelsSharedTasks", "\\pending{modelsSharedTasks}", "pending: fewer than three models in this build")

    # ---- mThree versus mThreeSens (coordinator Oct 20 09:02): printed in the build, never stops ----
    if any(k.startswith("mThreeSens") and k != "mThreeSensChanged" for k in M):
        print("== mThree versus mThreeSens (harmony marker goals removed)")
        changed = 0
        for nm in ("EarlyFrSave", "LateSrSave"):
            row = []
            for p in ("mThree", "mThreeSens"):
                v = [M.get(p + nm + s) for s in ("", "Lo", "Hi")]
                ok = all(x is not None and not str(x).startswith("\\") for x in v)
                row.append((v, ok, "n.s." if "not significant" in NOTE.get(p + nm, "") else "sig"))
            (va, oka, sa), (vb, okb, sb) = row
            ch = not (oka and okb) or float(va[0]) * float(vb[0]) < 0 or sa != sb
            changed += ch
            print("  %-12s mThree %s (%s to %s) %s   mThreeSens %s (%s to %s) %s%s" % (
                nm, va[0], va[1], va[2], sa, vb[0], vb[1], vb[2], sb, "   CHANGED" if ch else ""))
        put("mThreeSensChanged", str(changed), "mThreeSens savings (EarlyFrSave, LateSrSave) whose sign or significance "
            "differs from mThree, or that are not defined")
        NOTE["mThreeSensChanged"] = "THIRD MODEL SENSITIVITY; report to the coordinator at once if above 0"
        if changed:
            print("ALERT: mThreeSensChanged = %d, report to the coordinator" % changed)

    # ---- R2 values, computed from R2's named sources (coordinator Oct 21); the build stops if they differ ----
    R2CHECK = {"etwoRejectedN": "136", "etwoRejectedSelfCorrect": "121", "perTurnCheckMs": "1.46", "acceptTestMs": "1.84"}
    r2dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "r2")
    tsv = os.path.join(r2dir, "e2_rejected_steps.tsv")
    e2led = glob.glob(os.path.join(art, "raf_e2", "raf_e2_run_ledger.jsonl"))
    if os.path.exists(tsv) and e2led:
        rows = [l.rstrip("\n").split("\t") for l in open(tsv) if l.strip() and not l.startswith("#")]
        ix = {h: i for i, h in enumerate(rows[0])}
        rej = {int(r[ix["goal_id"]]) for r in rows[1:] if r[ix["rerun"]] == "0" and r[ix["status"]] == "rejected"}
        sc = set()
        for l in open(e2led[0]):
            d = json.loads(l) if l.strip() else {}
            if d.get("goal_id") and (d.get("detail") or {}).get("self_corrected"):
                sc.add(int(d["goal_id"]))
        rsrc = "E2 rejected wrong steps (first records), %s sha256 %s (rule in its header); self corrected from detail.self_corrected in %s" % (
            os.path.basename(tsv), sha256(tsv), os.path.basename(e2led[0]))
        put("etwoRejectedN", str(len(rej)), rsrc)
        put("etwoRejectedSelfCorrect", str(len(rej & sc)), rsrc)
        put_wilson("etwoRejectedSelfCorrect", len(rej & sc), len(rej), rsrc)
    else:
        for nm in ("etwoRejectedN", "etwoRejectedSelfCorrect"):
            put(nm, "\\pending{%s}" % nm, "pending: %s or the E2 ledger missing" % tsv)

    def ms_stats(xs):
        xs = sorted(xs)
        n = len(xs)
        med = (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)
        return med, sum(xs) / n, xs[int(round(0.95 * (n - 1)))], n

    ann = None
    for (tname,) in st.c.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"):
        cols = [r[1] for r in st.c.execute("PRAGMA table_info(%s)" % tname)]
        if "annotation_type" in cols and "payload" in cols:
            ann = tname
            break
    tc = []
    if ann:
        for (pl,) in st.c.execute("SELECT payload FROM %s WHERE annotation_type = 'raf.turn_check'" % ann):
            try:
                tc += [c["ms"] for c in (json.loads(pl or "{}").get("checks") or []) if isinstance(c.get("ms"), (int, float))]
            except (ValueError, AttributeError):
                pass
    if tc:
        med, mean, p95, n = ms_stats(tc)
        put("perTurnCheckMs", "%.2f" % med, "%s.raf.turn_check checks[].ms, median of %d checks (mean %.2f, p95 %.2f ms)" % (ann, n, mean, p95))
        NOTE["perTurnCheckMs"] = "median, ms; mean %.2f, p95 %.2f, n %d" % (mean, p95, n)
    else:
        put("perTurnCheckMs", "\\pending{perTurnCheckMs}", "pending: no raf.turn_check annotations")
    acc = []
    e2bl = sorted(p for p in glob.glob(os.path.join(art, "raf_e2b_r2", "*ledger*.jsonl")) if "smoke" not in os.path.basename(p))
    for path in e2bl:
        for l in open(path):
            d = json.loads(l) if l.strip() else {}
            for am in (d.get("attempt_meta") or {}).values():
                co = am.get("corruption") if isinstance(am, dict) else None
                if isinstance(co, dict) and isinstance(co.get("accept_ms"), (int, float)):
                    acc.append(co["accept_ms"])
    if acc:
        med, mean, p95, n = ms_stats(acc)
        put("acceptTestMs", "%.2f" % med, "E2b r2 ledgers %s, attempt_meta.*.corruption.accept_ms, median of %d (mean %.2f, p95 %.2f ms)"
            % (",".join(os.path.basename(p) for p in e2bl), n, mean, p95))
        NOTE["acceptTestMs"] = "median, ms; mean %.2f, p95 %.2f, n %d" % (mean, p95, n)
    else:
        put("acceptTestMs", "\\pending{acceptTestMs}", "pending: no corruption.accept_ms in the E2b r2 ledgers")
    diff = ["%s computed %s, R2 %s" % (k, M.get(k), v) for k, v in R2CHECK.items()
            if not str(M.get(k, "")).startswith("\\") and M.get(k) != v]
    if diff:
        raise SystemExit("R2 value check FAILED (nothing written): " + "; ".join(diff))
    print("R2 value check: " + ", ".join("%s %s" % (k, M.get(k)) for k in R2CHECK))

    # ---- nMainGoals: valid goals of E1, E1b, E2, E2b (E3 later) ----
    e2l = glob.glob(os.path.join(art, "raf_e2", "raf_e2_run_ledger.jsonl"))
    e2bl = sorted(glob.glob(os.path.join(art, "raf_e2b_r2", "raf_e2b_r2_items_raf_e2b_r2_items_ledger.jsonl")))
    if led and bg and e2l and e2bl:
        n2, n2b = len(load_ledger(e2l, True)), len(load_ledger(e2bl, True))
        put("nMainGoals", fmt0(len(eg) + len(bg) + n2 + n2b),
            "valid latest records: E1 %d, E1b %d, E2 %d, E2b %d" % (len(eg), len(bg), n2, n2b))

    # ---- R5 values (copied, never recomputed) ----
    LABEL = "OFFLINE CALIBRATED RULE (R5, data_tag e1_e1b_e2_v2)"
    NOT_SIG = ("ctrlSavingVsRollback", "ctrlGainContam", "xstarRuleGainClean")
    g = r5 or {}
    sig_problems = []

    def r5_get(name):
        """Value, CI and sub tag of an R5 field: scalar plus nameCI, or a dict with value and ci."""
        v = g.get(name)
        if isinstance(v, dict):
            return v.get("value"), v.get("ci"), v.get("sub_tag")
        return v, g.get(name + "CI"), None

    def r5_put(name, val, key, fmt="%.1f", scale=1.0, sub=None):
        tag = LABEL + (", sub_tag " + sub if sub else "")
        if r5 is None or not r5_ok or val is None:
            put(name, "\\pending{%s}" % name, "pending: %s; %s, key %s" % (tag, r5_note, key))
            return
        txt = fmt0(val) if isinstance(val, int) else fmt % (val * scale)
        put(name, txt, "%s; %s, key %s" % (tag, r5_note, key))
        NOTE[name] = tag

    def r5_put_ci(name, key, fmt="%.1f", scale=1.0):
        val, ci, sub = r5_get(key)
        r5_put(name, val, key, fmt, scale, sub)
        ci = ci or [None, None]
        r5_put(name + "Lo", ci[0], key + " ci[0]", fmt, scale, sub)
        r5_put(name + "Hi", ci[1], key + " ci[1]", fmt, scale, sub)
        if name in NOT_SIG:
            if ci[0] is not None and ci[0] <= 0 <= ci[1]:
                for n in (name, name + "Lo", name + "Hi"):
                    if n in NOTE:
                        NOTE[n] += "; NOT SIGNIFICANT: 95 percent CI includes 0"
                        prov[n] += "; NOT SIGNIFICANT: 95 percent CI includes 0"
            else:
                sig_problems.append("%s flagged not significant but CI %s excludes 0" % (name, ci))

    for nm in ("ctrlSavingVsRestart", "ctrlSavingVsResume", "ctrlSavingVsRollback",
               "ctrlGainContam", "xstarRuleGainClean", "sameOutcomeModel", "sameOutcomeTool"):
        r5_put_ci(nm, nm)
    for nm in ("ctrlOfflineSucc", "frOfflineSucc", "srOfflineSucc"):
        r5_put_ci(nm, nm, scale=100.0)  # R5 stores fractions; paper states percent
    for nm in ("ctrlRegret", "gbrRegret"):
        r5_put(nm, g.get(nm), nm)
    for nm in ("nCtrlBlocks", "nCtrlGoals"):
        r5_put(nm, g.get(nm), nm)
    for nm in ("workCallsAcc", "workFracAcc", "workCallsAccClean", "workFracAccClean"):
        val, ci, sub = r5_get(nm)
        r5_put(nm, val, nm, scale=100.0, sub=sub)
    for nm in ("sameOutcomeModel", "sameOutcomeTool"):
        val, ci, sub = r5_get(nm)
        n = g.get(nm, {}).get("n") if isinstance(g.get(nm), dict) else None
        r5_put(nm + "N", n, nm + ".n", sub=sub)
    xs = g.get("xstar", {})
    for c, cam in CLS_CAMEL.items():  # four clean classes; silent class never emitted (O8)
        x = xs.get(c, {})
        ci = x.get("x_star_calls_ci") or [None, None]
        r5_put("xstar" + cam, x.get("x_star_calls"), "xstar.%s.x_star_calls" % c)
        r5_put("xstar" + cam + "Lo", ci[0], "xstar.%s.x_star_calls_ci[0]" % c)
        r5_put("xstar" + cam + "Hi", ci[1], "xstar.%s.x_star_calls_ci[1]" % c)
    law = g.get("energyLawLinear", {})
    for nm, key, f in (("eLawLinA", "linear_a", "%.1f"), ("eLawLinB", "linear_b", "%.4f")):
        ci = law.get(key + "_ci") or [None, None]
        r5_put(nm, law.get(key), "energyLawLinear." + key, f)
        r5_put(nm + "Lo", ci[0], "energyLawLinear.%s_ci[0]" % key, f)
        r5_put(nm + "Hi", ci[1], "energyLawLinear.%s_ci[1]" % key, f)
    r5_put("nLawCalls", law.get("n_calls"), "energyLawLinear.n_calls")
    r5_put("nLawTasks", law.get("n_tasks"), "energyLawLinear.n_tasks")
    if r5 is not None:
        put("rfiveCiMethod", g.get("ci_method", "unstated"), LABEL + "; key ci_method")
    for p in sig_problems:
        print("SIGNIFICANCE FLAG MISMATCH: " + p)

    # ---- impact (R8, Oct 21): TWh and homes per 1 percent adoption, from the offline saving against always restart ----
    IEA_TWH_2030 = 945.0  # iea2025energyai: data centre electricity projection for 2030, TWh
    KWH_HOME_MONTH = 865.0  # eia2025residential: average residential electricity per home and month, kWh
    s_rst = r5_get("ctrlSavingVsRestart")[0] if r5 is not None and r5_ok else None
    if isinstance(s_rst, (int, float)):
        twh = IEA_TWH_2030 * 0.01 * s_rst / 100.0
        put("impactTwhPerPct", "%.2f" % twh, "945 TWh (iea2025energyai) x 1 percent x ctrlSavingVsRestart %.3f percent / 100" % s_rst)
        put("impactHomesPerPct", fmt0(round(twh * 1e9 / (KWH_HOME_MONTH * 12), -3)),
            "impactTwhPerPct x 1e9 kWh / (865 kWh per home and month (eia2025residential) x 12), nearest thousand")
        NOTE["impactTwhPerPct"] = ("945 TWh in 2030 (iea2025energyai) x 1 percent adoption x ctrlSavingVsRestart %.1f percent "
                                   "(offline calibrated rule, R5 v2)" % s_rst)
        NOTE["impactHomesPerPct"] = "impactTwhPerPct / (865 kWh per home per month (eia2025residential) x 12), nearest thousand"
    else:
        for nm in ("impactTwhPerPct", "impactHomesPerPct"):
            put(nm, "\\pending{%s}" % nm, "pending: ctrlSavingVsRestart not available")

    # ---- E3 (online controller and baselines) ----
    e3l = sorted(glob.glob(os.path.join(art, "raf_e3", "raf_e3_items_raf_e3_split_*_ledger.jsonl")))
    E3ARMS = (("ctrl_beta", "CtrlBeta"), ("xstar_rule", "XstarRule"), ("token_rule", "TokenRule"),
              ("FR_warm", "FrWarm"), ("SR_warm", "SrWarm"), ("RB_cold", "RbCold"))
    E3FIXED = ("FR_warm", "SR_warm", "RB_cold")
    if e3l:
        best3, n_bad3, dec_ns, hist_ns = {}, 0, [], []
        for path in e3l:
            for l in open(path):
                d = json.loads(l)
                if not d.get("goal_id"):
                    continue
                p = d.get("plan", {})
                arm = p.get("arm") or d.get("arm")
                label = p.get("policy") if arm == "fixed" else arm  # fixed arms keep the option name
                if d.get("validity"):
                    n_bad3 += 1
                    continue
                key = (d.get("item_id"), arm, p.get("policy"))
                gid = int(d["goal_id"])
                if key not in best3 or gid > best3[key][0]:
                    best3[key] = (gid, (p.get("task"), p.get("cls"), p.get("point") or "", label), d)
        g3 = {gid: v for gid, v, _ in best3.values()}
        for gid, v, d in best3.values():
            if v[3] == "ctrl_beta":
                for dec in (d.get("decisions") or {}).values():
                    if dec.get("ns") is not None:
                        dec_ns.append(dec["ns"])
                    if dec.get("history_query_ns") is not None:
                        hist_ns.append(dec["history_query_ns"])
        c3 = cells(st, g3)
        src3 = "E3 split ledgers %s, goals %d to %d" % (",".join(os.path.basename(x) for x in e3l), min(g3), max(g3))
        put("nEthreeGoals", fmt0(len(g3)), src3 + ", valid latest records")
        put("nEthreeInvalid", str(n_bad3), src3 + ", records with a validity code")

        def arm_cells(lab):
            return [v for (c, pt, pol), v in c3.items() if pol == lab]

        rows, ach = [], {}
        for lab, cam in E3ARMS:
            vs = arm_cells(lab)
            if not vs:
                continue
            tag = ("E3 FIXED POLICY" if lab in E3FIXED else
                   "E3 RULE BASELINE" if lab in ("xstar_rule", "token_rule") else "ONLINE LEARNING CONTROLLER (E3)")
            k, n = sum(v["ok"] for v in vs), sum(v["n"] for v in vs)
            eb = sum(v["epg_board"] * v["n"] for v in vs)
            ach[lab] = eb / k if k else None
            put("ethree%sOk" % cam, "%d of %d" % (k, n), "%s; %s" % (tag, src3))
            put_wilson("ethree%sOk" % cam, k, n, tag + " E3 " + lab)
            put("ethree%sEpgJ" % cam, fmt0(eb / n), "%s; %s, board EpG" % (tag, src3))
            put("ethree%sAchJ" % cam, fmt0(ach[lab]) if ach[lab] else "none", "%s; %s, board per achieved" % (tag, src3))
            for nm in ("ethree%sOk" % cam, "ethree%sEpgJ" % cam, "ethree%sAchJ" % cam):
                NOTE[nm] = tag
        fixed_ok = [f for f in E3FIXED if ach.get(f)]
        bfix = min(fixed_ok, key=lambda f: ach[f]) if fixed_ok else None
        bsrc = "ONLINE LEARNING CONTROLLER (E3); paired bootstrap over tasks, %d resamples, seed %d, board per achieved" % (BOOT_REPS, BOOT_SEED)

        def save_vs(other):
            sit = [(c, pt) for (c, pt, pol) in c3 if pol == "ctrl_beta" and (c, pt, other) in c3]
            return boot_saving([(c3[(c, pt, "ctrl_beta")], c3[(c, pt, other)]) for c, pt in sit]), len(sit)

        for lab, cam in E3ARMS:
            if lab == "ctrl_beta" or lab not in ach or "ctrl_beta" not in ach:
                continue
            (p, lo, hi, nt, nu), ns = save_vs(lab)
            s = "%s; vs %s, %d situations, %d tasks, %d undefined draws" % (bsrc, lab, ns, nt, nu)
            for suf, val in (("", p), ("Lo", lo), ("Hi", hi)):
                put("ethreeCtrlVs%sSave%s" % (cam, suf), "%.1f" % val, s)
                NOTE["ethreeCtrlVs%sSave%s" % (cam, suf)] = "ONLINE LEARNING CONTROLLER (E3)"
        for lab, cam in E3ARMS:  # winner positive wording: how much the arm is below the controller
            if lab == "ctrl_beta" or lab not in ach or "ctrl_beta" not in ach:
                continue
            sit = [(c, pt) for (c, pt, pol) in c3 if pol == "ctrl_beta" and (c, pt, lab) in c3]
            p_, lo_, hi_, nt_, nu_ = boot_saving([(c3[(c, pt, lab)], c3[(c, pt, "ctrl_beta")]) for c, pt in sit])
            s_ = "%s; %s below the controller, %d situations, %d tasks" % (bsrc, lab, len(sit), nt_)
            for suf, val in (("", p_), ("Lo", lo_), ("Hi", hi_)):
                put("ethree%sVsCtrlSave%s" % (cam, suf), "%.1f" % val, s_)
        if bfix and "ctrl_beta" in ach:
            (p, lo, hi, nt, nu), ns = save_vs(bfix)
            s = "%s; vs best fixed arm %s, %d situations, %d tasks, %d undefined draws" % (bsrc, bfix, ns, nt, nu)
            for suf, val in (("", p), ("Lo", lo), ("Hi", hi)):
                put("ctrlSaving" + suf, "%.1f" % val, s)
                NOTE["ctrlSaving" + suf] = "ONLINE LEARNING CONTROLLER (E3)" + ("" if lo > 0 or hi < 0 else "; NOT SIGNIFICANT: 95 percent CI includes 0")
            put("ctrlBestFixed", bfix.replace("_", " "), s)
            if not (lo > 0 or hi < 0):
                for suf in ("", "Lo", "Hi"):
                    prov["ctrlSaving" + suf] += "; NOT SIGNIFICANT: 95 percent CI includes 0"

        # coordinator Oct 17 18:49: online controller aliases with explicit names
        def alias(new, old, extra=""):
            for suf in ("", "Lo", "Hi"):
                if old + suf in M:
                    put(new + suf, M[old + suf], prov[old + suf] + extra)
                    NOTE[new + suf] = NOTE.get(old + suf, "ONLINE LEARNING CONTROLLER (E3)")
        alias("ctrlOnlineSaveVsRestart", "ethreeCtrlVsFrWarmSave")
        alias("ctrlOnlineVsTokenRule", "ethreeCtrlVsTokenRuleSave")
        alias("ctrlOnlineVsBestFixed", "ctrlSaving", "; best fixed arm %s" % (bfix or "none"))

        # ---- ctrlOnlineRegret (coordinator Oct 21): cumulative, blocks of 20 controller goals in run order, vs RB_cold ----
        # option (b), coordinator Oct 21: the item set of boot_saving (situations shared by ctrl_beta and RB_cold,
        # tasks present in every one of them), so the last block equals ctrlOnlineVsBestFixed by construction
        sit_r = {(c, pt) for (c, pt, pol) in c3 if pol == "ctrl_beta" and (c, pt, "RB_cold") in c3}
        tasks_r = None
        for c, pt in sit_r:
            s_ = set(c3[(c, pt, "ctrl_beta")]["tasks"]) & set(c3[(c, pt, "RB_cold")]["tasks"])
            tasks_r = s_ if tasks_r is None else tasks_r & s_
        tasks_r = tasks_r or set()
        rbg = {key[0]: gid for key, (gid, v, d) in best3.items() if v[3] == "RB_cold"}
        ctg = sorted((gid, key[0], v) for key, (gid, v, d) in best3.items() if v[3] == "ctrl_beta")
        pr = [(gc, rbg[it]) for gc, it, v in ctg
              if it in rbg and norm_task(v[0]) in tasks_r and (v[1], v[2]) in sit_r]
        ec_ = er_ = oc_ = or_ = 0.0
        curve = []
        for i, (gc, gr) in enumerate(pr, 1):
            ec_ += st.energy(gc)[0]
            oc_ += st.success(gc)
            er_ += st.energy(gr)[0]
            or_ += st.success(gr)
            if i % 20 == 0 or i == len(pr):
                curve.append((i, 100 * (1 - (ec_ / oc_) / (er_ / or_)) if oc_ and or_ else None))
        rdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "figdata")
        os.makedirs(rdir, exist_ok=True)
        with open(os.path.join(rdir, "e3_regret.csv"), "w") as f:
            f.write("goals,regret_pct\n" + "".join("%d,%s\n" % (i, "" if v is None else "%.2f" % v) for i, v in curve))
        rsrc = ("ONLINE LEARNING CONTROLLER (E3); cumulative board J per successful goal, controller vs always roll back cold "
                "(RB_cold) on the same items, blocks of 20 controller goals in run order (goal id), %d pairs, item set of "
                "boot_saving for ctrlOnlineVsBestFixed (%d tasks), so the last block equals it by construction; negative = "
                "controller uses more board energy per successful goal (sign as ctrlOnlineVsBestFixed)" % (len(pr), len(tasks_r)))
        final = "%.1f" % curve[-1][1] if curve and curve[-1][1] is not None else None
        ref = M.get("ctrlOnlineVsBestFixed")
        if final is not None and bfix == "RB_cold" and final == ref:
            put("ctrlOnlineRegret", final, rsrc + "; final block equals ctrlOnlineVsBestFixed")
            NOTE["ctrlOnlineRegret"] = "E3, vs RB_cold, negative = controller above RB_cold"
            print("ctrlOnlineRegret %s equals ctrlOnlineVsBestFixed %s; %d blocks" % (final, ref, len(curve)))
        else:
            put("ctrlOnlineRegret", "\\pending{ctrlOnlineRegret}", "pending: check failed, " + rsrc)
            print("ALERT: ctrlOnlineRegret final %s vs ctrlOnlineVsBestFixed %s (best fixed %s); report to the coordinator"
                  % (final, ref, bfix))

        # ---- each deciding policy against always restart (R8, Oct 21): same boot_saving; F8 reads the same numbers ----
        sav_rows = []
        for lab, mac in (("ctrl_beta", "ctrlOnlineVsFr"), ("xstar_rule", "xstarRuleOnlineVsFr"), ("token_rule", "tokenRuleOnlineVsFr"),
                         ("SR_warm", "srWarmOnlineVsFr"), ("RB_cold", "rbColdOnlineVsFr")):  # fixed policies for F8 (R8 Oct 21)
            sit = [(c, pt) for (c, pt, pol) in c3 if pol == lab and (c, pt, "FR_warm") in c3]
            if not sit:
                for suf in ("", "Lo", "Hi"):
                    put(mac + suf, "\\pending{%s}" % (mac + suf), "pending: no %s cells with FR_warm" % lab)
                continue
            p_, lo_, hi_, nt_, nu_ = boot_saving([(c3[(c, pt, lab)], c3[(c, pt, "FR_warm")]) for c, pt in sit])
            flag = "" if (lo_ > 0 or hi_ < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
            s_ = "%s; %s below always restart (FR_warm), positive = %s lower energy per successful goal, %d situations, %d tasks, %d undefined draws%s" % (
                bsrc, lab, lab, len(sit), nt_, nu_, flag)
            for suf, val in (("", p_), ("Lo", lo_), ("Hi", hi_)):
                put(mac + suf, "%.1f" % val, s_)
                NOTE[mac + suf] = "E3, %s vs always restart, positive = %s lower%s" % (lab, lab, flag)
            vs = arm_cells(lab)
            sav_rows.append((lab, "%.1f" % p_, "%.1f" % lo_, "%.1f" % hi_, sum(v["ok"] for v in vs), sum(v["n"] for v in vs)))
        figd = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "figdata")
        os.makedirs(figd, exist_ok=True)
        with open(os.path.join(figd, "e3_savings.csv"), "w") as f:
            f.write("policy,saving,lo,hi,ok,n\n" + "".join("%s,%s,%s,%s,%d,%d\n" % r for r in sav_rows))

        def pctl(xs, q):
            xs = sorted(xs)
            return xs[int(round(q * (len(xs) - 1)))]
        if dec_ns:
            s = "ONLINE LEARNING CONTROLLER (E3); decisions.*.ns of ctrl_beta, %d decisions" % len(dec_ns)
            put("ctrlDecideMs", "%.1f" % (pctl(dec_ns, 0.5) / 1e6), s + ", median")
            put("ctrlDecideMsHi", "%.1f" % (pctl(dec_ns, 0.95) / 1e6), s + ", 95th percentile")
            put("nCtrlDecisions", str(len(dec_ns)), s)
        if hist_ns:
            s = "ONLINE LEARNING CONTROLLER (E3); decisions.*.history_query_ns of ctrl_beta, %d decisions" % len(hist_ns)
            put("ctrlHistoryMs", "%.1f" % (pctl(hist_ns, 0.5) / 1e6), s + ", median")
            put("ctrlHistoryMsHi", "%.1f" % (pctl(hist_ns, 0.95) / 1e6), s + ", 95th percentile")
        # ctrlDecideJ cut from the paper (R8, Oct 22); ctrlSplitMatch comes from paper_extra.py (R6 t1)

        for lab, cam in E3ARMS:
            if lab not in ach:
                continue
            vs = arm_cells(lab)
            k, n = sum(v["ok"] for v in vs), sum(v["n"] for v in vs)
            lo_w, hi_w = wilson(k, n)
            name = {"ctrl_beta": "EAR, learning mode", "xstar_rule": "threshold rule", "token_rule": "token rule (EAR)",
                    "FR_warm": "always restart", "SR_warm": "always resume", "RB_cold": "always roll back"}.get(lab, lab.replace("_", " "))
            a_txt = fmt0(ach[lab]) if ach[lab] else "none"
            if ach[lab] and ach[lab] == min(v for v in ach.values() if v):
                a_txt = "\\textbf{%s}" % a_txt  # bold marks the lowest arm, whichever it is
            rows.append("%s & %d/%d & %.0f to %.0f & %s & %s \\\\" % (
                name, k, n, 100 * lo_w, 100 * hi_w, fmt0(sum(v["epg_board"] * v["n"] for v in vs) / n), a_txt))
            if lab == "token_rule":
                rows.append("\\midrule")
        open(os.path.join(a.paper, "tables", "e3_table.tex"), "w").write(
            "% GENERATED by paper_numbers.py; do not edit by hand. ONLINE LEARNING CONTROLLER (E3) and fixed arms.\n"
            + "\n".join(rows) + "\n\\bottomrule\n")

    # ---- sensitivity: E3 headlines without flagged goals (coordinator rule) ----
    SENS = {"rule": "all goals is the paper value; ExclFlag drops light and heavy flagged goals, "
                    "ExclHeavy drops heavy only", "alerts": []}
    flags = {}
    if a.flags and os.path.exists(a.flags):
        for l in open(a.flags):
            parts = l.split("#")[0].split()
            if len(parts) >= 2:
                flags[int(parts[0])] = parts[1].lower()
        SENS["flag_file"] = "%s sha256 %s, %d goals (%d heavy)" % (
            a.flags, sha256(a.flags), len(flags), sum(1 for v in flags.values() if v == "heavy"))
        SENS["block_rule"] = "a block (item: task, class, point, all arms) is dropped if any of its goals is flagged"
    else:
        SENS["flag_file"] = "no flag file"
    SENS["flag_files"] = {f: sha256(f) for f in a.flag_files if os.path.exists(f)}
    if e3l and flags:
        def e3_head(gs):
            """Per arm per achieved, controller savings versus every arm and versus the best fixed arm."""
            cc = cells(st, gs)
            res = {"ach": {}, "save": {}}
            for lab, _ in E3ARMS:
                vs = [v for (c, pt, pol), v in cc.items() if pol == lab]
                k = sum(v["ok"] for v in vs)
                if vs:
                    res["ach"][lab] = sum(v["epg_board"] * v["n"] for v in vs) / k if k else None
            for lab, _ in E3ARMS:
                if lab == "ctrl_beta" or lab not in res["ach"] or "ctrl_beta" not in res["ach"]:
                    continue
                sit = [(c, pt) for (c, pt, pol) in cc if pol == "ctrl_beta" and (c, pt, lab) in cc]
                p, lo, hi, nt, nu = boot_saving([(cc[(c, pt, "ctrl_beta")], cc[(c, pt, lab)]) for c, pt in sit])
                res["save"][lab] = (p, lo, hi)
            fx = [f for f in E3FIXED if res["ach"].get(f)]
            res["best_fixed"] = min(fx, key=lambda f: res["ach"][f]) if fx else None
            return res

        item_of = {gid: key[0] for key, (gid, v, d) in best3.items()}  # goal -> item (block)
        bad_all = {item_of[g] for g in flags if g in item_of}
        bad_heavy = {item_of[g] for g, lab in flags.items() if lab == "heavy" and g in item_of}
        variants = {"all": g3,
                    "ExclFlag": {gid: v for gid, v in g3.items() if item_of.get(gid) not in bad_all},
                    "ExclHeavy": {gid: v for gid, v in g3.items() if item_of.get(gid) not in bad_heavy}}
        SENS["blocks_dropped"] = {"ExclFlag": len(bad_all), "ExclHeavy": len(bad_heavy)}
        heads = {name: e3_head(gs) for name, gs in variants.items()}
        SENS["e3_goals"] = {name: len(gs) for name, gs in variants.items()}
        base = heads["all"]
        for name in ("ExclFlag", "ExclHeavy"):
            h = heads[name]
            tag = "ONLINE LEARNING CONTROLLER (E3); sensitivity %s, %d goals" % (name, len(variants[name]))
            for lab, cam in E3ARMS:
                if h["ach"].get(lab):
                    put("ethree%sAchJ%s" % (cam, name), fmt0(h["ach"][lab]), tag)
            for lab, (p, lo, hi) in h["save"].items():
                cam = dict(E3ARMS)[lab]
                for suf, val in (("", p), ("Lo", lo), ("Hi", hi)):
                    put("ethreeCtrlVs%sSave%s%s" % (cam, suf, name), "%.1f" % val, tag)
                b = base["save"].get(lab)
                if not b:
                    continue
                if (p > 0) != (b[0] > 0):
                    SENS["alerts"].append("%s: controller vs %s changes sign (all %.1f, %s %.1f)" % (name, lab, b[0], name, p))
                if not (b[1] <= p <= b[2]):
                    SENS["alerts"].append("%s: controller vs %s leaves the all goals CI (all %.1f [%.1f, %.1f], %s %.1f)"
                                          % (name, lab, b[0], b[1], b[2], name, p))
            if h["best_fixed"] and h["best_fixed"] in h["save"]:
                p, lo, hi = h["save"][h["best_fixed"]]
                for suf, val in (("", p), ("Lo", lo), ("Hi", hi)):
                    put("ctrlSaving%s%s" % (suf, name), "%.1f" % val, tag + ", vs best fixed " + h["best_fixed"])
                if h["best_fixed"] != base["best_fixed"]:
                    SENS["alerts"].append("%s: best fixed arm changes from %s to %s" % (name, base["best_fixed"], h["best_fixed"]))
            SENS[name] = {"ach": h["ach"], "save": {k: list(v) for k, v in h["save"].items()},
                          "best_fixed": h["best_fixed"]}
        SENS["all"] = {"ach": base["ach"], "save": {k: list(v) for k, v in base["save"].items()},
                       "best_fixed": base["best_fixed"]}

        # ---- coordinator Oct 21: Sens aliases, and a sign or significance check of every E3 comparison in Section 6 ----
        fsha = sha256(a.flags)
        if not fsha.startswith("5d30a13c"):
            print("ALERT: flag file sha256 %s, coordinator named 5d30a13c" % fsha)
        fsrc = "flagged blocks dropped (block rule), flag file %s sha256 %s" % (os.path.basename(a.flags), fsha)
        for new, old in (("ctrlOnlineVsTokenRuleSens", "ethreeCtrlVsTokenRuleSave%sExclFlag"),
                         ("ctrlOnlineVsBestFixedSens", "ctrlSaving%sExclFlag")):
            for suf in ("", "Lo", "Hi"):
                if old % suf in M:
                    put(new + suf, M[old % suf], "ONLINE LEARNING CONTROLLER (E3), sensitivity; " + fsrc)
                    NOTE[new + suf] = "E3 sensitivity, negative = controller uses more board energy per successful goal; " + fsrc
        cx = cells(st, variants["ExclFlag"])

        def cmp3(cc, a_lab, b_lab, pt=None, cls=None):
            sit = [(c, p) for (c, p, pol) in cc if pol == a_lab and (c, p, b_lab) in cc
                   and (pt is None or p == pt) and (cls is None or c == cls)]
            if not sit:
                return None
            return boot_saving([(cc[(c, p, a_lab)], cc[(c, p, b_lab)]) for c, p in sit])[:3]

        checks = [("%s vs FR_warm" % l, l, "FR_warm", None, None)
                  for l in ("ctrl_beta", "xstar_rule", "token_rule", "SR_warm", "RB_cold")]
        checks += [("ctrl_beta vs %s" % l, "ctrl_beta", l, None, None) for l in ("xstar_rule", "token_rule", "SR_warm", "RB_cold")]
        checks += [("ctrl_beta vs token_rule %s %s" % (p, c), "ctrl_beta", "token_rule", p, c)
                   for p in ("early", "late") for c in ("tool_error", "json_parse")]
        nchg = nsign = 0
        SENSMAC = {"ctrl_beta vs FR_warm": "ctrlOnlineVsFrSens", "xstar_rule vs FR_warm": "xstarRuleOnlineVsFrSens",
                   "token_rule vs FR_warm": "tokenRuleOnlineVsFrSens", "SR_warm vs FR_warm": "srWarmOnlineVsFrSens",
                   "RB_cold vs FR_warm": "rbColdOnlineVsFrSens"}
        print("== E3 SENSITIVITY CHECK (all goals vs flagged blocks dropped)")
        for name, a_, b_, p_, c_ in checks:
            r0, r1 = cmp3(c3, a_, b_, p_, c_), cmp3(cx, a_, b_, p_, c_)
            if not r0 or not r1:
                print("  SENS %-36s missing" % name)
                continue
            s0 = "sig" if r0[1] > 0 or r0[2] < 0 else "n.s."
            s1 = "sig" if r1[1] > 0 or r1[2] < 0 else "n.s."
            ch = (r0[0] > 0) != (r1[0] > 0) or s0 != s1
            nchg += ch
            nsign += (r0[0] > 0) != (r1[0] > 0)
            if name in SENSMAC:
                mac = SENSMAC[name]
                flag = "" if s1 == "sig" else "; NOT SIGNIFICANT: 95 percent CI includes 0"
                for suf, val in (("", r1[0]), ("Lo", r1[1]), ("Hi", r1[2])):
                    put(mac + suf, "%.1f" % val, "E3 sensitivity, %s, positive = %s lower energy per successful goal than "
                        "always restart; %s%s" % (name, a_, fsrc, flag))
                    NOTE[mac + suf] = "E3 sensitivity, %s, positive = %s lower%s" % (name, a_, flag)
            print("  SENS %-36s all %.1f [%.1f, %.1f] %s   excl %.1f [%.1f, %.1f] %s%s"
                  % (name, r0[0], r0[1], r0[2], s0, r1[0], r1[1], r1[2], s1, "   CHANGED" if ch else ""))
        put("eThreeSensChanged", str(nchg), ("E3 comparisons in Section 6 that lose significance, no sign changes" if not nsign
            else "ALERT: %d sign changes among %d changed comparisons" % (nsign, nchg)) + ", when flagged blocks are dropped; " + fsrc)
        NOTE["eThreeSensChanged"] = "comparisons that lose significance, no sign changes" if not nsign else "SIGN CHANGES: %d" % nsign
    if e3l and flags and "ExclFlag" in SENS:
        n_blk = SENS["blocks_dropped"]["ExclFlag"]
        n_gl = SENS["e3_goals"]["all"] - SENS["e3_goals"]["ExclFlag"]
        e3_alerts = [x for x in SENS["alerts"]]
        txt = ("Dropping the %d flagged blocks (%d goals) changed the sign of no comparison and moved no point "
               "outside its all goals interval" % (n_blk, n_gl)) if not e3_alerts else \
              "\\pending{eThreeSensitivity: %d alerts}" % len(e3_alerts)
        put("eThreeSensitivityText", txt, "sensitivity, block rule, flag file %s" % SENS.get("flag_file"))
        put("eThreeBlocksDropped", str(n_blk), "E3 blocks dropped for shell overlap (block rule)")
        put("eThreeGoalsDropped", str(n_gl), "E3 goals in the dropped blocks")
        diffs = [abs(SENS["ExclFlag"]["save"][k][0] - SENS["all"]["save"][k][0])
                 for k in SENS["all"]["save"] if k in SENS["ExclFlag"]["save"]]
        if diffs:
            put("eThreeSensitivity", "%.1f" % max(diffs),
                "largest change in any E3 controller saving when flagged blocks are dropped, percentage points")
    # E2 sensitivity: block rule on the persistent escalating versus fixed headline
    if a.flags_e2 and os.path.exists(a.flags_e2) and e2l:
        f2 = set()
        for l in open(a.flags_e2):
            parts = l.split("#")[0].split()
            if parts:
                f2.add(int(parts[0]))
        items2 = {int(d["goal_id"]): it for (it, pol, arm), d in valid.items()}
        bad2 = {items2[g] for g in f2 if g in items2}
        g2x = {gid: v for gid, v in g2.items() if items2.get(gid) not in bad2}
        c2x = cells(st, g2x)
        prs_x = [(c2x[(c, p_, l2)], c2x[(c, p_, l)]) for (c, p_, l) in c2x for (cc, pp, l2) in c2x
                 if c.startswith("persistent") and l.endswith("@fixed") and cc == c and pp == p_
                 and l2.split("@")[0] == l.split("@")[0] and l2.split("@")[1] != "fixed"]
        SENS["e2"] = {"flag_file": "%s sha256 %s" % (a.flags_e2, sha256(a.flags_e2)),
                      "blocks_dropped": len(bad2), "goals_dropped": len(g2) - len(g2x)}
        if prs_x and "etwoEscVsFixedSave" in M:
            px, lox, hix, ntx, nux = boot_saving(prs_x)
            for suf, val in (("", px), ("Lo", lox), ("Hi", hix)):
                put("etwoEscVsFixedSave%sExclFlag" % suf, "%.1f" % val,
                    "E2 sensitivity, block rule, %d blocks dropped" % len(bad2))
            b_p, b_lo, b_hi = float(M["etwoEscVsFixedSave"]), float(M["etwoEscVsFixedSaveLo"]), float(M["etwoEscVsFixedSaveHi"])
            if (px > 0) != (b_p > 0):
                SENS["alerts"].append("E2 ExclFlag: escalating vs fixed changes sign (all %.1f, excl %.1f)" % (b_p, px))
            if not (b_lo <= px <= b_hi):
                SENS["alerts"].append("E2 ExclFlag: escalating vs fixed leaves the all goals CI (excl %.1f)" % px)
    for al in SENS["alerts"]:
        print("SENSITIVITY ALERT: " + al)

    # ---- reframing numbers (R8, Oct 22): totals, hindsight, price of a default, regret, counterfactual ----
    import reframe_numbers
    reframe_numbers.add(st, art, put, NOTE, a.paper, a.pilot_board_baseline, r5)

    # ---- write ----
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    head = "%% GENERATED by paper_numbers.py at %s from %s; do not edit by hand.\n" % (stamp, db)
    body = "".join("\\providecommand{\\%s}{}\\renewcommand{\\%s}{%s}%s\n"
                   % (k, k, re.sub(r"(?<!\\)([%&#])", r"\\\1", str(v)),  # escape % & # in values
                      (" % " + NOTE[k]) if k in NOTE else "") for k, v in sorted(M.items()))
    open(os.path.join(a.paper, "numbers_auto.tex"), "w").write(head + body)
    commit = subprocess.run(["git", "-C", a.paper, "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or "nogit"
    json.dump({"generated": stamp, "store": db, "paper_commit": commit, "r5": r5_note,
               "sensitivity": SENS, "values": M, "provenance": prov},
              open(os.path.join(a.paper, "numbers_auto.json"), "w"), indent=1)
    print("wrote %d macros, pilot table%s" % (len(M), ", E1 table" if led else ""))
    for k in sorted(M):
        print("  %-18s %s" % (k, M[k]))


if __name__ == "__main__":
    main()
