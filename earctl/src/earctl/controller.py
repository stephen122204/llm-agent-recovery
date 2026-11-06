"""
Energy aware recovery controller for agentic LLM workflows.

A thin wrapper around the controller that ran in the RAF study. The
decision itself is made by the vendored, byte identical code of R6 (beta_p)
and R5 (predict): this module only builds the inputs and formats the answer.

    from earctl import Controller
    ctl = Controller.load("controller_params.json")
    d = ctl.decide(error="HTTP 429 Too Many Requests", calls_done=7)
    d["option"]   # for example "SR_warm": step resume with a warm cache

Options are depth x cache: FR (full restart), SR (step resume), RB (roll back
to the start of the failed turn), SG (state grounded resume); warm or cold
cache; or ABANDON when even the best option costs more than the class budget.

Modes:
  ear       the default: the selector (selector_lr_v2.json) gives p from the
            failure class and calls done; p above the threshold uses
            token_rule, otherwise mean. In effect the token prediction for
            every class except silent_detected.
  token_rule  the option with the fewest predicted uncached tokens
            (tok_a + tok_b x calls_done from the params).
  thompson  the online rule of the study: one seeded draw per option from
            Beta(prior + successes, prior + failures). Pass the history
            counts and a seed to reproduce a decision exactly.
  mean      deterministic: the posterior mean instead of a draw (the offline
            rule). For users without history or who need repeatable choices.
"""

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ._vendor import ear as _ear
from ._vendor import raf_history as _hist
from ._vendor import token_rule as _tr
from ._vendor.base import ABANDON, OPTIONS, WORK_SOURCE_CALLS, FailureState
from ._vendor.beta_p import BetaP
from .classify import UNKNOWN, classify, observable

MODES = ("ear", "token_rule", "thompson", "mean")
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PARAMS = os.path.join(HERE, "params", "controller_params_v2.json")
DEFAULT_SELECTOR = os.path.join(HERE, "params", "selector_lr_v2.json")


class Controller:
    """Chooses a recovery option with the lowest expected energy per achieved goal."""

    def __init__(self, params: Dict[str, Any], manifest: Optional[Dict[str, Any]] = None,
                 selector_path: Optional[str] = DEFAULT_SELECTOR) -> None:
        self._beta = BetaP(params)
        self.params = params
        self.manifest = manifest or {}
        self.selector, self.selector_sha256 = _ear.load_selector(selector_path)

    @classmethod
    def load(cls, params_path: str = DEFAULT_PARAMS, manifest_path: Optional[str] = None,
             selector_path: Optional[str] = DEFAULT_SELECTOR) -> "Controller":
        with open(params_path) as fh:
            params = json.load(fh)
        manifest = None
        if manifest_path:
            with open(manifest_path) as fh:
                manifest = json.load(fh)
        return cls(params, manifest, selector_path)

    @property
    def params_version(self) -> str:
        return self._beta.version

    def state(self, failure_class: str, calls_done: int, attempt: int = 2,
              tokens_context: Optional[int] = None, tokens_cached: Optional[int] = None,
              previous_options: Sequence[str] = ()) -> FailureState:
        """The vendored FailureState; it rejects plan only class labels."""
        return FailureState(failure_class=failure_class, attempt=attempt,
                            calls_done=int(calls_done), tokens_context=tokens_context,
                            tokens_cached=tokens_cached, joules_done=None,
                            work_source=WORK_SOURCE_CALLS, turns_done=0, turn_starts=(),
                            previous_options=tuple(previous_options))

    def decide(self, error: Optional[str] = None, calls_done: int = 0, *,
               failure_class: Optional[str] = None, attempt: int = 2,
               tokens_context: Optional[int] = None, tokens_cached: Optional[int] = None,
               previous_options: Sequence[str] = (), counts: Optional[Dict[str, Any]] = None,
               seed: Optional[int] = None, mode: str = "ear",
               options: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        """
        Choose a recovery option.

        error or failure_class gives the class (failure_class wins); calls_done
        is model plus tool calls before the failure. counts maps "class|option"
        to [successes, failures] from your own history (record_outcome builds
        it). In thompson mode a missing seed is drawn and returned so the
        decision can be replayed.
        """
        if mode not in MODES:
            raise ValueError("mode must be one of %s" % (MODES,))
        cls = observable(failure_class) if failure_class else classify(error)
        opts = list(options) if options is not None else list(OPTIONS)
        st = self.state(cls, calls_done, attempt, tokens_context, tokens_cached, previous_options)
        counts = counts or {}
        if mode in ("ear", "token_rule"):
            return self._decide_ear(mode, cls, int(calls_done), attempt, st)
        if mode == "thompson":
            if seed is None:
                seed = int.from_bytes(os.urandom(8), "big")
            d = self._beta.decide(st, opts, counts=counts, seed=seed)
        else:
            seed = 0
            means = {}
            for o in self._beta.candidates(st, opts):
                if o in st.previous_options:
                    continue                 # tried options keep the repeat estimate
                a, b = self._beta.posterior(st, o, counts)
                means[o] = a / (a + b)
            d = self._beta.decide(st, opts, counts=counts, seed=seed, p_override=means,
                                  name="beta_mean")
        scores = []
        for s in d.scores:
            src = "mean" if (mode == "mean" and s.p_source == "laya") else s.p_source
            scores.append({"option": s.option, "p_success": s.p, "energy_j": s.e_pred,
                           "j_per_success": s.j_pred, "p_source": src})
        return {"option": d.option, "failure_class": cls, "mode": mode, "seed": seed,
                "calls_done": int(calls_done), "attempt": attempt,
                "params_version": d.params_version, "x_star_calls": d.x_star_calls,
                "scores": scores, "class_known": cls != UNKNOWN}

    def _tokens(self, cls: str, calls_done: int) -> Dict[str, Any]:
        """The vendored token_rule arithmetic with this controller's params."""
        tr = _tr.TokenRule()
        tr._beta = self._beta
        return tr.choose(cls, calls_done)

    def _decide_ear(self, mode: str, cls: str, calls_done: int, attempt: int,
                    st: FailureState) -> Dict[str, Any]:
        """EAR (the routing of the vendored ear.py) or token_rule alone. The
        vendored functions decide; this method only formats the answer."""
        out: Dict[str, Any] = {"failure_class": cls, "mode": mode, "calls_done": calls_done,
                               "attempt": attempt, "params_version": self._beta.version,
                               "class_known": cls != UNKNOWN, "seed": 0}
        p = thr = None
        if mode == "ear":
            if self.selector is None:
                raise ValueError("mode ear needs a readable selector file (selector_path)")
            x = _ear.features(self.selector, cls, calls_done)
            p = _ear.probability(self.selector, x)
            thr = float(self.selector.get("threshold", 0.5))
            out.update(p=p, threshold=thr, selector_sha256=self.selector_sha256)
        if mode == "token_rule" or p > thr:
            res = self._tokens(cls, calls_done)
            out.update(option=res["option"], decider_used="token_rule",
                       predicted_uncached_tokens=res["tokens"], token_source=res["source"],
                       fallback_reason=res["reason"], scores=[])
            return out
        e = _ear.Ear()
        e._beta = self._beta
        d, means = e.mean_decision(st)
        out.update(option=d.option, decider_used="beta_mean", means=means,
                   x_star_calls=d.x_star_calls,
                   scores=[{"option": s.option, "p_success": s.p, "energy_j": s.e_pred,
                            "j_per_success": s.j_pred, "p_source": s.p_source} for s in d.scores])
        return out


def record_outcome(counts: Dict[str, List[int]], decisions: Sequence[Sequence[str]],
                   passed: bool) -> Dict[str, List[int]]:
    """
    Update history counts after a goal ends, with the study's counting rule.

    decisions: the (failure_class, option) pairs chosen in this goal, in
    attempt order. The last option of a passed goal counts as a success;
    every other one as a failure (vendored raf_history._credit).
    """
    _hist._credit(counts, [(observable(c), o) for c, o in decisions], bool(passed))
    return counts


__all__ = ["Controller", "record_outcome", "ABANDON", "OPTIONS", "MODES"]
