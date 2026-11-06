"""RAF R5 (coordinator Oct 19): context range of the calls in the linear energy law fit.
Same call filter as fit_controller_params.main: rows with context_tokens and e_board_j.
Usage: python add_law_ctx.py <export_dir> <r5_numbers.json> <tag>
Merges lawCtxMax, lawCtxPNinetyFive, lawCtxN, lawCtxProvenance into the numbers file.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

import fit_controller_params as F


def main(exp, npath, tag):
    cp = os.path.join(exp, "calls.csv")
    c = pd.read_csv(cp).dropna(subset=["context_tokens", "e_board_j"])
    ctx = c.context_tokens.astype(float)
    nums = json.load(open(npath))
    nums.update(lawCtxMax=float(ctx.max()), lawCtxPNinetyFive=float(np.percentile(ctx, 95)),
                lawCtxN=int(len(ctx)),
                lawCtxProvenance=dict(data_tag=tag, export=exp, calls_sha256=F._sha(cp),
                                      unit="context tokens of a call",
                                      filter="calls with context_tokens and e_board_j (as in the energy law fit)"))
    json.dump(nums, open(npath, "w"), indent=1)
    print(f"lawCtxMax {nums['lawCtxMax']:.0f} lawCtxPNinetyFive {nums['lawCtxPNinetyFive']:.0f} n {nums['lawCtxN']}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
