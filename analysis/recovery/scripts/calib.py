"""Cross-study energy calibration: attempt 1 is the same history in E1 and E1b (prefix.py), so its board
energy should agree if the two studies are energy-comparable."""
from common import *
import statistics as stt
st = Store(); c = st.c
def att1(g):
    run, = c.execute("select run_id from goal_attempt where goal_id=? and attempt_number=1", (g,)).fetchone()
    dur, bid = c.execute("select duration_ns, baseline_id from runs where run_id=?", (run,)).fetchone()
    mw = c.execute("select avg(energy_uj) from energy_sample_domains where run_id=? and domain_id=28", (run,)).fetchone()[0]
    idle = st.idle_w(bid).get("DC_INPUT", 0.0)
    return (mw / 1000 - idle) * dur / 1e9, dur / 1e9, mw / 1000, idle, bid
e1 = collections.defaultdict(dict); e1b = collections.defaultdict(dict)
for g, v in e1_goals().items():
    if v[3] != "B0": e1[(pn.norm_task(v[0]), v[1], v[2])][v[3]] = g
for g, v in e1b_goals().items(): e1b[(pn.norm_task(v[0]), v[1], v[2])][v[3]] = g
rat, drat, wrat, i1, i2, b1, b2 = [], [], [], [], [], set(), set()
within = []
for k in e1:
    if k not in e1b: continue
    a = [att1(g) for g in e1[k].values()]; b = [att1(g) for g in e1b[k].values()]
    ea, eb = stt.mean(x[0] for x in a), stt.mean(x[0] for x in b)
    rat.append(eb / ea); drat.append(stt.mean(x[1] for x in b) / stt.mean(x[1] for x in a))
    wrat.append(stt.mean(x[2] for x in b) / stt.mean(x[2] for x in a))
    i1 += [x[3] for x in a]; i2 += [x[3] for x in b]; b1 |= {x[4] for x in a}; b2 |= {x[4] for x in b}
    within.append(max(x[0] for x in a) / min(x[0] for x in a))
tot1 = sum(sum(att1(g)[0] for g in d.values()) for k, d in e1.items() if k in e1b)
tot2 = sum(sum(att1(g)[0] for g in e1b[k].values()) for k in e1 if k in e1b)
print(json.dumps(dict(blocks=len(rat), att1_energy_ratio_E1b_over_E1_median=stt.median(rat),
      att1_energy_ratio_q10_q90=[sorted(rat)[len(rat)//10], sorted(rat)[9*len(rat)//10]],
      att1_energy_ratio_pooled=tot2 / tot1, duration_ratio_median=stt.median(drat), gross_power_ratio_median=stt.median(wrat),
      idle_W_E1=sorted(set(round(x, 2) for x in i1)), idle_W_E1b=sorted(set(round(x, 2) for x in i2)),
      baselines_E1=sorted(b1), baselines_E1b=sorted(b2), within_E1_block_max_over_min_median=stt.median(within)), indent=1))
