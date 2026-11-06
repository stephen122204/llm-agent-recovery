"""RAF R5: x* only refit for the middle slice (coordinator Oct 18).

Usage: python refit_xstar_mid.py <export_dir> <out_dir> <tag> [n_boot]
Writes <out_dir>/r5_xstar_mid.json and merges xstarMid fields into
<out_dir>/r5_numbers.json (created if absent; other fields untouched).

Rule fixed Oct 18 before the data: x* of a class is identified only if the
upper bound of its 95% CI lies inside the observed work done range (calls,
total model plus tool, attempt 1) of that class. Unidentified classes get
null values in the flat fields; the raw fit stays in xstarMid for audit.
"""
import json
import os
import sys

import fit_controller_params as F

CAMEL = {"json_parse": "JsonParse", "rate_limit": "RateLimit", "timeout": "Timeout",
         "tool_error": "ToolError", "silent_detected": "SilentDetected"}
RULE = ("identified only if the upper bound of the 95% CI of x* lies inside the observed "
        "work done range (calls) of the class")


def main(exp, out, tag, n_boot=300):
    os.makedirs(out, exist_ok=True)
    gp = os.path.join(exp, "goals.csv")
    t = F.goal_table(gp)
    params = F.fit(t)
    xs = F.xstar_table(t, params, n_boot)
    res = {}
    for cls, v in xs.items():
        s = t[t.cls == cls]
        lo, hi = float(s.W.min()), float(s.W.max())
        ci = v.get("x_star_calls_ci")
        ident = bool(ci is not None and lo <= ci[1] <= hi)
        res[cls] = dict(v, observed_W=[lo, hi], identified=ident, n_goals=int(len(s)),
                        points=sorted(str(p) for p in s.point.unique()))
    prov = dict(data_tag=tag, export=exp, goals_sha256=F._sha(gp), n_boot=int(n_boot), rule=RULE,
                unit="total calls (model plus tool) completed in attempt 1",
                label="offline calibrated rule (R5 decide, fixed parameters per fold, posterior mean)")
    json.dump(dict(provenance=prov, xstar=res), open(os.path.join(out, "r5_xstar_mid.json"), "w"), indent=1)

    npath = os.path.join(out, "r5_numbers.json")
    nums = json.load(open(npath)) if os.path.exists(npath) else {}
    nums["xstarMid"] = res
    nums["xstarMidProvenance"] = prov
    for cls, v in res.items():
        k = CAMEL.get(cls)
        if k is None:
            continue
        nums[f"xstarMid{k}"] = v["x_star_calls"] if v["identified"] else None
        nums[f"xstarMid{k}CI"] = v["x_star_calls_ci"] if v["identified"] else None
        nums[f"xstarMid{k}Identified"] = v["identified"]
    json.dump(nums, open(npath, "w"), indent=1)

    for cls, v in res.items():
        print(f"{cls:16s} x* {v['x_star_calls']:.1f} CI {v['x_star_calls_ci']} W {v['observed_W']} "
              f"identified {v['identified']} n {v['n_goals']} points {v['points']}")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], int(a[3]) if len(a) > 3 else 300)
