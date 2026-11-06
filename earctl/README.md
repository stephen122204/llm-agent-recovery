# earctl: energy aware recovery for agentic LLM workflows

When an agent step fails, the agent has to decide where to restart.
`earctl` makes that decision with EAR, the decider of the RAF study.
It needs no model, no GPU and no network: a decision is a weighted sum, a table lookup and a little arithmetic, in the Python standard library only.
The decision code is copied from the study's code; `src/earctl/_vendor/SOURCES.json` gives each file's hash as run and as shipped.

## What EAR decides

At a failure EAR returns one recovery option, a depth and a cache:

| Depth | Meaning |
|---|---|
| `FR` | full restart of the goal |
| `SR` | step resume: retry the failed step |
| `RB` | roll back to the start of the failed turn |
| `SG` | state grounded resume |

Each depth comes with a `warm` or `cold` cache, for example `RB_warm`.

## Inputs

Only what is known at the failure:

* the failure class, from the error text or passed as `failure_class`: json_parse, rate_limit, silent_detected, timeout or tool_error (anything else is an unseen class);
* calls done: the number of model plus tool calls before the failure.

## How EAR decides

1. A logistic regression selector (`params/selector_lr_v2.json`) computes p = 1 / (1 + exp(-(intercept + coef · x))), where x is the one hot failure class (all zeros for an unseen class) and the unscaled calls done.
2. If p > 0.5, the token rule decides: the option with the fewest predicted uncached prompt tokens, tok_a + tok_b × calls done, from the parameters.
3. Otherwise the cost model decides in mean mode: the posterior mean success rate of each option, from the priors in the parameters, with the fitted energy law; the option with the lowest expected energy per achieved goal wins.

Stated plainly: in effect EAR is the token prediction for every class except silent_detected, where the cost model in mean mode decides; no significant offline gain on training tasks.
The selector's weight on calls done is small, so within the observed range of calls the choice between the two depends on the class only.

## Quick start

From the unzipped folder, with Python 3.8 or newer. Paste the commands as they are; the block has no comments, so it works in bash and in zsh (the macOS default).

```bash
cd earctl
python3 -m venv .venv
. .venv/bin/activate
pip install .
python -c "from earctl import Controller; d = Controller.load().decide(error='HTTP 429 Too Many Requests', calls_done=7); print(d['option'], d['decider_used'])"
earctl-parity --mode ear --params src/earctl/params/controller_params_v2.json --decisions tests/fixtures/e3_decisions.jsonl
pip install pytest
pytest -q tests
```

Expected results:

* `pip install .` installs earctl with no dependencies outside the Python standard library.
* The `python -c` line prints `RB_warm token_rule`: one EAR decision with the shipped parameters.
* `earctl-parity` prints `PARITY PASS: 111 of 111 identical`: EAR reproduces the 111 logged E3 token rule decisions.
* `pytest` reports no failures; pytest is needed for the tests only.

## Install

```bash
pip install .
```

## Use

```python
from earctl import Controller, record_outcome

ctl = Controller.load()          # the shipped parameters (v2) and selector
d = ctl.decide(error="HTTP 429 Too Many Requests", calls_done=7)
print(d["option"], d["decider_used"], round(d["p"], 4))    # RB_warm token_rule 0.5623
```

Each answer also carries the failure class, the predicted tokens (token rule) or the scores (cost model), and the selector's sha256.
When the token rule has no token fit for a class, `option` is `None`: keep your agent's own recovery policy (the study logged this as `keep`).

## Modes

| Mode | Rule | Use when |
|---|---|---|
| `ear` (default) | the selector chooses the token rule or the cost model in mean mode | the decision as defined above |
| `token_rule` | the option with the fewest predicted uncached prompt tokens | you want the token rule alone |
| `mean` | cost model, posterior mean, deterministic | no history, or you need the same answer every time |
| `thompson` | the study's online controller: one seeded draw per option from the Beta posterior of its success rate | you keep history and want the controller to keep learning |

In `thompson` mode the returned `seed`, together with the `counts` you passed, reproduces the decision exactly.

## Learning from your own runs

The `thompson` and `mean` modes use your history:

```python
history = {}
# after each goal: the (class, option) pairs chosen, in order, and whether the goal passed
record_outcome(history, [("timeout", "SR_warm"), ("timeout", "FR_warm")], passed=True)
d = ctl.decide(error="timeout", calls_done=5, counts=history, mode="thompson")
```

## Calibration

`controller_params_v2.json` (the default) holds, per failure class and option, the prior success counts, the token fit and the energy law fitted on measured runs.
`controller_params_r5-1.json` holds the parameters the E3 study ran with; it is shipped for the parity replays.
The shipped parameters were measured on one model and one machine, named in the manifest.
For another model or machine, measure your own runs with an energy meter and fit new parameters.

## Parity

`earctl-parity` replays logged decisions and reports whether every option is reproduced:

* `--mode ear` and `--mode token_rule` replay the logged token rule decisions; when the parameters carry the params version and data tag the run logged, every predicted token count must also match;
* `--mode thompson` replays the online controller's decisions from their recorded counts and seeds.

The logged E3 decisions are included as `tests/fixtures/e3_decisions.jsonl` (333 rows: 111 per arm; one field, `source`, anonymized). Three replays run from the zip alone:

```bash
earctl-parity --mode ear --params src/earctl/params/controller_params_v2.json --decisions tests/fixtures/e3_decisions.jsonl
earctl-parity --mode token_rule --params src/earctl/params/controller_params_r5-1.json --decisions tests/fixtures/e3_decisions.jsonl
earctl-parity --mode thompson --params src/earctl/params/controller_params_r5-1.json --decisions tests/fixtures/e3_decisions.jsonl
```

Expected: each prints `PARITY PASS: 111 of 111 identical`.

* `ear` and `token_rule` replay the 111 decisions of the E3 token rule arm. The option must be identical; when the parameters carry the params version and data tag the run logged (here r5-1), every predicted token count must also be identical (`tokens_checked` 111, `token_mismatch` 0). With params v2 the options are compared and the token counts are not (`tokens_checked` 0). Scope: these 111 decisions are json_parse (56) and tool_error (55); v2 changes the token fit only for silent_detected and unseen classes, which they do not contain.
* `thompson` replays the 111 decisions of the online controller arm from their logged counts and seeds (`energy_mismatch` 0).

Without installing, run `PYTHONPATH=src python -m earctl.parity` with the same arguments.

## License

Apache 2.0, see `LICENSE`. Copyright 2026 Anonymous Authors.
