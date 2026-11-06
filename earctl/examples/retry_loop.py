"""
Minimal agent retry loop with earctl.

Replace run_attempt with your agent: it runs one attempt of a goal under a
recovery option and returns (passed, error_text, calls_done).
"""

import random

from earctl import Controller, record_outcome


def run_attempt(option, attempt):
    """Stand in for an agent attempt; returns (passed, error, calls_done)."""
    if option is None:                       # first attempt, no recovery yet
        return False, "HTTP 429 Too Many Requests", 6
    return random.random() < 0.8, "request timed out", 4


def run_goal(ctl, history, max_attempts=4):
    chosen = []                              # (class, option) per decision
    option, attempt = None, 1
    while attempt <= max_attempts:
        passed, error, calls = run_attempt(option, attempt)
        if passed:
            break
        attempt += 1
        d = ctl.decide(error=error, calls_done=calls, attempt=attempt,
                       previous_options=[o for _, o in chosen], counts=history)
        if d["option"] == "ABANDON":
            break
        chosen.append((d["failure_class"], d["option"]))
        option = d["option"]
        print("attempt %d: %s (class %s, seed %d)" % (attempt, option, d["failure_class"], d["seed"]))
    record_outcome(history, chosen, passed)  # learning: counts feed the next goals
    return passed


if __name__ == "__main__":
    import sys
    ctl = Controller.load(sys.argv[1])       # controller_params.json
    history = {}
    for _ in range(3):
        print("goal passed:", run_goal(ctl, history))
    print("history:", history)
