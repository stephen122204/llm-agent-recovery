#!/usr/bin/env python3
"""F5: the recovery choice moves energy; the cache barely does (main study, board energy).

Each bar is the energy of one choice as a percent of the alternative (100 = alternative), pooled over tasks,
with a 95% bootstrap interval that resamples tasks.
  Cache row: warm over cold of the same option, recovery attempt energy; light bar: uncached prompt tokens.
  Depth rows: energy per successful goal of warm restart over warm resume (early failures) and of warm resume
  over warm restart (late failures).
Usage: python3 make_f5.py goals.csv OUTSTEM
"""
import random, sys
import figstyle as S, goalsdata as G

rows = G.load(sys.argv[1], studies=("e1", "e1b"))
idx = {(r["task"], r["cls"], r["point"], r["option"]): r for r in rows}
rnd = random.Random(7)


def boot(units, f, reps=2000):
    est = f(units); bs = sorted(f([rnd.choice(units) for _ in units]) for _ in range(reps))
    return est, bs[int(0.025 * reps)], bs[int(0.975 * reps)]


# cache: pairs (cold, warm) per task, failure and depth, grouped by task for resampling
cache_e, cache_t = {}, {}
for (task, cls, pt, opt), w in idx.items():
    if not opt.endswith("_warm") or w["board_j_rec"] is None:
        continue
    c = idx.get((task, cls, pt, opt.replace("_warm", "_cold")))
    if c and c["board_j_rec"] and c["tok_uncached_rec"]:
        cache_e.setdefault(task, []).append((c["board_j_rec"], w["board_j_rec"]))
        cache_t.setdefault(task, []).append((c["tok_uncached_rec"], w["tok_uncached_rec"]))
ratio = lambda groups: 100.0 * sum(b for g in groups for a, b in g) / sum(a for g in groups for a, b in g)
cache_energy = boot(list(cache_e.values()), ratio)
cache_tokens = boot(list(cache_t.values()), ratio)


def per_ach_ratio(point, num, den):
    """energy per successful goal of option num over option den, pooled over tasks (both types of each side)."""
    by = {}
    for (task, cls, pt, opt), r in idx.items():
        if pt == point and opt in (num, den):
            by.setdefault(task, []).append(r)

    def f(groups):
        s = {num: [0.0, 0], den: [0.0, 0]}
        for g in groups:
            for r in g:
                s[r["option"]][0] += r["board_j"]; s[r["option"]][1] += r["ok"]
        return 100.0 * (s[num][0] / s[num][1]) / (s[den][0] / s[den][1])
    return boot(list(by.values()), f)


early = per_ach_ratio("early", "FR_warm", "SR_warm")
late = per_ach_ratio("late", "SR_warm", "FR_warm")
bars = [("Warm cache", "instead of cold", "#000000", cache_energy, cache_tokens, "of cold"),
        ("Early failure: restart", "instead of resume", S.OPT["FR"], early, None, "of resume"),
        ("Late failure: resume", "instead of restart", S.OPT["SR"], late, None, "of restart")]
S.apply()
fig = S.plt.figure(figsize=(S.COL, 1.9))
S.frame(fig, "The recovery choice moves energy; the cache does not", head=0.13)
ax = fig.add_axes([0.34, 0.25, 0.58, 0.56]); S.clean(ax)
n = len(bars)
for i, (lab, sub, col, en, tok, of) in enumerate(bars):
    y = n - 1 - i
    h = 0.36 if tok else 0.5
    yy = y - (0.2 if tok else 0)
    ax.barh(yy, en[0], height=h, color=col, lw=0)
    ax.plot([en[1], en[2]], [yy, yy], color="#bbbbbb" if col == "#000000" else S.INK, lw=1.0)
    ax.text(2, yy, "energy %.0f%% %s" % (en[0], of), ha="left", va="center", fontsize=5.9, color="white", fontweight="bold")
    if tok:
        ax.barh(y + 0.2, tok[0], height=0.3, color=col, alpha=0.4, lw=0)
        ax.text(tok[2] + 1.5, y + 0.2, "prompt tokens %.0f%% %s" % (tok[0], of), va="center", fontsize=5.9, color=S.INK)
    fy = 0.25 + 0.56 * (y + 0.6) / (n + 0.2)
    fig.text(0.325, fy + 0.03, lab, ha="right", va="center", fontsize=6.3, color=S.INK, fontweight="bold")
    fig.text(0.325, fy - 0.035, sub, ha="right", va="center", fontsize=5.8, color=S.MUT)
ax.axvline(100, color=S.MUT, lw=0.7, ls=(0, (3, 2)))
ax.set_xlim(0, 108); ax.set_ylim(-0.6, n - 0.4); ax.set_yticks([]); ax.set_xticks([0, 25, 50, 75, 100])
ax.set_xlabel("Percent of the alternative (100 = no change)", fontsize=6, color=S.INK, labelpad=1)
fig.text(0.5, 0.025, "Cache: energy of the recovery attempt.  Choice: energy per successful goal.", ha="center", fontsize=5.4, color=S.MUT)
S.save(fig, sys.argv[2])
