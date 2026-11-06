# Recovery follow-up analyses

scripts/analyses.py, calib.py, calibrated.py, extra.py, and prefix.py compute follow-up quantities from the frozen experiment data. out/ holds the saved summaries consumed by the plotting code. common.py loads the original paper_numbers.py definitions and opens SQLite with immutable=1. It never writes to the database.

By default the data root is inputs and the definitions module is loaded from the repository’s scripts/ directory. Set RAF_DATA_ROOT and RAF_DEFINITION_DIR to use another frozen data copy and definition module. The analysis expects data/frozen_oct23/experiments_frozen_oct23.db and data/frozen_oct23/ledgers beneath the data root. Use the definition module shipped with that frozen dataset to preserve the original estimates.

Run the analyses from a separate scripts/ working directory with a sibling out/ directory. Outputs use ../out relative to that working directory, so running elsewhere preserves the tracked summaries:

```bash
mkdir -p /var/tmp/raf-recovery-analysis/{scripts,out}
cd /var/tmp/raf-recovery-analysis/scripts
python3 /path/to/repository/analysis/recovery/scripts/analyses.py
```

Use the environment installed from the repository's requirements.txt. calib.py prints calibration JSON to standard output. Save it to ../out/calib.json before running calibrated.py. extra.py and prefix.py read the database independently. calibrated.py reads ../out/calib.json. The scripts retain the original sampling and energy definitions.

From the repository root, draw the alternative analysis plots with:

```bash
python analysis/recovery/scripts/draw_data_figures.py output/analysis
```

It reads the saved summaries in out/ and draws recovery-results, resume-cost,
and heldout-policy. The held-out comparisons are embedded summary values in
the plotter. The top-level `python reproduce.py` command draws both these
plots and the five figures in scripts/figures/recovery/.
