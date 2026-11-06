"""RAF follow-up analyses on the frozen October database (EXPERIMENT-SPECS items 2-6).

Uses Deepak's definitions from paper_numbers.py unchanged: goal selection (load_ledger, latest record
per item and policy), success (last output_quality.pass_fail), board energy per attempt
((mean DC_INPUT W - idle DC_INPUT W of the run's baseline) x run duration), and the paired task
bootstrap (boot_saving, 2000 resamples, seed 20261013).

Outputs out/analyses.json.
"""
import hashlib, statistics as stt
from common import *

st = Store(); c = st.c
eg, bg = e1_goals(), e1b_goals()
GOALS = {**{g: v + ("E1",) for g, v in eg.items()}, **{g: v + ("E1b",) for g, v in bg.items()}}

idle_cache = {}


def idle_board(bid):
    if bid not in idle_cache:
        idle_cache[bid] = st.idle_w(bid).get("DC_INPUT", 0.0)
    return idle_cache[bid]


def goal_record(gid):
    atts = []
    for aid, run, num, ok_a in c.execute("SELECT attempt_id, run_id, attempt_number, pass_fail FROM goal_attempt "
                                         "WHERE goal_id=? ORDER BY attempt_number", (gid,)).fetchall():
        start, end, dur, bid, tcalls = c.execute("SELECT start_time_ns, end_time_ns, duration_ns, baseline_id, tool_calls "
                                                 "FROM runs WHERE run_id=?", (run,)).fetchone()
        mw = c.execute("SELECT AVG(energy_uj) FROM energy_sample_domains WHERE run_id=? AND domain_id=28",
                       (run,)).fetchone()[0] or 0.0
        board = (mw / 1000.0 - idle_board(bid)) * (dur or 0) / 1e9
        n_llm, pt, ct = c.execute("SELECT COUNT(*), COALESCE(SUM(prompt_tokens),0), COALESCE(SUM(completion_tokens),0) "
                                  "FROM llm_interactions WHERE run_id=?", (run,)).fetchone()
        n_sre, reused = c.execute("SELECT COUNT(*), COALESCE(SUM(tokens_reused),0) FROM state_reuse_events "
                                  "WHERE run_id=?", (run,)).fetchone()
        atts.append(dict(aid=aid, run=run, num=num, start=start, end=end, dur=(dur or 0) / 1e9, board=board,
                         llm=n_llm, tool=tcalls or 0, pt=pt, ct=ct, reused=reused, n_sre=n_sre,
                         mean_w=board / ((dur or 1) / 1e9)))
    return dict(gid=gid, ok=st.success(gid), atts=atts)


print("loading", len(GOALS), "goals")
REC = {g: goal_record(g) for g in GOALS}
print("loaded")
OUT = {"n_goals": len(GOALS), "n_e1": len(eg), "n_e1b": len(bg)}

# sanity: our per-goal board energy equals Store.energy (Deepak's) on a sample
chk = [g for g in list(GOALS)[::97]]
dev = max(abs(sum(a["board"] for a in REC[g]["atts"]) - st.energy(g)[0]) for g in chk)
OUT["sanity_max_abs_dev_J"] = dev
sre_cov = [a["n_sre"] == a["llm"] for r in REC.values() for a in r["atts"]]
OUT["sre_row_per_call_share"] = sum(sre_cov) / len(sre_cov)

SIDE = {"json_parse": "model", "rate_limit": "model", "tool_error": "tool", "timeout": "tool"}
POLS = ("FR_warm", "FR_cold", "SR_warm", "SR_cold", "RB_warm", "RB_cold", "SG_warm", "SG_cold")

# ---------- item 2: token breakdown per recovery x point x side ----------
tok = {}
for pol in POLS:
    for pt in ("early", "late"):
        for side in ("model", "tool"):
            gs = [g for g, v in GOALS.items() if v[3] == pol and v[2] == pt and SIDE.get(v[1]) == side]
            if not gs:
                continue
            ok = sum(REC[g]["ok"] for g in gs)
            A = [a for g in gs for a in REC[g]["atts"]]
            R = [a for g in gs for a in REC[g]["atts"] if a["num"] >= 2]
            s = lambda xs, k: sum(a[k] for a in xs)
            row = dict(n=len(gs), ok=ok,
                       cached_in_per_ok=s(A, "reused") / ok, uncached_in_per_ok=(s(A, "pt") - s(A, "reused")) / ok,
                       out_per_ok=s(A, "ct") / ok, calls_per_goal=s(A, "llm") / len(gs),
                       epg_board=s(A, "board") / ok,
                       rec_cached_in_per_goal=s(R, "reused") / len(gs),
                       rec_uncached_in_per_goal=(s(R, "pt") - s(R, "reused")) / len(gs),
                       rec_out_per_goal=s(R, "ct") / len(gs), rec_calls_per_goal=s(R, "llm") / len(gs),
                       rec_board_per_goal=s(R, "board") / len(gs),
                       att1_board_per_goal=sum(a["board"] for a in A if a["num"] == 1) / len(gs),
                       att1_calls_per_goal=sum(a["llm"] + a["tool"] for a in A if a["num"] == 1) / len(gs),
                       study=GOALS[gs[0]][4])
            tok["%s|%s|%s" % (pol, pt, side)] = row
OUT["tokens"] = tok

# ---------- item 3: between-attempt overhead (outside every attempt window) ----------
gaps, gap_share, gap_e_share = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
for g, v in GOALS.items():
    at = REC[g]["atts"]
    if len(at) < 2:
        continue
    gs = [(at[i + 1]["start"] - at[i]["end"]) / 1e9 for i in range(len(at) - 1)]
    tot_dur = sum(a["dur"] for a in at)
    tot_e = sum(a["board"] for a in at)
    w = tot_e / tot_dur if tot_dur else 0.0  # mean above-idle power during attempts: an upper bound for the gap
    gaps[v[3]] += gs
    gap_share[v[3]].append(100 * sum(gs) / tot_dur)
    gap_e_share[v[3]].append(100 * w * sum(gs) / tot_e if tot_e else 0.0)
q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]
OUT["overhead"] = {pol: dict(n_gaps=len(gaps[pol]), median_s=stt.median(gaps[pol]), p95_s=q(gaps[pol], .95),
                             max_s=max(gaps[pol]), median_time_share_pct=stt.median(gap_share[pol]),
                             p95_time_share_pct=q(gap_share[pol], .95),
                             median_energy_bound_pct=stt.median(gap_e_share[pol]),
                             p95_energy_bound_pct=q(gap_e_share[pol], .95))
                   for pol in POLS if gaps[pol]}
re_cols = c.execute("SELECT COUNT(*), SUM(recovery_end_ns IS NOT NULL), SUM(recovery_energy_uj IS NOT NULL) "
                    "FROM recovery_events WHERE goal_id IN (%s)" % ",".join(map(str, GOALS))).fetchone()
OUT["recovery_events_coverage"] = dict(rows=re_cols[0], with_end=re_cols[1], with_energy=re_cols[2])

# ---------- item 4: prefix identity of attempt 1 within each block ----------
def att1_hash(g, upto_fail=True):
    a = REC[g]["atts"][0]
    h = hashlib.sha1()
    for p, r in c.execute("SELECT prompt, response FROM llm_interactions WHERE run_id=? ORDER BY step_index, interaction_id",
                          (a["run"],)):
        h.update((p or "").encode()); h.update(b"\x00"); h.update((r or "").encode()); h.update(b"\x01")
    for ih, oh in c.execute("SELECT input_payload_hash, output_payload_hash FROM orchestration_events WHERE run_id=? "
                            "AND tool_name IS NOT NULL ORDER BY start_time_ns", (a["run"],)):
        h.update(("%s|%s" % (ih, oh)).encode())
    return h.hexdigest()


def first_prompt_hash(g):
    a = REC[g]["atts"][0]
    p = c.execute("SELECT prompt FROM llm_interactions WHERE run_id=? ORDER BY step_index, interaction_id LIMIT 1",
                  (a["run"],)).fetchone()
    return hashlib.sha1(((p or [""])[0] or "").encode()).hexdigest()


blocks = collections.defaultdict(dict)
for g, v in GOALS.items():
    if v[3] == "B0":
        continue
    blocks[(pn.norm_task(v[0]), v[1], v[2], v[4])][v[3]] = g
pid = {}
for study in ("E1", "E1b"):
    bs = {k: d for k, d in blocks.items() if k[3] == study}
    same_all = same_first = 0
    same_by_cls = collections.Counter(); n_by_cls = collections.Counter()
    for k, d in bs.items():
        hs = {att1_hash(g) for g in d.values()}
        fs = {first_prompt_hash(g) for g in d.values()}
        same_all += len(hs) == 1; same_first += len(fs) == 1
        n_by_cls[k[1] + "|" + k[2]] += 1; same_by_cls[k[1] + "|" + k[2]] += len(hs) == 1
    pid[study] = dict(blocks=len(bs), identical_attempt1=same_all, identical_first_prompt=same_first,
                      by_situation={s: "%d of %d" % (same_by_cls[s], n_by_cls[s]) for s in sorted(n_by_cls)})
# cross-study: same task/class/point, E1 SR_warm vs E1b RB_warm attempt 1
cross = n_cross = 0
for k, d in blocks.items():
    if k[3] != "E1":
        continue
    kb = (k[0], k[1], k[2], "E1b")
    if kb in blocks and "SR_warm" in d and "RB_warm" in blocks[kb]:
        n_cross += 1
        cross += att1_hash(d["SR_warm"]) == att1_hash(blocks[kb]["RB_warm"])
pid["cross_E1_SRwarm_vs_E1b_RBwarm"] = "%d of %d" % (cross, n_cross)
OUT["prefix_identity"] = pid

# ---------- item 5: paired intervals involving warm roll back ----------
ec, bc = pn.cells(st, eg), pn.cells(st, bg)
cellsx = {}
for (cls, pt, pol), v in ec.items():
    cellsx[(cls, pt, pol)] = v
for (cls, pt, pol), v in bc.items():
    cellsx[(cls, pt, pol)] = v


def comp(win, lose, pt, classes):
    p, lo, hi, nt, nu = pn.boot_saving([(cellsx[(cl, pt, win)], cellsx[(cl, pt, lose)]) for cl in classes])
    k = sum(cellsx[(cl, pt, win)]["ok"] for cl in classes); n = sum(cellsx[(cl, pt, win)]["n"] for cl in classes)
    k2 = sum(cellsx[(cl, pt, lose)]["ok"] for cl in classes); n2 = sum(cellsx[(cl, pt, lose)]["n"] for cl in classes)
    return dict(saving_pct=p, lo=lo, hi=hi, tasks=nt, undefined=nu, win_ok="%d of %d" % (k, n), lose_ok="%d of %d" % (k2, n2))


ci = {}
for side, classes in (("tool", TOOL), ("model", MODEL)):
    for pt in ("early", "late"):
        for win, lose in (("RB_warm", "FR_warm"), ("RB_warm", "SR_warm"), ("RB_warm", "RB_cold"), ("RB_warm", "SG_warm"),
                          ("FR_warm", "SR_warm"), ("SR_warm", "FR_warm")):
            ci["%s vs %s | %s %s" % (win, lose, pt, side)] = comp(win, lose, pt, classes)
for pt in ("early", "late"):
    for cl in CLS:
        for lose in ("FR_warm", "SR_warm"):
            ci["RB_warm vs %s | %s %s" % (lose, pt, cl)] = comp("RB_warm", lose, pt, (cl,))
OUT["paired"] = ci
# best of the six (warm and cold FR, SR, RB) per situation, energy per successful goal
best = {}
for cl in CLS:
    for pt in ("early", "late"):
        a = {o: cellsx[(cl, pt, o)]["ach_board"] for o in ("FR_warm", "FR_cold", "SR_warm", "SR_cold", "RB_warm", "RB_cold")
             if cellsx.get((cl, pt, o)) and cellsx[(cl, pt, o)]["ach_board"]}
        w = min(a, key=a.get)
        best["%s|%s" % (cl, pt)] = dict(winner=w, ach={o: round(x) for o, x in a.items()},
                                        ok={o: "%d/%d" % (cellsx[(cl, pt, o)]["ok"], cellsx[(cl, pt, o)]["n"]) for o in a})
OUT["best_of_six"] = best

# ---------- item 6: Eq. 2 decomposition per situation (restart FR_warm vs resume SR_warm, E1) ----------
eq = {}
for cl in CLS:
    for pt in ("early", "late"):
        fr = [g for g, v in eg.items() if v[1] == cl and v[2] == pt and v[3] == "FR_warm"]
        sr = [g for g, v in eg.items() if v[1] == cl and v[2] == pt and v[3] == "SR_warm"]
        m = lambda gs, f: sum(f(REC[g]) for g in gs) / len(gs)
        att1 = lambda r: r["atts"][0]["board"]
        recov = lambda r: sum(a["board"] for a in r["atts"][1:])
        S = (m(fr, att1) + m(sr, att1)) / 2          # energy before the failure (attempt 1), both arms
        E = m(fr, recov)                              # a restart repeats the run
        R_K = m(sr, recov)                            # a resume's recovery energy
        D = R_K - (E - S)                             # extra work the kept failure causes
        pR = m(fr, lambda r: r["ok"]); pK = m(sr, lambda r: r["ok"])
        W = (m(fr, lambda r: r["atts"][0]["llm"] + r["atts"][0]["tool"]) + m(sr, lambda r: r["atts"][0]["llm"] + r["atts"][0]["tool"])) / 2
        succ_term = (pR / pK - 1) * E; extra_term = (pR / pK) * D
        J_R = (S + E) / pR; J_K = (S + R_K) / pK
        eq["%s|%s" % (cl, pt)] = dict(S=S, E=E, R_K=R_K, Delta=D, pR=pR, pK=pK, work_calls=W,
                                      success_term=succ_term, extra_term=extra_term, threshold=succ_term + extra_term,
                                      restart_pays=S < succ_term + extra_term, J_restart=J_R, J_resume=J_K,
                                      observed_restart_cheaper=ec[(cl, pt, "FR_warm")]["ach_board"] < ec[(cl, pt, "SR_warm")]["ach_board"],
                                      S_over_E=S / E)
OUT["eq2"] = eq

json.dump(OUT, open("../out/analyses.json", "w"), indent=1, default=str)
print(json.dumps({k: OUT[k] for k in ("sanity_max_abs_dev_J", "sre_row_per_call_share", "overhead", "prefix_identity",
                                      "recovery_events_coverage")}, indent=1, default=str))
