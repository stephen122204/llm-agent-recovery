"""
Stub of the platform adapter, written for earctl (not vendored).

The vendored ear.py and token_rule.py import _load_beta from here. The
platform adapter also wires the learned estimator and the fail closed
wrapper; earctl ships neither. The library itself never calls this: the
Controller hands its own BetaP to the vendored code.
"""

import os

from .beta_p import BetaP

PARAMS_ENV = "EAR_PARAMS"


def _load_beta() -> BetaP:
    """BetaP from the file in EAR_PARAMS, else the shipped params v2."""
    path = os.environ.get(PARAMS_ENV) or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "params", "controller_params_v2.json")
    return BetaP.from_file(path)
