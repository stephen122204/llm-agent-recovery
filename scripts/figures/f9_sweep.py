#!/usr/bin/env python3
"""F9: energy per model call against context length, GB10 (board) and A100 (GPU), cached and uncached.

Caption (how to read it; no findings):
  Energy of one model call as the prompt grows, with the prefix cache cold (solid) or warm (dashed).
  Points are medians over repeated calls; whiskers span the interquartile range.
  Thin curves are the preregistered quadratic fits to the uncached calls.
  The shaded band marks the context sizes reached by our tasks; inside it, the dash dotted line in panel (a)
  is the linear per call law of Section 5.
  Panel (a) reports board energy on GB10 and panel (b) GPU energy on an A100; the two y axes measure different
  quantities and are not comparable.

Reads (no store): data/sweep/gb10_sweep.jsonl, data/sweep/a100_sweep.jsonl, data/summaries/numbers_auto.json and
data/summaries/numbers_extra.json (fit coefficients and the task range; values copied, never refitted).
Usage:
  python3 scripts/figures/f9_sweep.py --out output/sweep
"""
import argparse
import collections
import json
import os
import re

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

import style as S

MODEL_COL = {"Qwen3 30B": "black", "gpt-oss 20B": "#E69F00"}  # colour blind safe, no option colour reused


def num(vals, name):
    """Float value of a macro; strips LaTeX thousands separators and dollar signs."""
    v = vals.get(name)
    if v is None:
        raise SystemExit("macro %s missing; rebuild numbers first" % name)
    m = re.search(r"-?[0-9][0-9.]*(?:e-?[0-9]+)?", str(v).replace("{,}", "").replace(",", ""))
    if not m:
        raise SystemExit("macro %s has no number: %r" % (name, v))
    return float(m.group(0))


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def median_iqr(xs):
    xs = sorted(xs)
    q = lambda f: xs[int(round(f * (len(xs) - 1)))]
    return q(0.5), q(0.25), q(0.75)


def groups(rows, model_key=None):
    """{(model, cache): [(context k tokens, median, q1, q3)]} over repeats of one context size."""
    g = collections.defaultdict(list)
    for r in rows:
        if r.get("gate_ok") is False:
            continue  # calls whose cache state was not as intended are never plotted
        ctx = r.get("size") or r.get("context_tokens")
        g[(r.get(model_key) if model_key else "Qwen3 30B", r["cache"], ctx)].append(r["joules_net"])
    out = collections.defaultdict(list)
    for (m, c, ctx), js in sorted(g.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        md, q1, q3 = median_iqr(js)
        out[(m, c)].append((ctx / 1000.0, md, q1, q3))
    return out


def quad(a, b, d, pts):
    """Pick the context unit the fit was made in (tokens or k tokens) by its error against the medians."""
    best = None
    for unit, scale in (("k tokens", 1.0), ("tokens", 1000.0)):
        err = sum(abs(a + b * (x * scale) + d * (x * scale) ** 2 - y) for x, y, _, _ in pts) / len(pts)
        if best is None or err < best[1]:
            best = (scale, err, unit)
    return best


def panel(ax, data, fits, ctx_max, law=None):
    """One panel: medians with IQR whiskers, quadratic fit for uncached, task band, optional linear law."""
    ax.axvspan(0, ctx_max / 1000.0, color="#EAF2F8", lw=0, zorder=0)
    ax.text(ctx_max / 2000.0, 1.01, "our tasks", transform=ax.get_xaxis_transform(), ha="center", va="bottom",
            fontsize=6)  # above the axes, never on the band
    info = {}
    for (m, cache), pts in data.items():
        col = MODEL_COL.get(m, "black")
        ls = "-" if cache == "uncached" else "--"
        xs = [p[0] for p in pts]
        ax.plot(xs, [p[1] for p in pts], color=col, ls=ls, lw=0.9, marker="o", ms=2.5, zorder=3)
        for x, md, q1, q3 in pts:
            ax.plot([x, x], [q1, q3], color=col, lw=0.8, zorder=3)
        if cache == "uncached" and m in fits:
            a, b, d = fits[m]
            scale, err, unit = quad(a, b, d, pts)
            grid = [i * 0.25 for i in range(0, 133)]
            ax.plot(grid, [a + b * x * scale + d * (x * scale) ** 2 for x in grid], color=col, lw=0.5, zorder=2)
            info[m] = {"fit_unit": unit, "mean_abs_error_j": round(err, 2)}
            print("  %s fit in %s, mean error against medians %.1f J" % (m, unit, err))
    if law:
        a, b = law
        xs = [0, ctx_max / 1000.0]
        ax.plot(xs, [a + b * x * 1000 for x in xs], color="black", ls="-.", lw=1.2, zorder=6)
    ax.set_xlim(0, 33)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Context (k tokens)")
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
                    help="repository root containing data/")
    ap.add_argument("--out", default="output/sweep")
    a = ap.parse_args()
    vals = {}
    for fn in ("numbers_auto.json", "numbers_extra.json"):
        vals.update(json.load(open(os.path.join(a.paper, "data", "summaries", fn)))["values"])
    ctx_max = num(vals, "lawCtxMax")
    gb10 = groups(load(os.path.join(a.paper, "data", "sweep", "gb10_sweep.jsonl")), "model")
    a100 = groups(load(os.path.join(a.paper, "data", "sweep", "a100_sweep.jsonl")))
    fits_gb = {"Qwen3 30B": tuple(num(vals, "sweepQwenUncachedQuad" + t) for t in ("A", "B", "D")),
               "gpt-oss 20B": tuple(num(vals, "sweepGptossUncachedQuad" + t) for t in ("A", "B", "D"))}
    fits_a1 = {"Qwen3 30B": tuple(num(vals, "sweepQuad" + t) for t in ("A", "B", "D"))}
    law = (num(vals, "eLawLinA"), num(vals, "eLawLinB"))

    S.apply()
    fig, (pa, pb) = plt.subplots(1, 2, figsize=(S.COL, 2.2))
    print("panel a (GB10)")
    ia = panel(pa, gb10, fits_gb, ctx_max, law)
    print("panel b (A100)")
    ib = panel(pb, a100, fits_a1, ctx_max)
    pa.set_ylabel("(a) GB10 board J per call")
    pb.set_ylabel("(b) A100 GPU J per call")
    handles = [Line2D([], [], color="black", ls="-", lw=0.9, label="uncached"),
               Line2D([], [], color="black", ls="--", lw=0.9, label="cached"),
               Line2D([], [], color="black", ls="-", lw=0.5, label="quadratic fit"),
               Line2D([], [], color="black", ls="-.", lw=1.2, label="linear law (Sec. 5)"),
               Line2D([], [], color=MODEL_COL["Qwen3 30B"], ls="none", marker="o", ms=3.5, label="Qwen3 30B"),
               Line2D([], [], color=MODEL_COL["gpt-oss 20B"], ls="none", marker="o", ms=3.5, label="gpt-oss 20B")]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=5.5, handlelength=2.2, columnspacing=1.0,
               bbox_to_anchor=(0.5, 0.0))
    fig.subplots_adjust(left=0.13, right=0.98, top=0.92, bottom=0.36, wspace=0.42)
    fig.add_artist(Rectangle((0.003, 0.003), 0.994, 0.994, transform=fig.transFigure, fill=False,
                             lw=0.8, edgecolor="black"))  # thin black box, as every paper figure
    data = {"gb10": {"%s|%s" % k: v for k, v in gb10.items()}, "a100": {"%s|%s" % k: v for k, v in a100.items()},
            "fits": {"gb10": fits_gb, "a100": fits_a1, "check": {"a": ia, "b": ib}},
            "linear_law": law, "task_ctx_max": ctx_max}
    S.save(fig, "F9_sweep", a.out, data)
    print("wrote F9_sweep to %s" % a.out)


if __name__ == "__main__":
    main()
