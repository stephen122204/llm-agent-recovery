"""
Tests for earctl. Standard library plus pytest; no engine, no store, no network.
Run: pytest tests -q
"""

import hashlib
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from earctl import Controller, classify, record_outcome  # noqa: E402
from earctl._vendor.base import OPTIONS  # noqa: E402
from earctl._vendor.beta_p import BetaP  # noqa: E402
from earctl.parity import replay  # noqa: E402

VENDOR = ROOT / "src" / "earctl" / "_vendor"


def params():
    opts = {}
    for i, o in enumerate(o for o in OPTIONS if o != "ABANDON"):
        opts[o] = {"alpha": 2.0 + i, "beta": 1.0 + (i % 3), "e2_a": 100.0 + 10 * i,
                   "e2_b": 5.0 + i, "e2_g": 0.0, "e2_h": 0.0, "p_repeat_after_fail": 0.3}
    return {"params_version": "test", "data_tag": "unit",
            "classes": {"_default": {"options": opts, "_budget_j": 5000.0},
                        "timeout": {"options": opts, "_x_star_calls": 3.0, "_budget_j": 5000.0}}}


def test_vendored_files_are_byte_identical():
    src = json.load(open(VENDOR / "SOURCES.json"))["files"]
    for name, meta in src.items():
        got = hashlib.sha256((VENDOR / name).read_bytes()).hexdigest()
        assert got == meta["sha256"], name


def test_classify():
    assert classify("HTTP 429 Too Many Requests") == "rate_limit"
    assert classify("request timed out after 30 s") == "timeout"
    assert classify("JSONDecodeError: Expecting value") == "json_parse"
    assert classify("Tool raised an exception") == "tool_error"
    assert classify("injected json_parse") == "json_parse"
    assert classify("") == "unknown"


def test_thompson_matches_vendored_beta_p_exactly():
    ctl = Controller(params())
    raw = BetaP(params())
    rng = random.Random(3)
    for _ in range(200):
        cls = rng.choice(["timeout", "rate_limit", "unknown"])
        calls = rng.randint(0, 12)
        counts = {"%s|%s" % (cls, o): [rng.randint(0, 9), rng.randint(0, 9)]
                  for o in OPTIONS if rng.random() < 0.5}
        seed = rng.getrandbits(64)
        prev = tuple(rng.sample([o for o in OPTIONS if o != "ABANDON"], rng.randint(0, 2)))
        st = ctl.state(cls, calls, 2 + len(prev), None, None, prev)
        want = raw.decide(st, list(OPTIONS), counts=counts, seed=seed).option
        got = ctl.decide(failure_class=cls, calls_done=calls, attempt=2 + len(prev),
                         previous_options=prev, counts=counts, seed=seed, mode="thompson")["option"]
        assert got == want


def test_mean_mode_is_deterministic_and_uses_posterior_mean():
    ctl = Controller(params())
    a = ctl.decide(error="timeout", calls_done=8, mode="mean")
    b = ctl.decide(error="timeout", calls_done=8, mode="mean")
    assert a == b
    for s in a["scores"]:
        assert s["p_source"] == "mean"
    # Lowest energy per success under posterior means.
    best = min((s for s in a["scores"] if s["j_per_success"] is not None),
               key=lambda s: (s["j_per_success"], s["option"]))
    assert a["option"] == best["option"]


def test_xstar_gate_restricts_to_restart():
    ctl = Controller(params())
    d = ctl.decide(failure_class="timeout", calls_done=1, mode="mean")
    assert all(s["option"].startswith("FR_") for s in d["scores"])


def test_plan_only_label_is_made_observable():
    ctl = Controller(params())
    d = ctl.decide(failure_class="persistent_timeout", calls_done=5, mode="mean")
    assert d["failure_class"] == "timeout"
    d2 = ctl.decide(failure_class="wrong_model_step", calls_done=5, mode="mean")
    assert d2["failure_class"] == "silent_detected"


def test_abandon_when_over_budget():
    p = params()
    p["classes"]["timeout"]["_budget_j"] = 1.0
    d = Controller(p).decide(failure_class="timeout", calls_done=8, mode="mean")
    assert d["option"] == "ABANDON"


def test_record_outcome_counting_rule():
    c = record_outcome({}, [("timeout", "SR_warm"), ("timeout", "FR_warm")], passed=True)
    assert c == {"timeout|SR_warm": [0, 1], "timeout|FR_warm": [1, 0]}


def test_parity_replay_on_logged_decisions():
    ctl = Controller(params())
    raw = BetaP(params())
    rows, rng = [], random.Random(9)
    for g in range(40):
        prev = []
        for att in (2, 3):
            cls, calls, seed = "timeout", rng.randint(0, 10), rng.getrandbits(64)
            counts = {"timeout|SR_warm": [rng.randint(0, 5), rng.randint(0, 5)]}
            d = raw.decide(ctl.state(cls, calls, att, None, None, tuple(prev)),
                           list(OPTIONS), counts=counts, seed=seed)
            rows.append({"goal_id": g, "decision_attempt": att, "failure_class": cls,
                         "calls_done": calls, "counts": counts, "seed": seed,
                         "option": d.option, "decider_used": "beta_p",
                         "scores": [{"option": s.option, "e_pred": s.e_pred} for s in d.scores]})
            prev.append(d.option)
    res = replay(ctl, rows)
    assert res["parity"] and res["replayed"] == 80 and res["energy_mismatch"] == 0
    rows[0]["option"] = "RB_cold" if rows[0]["option"] != "RB_cold" else "FR_cold"
    assert not replay(ctl, rows)["parity"]
