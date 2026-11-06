from common import *
st = Store(); bc = pn.cells(st, e1b_goals())
out = {}
for lab, sits in (("e3_situations", [(c, p) for c in ("json_parse", "tool_error") for p in ("early", "late")]),
                  ("all8", [(c, p) for c in CLS for p in ("early", "late")])):
    p, lo, hi, nt, nu = pn.boot_saving([(bc[(c, pt, "RB_warm")], bc[(c, pt, "RB_cold")]) for c, pt in sits])
    out["RBwarm_vs_RBcold_" + lab] = [round(p, 1), round(lo, 1), round(hi, 1)]
json.dump(out, open("../out/extra.json", "w")); print(out)
