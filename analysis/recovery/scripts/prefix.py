"""Item 4: are the recoveries in one block launched from the same history? Compare attempt 1 call by call
after normalising generated identifiers (tool-call ids, request ids, uuids, hex digests)."""
from common import *
import re, hashlib
st = Store(); c = st.c
RX = [re.compile(p) for p in (r"(?:call|chatcmpl|req|cmpl|toolu|run)[-_][A-Za-z0-9]+",
                               r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                               r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{8,}\b")]
def norm(s):
    s = s or ""
    for r in RX: s = r.sub("<id>", s)
    return s
def seq(g):
    run = c.execute("select run_id from goal_attempt where goal_id=? and attempt_number=1", (g,)).fetchone()[0]
    return [hashlib.sha1((norm(p) + "\x00" + norm(r)).encode()).hexdigest()
            for p, r in c.execute("select prompt, response from llm_interactions where run_id=? order by step_index, interaction_id", (run,))]
def first_div(seqs):
    L = min(len(s) for s in seqs)
    for i in range(L):
        if len({s[i] for s in seqs}) > 1: return i, L
    return (L if len({len(s) for s in seqs}) == 1 else L), L
res = {}
for study, goals in (("E1", e1_goals()), ("E1b", e1b_goals())):
    blk = collections.defaultdict(dict)
    for g, v in goals.items():
        if v[3] != "B0": blk[(pn.norm_task(v[0]), v[1], v[2])][v[3]] = g
    full = upto_last = 0; where = collections.Counter(); by = collections.defaultdict(lambda: [0, 0]); n_calls = collections.Counter()
    S = {}
    for k, d in blk.items():
        ss = [seq(g) for g in d.values()]; S[k] = ss
        lens = sorted({len(s) for s in ss}); n_calls[str(lens)] += 0
        i, L = first_div(ss)
        same_len = len({len(s) for s in ss}) == 1
        full += (i == L and same_len)
        ok = i >= L - 1 and same_len   # identical except possibly the failed call itself
        upto_last += ok
        by[k[1] + "|" + k[2]][0] += ok; by[k[1] + "|" + k[2]][1] += 1
        if not ok: where["div at call %d of %s" % (i + 1, "/".join(map(str, sorted({len(s) for s in ss}))))] += 1
    res[study] = dict(blocks=len(blk), identical_all_calls=full, identical_before_failed_call=upto_last,
                      by_situation={s: "%d of %d" % tuple(v) for s, v in sorted(by.items())},
                      divergences=where.most_common(12))
    res[study + "_seqs"] = S
# cross-study: E1 SR_warm vs E1b RB_warm and E1 FR_warm vs E1b RB_warm, same block
for a_pol, b_pol in (("SR_warm", "RB_warm"), ("FR_warm", "RB_warm")):
    e1 = collections.defaultdict(dict); e1b = collections.defaultdict(dict)
    for g, v in e1_goals().items(): e1[(pn.norm_task(v[0]), v[1], v[2])][v[3]] = g
    for g, v in e1b_goals().items(): e1b[(pn.norm_task(v[0]), v[1], v[2])][v[3]] = g
    same = n = 0
    for k in e1:
        if k in e1b and a_pol in e1[k] and b_pol in e1b[k]:
            s1, s2 = seq(e1[k][a_pol]), seq(e1b[k][b_pol]); n += 1
            i, L = first_div([s1, s2]); same += (i >= L - 1 and len(s1) == len(s2))
    res["cross_%s_vs_E1b_%s" % (a_pol, b_pol)] = "%d of %d" % (same, n)
for k in ("E1_seqs", "E1b_seqs"): res.pop(k)
json.dump(res, open("../out/prefix.json", "w"), indent=1)
print(json.dumps(res, indent=1))
