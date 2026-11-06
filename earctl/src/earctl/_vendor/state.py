"""
Stub of the platform state builder, written for earctl (not vendored).

build_state reads a live agent run (the executor). Only the in goal wrappers
of the vendored ear.py and token_rule.py call it; the library never does.
"""


def build_state(executor, attempt, previous):
    raise RuntimeError("build_state needs a live agent run; in earctl use Controller.decide")
