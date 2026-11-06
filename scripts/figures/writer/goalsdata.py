"""Read goals.csv (R4 export) into per cell, per task values. No numbers live in figure scripts."""
import csv, random


def load(path, studies):
    rows = [r for r in csv.DictReader(open(path)) if r["study"] in studies and r["cls"] not in ("none", "")]
    for r in rows:
        r["ok"] = int(r["ok"]); r["board_j"] = float(r["board_j"])
        for k in ("board_j_rec", "tok_uncached_rec"):
            r[k] = float(r[k]) if r.get(k) not in (None, "", "NA") else None
    return rows


def per_achieved(rows):
    """Mean energy per goal over tasks divided by success rate. Returns (epg, per_ach or None, k, n)."""
    n = len(rows); k = sum(r["ok"] for r in rows)
    epg = sum(r["board_j"] for r in rows) / n
    return epg, (epg * n / k if k else None), k, n


def boot_ratio(pairs, reps=2000, seed=7):
    """pairs: list of (cold, warm) per task. Percent reduction of sums, bootstrap over tasks."""
    rnd = random.Random(seed)
    f = lambda ps: 100.0 * (1 - sum(w for c, w in ps) / sum(c for c, w in ps))
    est = f(pairs); bs = sorted(f([rnd.choice(pairs) for _ in pairs]) for _ in range(reps))
    return est, bs[int(0.025 * reps)], bs[int(0.975 * reps)]
