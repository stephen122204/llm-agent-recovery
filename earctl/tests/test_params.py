"""
Shipped parameters: hash matches SOURCES.json and manifest; the controller loads them.
Run: pytest tests -q
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from earctl import Controller  # noqa: E402

PKG = ROOT / "src" / "earctl"
PARAMS = PKG / "params" / "controller_params_r5-1.json"
MANIFEST = PKG / "params" / "manifest_r5-1.json"


def test_params_hash_recorded():
    sha = hashlib.sha256(PARAMS.read_bytes()).hexdigest()
    src = json.load(open(PKG / "_vendor" / "SOURCES.json"))["params"]["controller_params_r5-1.json"]
    assert sha == src["sha256"]
    assert sha == json.load(open(MANIFEST))["params_sha256"]


def test_params_load_and_decide():
    ctl = Controller.load(str(PARAMS), str(MANIFEST))
    assert ctl.params_version == "r5-1"
    for cls in ("timeout", "rate_limit", "tool_error", "json_parse", "silent_detected"):
        d = ctl.decide(failure_class=cls, calls_done=6, tokens_context=3000, mode="mean")
        assert d["option"] in ("FR_warm", "FR_cold", "SR_warm", "SR_cold", "RB_warm",
                               "RB_cold", "SG_warm", "SG_cold", "ABANDON")
