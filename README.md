# LLM agent recovery

This repository accompanies *Repeating Work Can Lower Energy per Successful Goal in LLM Agents*. When a model or tool call fails partway through a task, should the agent start over, repeat the interrupted turn, or continue from the failure? Repeating less work saves some computation, but it also changes what the agent does next and whether it finishes correctly. We compare recovery choices by **energy per successful goal**: the total board energy above idle for all runs, including failed runs, divided by the number of correct completions.

The [experiment drivers](experiments/README.md) inject early and late failures and record what happens under each recovery choice. The [measurement exports](data/dataset/README.md) give the energy and outcome of individual runs. The [analysis](analysis/) uses those records to compare recoveries, and the [paper figures](figures/paper/) show the results. We then evaluate whether a controller can use information available at the failure to choose a recovery on new tasks. The [`earctl` controller](earctl/) and its recorded decisions are included here, so the choices can be replayed alongside their measured outcomes.

## Reproduce Table 1

Clone this repository and run the following command with Python 3. It needs only the standard library and the included measurements.

```bash
git clone https://github.com/stephen122204/llm-agent-recovery.git
cd llm-agent-recovery
python3 analysis/late_tool_recovery.py
```

This comparison uses 30 Qwen3 30B tasks per recovery, each interrupted by one late tool error with the prefix cache retained. Resuming costs **1,208 J per run** and succeeds on **24 of 30** tasks. Repeating the interrupted turn costs **1,295 J per run** and succeeds on **27 of 30**. Once failed runs count, repeating the turn uses **1,439 J per successful goal**, compared with **1,510 J** for resuming. The same command also reports restarting and resuming with a correction notice.

## Experiments and results

| Question | Experiment and evidence |
| --- | --- |
| When is restarting cheaper than continuing? | Main recovery batches `e1` and `e1b`, plus model comparisons `m3` and `m4`. Use the [goal and call exports](data/dataset/README.md), [model and serving settings](data/r2/provenance_studies.tsv), and [recovery comparisons](analysis/recovery/README.md). |
| What changes when only the interrupted turn is repeated? | [Failure injection and recovery operations](experiments/platform/alems-plugin-bfcl/alems_plugin_bfcl/raf_hooks.py), [study configurations](experiments/platform/scripts/raf), and the same matched failure comparisons. |
| How much energy does retaining the cache save? | [GB10 and A100 call measurements](data/sweep), [fit summaries](data/summaries), and the [sweep plot](scripts/figures/f9_sweep.py). GB10 measures board energy and A100 measures GPU energy. |
| How do recovery rules perform on held-out tasks? | [Held-out task configuration](experiments/platform/scripts/raf/e3_gn100.yaml), [fitting scripts](experiments/fitting/scripts/raf), [released controller and decision records](earctl), and [held-out summaries](data/r7). The paired comparison uses 27 complete tasks and 108 goals per policy. The full study contains 28 tasks and 111 goals per policy. |
| Which additional conditions were measured? | The [study guide](data/README.md) identifies the pilot, wrong-step, middle-position, sampling, and additional-model studies, and maps the identifiers to their saved analyses. |

The main [measurement export](data/dataset) contains 4,712 goals and 65,482 calls. The smaller plotting exports in [data/figdata](data/figdata) cover different populations. Verify the main export with `(cd data/dataset && shasum -a 256 -c SHA256SUMS)`.

## Draw the figures

The [six paper figure PDFs](figures/paper) are included for comparison. To redraw the five figures covered by the primary plotting scripts and three alternative plots, including the resume-cost breakdown:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python reproduce.py
python scripts/figures/f9_sweep.py --out output/sweep
```

The first command that draws figures, `python reproduce.py`, writes five figure pairs to `output/figures/` and three alternative pairs to `output/analysis/`. The sweep command writes its context-length plot to `output/sweep/`. The scripts use Arial regular and bold. If Arial is outside the system font search path, set `RAF_FONT_DIR` to a directory containing those font files. The redraws use saved summaries and plotting constants. The [follow-up analyses](analysis/recovery) document the inputs needed to recompute the estimates and confidence intervals.

## Replay the controller

The [controller package](earctl/) includes its source, fitted parameters, tests, and recorded decision inputs.

To repeat the published checks on a CPU:

```bash
cd earctl
python -m pip install --no-deps .
earctl-parity --mode ear --params src/earctl/params/controller_params_v2.json --decisions tests/fixtures/e3_decisions.jsonl
earctl-parity --mode token_rule --params src/earctl/params/controller_params_r5-1.json --decisions tests/fixtures/e3_decisions.jsonl
earctl-parity --mode thompson --params src/earctl/params/controller_params_r5-1.json --decisions tests/fixtures/e3_decisions.jsonl
```

Each command should report `PARITY PASS: 111 of 111 identical`. This checks that the controller selects the same options for the recorded inputs. To evaluate the energy and correctness of those choices, use the `e3` rows in the [goals export](data/dataset/goals.csv).

## Rerun the hardware experiments

[experiments/](experiments/README.md) contains the BFCL plugin, recovery hooks, task selection, failure schedules, configurations, fitting code and a file index for the RAF platform releases. The hardware drivers use the [included ALEMS runtime and plugins](experiments/platform), a configured model server, and energy metering. See the [offline input guide](analysis/r5/INPUTS.md) for the full database, ledgers and original task inputs required by particular analyses. Those inputs and model weights are not part of the measurement export.

## Citation

The paper authors are Deepak Panigrahy, Stephen Abkin, Aakash Tyagi, David Kebo Houngninou, and Rabi Mahapatra. The study and experiment platform originated with the ALEMS team. See [CITATION.cff](CITATION.cff).

## License

Original RAF code is licensed under [MIT](LICENSE). Original RAF data and figures are licensed under [CC BY 4.0](LICENSE-DATA). Bundled software and benchmark materials retain their [upstream licenses](REUSE.md).
