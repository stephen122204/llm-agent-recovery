"""EAR and token_rule modes: vendored hashes, selector routing, token arithmetic."""

import hashlib
import json
import os
import sys

PKG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "earctl")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from earctl import Controller  # noqa: E402


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def test_vendored_ear_files_match_sources():
    with open(os.path.join(PKG, "_vendor", "SOURCES.json")) as fh:
        src = json.load(fh)
    for name in ("ear.py", "token_rule.py"):
        assert _sha(os.path.join(PKG, "_vendor", name)) == src["files"][name]["sha256"]
    for name in ("controller_params_v2.json", "selector_lr_v2.json"):
        assert _sha(os.path.join(PKG, "params", name)) == src["params"][name]["sha256"]


def test_default_mode_is_ear_with_v2():
    d = Controller.load().decide(failure_class="json_parse", calls_done=10)
    assert d["mode"] == "ear"
    assert d["params_version"] == Controller.load().params_version
    assert d["decider_used"] == "token_rule"
    assert 0.5 < d["p"] < 0.6


def test_silent_detected_goes_to_mean():
    d = Controller.load().decide(failure_class="silent_detected", calls_done=10)
    assert d["decider_used"] == "beta_mean"
    assert d["p"] < 0.5


def test_token_rule_picks_fewest_tokens():
    d = Controller.load().decide(failure_class="tool_error", calls_done=12, mode="token_rule")
    t = d["predicted_uncached_tokens"]
    assert d["option"] == min(sorted(t), key=lambda o: t[o])


def test_ear_equals_token_rule_when_routed_to_tokens():
    ctl = Controller.load()
    for c in ("json_parse", "rate_limit", "timeout", "tool_error"):
        for n in (6, 20, 33):
            assert ctl.decide(failure_class=c, calls_done=n)["option"] == \
                ctl.decide(failure_class=c, calls_done=n, mode="token_rule")["option"]
