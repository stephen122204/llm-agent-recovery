#!/usr/bin/env python3
"""F5 (sweep version): energy of one model call against its context length, cached and uncached.

Left panel: GB10, board energy per call, one line pair per model. Right panel: A100, GPU energy only.
Input: JSON lines with fields cache ("cached" or "uncached"), context_tokens, joules_net (idle subtracted)
and, when several models share a file, model. Points are medians per context; bands are the interquartile range.
The label at the longest context is the measured ratio of cached to uncached median energy there.
The two panels never share an axis: they measure different boundaries on different machines.
Usage: python3 make_f5_sweep.py GB10.jsonl A100.jsonl OUTSTEM   (use - for a missing file)
"""
import collections, json, statistics, sys
import figstyle as S

UNC, CAC = "#1a1a1a", "#0072B2"
LS = ["-", (0, (4, 2)), (0, (1, 1.5))]


def load(path):
    by = collections.defaultdict(list)
    if path == "-":
        return {}
    for line in open(path):
        if line.strip():
            r = json.loads(line)
            by[(r.get("model", ""), r["cache"], int(r["context_tokens"]))].append(float(r["joules_net"]))
    out = collections.defaultdict(list)
    for (m, cache, ctx), v in sorted(by.items()):
        q = statistics.quantiles(v, n=4) if len(v) > 1 else [v[0]] * 3
        out[(m, cache)].append((ctx / 1000.0, statistics.median(v), q[0], q[2]))
    return out


def panel(ax, data, title):
    S.clean(ax)
    models = sorted({m for m, _ in data})
    for i, m in enumerate(models):
        for cache, col in (("uncached", UNC), ("cached", CAC)):
            pts = data.get((m, cache), [])
            if not pts:
                continue
            x, y, lo, hi = zip(*pts)
            ax.fill_between(x, lo, hi, color=col, alpha=0.15, lw=0)
            ax.plot(x, y, color=col, lw=1.3, ls=LS[i % 3], marker="o" if cache == "uncached" else "s", ms=2.6,
                    mfc="white" if cache == "uncached" else col, mec=col, mew=0.8)
        u, c = data.get((m, "uncached")), data.get((m, "cached"))
        if u and c and u[-1][0] == c[-1][0]:
            ax.text(u[-1][0] * 1.02, (u[-1][1] + c[-1][1]) / 2, "%.2f" % (c[-1][1] / u[-1][1]),
                    fontsize=5.6, color=S.INK, va="center", clip_on=False)
    ax.text(0.02, 1.0, title, transform=ax.transAxes, fontsize=6.4, color=S.INK, fontweight="bold", va="bottom")
    ax.set_xlabel("Context (1k tokens)", fontsize=6.2, color=S.INK, labelpad=1)
    ax.set_ylim(bottom=0)
    return models


gb, a1 = load(sys.argv[1]), load(sys.argv[2])
S.apply()
fig = S.plt.figure(figsize=(S.COL, 2.35))
S.frame(fig, "Energy of one call, cached and uncached", head=0.105)
axl = fig.add_axes([0.12, 0.15, 0.33, 0.58]); axr = fig.add_axes([0.62, 0.15, 0.26, 0.58])
models = panel(axl, gb, "GB10, board energy") if gb else []
if not gb:
    S.clean(axl); axl.text(0.5, 0.5, "GB10 sweep pending", transform=axl.transAxes, ha="center", color=S.MUT)
panel(axr, a1, "A100, GPU energy only")
axl.set_ylabel("Energy per call (J)", fontsize=6.2, color=S.INK, labelpad=1)
h = [S.plt.Line2D([], [], color=UNC, marker="o", mfc="white", ms=3, lw=1.2, label="uncached"),
     S.plt.Line2D([], [], color=CAC, marker="s", ms=3, lw=1.2, label="cached")]
h += [S.plt.Line2D([], [], color=S.MUT, ls=LS[i % 3], lw=1.2, label=m) for i, m in enumerate(models) if len(models) > 1]
fig.legend(handles=h, loc="lower center", ncol=len(h), fontsize=5.8, frameon=False, bbox_to_anchor=(0.5, 0.80))

S.save(fig, sys.argv[3])
