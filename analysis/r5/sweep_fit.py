"""RAF R5 (coordinator Oct 20/21): GB10 context sweep law per model, cached and uncached separately.
One measured call per goal: attempt 1, the call whose prompt_tokens equals the planned size.
Cache class from the hit counter field usage.prompt_tokens_details.cached_tokens (> 0 cached, else uncached);
checked against the planned mode. Fits e = a + b c and e = a + b c + d c^2 (c = prompt tokens, e = board J),
bootstrap stratified by size, resampling repeats (1000 draws, seed 0). Quadratic supported only if the CI of d
excludes zero (rule fixed Oct 18). Cached to uncached energy ratio per size. Slope low (2048 to 8192) and
high (16384 to 32672) by linear fit on that range.
Usage: python sweep_fit.py <export_dir> <ledger_dir> <out_dir> <tag>
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

import fit_controller_params as F

B, SEED = 1000, 0
MODEL = {"raf_sweep_qwen": "Qwen", "raf_sweep_m4": "Gptoss"}
LOW, HIGH = (2048, 8192), (16384, 32672)


def fit(x, y, quad):
    X = np.column_stack([np.ones(len(x)), x] + ([x ** 2] if quad else []))
    return np.linalg.lstsq(X, y, rcond=None)[0]


def ci(v):
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def boot_fit(d, quad, rng, cols=("c", "e")):
    th = fit(d[cols[0]].values.astype(float), d[cols[1]].values, quad)
    groups = [g for _, g in d.groupby("size")]
    draws = []
    for _ in range(B):
        s = pd.concat([g.iloc[rng.integers(0, len(g), len(g))] for g in groups])
        draws.append(fit(s[cols[0]].values.astype(float), s[cols[1]].values, quad))
    return th, np.array(draws)


def main(exp, ledir, out, tag):
    os.makedirs(out, exist_ok=True)
    rows = []
    for f in glob.glob(ledir + "/*ledger*.jsonl"):
        if "smoke" in f:
            continue
        for l in open(f):
            if l.strip():
                r = json.loads(l)
                if r.get("study") not in MODEL or r.get("validity"):
                    continue
                u = ((r.get("attempt_meta") or {}).get("1") or {}).get("sweep_usage") or {}
                det = u.get("prompt_tokens_details") or {}
                rows.append(dict(goal_id=r["goal_id"], study=r["study"], size=r["detail"]["size"],
                                 mode=r["detail"]["mode"], rep=r["plan"]["rep"],
                                 cached_tokens=det.get("cached_tokens"), prompt_usage=u.get("prompt_tokens")))
    led = pd.DataFrame(rows).sort_values("goal_id").drop_duplicates(["study", "size", "mode", "rep"], keep="last")
    # The store has no llm_interactions rows for sweep runs; each sweep run is one request,
    # so the energy is the board energy of attempt 1 (run energy minus idle), tokens from the ledger usage.
    gl = pd.read_csv(os.path.join(exp, "goals.csv"))
    gl = gl[gl.attempt == 1][["goal_id", "e_board_j"]].dropna()
    m = gl.merge(led, on="goal_id", how="inner")
    m["prompt_tokens"] = m.prompt_usage
    multi = int((m.prompt_tokens != m["size"]).sum())
    m["cls"] = np.where(m.cached_tokens.fillna(0) > 0, "Cached", "Uncached")
    m["c"] = m.prompt_tokens.astype(float)
    m["e"] = m.e_board_j.astype(float)
    mism = int((m.cls.str.lower() != m["mode"]).sum())
    rng = np.random.default_rng(SEED)
    nums, detail = {}, {}
    for st, M in MODEL.items():
        dm = m[m.study == st]
        for C in ("Uncached", "Cached"):
            d = dm[dm.cls == C]
            if len(d) < 6:
                continue
            p = f"sweep{M}{C}"
            th1, dr1 = boot_fit(d, False, rng)
            th2, dr2 = boot_fit(d, True, rng)
            nums[p + "LinA"] = dict(value=float(th1[0]), ci=ci(dr1[:, 0]))
            nums[p + "LinB"] = dict(value=float(th1[1]), ci=ci(dr1[:, 1]))
            nums[p + "QuadA"] = dict(value=float(th2[0]), ci=ci(dr2[:, 0]))
            nums[p + "QuadB"] = dict(value=float(th2[1]), ci=ci(dr2[:, 1]))
            nums[p + "QuadD"] = dict(value=float(th2[2]), ci=ci(dr2[:, 2]))
            dci = nums[p + "QuadD"]["ci"]
            nums[p + "QuadSupported"] = bool(dci[0] > 0 or dci[1] < 0)
            for nm, (lo, hi) in (("SlopeLow", LOW), ("SlopeHigh", HIGH)):
                s = d[(d["size"] >= lo) & (d["size"] <= hi)]
                if s["size"].nunique() >= 2:
                    th, dr = boot_fit(s, False, rng)
                    nums[p + nm] = dict(value=float(th[1]), ci=ci(dr[:, 1]), sizes=[lo, hi])
            nums[p + "NCalls"] = int(len(d))
            nums[p + "CtxMax"] = int(d.c.max())
            nums[p + "CtxPNinetyFive"] = int(np.percentile(d.c, 95))
            detail[p + "MeanBySize"] = {int(k): float(v) for k, v in d.groupby("size").e.mean().items()}
        cu = dm[dm.cls == "Uncached"].groupby("size").e
        cc = dm[dm.cls == "Cached"].groupby("size").e
        for size in sorted(set(dm[dm.cls == "Cached"]["size"]) & set(dm[dm.cls == "Uncached"]["size"])):
            a, b = cc.get_group(size).values, cu.get_group(size).values
            dr = [rng.choice(a, len(a)).mean() / rng.choice(b, len(b)).mean() for _ in range(B)]
            nums[f"sweep{M}CachedRatio{size}"] = dict(value=float(a.mean() / b.mean()), ci=ci(dr))
    nums["sweepProvenance"] = dict(data_tag=tag, export=exp, goals_sha256=F._sha(os.path.join(exp, "goals.csv")),
                                   calls_sha256=F._sha(os.path.join(exp, "calls.csv")), boot=B, seed=SEED,
                                   calls_used=int(len(m)), goals_in_ledgers=int(len(led)),
                                   class_vs_mode_mismatch=mism, usage_tokens_not_equal_size=multi,
                                   energy="board DC_INPUT of attempt 1 minus idle; one request per sweep run",
                                   cache_class="usage.prompt_tokens_details.cached_tokens > 0",
                                   bootstrap="stratified by size, repeats resampled",
                                   slope_ranges=dict(low=LOW, high=HIGH), detail=detail)
    json.dump(nums, open(os.path.join(out, "r5_numbers.json"), "w"), indent=1)
    for k, v in nums.items():
        if isinstance(v, dict) and "value" in v:
            print(f"{k:40s} {v['value']:.6g} CI {[round(x, 6) for x in v['ci']]}")
        elif k != "sweepProvenance":
            print(f"{k:40s} {v}")
    print("calls used", len(m), "goals in ledgers", len(led), "class vs mode mismatch", mism, "multi", multi)


if __name__ == "__main__":
    main(*sys.argv[1:5])
