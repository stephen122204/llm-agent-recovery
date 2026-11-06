# Study data

`dataset/` contains the per-goal and per-call export. `figdata/` contains a
different, smaller export for plotting. Their columns and populations differ,
so use each with the scripts that name it as an input.

## Study identifiers

| Identifier | Study |
| --- | --- |
| `pilot` | Pilot tasks |
| `e1`, `e1b` | Main recovery comparisons, including the separate rollback batch |
| `e2`, `e2b` | Controller training and follow-up comparisons |
| `e3` | Online held-out evaluation |
| `mid` | Failures placed in the middle of tasks |
| `m3` | Mistral model comparison |
| `m4` | gpt-oss model comparison |
| `samp1`, `samp2`, `samp3` | Sampling repetitions |

Recovery codes are `FR` for restart, `SR` for resume, `RB` for rollback,
and `SG` for grounded resume. Suffixes `_warm` and `_cold` identify cache
conditions. `B0` is the no-injected-failure baseline.

## Saved analysis

These directories retain the identifiers used by the original scripts and
provenance records:

| Directory | Contents |
| --- | --- |
| `r2/` | Excluded steps, model markers, study provenance, and pilot configuration code |
| `r4/` | Offline recovery decisions for additional models |
| `r5/`, `r5tok/` | Main offline fits and token-rule comparisons |
| `r5mid/`, `r5m3/`, `r5m4/` | Middle-position and additional-model fits |
| `r5sweep/`, `r5samp/` | Context sweep and sampling fits |
| `r5sel/` | Controller and selector parameters |
| `r6/` | Selection, exploration, overhead, and changed-context summaries |
| `r7/` | Additional summaries and decision-parity results |
| `summaries/` | Original `numbers_auto.json` and `numbers_extra.json`, including provenance |

Files ending in `.orig.json` and `r5_numbers_r5-1.json` are earlier comparison
inputs retained for the scripts that compare them. They are not replacement
estimates for the current summaries. Source paths in the summaries are portable labels for the original inputs.
