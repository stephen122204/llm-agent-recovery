"""Item 5 sensitivity: E1b (roll back) energies divided by the attempt-1 calibration ratio (calib.json)."""
from common import *
import copy
st = Store()
eg, bg = e1_goals(), e1b_goals()
ec, bc = pn.cells(st, eg), pn.cells(st, bg)
R = json.load(open("../out/calib.json"))["att1_energy_ratio_pooled"]
bcal = copy.deepcopy(bc)
for v in bcal.values():
    for t in v["tasks"].values():
        t[0] /= R; t[3] /= R
    v["eb"] = None
    if v["ach_board"]: v["ach_board"] /= R
X = {**ec, **bcal}; RAW = {**ec, **bc}
out = {"ratio": R}
for side, classes in (("tool", TOOL), ("model", MODEL)):
    for pt in ("early", "late"):
        for win, lose in (("RB_warm", "FR_warm"), ("RB_warm", "SR_warm"), ("RB_cold", "FR_warm"), ("RB_cold", "SR_warm")):
            for lab, cc in (("raw", RAW), ("cal", X)):
                p, lo, hi, nt, nu = pn.boot_saving([(cc[(cl, pt, win)], cc[(cl, pt, lose)]) for cl in classes])
                out["%s vs %s | %s %s | %s" % (win, lose, pt, side, lab)] = [round(p, 1), round(lo, 1), round(hi, 1)]
best = {}
for cl in CLS:
    for pt in ("early", "late"):
        a = {o: X[(cl, pt, o)]["ach_board"] for o in ("FR_warm", "FR_cold", "SR_warm", "SR_cold", "RB_warm", "RB_cold") if X[(cl, pt, o)]["ach_board"]}
        best["%s|%s" % (cl, pt)] = min(a, key=a.get)
out["best_of_six_calibrated"] = best
json.dump(out, open("../out/calibrated.json", "w"), indent=1)
print(json.dumps(out, indent=1))
