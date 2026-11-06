# Exported recovery measurements

This export contains 4,712 goals and 65,482 model calls from the frozen study
database. It contains no prompts or model responses. `scripts/export_dataset.py`
is the exporter and `scripts/paper_numbers.py` supplies energy and selection
definitions. The database SHA256 is
`d5fa57f5a4f0ff5e8c48ff6788cb009ee887f2accb5793b55dfba1779b5dbbf5`.

`SHA256SUMS` records the CSV and totals-file checksums. The CSV bytes are
unchanged from the original dataset archive.

## Goals

`goals.csv` has one row per selected valid goal. Within each study the latest
ledger record wins for the study's item, policy, and arm keys. Records with a
validity code are excluded.

| Columns | Meaning |
| --- | --- |
| `study`, `goal_id`, `task` | Study, database goal identifier, and task identifier |
| `class`, `observable_class` | Injected failure class and class visible to the recovery controller |
| `position` | Failure point, such as early or late |
| `option`, `arm`, `rep` | Recovery option, study arm, and repetition when recorded |
| `outcome` | Latest correctness-check result, 1 for pass and 0 for fail |
| `board_j`, `package_j` | Above-idle board and CPU-package energy, summed over all attempts |
| `attempts` | Number of attempts |
| `calls_total`, `calls_model` | Model plus tool calls, and model calls, in attempt 1 |
| `last_prompt_tokens` | Prompt tokens of the last model call in attempt 1 |
| `fired_phase` | Phase in which the failure was injected, when recorded |
| `tok_uncached_rest` | Uncached prompt tokens from recovery through the end of the goal, when available |

Board energy uses the mean `DC_INPUT` power for each run, subtracts that run's
idle baseline, and multiplies by duration. Energy per successful goal is total
energy divided by the number of correct goals, including energy spent on
failed goals in the numerator.

## Model calls

`calls.csv` identifies each call by `study`, `goal_id`, `attempt`, and `step`.
It records `prompt_tokens`, `cached_tokens`, `completion_tokens`, and
`board_j`. Cached tokens are paired to calls only when the recorded counts
match. Call energy uses samples inside the call window with the idle baseline
subtracted. Empty values indicate unavailable measurements.

## Populations

| Study | Goals | Model calls |
| --- | ---: | ---: |
| pilot | 350 | 4,196 |
| e1 | 1,050 | 15,371 |
| e1b | 960 | 12,642 |
| e2 | 510 | 7,336 |
| e2b | 216 | 3,187 |
| e3 | 666 | 8,979 |
| m3 | 192 | 2,407 |
| m4 | 288 | 4,221 |
| mid | 240 | 3,485 |
| samp1 | 80 | 1,220 |
| samp2 | 80 | 1,222 |
| samp3 | 80 | 1,216 |

These are export populations. Individual comparisons apply further task,
failure-class, or policy selections. See the [study map](../README.md) and the
analysis scripts before combining rows.

`totals_per_study.json` records the selected export counts and energy totals.
`totals.json` is an earlier summary of the broader run population, including
5,300 goals run and 5,095 valid goals. Its totals are not row counts for these
CSVs.
