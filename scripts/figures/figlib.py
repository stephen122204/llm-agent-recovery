"""figlib.py: shared data access and statistics for the figure scripts.

Inputs are the CSV files written by export_figdata.py (one store read in a window);
figure scripts never touch the store.

goals.csv  study, goal_id, task, cls, point, option, ok, board_j, pkg_j, tok_uncached, tok_billed, calls
calls.csv  study, goal_id, attempt, step, kind, prompt_tokens, uncached_tokens, board_j, failed
Definitions follow paper_numbers.py: per achieved = sum board J / successes (a cell),
intervals = paired bootstrap over tasks, 2000 resamples, seed 20261013; success Wilson 95.
"""
import collections
import csv
import math
import os
import random

BOOT_REPS, BOOT_SEED = 2000, 20261013


def data_dir(arg=None):
    here = os.path.dirname(os.path.abspath(__file__))
    return arg or os.path.join(here, "..", "..", "data", "figdata")


def is_demo(d):
    return os.path.exists(os.path.join(d, "DEMO"))


def load_goals(d, studies=None):
    rows = []
    with open(os.path.join(d, "goals.csv")) as f:
        for r in csv.DictReader(f):
            if studies and r["study"] not in studies:
                continue
            for k in ("ok",):
                r[k] = int(r[k])
            for k in ("board_j", "pkg_j", "tok_uncached", "tok_billed", "calls"):
                r[k] = float(r[k]) if r.get(k) not in (None, "", "NA") else None
            rows.append(r)
    return rows


def load_calls(d):
    out = collections.defaultdict(list)
    p = os.path.join(d, "calls.csv")
    if not os.path.exists(p):
        return out
    with open(p) as f:
        for r in csv.DictReader(f):
            for k in ("attempt", "step", "failed"):
                r[k] = int(r[k])
            for k in ("prompt_tokens", "uncached_tokens", "board_j"):
                r[k] = float(r[k]) if r.get(k) not in (None, "", "NA") else None
            out[int(r["goal_id"])].append(r)
    for g in out.values():
        g.sort(key=lambda r: (r["attempt"], r["step"]))
    return out


def by_task(rows, value="board_j"):
    """{task: [sum value, successes, n]} for one cell."""
    t = collections.defaultdict(lambda: [0.0, 0, 0])
    for r in rows:
        v = t[r["task"]]
        v[0] += r[value] or 0.0
        v[1] += r["ok"]
        v[2] += 1
    return dict(t)


def per_achieved(cell):
    e = sum(v[0] for v in cell.values())
    k = sum(v[1] for v in cell.values())
    return e / k if k else None


def per_goal(cell):
    e = sum(v[0] for v in cell.values())
    n = sum(v[2] for v in cell.values())
    return e / n if n else None


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def _pct(vals, q):
    vals = sorted(vals)
    return vals[int(round(q * (len(vals) - 1)))]


def boot_cell(cell, stat=per_achieved):
    """Point and 95 percent interval of a cell statistic, bootstrap over tasks."""
    tasks = sorted(cell)
    rng = random.Random(BOOT_SEED)
    vals = []
    for _ in range(BOOT_REPS):
        # resampled tasks keep their own sums; duplicates get distinct keys
        draw = {"%s#%d" % (t, i): cell[t] for i, t in enumerate(rng.choice(tasks) for _ in tasks)}
        v = stat(draw)
        if v is not None:
            vals.append(v)
    return stat(cell), _pct(vals, 0.025), _pct(vals, 0.975)


def boot_saving(pairs):
    """Percent by which A is below B in per achieved energy, pooled over pairs, paired by task.

    pairs: list of (cell A, cell B). Returns (point, lo, hi, n_tasks).
    """
    tasks = None
    for a, b in pairs:
        s = set(a) & set(b)
        tasks = s if tasks is None else tasks & s
    tasks = sorted(tasks)

    def sav(draw):
        ea = oa = eb = ob = 0.0
        for a, b in pairs:
            for t in draw:
                ea += a[t][0]; oa += a[t][1]
                eb += b[t][0]; ob += b[t][1]
        if not oa or not ob:
            return None
        return 100 * (1 - (ea / oa) / (eb / ob))

    rng = random.Random(BOOT_SEED)
    vals = [v for v in (sav([rng.choice(tasks) for _ in tasks]) for _ in range(BOOT_REPS)) if v is not None]
    return sav(tasks), _pct(vals, 0.025), _pct(vals, 0.975), len(tasks)


def cells(rows, value="board_j"):
    """{(cls, point, option): by_task cell}"""
    g = collections.defaultdict(list)
    for r in rows:
        g[(r["cls"], r["point"], r["option"])].append(r)
    return {k: by_task(v, value) for k, v in g.items()}
