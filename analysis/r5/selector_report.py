"""RAF R5: SELECTOR_REPORT_V2.md from rules_v2.json (fit_selector.py output).
Usage: python selector_report.py OUT_DIR
"""
import json
import os
import sys


def f(x, d=1):
    return "n/a" if x is None else f"{x:.{d}f}"


def sv(b):
    return "n/a" if not b else f"{f(b['value'])} [{f(b['ci'][0])}, {f(b['ci'][1])}] ({b['n_tasks']} tasks)"


def main(out):
    R = json.load(open(os.path.join(out, "rules_v2.json")))
    S, E = R["selector"], R["evaluation"]
    L = ["# EAR selector v2 (logistic regression) and rules compared (R5, offline, training tasks only)", "",
         f"Snapshot {R['snapshot']} sha256 {R['snapshot_sha256']}; held out list sha256 {R['heldout_sha256']}; "
         f"training tasks {R['training_tasks']}, goals {R['goals']}, overlap with held out 0.",
         f"Params v2 sha256 {R['params_sha256']}.", "",
         "## Selector", "",
         f"Fit: {S['fit']}. Chosen C {S['C']}. Threshold {S['threshold']}.",
         f"Decision: {S['decision']}.", f"Encoding: {S['encoding']}.", f"Label: {S['label']}.", "",
         "| Feature | Coefficient |", "|---|---|"]
    L += [f"| {n} | {c:.6g} |" for n, c in zip(S["features"], S["coef"])]
    L += [f"| intercept | {S['intercept']:.6g} |", ""]
    icpt, wcalls = S["intercept"], S["coef"][-1]
    L += [f"Calls weight: {wcalls:.4g} per call done (log odds of tokens).", "",
          "Per class pick (z = intercept + class coefficient + calls weight times calls done; tokens if p > threshold):", "",
          "| Class | z at 0 calls | Pick at 0 calls | Calls done where the pick flips |", "|---|---|---|---|"]
    for n, c in zip(S["features"][:-1], S["coef"][:-1]):
        z0 = icpt + c
        flip = (-z0 / wcalls) if wcalls else None
        pick = "uncached_tokens" if z0 > 0 else "cost_model_mean"
        fl = "none (flip below 0)" if flip is None or flip <= 0 else f"{flip:.0f}"
        L.append(f"| {n[4:]} | {z0:.4f} | {pick} | {fl} |")
    L += ["",
          "## Offline evaluation against always using the cost model (outer grouped CV by task)", "",
          f"Blocks {E['blocks']}, tasks {E['tasks']}; share of blocks where tokens were better {f(E['label_share_tokens_better'],3)}.",
          f"Grouped CV accuracy {f(E['grouped_cv_accuracy'],3)} (always cost model {f(E['accuracy_always_cost_model'],3)}, "
          f"always tokens {f(E['label_share_tokens_better'],3)}).",
          f"Selector used tokens in {E['blocks_selector_uses_tokens']} of {E['blocks']} blocks.", "",
          "| Method | J per successful goal | Success | Saving vs cost model [95% CI] |", "|---|---|---|---|",
          f"| cost model (mean, E3 inputs) | {f(E['EpS_cost_model'],0)} | {f(E['success_cost_model'],3)} | reference |",
          f"| selector | {f(E['EpS_selector'],0)} | {f(E['success_selector'],3)} | {sv(E['saving_selector_vs_cost_model'])} |",
          f"| tokens always | {f(E['EpS_tokens'],0)} | {f(E['success_tokens'],3)} | {sv(E['saving_tokens_vs_cost_model'])} |",
          "", "## Every rule compared (out of fold, all blocks)", "",
          "model = cost model with context tokens at failure (O3, not live in E3); model_e3inputs = EAR's cost model.", "",
          "| Rule | Blocks | J per successful goal | Success |", "|---|---|---|---|"]
    for m, v in sorted(R["overall_rules"].items(), key=lambda kv: kv[1]["EpS"] or 1e18):
        L.append(f"| {m} | {v['blocks']} | {f(v['EpS'],0)} | {f(v['success'],3)} |")
    p = os.path.join(out, "SELECTOR_REPORT_V2.md")
    open(p, "w").write("\n".join(L) + "\n")
    print(p)


if __name__ == "__main__":
    main(sys.argv[1])
