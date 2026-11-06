#!/usr/bin/env python3
"""reframe_numbers.py: totals, best fixed policy in hindsight, price of a wrong default, regret against the cell
oracle, controller against hindsight, and the counterfactual of the 44 changed decisions (R8 request, Oct 22).

Called from paper_numbers.py (same store, same ledgers, same macro file):
  reframe_numbers.add(st, art, put, NOTE, paper_dir, pilot_board_baseline, r5)
Definitions (all board energy):
  energy per successful goal of a policy = sum of its goal energies / number of its correct goals, pooled over cells
  cell = failure type x failure point; cell oracle = the option with the lowest energy per successful goal in that
         cell, chosen on the same data (a bound, not a policy anyone could run)
  price of a default (= regret against the cell oracle) = percent above the pooled oracle; extra kWh = (J of the
         policy minus J of the oracle) x correct goals of the policy
  totals: gross board energy = mean DC_INPUT power x duration over every run; net = minus the run's idle power
Writes tables/winners_table.tex and tables/regret_table.tex (rows only, ending with \\bottomrule).
"""
import collections
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paper_numbers as pn  # noqa: E402

DATA = os.path.join(os.path.dirname(HERE), "data")
OPT8 = ("FR_warm", "FR_cold", "SR_warm", "SR_cold", "RB_warm", "RB_cold", "SG_warm", "SG_cold")
OPT3 = ("FR_warm", "SR_warm", "RB_cold")
NAME = {"FR_warm": "restart warm", "FR_cold": "restart cold", "SR_warm": "resume warm", "SR_cold": "resume cold",
        "RB_warm": "roll back warm", "RB_cold": "roll back cold", "SG_warm": "grounded warm",
        "SG_cold": "grounded cold", "ctrl_beta": "online controller", "xstar_rule": "threshold rule",
        "token_rule": "token rule"}
# (scope macro name, model, study folder patterns); smoke ledgers are never read
STUDIES = (
    ("Qwen", "Qwen3 30B", ["raf_e1/raf_e1_run_ledger.jsonl", "raf_e1/*rerun*ledger*.jsonl"]),
    ("Qwen", "Qwen3 30B", ["raf_e1b/raf_e1b_run_ledger.jsonl"]),
    ("Qwen", "Qwen3 30B", ["raf_e2/raf_e2_run_ledger.jsonl"]),
    ("Qwen", "Qwen3 30B", ["raf_e2b_r2/raf_e2b_r2_items_raf_e2b_r2_items_ledger.jsonl"]),
    ("Qwen", "Qwen3 30B", ["raf_e3/raf_e3_items_raf_e3_split_*_ledger.jsonl"]),
    ("Qwen", "Qwen3 30B", ["raf_mid/*ledger*.jsonl"]),
    ("Qwen", "Qwen3 30B", ["raf_samp_s1/raf_samp_s1_run_ledger.jsonl"]),
    ("Qwen", "Qwen3 30B", ["raf_samp_s2/raf_samp_s2_run_ledger.jsonl"]),
    ("Qwen", "Qwen3 30B", ["raf_samp_s3/raf_samp_s3_run_ledger.jsonl"]),
    ("Qwen", "Qwen3 30B", ["raf_sweep_qwen/raf_sweep_qwen_run_ledger.jsonl"]),
    ("Mistral", "Mistral Small 3.2 24B", ["raf_m3/raf_m3_run_ledger.jsonl"]),
    ("Mistral", "Mistral Small 3.2 24B", ["raf_m3_b0/raf_m3_b0_run_ledger.jsonl"]),
    ("Gptoss", "gpt-oss 20B", ["raf_m4/raf_m4_run_ledger.jsonl"]),
    ("Gptoss", "gpt-oss 20B", ["raf_m4_b0/raf_m4_b0_run_ledger.jsonl"]),
    ("Gptoss", "gpt-oss 20B", ["raf_sweep_m4/raf_sweep_m4_run_ledger.jsonl"]),
)


def paths(art, pats):
    return sorted({p for pat in pats for p in glob.glob(os.path.join(art, pat)) if "smoke" not in os.path.basename(p)})


def records(ps):
    out = []
    for p in ps:
        out += [json.loads(l) for l in open(p) if l.strip()]
    return [d for d in out if d.get("goal_id")]


def latest_valid(recs):
    """Latest valid record per (item, policy, arm): the paper's rule."""
    best = {}
    for d in recs:
        if d.get("validity"):
            continue
        p = d.get("plan", {})
        k = (d.get("item_id"), p.get("policy"), p.get("arm") or d.get("arm"))
        if k not in best or int(d["goal_id"]) > int(best[k]["goal_id"]):
            best[k] = d
    return list(best.values())


def goal_stats(st, gid, tool_col, board_bid=None):
    """(model calls, tool calls, gross board J, net board J, seconds) of one goal, all attempts."""
    c = st.c
    calls = tools = gross = net = sec = 0.0
    for run, dur, bid in c.execute("SELECT ga.run_id, r.duration_ns, r.baseline_id FROM goal_attempt ga "
                                   "JOIN runs r ON r.run_id = ga.run_id WHERE ga.goal_id = ?", (gid,)).fetchall():
        s = (dur or 0) / 1e9
        mw = c.execute("SELECT AVG(energy_uj) FROM energy_sample_domains WHERE run_id = ? AND domain_id = 28",
                       (run,)).fetchone()[0] or 0.0
        idle = st.idle_w(board_bid or bid).get("DC_INPUT", 0.0)
        gross += mw / 1000.0 * s
        net += (mw / 1000.0 - idle) * s
        sec += s
        calls += c.execute("SELECT COUNT(*) FROM llm_interactions WHERE run_id = ?", (run,)).fetchone()[0]
        if tool_col:
            tools += c.execute("SELECT COALESCE(%s, 0) FROM runs WHERE run_id = ?" % tool_col, (run,)).fetchone()[0]
    return calls, tools, gross, net, sec


def totals(st, art, put, NOTE, pilot_bid):
    """Item 1: goals run (all, valid), tasks, model and tool calls, kWh (gross, net), hours; per model and all."""
    tool_col = "tool_calls" if "tool_calls" in [r[1] for r in st.c.execute("PRAGMA table_info(runs)")] else None
    acc = collections.defaultdict(lambda: {"all": set(), "valid": set(), "tasks": set(), "v": [0.0] * 5})
    pilot_csv = os.path.join(art, "raf_pilot", "s7_goals.csv")
    scopes = []
    if os.path.exists(pilot_csv):
        for r in csv.DictReader(open(pilot_csv)):
            g = int(r["goal_id"])
            for sc in ("QwenSmall", "All"):
                acc[sc]["all"].add(g); acc[sc]["valid"].add(g); acc[sc]["tasks"].add(pn.norm_task(r["task"]))
        scopes.append(("QwenSmall", sorted(acc["QwenSmall"]["valid"]), pilot_bid))
    for sc, model, pats in STUDIES:
        recs = records(paths(art, pats))
        if not recs:
            print("reframe totals: no ledger for %s" % pats)
            continue
        valid = latest_valid(recs)
        if sc == "Gptoss" and "raf_m4/" in pats[0]:
            valid = [d for d in valid if pn.norm_task((d.get("plan") or {}).get("task")) != "multi_turn_base_105"]
        for s in (sc, "All"):
            acc[s]["all"] |= {int(d["goal_id"]) for d in recs}
            acc[s]["valid"] |= {int(d["goal_id"]) for d in valid}
            acc[s]["tasks"] |= {pn.norm_task((d.get("plan") or {}).get("task")) for d in valid}
    for sc in ("QwenSmall", "Qwen", "Mistral", "Gptoss"):
        bid = pilot_bid if sc == "QwenSmall" else None
        for g in sorted(acc[sc]["valid"]):
            vals = goal_stats(st, g, tool_col, bid)
            for s in (sc, "All"):
                acc[s]["v"] = [x + y for x, y in zip(acc[s]["v"], vals)]
    src = ("frozen store; every paper study ledger (smoke excluded); valid = latest valid per (item, policy, arm), "
           "gpt-oss task 105 removed; energy and time over valid goals, all attempts; gross = mean DC_INPUT x duration, "
           "net = minus the run's idle DC_INPUT; pilot (Qwen3 4B) uses the pilot board baseline")
    for sc in ("All", "QwenSmall", "Qwen", "Mistral", "Gptoss"):
        a = acc[sc]
        calls, tools, gross, net, sec = a["v"]
        for nm, val in (("GoalsRun", pn.fmt0(len(a["all"]))), ("GoalsValid", pn.fmt0(len(a["valid"]))),
                        ("Tasks", str(len(a["tasks"]))), ("ModelCalls", pn.fmt0(calls)), ("ToolCalls", pn.fmt0(tools)),
                        ("KwhGross", "%.1f" % (gross / 3.6e6)), ("KwhNet", "%.1f" % (net / 3.6e6)),
                        ("Hours", "%.0f" % (sec / 3600))):
            put("tot%s%s" % (sc, nm), val, src + ", scope " + sc)
            NOTE["tot%s%s" % (sc, nm)] = "TOTALS, scope %s (QwenSmall = pilot Qwen3 4B)" % sc
    return len(acc["All"]["all"]), len(acc["All"]["valid"])


def pooled(cc, opt, cells_):
    e = ok = n = 0.0
    for c in cells_:
        v = cc.get(c + (opt,))
        if v:
            e += v["epg_board"] * v["n"]; ok += v["ok"]; n += v["n"]
    return (e / ok if ok else None), ok, n


def winner(cc, c, opts):
    vs = {o: cc[c + (o,)]["ach_board"] for o in opts if cc.get(c + (o,)) and cc[c + (o,)]["ach_board"]}
    return min(vs, key=vs.get) if vs else None


def oracle(cc, cells_, opts):
    """Pooled energy per successful goal of the per cell best option."""
    e = ok = 0.0
    for c in cells_:
        w = winner(cc, c, opts)
        if w:
            v = cc[c + (w,)]
            e += v["epg_board"] * v["n"]; ok += v["ok"]
    return e / ok if ok else None


def hindsight(st, art, put, NOTE, paper_dir, r5):
    """Items 2, 3, 4 (offline part) and 5."""
    e1 = pn.load_ledger(paths(art, ["raf_e1/raf_e1_run_ledger.jsonl", "raf_e1/*rerun*ledger*.jsonl"]))
    e1b = pn.load_ledger(paths(art, ["raf_e1b/raf_e1b_run_ledger.jsonl"]))
    m3 = pn.load_ledger(paths(art, ["raf_m3/raf_m3_run_ledger.jsonl"]))
    m4 = {g: v for g, v in pn.load_ledger(paths(art, ["raf_m4/raf_m4_run_ledger.jsonl"])).items()
          if pn.norm_task(v[0]) != "multi_turn_base_105"}
    qwen = {g: v for g, v in list(e1.items()) + list(e1b.items()) if v[3] in OPT8}
    models = (("Qwen", "Qwen3 30B", pn.cells(st, qwen), OPT8), ("Mistral", "Mistral Small 3.2 24B", pn.cells(st, m3), OPT3),
              ("Gptoss", "gpt-oss 20B", pn.cells(st, m4), OPT3))
    cells_ = [(c, p) for c, p in pn.SITUATIONS]
    src = ("E1 and E1b (Qwen3 30B, 8 options), raf_m3 (Mistral), raf_m4 without task 105 (gpt-oss); latest valid per "
           "(item, policy); board J per successful goal; cell oracle chosen on the same data (a bound)")
    win3 = {}
    regret = collections.defaultdict(dict)
    for key, label, cc, opts in models:
        jor = oracle(cc, cells_, opts)
        best = min((o for o in opts if pooled(cc, o, cells_)[0]), key=lambda o: pooled(cc, o, cells_)[0])
        put("hind%sBestFixed" % key, NAME[best], src + ", %s, lowest pooled energy per successful goal" % label)
        put("hind%sOracleJ" % key, pn.fmt0(jor), src + ", %s, pooled cell oracle" % label)
        for o in opts:
            j, ok, n = pooled(cc, o, cells_)
            if not j:
                continue
            pct = 100 * (j / jor - 1)
            kwh = (j - jor) * ok / 3.6e6
            regret[o][key] = pct
            cam = o.replace("_warm", "Warm").replace("_cold", "Cold").replace("FR", "Fr").replace("SR", "Sr") \
                   .replace("RB", "Rb").replace("SG", "Sg")
            put("price%s%s" % (key, cam), "%.1f" % pct, src + ", %s, %s, percent above the cell oracle" % (label, o))
            put("price%s%sWh" % (key, cam), "%.0f" % (kwh * 1000), src + ", %s, %s, extra Wh over its %d correct goals"
                % (label, o, ok))
            NOTE["price%s%s" % (key, cam)] = "price of a wrong default (= regret against the cell oracle), %s" % label
        win3[key] = {c: winner(cc, c, OPT3) for c in cells_}
        if key == "Qwen":
            win3["Qwen8"] = {c: winner(cc, c, OPT8) for c in cells_}
    same = sum(1 for c in cells_ if win3["Qwen"][c] and win3["Qwen"][c] == win3["Mistral"][c] == win3["Gptoss"][c])
    put("winSameAcrossModels", "%d of %d" % (same, len(cells_)), src + ", cells where restart warm, resume warm and "
        "roll back cold rank the same winner on all three models")
    rows = []
    for c in cells_:
        rows.append("%s & %s & %s & %s & %s & %s \\\\" % (pn.CLS_NAME[c[0]], c[1], *(
            NAME.get(win3[k][c], "none") for k in ("Qwen8", "Qwen", "Mistral", "Gptoss"))))
        if c == cells_[3]:
            rows.append("\\midrule")
    open(os.path.join(paper_dir, "tables", "winners_table.tex"), "w").write(
        "% GENERATED by reframe_numbers.py; do not edit by hand. Lowest board J per successful goal per cell. "
        "Columns: type, point, Qwen3 30B (8 options), Qwen3 30B (3 shared options), Mistral, gpt-oss.\n"
        + "\n".join(rows) + "\n\\bottomrule\n")

    # item 4, offline: R5's rule against the best and the worst fixed policy in hindsight, per model (copied)
    files = (("Qwen", r5, ""), ("Mistral", json.load(open(os.path.join(DATA, "r5m3", "r5_numbers.json"))), "m3"),
             ("Gptoss", json.load(open(os.path.join(DATA, "r5m4", "r5_numbers.json"))), "m4"))
    worst = {}  # model -> (offline rule saving against its worst fixed policy, that policy)
    for key, g, px in files:
        sv = {}
        for fx in ("Restart", "Resume", "Rollback"):
            v = g.get(px + ("CtrlSavingVs" if px else "ctrlSavingVs") + fx)
            if isinstance(v, dict):
                sv[fx] = (v.get("value"), v.get("ci"))
            elif v is not None:
                sv[fx] = (v, g.get(("ctrlSavingVs" + fx) + "CI"))
        sv = {k: v for k, v in sv.items() if v[0] is not None and v[1]}
        if not sv:
            continue
        for tag, pick in (("Best", min), ("Worst", max)):
            fx = pick(sv, key=lambda k: sv[k][0])
            val, ci = sv[fx]
            flag = "" if (ci[0] > 0 or ci[1] < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
            s = "R5 offline calibrated rule, %s, saving against always %s, the %s fixed policy in hindsight (R5 file, copied)%s" % (
                key, fx.lower(), tag.lower(), flag)
            for suf, x in (("", val), ("Lo", ci[0]), ("Hi", ci[1])):
                put("hind%sCtrlVs%s%s" % (key, tag, suf), "%.1f" % x, s)
                NOTE["hind%sCtrlVs%s%s" % (key, tag, suf)] = "offline rule vs %s fixed in hindsight%s" % (tag.lower(), flag)
            put("hind%sCtrlVs%sPolicy" % (key, tag), "always " + fx.lower(), s)
            if tag == "Worst":
                worst[key] = (val, fx)
    if worst:
        for nm, pick in (("hindCtrlVsWorstMin", min), ("hindCtrlVsWorstMax", max)):
            k = pick(worst, key=lambda m: worst[m][0])
            put(nm, "%.1f" % worst[k][0], "R5 offline calibrated rule against the worst fixed policy in hindsight, %s "
                "across models: %s, against always %s" % ("lowest" if pick is min else "highest", k, worst[k][1].lower()))
            NOTE[nm] = "offline rule vs worst default, %s (always %s)" % (k, worst[k][1].lower())
    return regret


def online(st, art, put, NOTE, regret):
    """Item 4 (online part) and the online column of item 5: six E3 policies, cell oracle over the fixed arms."""
    best = {}
    for p in paths(art, ["raf_e3/raf_e3_items_raf_e3_split_*_ledger.jsonl"]):
        for l in open(p):
            d = json.loads(l) if l.strip() else {}
            if not d.get("goal_id") or d.get("validity"):
                continue
            pl = d.get("plan", {})
            arm = pl.get("arm") or d.get("arm")
            lab = pl.get("policy") if arm == "fixed" else arm
            k = (d.get("item_id"), arm, pl.get("policy"))
            if k not in best or int(d["goal_id"]) > best[k][0]:
                best[k] = (int(d["goal_id"]), (pl.get("task"), pl.get("cls"), pl.get("point") or "", lab), d.get("item_id"))
    g3 = {g: v for g, v, _ in best.values()}
    cc = pn.cells(st, g3)
    cells_ = sorted({(c, p) for (c, p, _) in cc})
    jor = oracle(cc, cells_, OPT3)
    pol = ("ctrl_beta", "xstar_rule", "token_rule") + OPT3
    jj = {o: pooled(cc, o, cells_) for o in pol}
    for o in pol:
        if jj[o][0]:
            regret[o]["Online"] = 100 * (jj[o][0] / jor - 1)
    fixed = [o for o in OPT3 if jj[o][0]]
    src = "E3 split ledgers, latest valid per (item, arm, policy), board J per successful goal, paired bootstrap over tasks"
    for tag, pick in (("Best", min), ("Worst", max)):
        fx = pick(fixed, key=lambda o: jj[o][0])
        sit = [c for c in cells_ if cc.get(c + ("ctrl_beta",)) and cc.get(c + (fx,))]
        p, lo, hi, nt, nu = pn.boot_saving([(cc[c + ("ctrl_beta",)], cc[c + (fx,)]) for c in sit])
        flag = "" if (lo > 0 or hi < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
        s = "%s; controller vs %s (%s fixed in hindsight), positive = controller lower, %d tasks%s" % (src, fx, tag.lower(), nt, flag)
        for suf, x in (("", p), ("Lo", lo), ("Hi", hi)):
            put("hindOnlineCtrlVs%s%s" % (tag, suf), "%.1f" % x, s)
            NOTE["hindOnlineCtrlVs%s%s" % (tag, suf)] = "online controller vs %s fixed in hindsight%s" % (tag.lower(), flag)
        put("hindOnlineCtrlVs%sPolicy" % tag, NAME[fx], s)
        put("hindOnlineCtrlVs%sWh" % tag, "%.0f" % ((jj["ctrl_beta"][0] - jj[fx][0]) * jj["ctrl_beta"][1] / 3600.0),
            s + "; Wh = (controller J minus %s J) x controller correct goals; positive = controller used more" % fx)
    return best, cc


def regret_table(paper_dir, regret, put):
    cols = ("Qwen", "Mistral", "Gptoss", "Online")
    head = ("% GENERATED by reframe_numbers.py; do not edit by hand. Percent above the per cell oracle (board J per "
            "successful goal, cell = failure type x point). Oracle option set per column: Qwen3 30B the 8 options of E1 "
            "and E1b (FR, SR, RB, SG, warm and cold); Mistral and gpt-oss their 3 options (FR warm, SR warm, RB cold); "
            "online study its 3 fixed arms. The deciding policies ran only in the online study. A dash: not run. "
            "No \\bottomrule: the table adds it.")
    deciders = ("ctrl_beta", "xstar_rule", "token_rule")
    for fn, opts in (("regret_table.tex", OPT3), ("regret_table_full.tex", OPT8)):  # Section 6, appendix (R8)
        rows = []
        for o in opts + deciders:
            if o not in regret:
                continue
            rows.append("%s & %s \\\\" % (NAME[o], " & ".join(("%.1f" % regret[o][c]) if c in regret[o] else "--"
                                                            for c in cols)))
            if o == opts[-1]:
                rows.append("\\midrule")
        open(os.path.join(paper_dir, "tables", fn), "w").write(head + "\n" + "\n".join(rows) + "\n")
    pr = [(regret[o][m], o, m) for o in OPT8 for m in ("Qwen", "Mistral", "Gptoss") if m in regret.get(o, {})]
    model = {"Qwen": "Qwen3 30B", "Mistral": "Mistral Small 3.2 24B", "Gptoss": "gpt-oss 20B"}
    for nm, (v, o, m) in (("priceMinAll", min(pr)), ("priceMaxAll", max(pr))):
        put(nm, "%.1f" % v, "price of a wrong default (percent above the per cell oracle), %s across the three models "
            "and every option each ran: %s, %s" % ("lowest" if nm == "priceMinAll" else "highest", NAME[o], model[m]))
    for o in ("ctrl_beta", "xstar_rule", "token_rule"):
        if "Online" in regret.get(o, {}):
            nm = {"ctrl_beta": "regretOnlineCtrl", "xstar_rule": "regretOnlineXstar", "token_rule": "regretOnlineToken"}[o]
            put(nm, "%.1f" % regret[o]["Online"], "E3, percent above the cell oracle over the three fixed arms")


def counterfactual(st, put, NOTE, best):
    """Item 7: the 44 changed decisions, with the recorded outcome of the alternative option on the same item."""
    tsv = os.path.join(DATA, "r6", "r7_changed_44.tsv")
    if not os.path.exists(tsv):
        return
    rows = list(csv.DictReader(open(tsv), delimiter="\t"))
    item_of = {g: it for (it, arm, pol), (g, v, _) in best.items() if v[3] == "ctrl_beta"}
    fixed_goal = {(it, v[3]): g for (it, arm, pol), (g, v, _) in best.items() if arm == "fixed"}
    e_c = ok_c = e_a = ok_a = 0.0
    cov, miss = 0, collections.Counter()
    for r in rows:
        g = int(r["goal_id"])
        alt = fixed_goal.get((item_of.get(g), r["with_export_tokens"]))
        if alt is None:
            miss[r["with_export_tokens"]] += 1
            continue
        cov += 1
        e_c += st.energy(g)[0]; ok_c += st.success(g)
        e_a += st.energy(alt)[0]; ok_a += st.success(alt)
    src = ("r7_changed_44.tsv (sha256 6a1c8517); alternative outcome = the fixed arm goal of the same E3 item running "
           "that option; no outcome for: " + (", ".join("%s %d" % kv for kv in sorted(miss.items())) or "none"))
    put("ctxCfCovered", "%d of %d" % (cov, len(rows)), src)
    if cov and ok_c and ok_a:
        jc, ja = e_c / ok_c, e_a / ok_a
        put("ctxCfActualJ", pn.fmt0(jc), src + ", controller as run, board J per successful goal")
        put("ctxCfAltJ", pn.fmt0(ja), src + ", alternative option, board J per successful goal")
        put("ctxCfPct", "%.1f" % (100 * (1 - ja / jc)), src + ", positive = alternative lower")
        for k in ("ctxCfActualJ", "ctxCfAltJ", "ctxCfPct"):
            NOTE[k] = "counterfactual of the changed decisions with a recorded outcome only (%d of %d)" % (cov, len(rows))
    print("reframe counterfactual: %d of %d covered; missing %s" % (cov, len(rows), dict(miss)))


QW, MI, GP = "Qwen3 30B A3B Instruct 2507", "Mistral Small 3.2 24B Instruct 2506", "gpt-oss 20B"
STUDY_CODE = {"Pilot (Qwen3 4B)": "P", "Main study restart and resume": "M1", "Main study roll back and grounded resume": "M2",
              "First contaminating study": "C1", "Second contaminating study": "C2", "Online study": "O",
              "Middle positions": "Mid", "Second model": "Mis", "Third model": "Gpt", "Sampling": "T"}


def study_code(name, model):
    """R8's short study codes (Oct 23); the context sweep is Sw1 (Qwen3 30B) or Sw2 (gpt-oss 20B)."""
    if name == "Context sweep":
        return "Sw1" if model == QW else "Sw2"
    return STUDY_CODE[name]
AUDIT = (  # paper name, model (as in provenance_table), ledger patterns (counted one by one, as totals() does)
    ("Main study restart and resume", QW, [["raf_e1/raf_e1_run_ledger.jsonl", "raf_e1/*rerun*ledger*.jsonl"]]),  # pooled: reruns replace
    ("Main study roll back and grounded resume", QW, ["raf_e1b/raf_e1b_run_ledger.jsonl"]),
    ("First contaminating study", QW, ["raf_e2/raf_e2_run_ledger.jsonl"]),
    ("Second contaminating study", QW, ["raf_e2b_r2/raf_e2b_r2_items_raf_e2b_r2_items_ledger.jsonl"]),
    ("Online study", QW, ["raf_e3/raf_e3_items_raf_e3_split_*_ledger.jsonl"]),
    ("Middle positions", QW, ["raf_mid/*ledger*.jsonl"]),
    ("Second model", MI, ["raf_m3/raf_m3_run_ledger.jsonl", "raf_m3_b0/raf_m3_b0_run_ledger.jsonl"]),
    ("Third model", GP, ["raf_m4/raf_m4_run_ledger.jsonl", "raf_m4_b0/raf_m4_b0_run_ledger.jsonl"]),
    ("Sampling", QW, ["raf_samp_s1/raf_samp_s1_run_ledger.jsonl", "raf_samp_s2/raf_samp_s2_run_ledger.jsonl",
                      "raf_samp_s3/raf_samp_s3_run_ledger.jsonl"]),
    ("Context sweep", GP, ["raf_sweep_m4/raf_sweep_m4_run_ledger.jsonl"]),
    ("Context sweep", QW, ["raf_sweep_qwen/raf_sweep_qwen_run_ledger.jsonl"]),
)


def audit(art, put, paper_dir, tot_run, tot_valid):
    """Count audit (R8, Oct 23): per study tasks, goals run, valid, recovery, without failures; totals checked."""
    lines, all_tasks = [], set()
    pc = os.path.join(art, "raf_pilot", "s7_goals.csv")
    if os.path.exists(pc):
        pr = list(csv.DictReader(open(pc)))
        t = {pn.norm_task(r["task"]) for r in pr}
        b0 = sum(1 for r in pr if r["policy"] == "B0")
        lines.append(("Pilot (Qwen3 4B)", None, t, len(pr), len(pr), len(pr) - b0, b0))
    for name, model, pats in AUDIT:
        run = valid = rec = b0 = 0
        t = set()
        for pat in pats:
            recs = records(paths(art, pat if isinstance(pat, list) else [pat]))  # a nested list is pooled first
            v = latest_valid(recs)
            if "raf_m4/" in str(pat):  # the paper removes task 105 from the third model's recovery study
                v = [d for d in v if pn.norm_task((d.get("plan") or {}).get("task")) != "multi_turn_base_105"]
            run += len({int(d["goal_id"]) for d in recs})
            valid += len(v)
            b = sum(1 for d in v if (d.get("plan") or {}).get("policy") == "B0")
            b0 += b
            rec += len(v) - b
            t |= {pn.norm_task((d.get("plan") or {}).get("task")) for d in v}
        lines.append((name, model, t, run, valid, rec, b0))
    counts, rows = {}, []
    sums = [0, 0, 0, 0]
    for name, model, t, run, valid, rec, b0 in lines:
        all_tasks |= t
        sums = [x + y for x, y in zip(sums, (run, valid, rec, b0))]
        code = study_code(name, model)
        rows.append("%s & %d & %s & %s & %s & %s \\\\" % (code, len(t), pn.fmt0(run), pn.fmt0(valid), pn.fmt0(rec), pn.fmt0(b0)))
        counts[code] = {"tasks": len(t), "valid": valid}
    rows.append("\\midrule")
    rows.append("Total & %d & %s & %s & %s & %s \\\\" % (len(all_tasks), *(pn.fmt0(x) for x in sums)))
    ok = sums[0] == tot_run and sums[1] == tot_valid
    if not ok:
        print("ALERT: count audit totals %d run, %d valid differ from totAllGoalsRun %d, totAllGoalsValid %d"
              % (sums[0], sums[1], tot_run, tot_valid))
    put("auditTotalsMatch", "true" if ok else "false", "count audit: totals row equals totAllGoalsRun and totAllGoalsValid")
    open(os.path.join(paper_dir, "tables", "audit_table.tex"), "w").write(
        "% GENERATED by reframe_numbers.py; do not edit by hand. Count audit from the frozen ledgers: tasks, goals run, "
        "valid goals (latest valid per item, policy, arm), recovery goals, runs without failures; totals equal "
        "totAllGoalsRun and totAllGoalsValid. No \\bottomrule: the table adds it.\n" + "\n".join(rows) + "\n")
    os.makedirs(os.path.join(DATA, "figdata"), exist_ok=True)
    json.dump(counts, open(os.path.join(DATA, "figdata", "study_counts.json"), "w"), indent=1)


EAR_LABEL = {"FR_warm": "always restart", "SR_warm": "always resume", "RB_cold": "always roll back",
             "ctrl_beta": "EAR, learning mode", "xstar_rule": "threshold rule", "token_rule": "EAR"}
EAR_CAM = {"FR_warm": "FrWarm", "SR_warm": "SrWarm", "RB_cold": "RbCold", "ctrl_beta": "Ctrl",
           "xstar_rule": "Xstar", "token_rule": "Ear"}


def ear(cc, put, NOTE, paper_dir):
    """EAR in E3 = the token_rule arm (coordinator Oct 22). Savings, success per arm, F8 points, ear_table.tex."""
    cells_ = sorted({(c, p) for (c, p, _) in cc})
    src = ("E3 split ledgers, latest valid per (item, arm, policy); EAR = the token_rule arm (coordinator Oct 22); "
           "board J per successful goal; paired bootstrap over tasks, %d resamples, seed %d" % (pn.BOOT_REPS, pn.BOOT_SEED))
    sav = {}
    for o in ("FR_warm", "SR_warm", "RB_cold", "ctrl_beta", "xstar_rule"):
        sit = [c for c in cells_ if cc.get(c + ("token_rule",)) and cc.get(c + (o,))]
        sav[o] = pn.boot_saving([(cc[c + ("token_rule",)], cc[c + (o,)]) for c in sit])
    for nm, o in (("earSaveVsRestart", "FR_warm"), ("earVsBestFixed", "RB_cold"), ("earVsResume", "SR_warm")):
        p, lo, hi, nt, nu = sav[o]
        flag = "" if (lo > 0 or hi < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
        for suf, x in (("", p), ("Lo", lo), ("Hi", hi)):
            put(nm + suf, "%.1f" % x, "%s; EAR vs %s, positive = EAR lower, %d tasks%s" % (src, o, nt, flag))
            NOTE[nm + suf] = "EAR (E3 token_rule arm) vs %s, positive = EAR lower%s" % (o, flag)
    trows, frows = [], ["policy,label,ach_j,ok,n,succ_lo,succ_hi"]
    for o in ("FR_warm", "SR_warm", "RB_cold", "ctrl_beta", "xstar_rule", "token_rule"):
        j, ok, n = pooled(cc, o, cells_)
        ok, n = int(ok), int(n)
        lo, hi = pn.wilson(ok, n)
        nm = "earOk" + EAR_CAM[o]
        put(nm, "%d of %d" % (ok, n), src + ", %s, correct goals" % o)
        put(nm + "Lo", "%.0f" % (100 * lo), "Wilson 95, " + src + ", " + o)
        put(nm + "Hi", "%.0f" % (100 * hi), "Wilson 95, " + src + ", " + o)
        frows.append("%s,%s,%.1f,%d,%d,%.4f,%.4f" % (o, EAR_LABEL[o], j, ok, n, lo, hi))
        if o == "token_rule":
            cell = "--"
        else:
            p, l_, h_ = sav[o][:3]
            cell = "$%.1f$ ($%.1f$ to $%.1f$)" % (p, l_, h_)
        trows.append("%s & %s & %s & %d/%d \\\\" % (EAR_LABEL[o], pn.fmt0(j), cell, ok, n))
    figd = os.path.join(DATA, "figdata")
    os.makedirs(figd, exist_ok=True)
    open(os.path.join(figd, "e3_points.csv"), "w").write("\n".join(frows) + "\n")
    open(os.path.join(paper_dir, "tables", "ear_table.tex"), "w").write(
        "% GENERATED by reframe_numbers.py; do not edit by hand. E3; EAR = the token_rule arm. Columns: policy, board J "
        "per successful goal, EAR saving against that row (percent, 95 percent CI, positive = EAR lower), correct goals. "
        "No \\bottomrule: the table adds it.\n" + "\n".join(trows) + "\n")
    # replay macros from R2's file (by name); offline EAR vs all tokens needs a field R5 has not delivered
    rp = os.path.join(DATA, "r2", "ear_replay.json")
    if os.path.exists(rp):
        r = json.load(open(rp))
        for nm in ("earReplayMatch", "earSelectorTokenShare"):
            v = r.get(nm) or {}
            if isinstance(v.get("k"), int) and v.get("n"):
                put(nm, "%d of %d" % (v["k"], v["n"]), "R2 ear_replay.json sha256 %s, field %s" % (pn.sha256(rp), nm))
                if nm == "earSelectorTokenShare":
                    put(nm + "Pct", "%.1f" % (100.0 * v["k"] / v["n"]), "R2 ear_replay.json, field %s, percent" % nm)
            else:
                put(nm, "\\pending{%s}" % nm, "pending: %s has no k and n for %s" % (rp, nm))
    else:
        for nm in ("earReplayMatch", "earSelectorTokenShare"):
            put(nm, "\\pending{%s}" % nm, "pending: R2 replay file data/r2/ear_replay.json not given")
    # earctl 0.2.0 parity (R7, Oct 22); earVsAllTokens dropped (coordinator)
    pp = os.path.join(os.path.dirname(DATA), "data", "r7", "earparity_020.json")
    if os.path.exists(pp):
        pj = json.load(open(pp))
        for nm in ("earParityEar", "earParityTokenRule", "earParityThompson"):
            v = pj.get(nm)
            if isinstance(v, dict) and isinstance(v.get("k"), int) and v.get("n"):
                v = "%d of %d" % (v["k"], v["n"])
            if v is None:
                put(nm, "\\pending{%s}" % nm, "pending: no %s in %s" % (nm, pp))
                continue
            put(nm, str(v), "R7 earparity_020.json sha256 %s, field %s; replay of the 111 E3 token_rule decisions "
                "(e3_decisions.jsonl 3537f813)" % (pn.sha256(pp), nm))
            NOTE[nm] = "earctl 0.2.0 parity; json_parse and tool_error only (no silent_detected decision in E3)"
    else:
        for nm in ("earParityEar", "earParityTokenRule", "earParityThompson"):
            put(nm, "\\pending{%s}" % nm, "pending: data/r7/earparity_020.json not given")
    return sav


def ear_models_table(v, paper_dir):
    """tables/ear_models_table.tex (R8, Oct 23): EAR on unseen data, one row per model."""
    def ci(k):
        return "$%s$ ($%s$ to $%s$)" % (v[k], v[k + "Lo"], v[k + "Hi"])
    rows = []
    specs = (("Qwen3 30B (held-out, live)", "earSaveVsRestart", "earVsResume", "earVsBestFixed", "earOkEar"),
             ("Mistral 24B (offline, restricted)", "earMistralVsRestart", "earMistralVsResume", "earMistralVsRollback",
              "earMistralOk"),
             ("gpt-oss 20B (offline, restricted)", "earGptossVsRestart", "earGptossVsResume", "earGptossVsRollback",
              "earGptossOk"))
    for label, r, s, b, ok in specs:
        if not all(k in v and k + "Lo" in v for k in (r, s, b)) or ok not in v:
            print("ear_models_table: missing values for %s, row left out" % label)
            continue
        k_, n_ = v[ok].split(" of ")
        rows.append("%s & %s & %s & %s & %s & %s/%s \\\\" % (label, n_, ci(r), ci(s), ci(b), k_, n_))
    open(os.path.join(paper_dir, "tables", "ear_models_table.tex"), "w").write(
        "% GENERATED by reframe_numbers.py; do not edit by hand. EAR on unseen data. Columns: items, EAR saving in "
        "energy per successful goal against always restart, always resume, always roll back (percent, 95 percent CI, "
        "positive = EAR lower), successful goals of EAR. Qwen3 30B: online study, held-out tasks (token_rule arm); "
        "Mistral and gpt-oss: offline replay restricted to the three options each ran. No \\bottomrule.\n"
        + "\n".join(rows) + "\n")


def ear_table_all(cc, sav, v, eo, paper_dir):
    """ear_table.tex for all three models (R8, Oct 23): per model EpG, EAR's saving against the row, k/n."""
    cells_ = sorted({(c, p) for (c, p, _) in cc})
    tab = json.load(open(eo)).get("table", {}) if os.path.exists(eo) else {}
    ci = lambda a, b, c: "$%s$ ($%s$ to $%s$)" % (a, b, c)
    off = {"FR_warm": "Restart", "SR_warm": "Resume", "RB_cold": "Rollback"}
    rows = []
    for o in ("FR_warm", "SR_warm", "RB_cold", "ctrl_beta", "xstar_rule", "token_rule"):
        j, ok, n = pooled(cc, o, cells_)
        q = [pn.fmt0(j), "--" if o == "token_rule" else ci(*("%.1f" % x for x in sav[o][:3])), "%d/%d" % (ok, n)]
        for m in ("Mistral", "Gptoss"):
            t = tab.get(m, {}).get("EAR" if o == "token_rule" else o)
            if not t or t["j"] is None:
                q += ["--", "--", "--"]
                continue
            s = "--" if o == "token_rule" else ci(v["ear%sVs%s" % (m, off[o])], v["ear%sVs%sLo" % (m, off[o])],
                                                  v["ear%sVs%sHi" % (m, off[o])])
            q += [pn.fmt0(t["j"]), s, "%d/%d" % (t["ok"], t["n"])]
        rows.append("%s & %s \\\\" % (EAR_LABEL[o], " & ".join(q)))
    open(os.path.join(paper_dir, "tables", "ear_table.tex"), "w").write(
        "% GENERATED by reframe_numbers.py; do not edit by hand. Rows: always restart, always resume, always roll back, "
        "EAR learning mode, threshold rule, EAR. Per model three columns: EpG (board J per successful goal), EAR's saving "
        "against the row (percent, 95 percent CI, positive = EAR lower), successful k/n. Models: Qwen3 30B (online study, "
        "held-out, live), Mistral 24B and gpt-oss 20B (offline, restricted to the three options each ran). "
        "-- = not run on that model. No \\bottomrule.\n" + "\n".join(rows) + "\n")


def ear_tasks(cc, put, NOTE, paper_dir):
    """Per task view on the held-out tasks (R8, Oct 23): EpG of EAR, always restart, always roll back."""
    def per_task(lab):
        agg = collections.defaultdict(lambda: [0.0, 0])
        for (c, p, l), v in cc.items():
            if l != lab:
                continue
            for t, x in v["tasks"].items():
                agg[t][0] += x[0]
                agg[t][1] += x[1]
        return {t: (e / ok if ok else None) for t, (e, ok) in agg.items()}
    ear_, fr, rb = per_task("token_rule"), per_task("FR_warm"), per_task("RB_cold")
    tasks = sorted(set(ear_) & set(fr) & set(rb), key=lambda t: int(t.split("_")[-1]) if t.split("_")[-1].isdigit() else 0)

    def wins(other):  # EAR lower EpG; EAR with successes beats a policy with none on that task
        return sum(1 for t in tasks if ear_[t] is not None and (other[t] is None or ear_[t] < other[t]))
    src = ("E3 held-out tasks; EpG per task = board J of a policy's goals on the task over its successful goals; "
           "EAR = the token_rule arm; a task where EAR has successes and the other policy none counts as an EAR win")
    for nm, other, lab in (("earTaskWinsVsRestart", fr, "always restart"), ("earTaskWinsVsBestFixed", rb, "always roll back")):
        put(nm, "%d of %d" % (wins(other), len(tasks)), src + ", vs " + lab)
        NOTE[nm] = "held-out tasks where EAR's EpG is lower than %s" % lab
    # one sided sign test, EAR vs always roll back (R8, Oct 23): ties (equal EpG, or no success in both) excluded
    import math
    ties = [t for t in tasks if ear_[t] == rb[t]]
    w = wins(rb)
    m = len(tasks) - len(ties)
    p = sum(math.comb(m, k) for k in range(w, m + 1)) / 2.0 ** m if m else 1.0
    txt = "$p < 0.001$" if p < 0.001 else "$p = %s$" % ("%.2g" % p)
    put("earTaskSignP", txt, src + ", one sided exact sign test, %d EAR wins of %d tasks vs always roll back, "
        "%d ties excluded (%s), p = %.3g" % (w, m, len(ties), ", ".join(ties) or "none", p))
    NOTE["earTaskSignP"] = "one sided sign test, %d of %d vs always roll back, %d ties excluded, p = %.3g" % (w, m, len(ties), p)
    f = lambda x: pn.fmt0(x) if x is not None else "none"
    rows = ["%s & %s & %s & %s \\\\" % (t.split("_")[-1], f(ear_[t]), f(fr[t]), f(rb[t])) for t in tasks]
    open(os.path.join(paper_dir, "tables", "ear_tasks_table.tex"), "w").write(
        "% GENERATED by reframe_numbers.py; do not edit by hand. Held-out tasks (BFCL multi turn base number). "
        "Columns: task, EpG (board J per successful goal) of EAR, always restart, always roll back; none = no "
        "successful goal. No \\bottomrule.\n" + "\n".join(rows) + "\n")


def time_succ(st, art, put, NOTE):
    """Median wall time of a successful goal per option and point (R8, Oct 23), main study: FR_warm and SR_warm from
    E1, RB_cold from E1b; four failure types pooled. Wall time = sum of runs.duration_ns over all attempts of the goal
    (first call to final answer); the gaps between attempts (state restore, cache reset) are not inside a run."""
    e1 = pn.load_ledger(paths(art, ["raf_e1/raf_e1_run_ledger.jsonl", "raf_e1/*rerun*ledger*.jsonl"]))
    e1b = pn.load_ledger(paths(art, ["raf_e1b/raf_e1b_run_ledger.jsonl"]))
    src = ("main study (FR_warm, SR_warm from E1; RB_cold from E1b, another engine commit), latest valid per (item, "
           "policy), successful goals only, four failure types pooled; wall time = sum of attempt run durations, "
           "excluding the gaps between attempts; median, seconds")
    for opt, cam, goals in (("FR_warm", "FrWarm", e1), ("SR_warm", "SrWarm", e1), ("RB_cold", "RbCold", e1b)):
        for pt in ("early", "late"):
            ts, tot, k = [], 0.0, 0  # successful goal times; total time of all goals; successes
            for g, (task, cls, p, pol) in goals.items():
                if pol != opt or p != pt:
                    continue
                ns = st.c.execute("SELECT SUM(r.duration_ns) FROM goal_attempt ga JOIN runs r ON r.run_id = ga.run_id "
                                  "WHERE ga.goal_id = ?", (g,)).fetchone()[0] or 0
                tot += ns / 1e9
                if st.success(g):
                    k += 1
                    if ns:
                        ts.append(ns / 1e9)
            ne = "timeEpg%s%s" % (cam, pt.capitalize())
            if k:
                put(ne, "%.1f" % (tot / k), src.replace("successful goals only", "all goals, failed included")
                    .replace("median, seconds", "total wall time divided by successful goals, seconds")
                    + ", %s %s, %d successful goals" % (opt, pt, k))
                NOTE[ne] = "wall time per successful goal (EpG sense), s, all goals and attempts, gaps between attempts excluded"
            else:
                put(ne, "\\pending{%s}" % ne, "pending: no successful %s %s goals" % (opt, pt))
            nm = "timeSucc%s%s" % (cam, pt.capitalize())
            if not ts:
                put(nm, "\\pending{%s}" % nm, "pending: no successful %s %s goals" % (opt, pt))
                continue
            ts.sort()
            med = ts[len(ts) // 2] if len(ts) % 2 else (ts[len(ts) // 2 - 1] + ts[len(ts) // 2]) / 2
            put(nm, "%.1f" % med, src + ", %s %s, %d successful goals" % (opt, pt, len(ts)))
            NOTE[nm] = "median wall time of a successful goal, s, all attempts, gaps between attempts excluded"


def add(st, art, put, NOTE, paper_dir, pilot_bid, r5):
    tr, tv = totals(st, art, put, NOTE, pilot_bid)
    audit(art, put, paper_dir, tr, tv)
    regret = hindsight(st, art, put, NOTE, paper_dir, r5 or {})
    best, cc3 = online(st, art, put, NOTE, regret)
    rec = {}

    def put_r(k, v, s):  # records the EAR values for ear_models_table
        rec[k] = v
        put(k, v, s)
    sav3 = ear(cc3, put_r, NOTE, paper_dir)
    eo = os.path.join(DATA, "r4", "ear_offline.json")  # out of model EAR replay (ear_offline.py, platform environment)
    if os.path.exists(eo):
        for k, v in json.load(open(eo))["values"].items():
            put_r(k, v, "ear_offline.json sha256 %s; %s" % (pn.sha256(eo)[:8], json.load(open(eo))["provenance"][k]))
            NOTE[k] = "EAR, out of model offline replay (second or third model), options restricted to FR_warm, SR_warm, RB_cold"
    ear_models_table(rec, paper_dir)
    ear_table_all(cc3, sav3, rec, eo, paper_dir)
    ear_tasks(cc3, put, NOTE, paper_dir)
    time_succ(st, art, put, NOTE)
    regret_table(paper_dir, regret, put)
    counterfactual(st, put, NOTE, best)
