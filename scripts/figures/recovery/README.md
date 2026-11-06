# Recovery figure generation

These scripts draw recovery-operations, measurement-windows, recovery-results, cache-effects, and heldout-policy as PDF and PNG files. The mechanism diagrams are schematic. The three data figures use the printed summary values embedded in draw_published_data_figures.py. They do not query the experiment database or recompute estimators.

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
RAF_PYTHON="$PWD/.venv/bin/python" bash scripts/figures/recovery/build.sh
```

Outputs go to analysis/recovery/generated/figures/. Pass a directory as the build script's first argument to choose a different destination. The script writes no manuscript files.

Arial must be installed. Alternatively, set RAF_FONT_DIR to a directory containing the Arial regular and bold TTF files. Fonts are not distributed in this repository.

| Filename | Source | Input |
|---|---|---|
| recovery-operations | draw_mechanisms.py | retained conversation, repeated work, and tool-state operations |
| measurement-windows | draw_mechanisms.py | attempt energy measurement boundaries |
| recovery-results | draw_published_data_figures.py | success counts and energy per successful goal |
| cache-effects | draw_published_data_figures.py | cache summary estimates and isolated-call ratios |
| heldout-policy | draw_published_data_figures.py | percentage savings and uncertainty intervals |

Follow-up analysis sources and saved summaries are in analysis/recovery/. The alternative draw_data_figures.py there produces a different panel layout and a resume-cost figure. It is separate from this five-figure set.

The numerical table generators are scripts/paper_numbers.py and scripts/paper_extra.py. They require the frozen database and ledgers and write to a separate output folder.
