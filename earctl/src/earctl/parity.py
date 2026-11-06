"""
Parity replay: does this library reproduce every logged E3 controller decision?

Input: JSONL of raf.controller decision payloads (R4's freeze export), one per
line, as the R6 adapter writes them: goal_id, decision_attempt, failure_class,
calls_done, counts, seed, option, decider, decider_used, scores; tokens_context
and tokens_cached when present. Each decision is replayed in thompson mode
from its own logged counts and seed, with previous options rebuilt from the
earlier decisions of the same goal. Parity requires an identical option for
every replayed decision.

    python -m earctl.parity --params controller_params.json --decisions e3_decisions.jsonl
"""

import argparse
import json
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional

from .controller import Controller


def replay(ctl: Controller, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_goal: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    skipped = defaultdict(int)
    for r in rows:
        if r.get("decider_used") not in (None, "beta_p"):
            skipped["decider_%s" % r.get("decider_used")] += 1
            continue
        if r.get("fallback_reason"):
            skipped["fallback"] += 1
            continue
        by_goal[r.get("goal_id")].append(r)
    total, equal, energy_mismatch, mismatches = 0, 0, 0, []
    for goal, recs in by_goal.items():
        recs.sort(key=lambda r: int(r["decision_attempt"]))
        prev: List[str] = []
        for r in recs:
            att = int(r["decision_attempt"])
            d = ctl.decide(failure_class=r["failure_class"], calls_done=int(r["calls_done"]),
                           attempt=att, tokens_context=r.get("tokens_context"),
                           tokens_cached=r.get("tokens_cached"), previous_options=tuple(prev),
                           counts=r.get("counts") or {}, seed=int(r["seed"]), mode="thompson")
            total += 1
            logged_e = {s["option"]: s.get("e_pred") for s in (r.get("scores") or [])}
            mine_e = {s["option"]: s["energy_j"] for s in d["scores"]}
            e_ok = all(logged_e.get(o) is None or mine_e.get(o) is None
                       or abs(logged_e[o] - mine_e[o]) <= 1e-6 * max(1.0, abs(logged_e[o]))
                       for o in logged_e)
            if not e_ok:
                energy_mismatch += 1
            if d["option"] == r["option"]:
                equal += 1
            else:
                mismatches.append({"goal_id": goal, "decision_attempt": att,
                                   "logged": r["option"], "replayed": d["option"],
                                   "energy_matches_log": e_ok})
            prev.append(r["option"])
    return {"replayed": total, "identical": equal,
            "parity": total > 0 and equal == total,
            "energy_mismatch": energy_mismatch, "skipped": dict(skipped),
            "mismatches": mismatches[:50]}


def replay_tokens(ctl: Controller, rows: List[Dict[str, Any]], mode: str) -> Dict[str, Any]:
    """Replay the logged token_rule decisions in mode token_rule or ear.
    Identical: the same option (a logged "keep" equals no option). When the
    token path decided with the params version the run logged, the predicted
    uncached tokens must also be equal."""
    total, equal, token_checked, token_mismatch, mismatches = 0, 0, 0, 0, []
    routed: Dict[str, int] = defaultdict(int)
    skipped: Dict[str, int] = defaultdict(int)
    p_seen: List[float] = []
    for r in rows:
        if r.get("decider_used") != "token_rule":
            skipped["decider_%s" % r.get("decider_used")] += 1
            continue
        d = ctl.decide(failure_class=r["failure_class"], calls_done=int(r["calls_done"]),
                       attempt=int(r.get("decision_attempt") or 2), mode=mode)
        total += 1
        routed[d["decider_used"]] += 1
        if d.get("p") is not None:
            p_seen.append(d["p"])
        t_ok = True
        if (d["decider_used"] == "token_rule" and r.get("params_version") == ctl.params_version
                and r.get("data_tag") == ctl._beta.data_tag):
            token_checked += 1
            lt = r.get("predicted_uncached_tokens") or {}
            mt = d.get("predicted_uncached_tokens") or {}
            t_ok = set(lt) == set(mt) and all(
                abs(float(lt[o]) - float(mt[o])) <= 1e-9 * max(1.0, abs(float(lt[o]))) for o in lt)
            if not t_ok:
                token_mismatch += 1
        mine = d["option"] or "keep"
        if mine == r["option"] and t_ok:
            equal += 1
        else:
            mismatches.append({"goal_id": r.get("goal_id"), "failure_class": r["failure_class"],
                               "calls_done": r["calls_done"], "logged": r["option"],
                               "replayed": mine, "decider_used": d["decider_used"],
                               "tokens_match_log": t_ok})
    return {"mode": mode, "params_version": ctl.params_version, "replayed": total,
            "identical": equal, "parity": total > 0 and equal == total,
            "tokens_checked": token_checked, "token_mismatch": token_mismatch,
            "routed": dict(routed), "p_min": min(p_seen) if p_seen else None,
            "p_max": max(p_seen) if p_seen else None, "skipped": dict(skipped),
            "mismatches": mismatches[:50]}


def flatten(rec: Dict[str, Any], export_tokens: bool = False) -> Dict[str, Any]:
    """A raf.controller payload as is, or a store export row that wraps it in
    "payload" (the E3 freeze export). By default only the payload is used: it
    holds exactly the inputs the controller logged at decision time. With
    export_tokens, tokens_context and tokens_cached of the outer row (added
    by the export from the store, after the run) are copied in."""
    p = rec.get("payload")
    if not isinstance(p, dict):
        return rec
    out = dict(p)
    if export_tokens:
        for k in ("tokens_context", "tokens_cached"):
            if out.get(k) is None and rec.get(k) is not None:
                out[k] = rec[k]
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="replay logged controller decisions")
    ap.add_argument("--params", required=True)
    ap.add_argument("--decisions", required=True, help="JSONL of raf.controller payloads")
    ap.add_argument("--mode", choices=("thompson", "token_rule", "ear"), default="thompson",
                    help="thompson replays the controller rows; token_rule and ear the token_rule rows")
    ap.add_argument("--selector", default=None, help="selector file for --mode ear (default: shipped)")
    ap.add_argument("--export-tokens", action="store_true",
                    help="use tokens_context and tokens_cached of the export row (added after the run); "
                         "default: only what the controller logged")
    a = ap.parse_args(argv)
    ctl = Controller.load(a.params, selector_path=a.selector) if a.selector else Controller.load(a.params)
    rows = [flatten(json.loads(l), a.export_tokens) for l in open(a.decisions) if l.strip()]
    res = replay(ctl, rows) if a.mode == "thompson" else replay_tokens(ctl, rows, a.mode)
    json.dump(res, sys.stdout, indent=2)
    print()
    print("PARITY %s: %d of %d identical" % ("PASS" if res["parity"] else "FAIL",
                                             res["identical"], res["replayed"]))
    return 0 if res["parity"] else 1


if __name__ == "__main__":
    sys.exit(main())
