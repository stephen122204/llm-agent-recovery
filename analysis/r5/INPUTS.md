# Offline analysis inputs

These scripts produced the paper's numbers from the measurement store; the CSVs hold the same per goal and per call values. Included for inspection.

| Script | Inputs it expects |
|---|---|
| replay_token_rules.py | export goals.csv |
| refit_xstar_mid.py | export goals.csv |
| silent_direct.py | export goals.csv |
| sg_lowest.py | export goals.csv |
| model_ci.py | export goals.csv and calls.csv |
| add_law_ctx.py | export calls.csv |
| sweep_fit.py | export goals.csv and the sweep ledger JSONL |
| samp_analysis.py | export goals.csv (sampling and greedy reference) and the sampling ledger JSONL |
| null_check.py | SQLite store and ledger JSONL |
| check_keys.py | ledger JSONL |
| check_valid.py | ledger JSONL |
| rerun_frozen.sh | SQLite store and ledger JSONL (drives every script above) |
| compare_numbers.py | two r5_numbers.json files |
| platform/scripts/raf/export_recovery_store.py | SQLite store and ledger JSONL; writes export goals.csv and calls.csv |
| platform/scripts/raf/recovery_features.py | ledger JSONL (selection rules: latest record per study, item, policy, rep; validity; excluded cells) |
| platform/scripts/raf/fit_controller_params.py | export goals.csv and calls.csv (goal_table, cross_validate, fits) |
| platform/scripts/raf/augment_r5_numbers.py | export goals.csv and calls.csv, plus an existing r5_numbers.json |
| platform/scripts/raf/run_recovery_controller.sh | SQLite store and ledger JSONL (export then fit) |
| platform/scripts/raf/controller_model.py | none (functions used by the fits) |
| platform/alems-plugin-bfcl/alems_plugin_bfcl/decider/predict.py | a controller_params.json (prediction and decision functions) |

The original analysis recorded platform revision `0203d7c`. That revision could not be resolved in the current public upstream. The available controller-fitting code from commit `662e69aa89e46faa46a2ae6bff1f43e135ecb3c5` is included in [experiments/fitting](../../experiments/fitting). Use the [platform snapshot](../../experiments/platform) for the recovery plugin. Some fits require the original database, task lists or run ledgers in addition to the CSV exports. Historical fits have not been rerun with the newer fitting snapshot.
