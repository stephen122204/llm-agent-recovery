#!/usr/bin/env python3
"""F1: one real goal, attempt 1 plus three recoveries, as a node and edge graph.

All values come from two CSV files written by export_f1_trace.py:
  attempts.csv  goal,policy,attempt,run,board_j,ok          (board J measured per attempt)
  calls.csv     run,step,time_ms,prompt_tok,completion_tok,tools   (tools: names the call asked for, ';' separated)
Circles are model calls, coloured by energy; squares are the tool calls each model call asked for.
A model call that asks for no tool answers the user and ends a turn, which gives the turn bands.
A call's energy is its attempt's measured board energy split by the call's duration.
Usage: python3 make_f1_trace.py attempts.csv calls.csv OUTSTEM [goals.csv]
With goals.csv, each recovery row also shows the uncached prompt tokens of its recovery attempt (tok_uncached_rec).
"""
import csv, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.colors as mc
from matplotlib.patches import FancyArrowPatch

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
                     "font.size": 7, "pdf.fonttype": 42, "svg.fonttype": "none"})
SHORT = {"get_zipcode_based_on_city": "zip code", "estimate_distance": "distance",
         "estimate_drive_feasibility_by_mileage": "range check", "fillFuelTank": "fill tank",
         "displayCarStatus": "car status", "startEngine": "start engine", "lockDoors": "lock doors",
         "pressBrakePedal": "brake", "set_navigation": "navigation"}
LABEL = {"FR": "Restart", "SR": "Resume", "RB": "Roll back"}
TOOL_C, FAIL = "#cfd8e3", "#c00000"

att_path, call_path, out = sys.argv[1:4]
unc = {}
if len(sys.argv) > 4:
    for r in csv.DictReader(open(sys.argv[4])):
        unc[r["goal_id"]] = r["tok_uncached_rec"]
att = list(csv.DictReader(open(att_path)))
calls = {}
for r in csv.DictReader(open(call_path)):
    calls.setdefault(r["run"], []).append((int(r["step"]), float(r["time_ms"]), [t for t in r["tools"].split(";") if t]))
for k in calls:
    calls[k].sort()

by = {}
for a in att:
    by.setdefault(a["policy"], {})[int(a["attempt"])] = a
order = sorted(by, key=lambda p: ({"FR": 0, "RB": 1, "SR": 2}[p[:2]], p.endswith("cold")))


def seq(run, board_j):
    """List of (energy, tools) per model call; energy split by call duration."""
    cs = calls[run]; tot = sum(t for _, t, _ in cs)
    return [(board_j * t / tot, tl) for _, t, tl in cs]


first = by[order[0]][1]
a1 = seq(first["run"], float(first["board_j"]))
rows = [(p, seq(by[p][2]["run"], float(by[p][2]["board_j"])), float(by[p][2]["board_j"]), int(by[p][2]["ok"])) for p in order]
goal_of = {p: by[p][2]["goal"] for p in order}
full = max((r[1] for r in rows), key=len)       # restart holds the whole task
ntot, nfail = len(full), len(a1)

# x position of every model call, laid out on the full task with room for its tool squares
xs, x = [], 0.0
for e, tl in full:
    xs.append(x); x += 1.0 + 0.62 * len(tl)
xend = x
turn_end = [i for i, (e, tl) in enumerate(full) if not tl]   # a text reply to the user ends a turn

allE = [e for e, _ in a1] + [e for _, s, _, _ in rows for e, _ in s]
cmap = plt.get_cmap("RdYlGn_r"); norm = mc.Normalize(min(allE), max(allE))
fig = plt.figure(figsize=(6.9, 2.8))
ax = fig.add_axes([0.175, 0.02, 0.685, 0.74]); cax = fig.add_axes([0.30, 0.89, 0.30, 0.03])


def arrow(x0, y0, x1, y1, col="#000000", ls="-", rad=0.0, lw=0.7, sa=4, sb=4):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=5, color=col, lw=lw, ls=ls,
                                 connectionstyle="arc3,rad=%s" % rad, shrinkA=sa, shrinkB=sb, zorder=2))


def draw_row(y, s, start, fade_before, labels=False):
    """Draw model circles and tool squares of a row whose first call is full-task call `start`."""
    prev = None
    for j, (e, tl) in enumerate(s):
        i = start + j; fade = i < fade_before; a = 0.3 if fade else 1.0
        cx = xs[i]
        if prev is not None:
            arrow(prev, y, cx, y)
        ax.scatter(cx, y, s=62, marker="o", c=[mc.to_rgba(cmap(norm(e)), 0.3) if fade else cmap(norm(e))], edgecolors="#000000", linewidths=0.7, zorder=3)
        prev = cx
        for k, t in enumerate(tl):
            tx = cx + 0.62 * (k + 1)
            arrow(prev, y, tx, y, sb=3)
            ax.scatter(tx, y, s=30, marker="s", c=[mc.to_rgba(TOOL_C, 0.3) if fade else TOOL_C], edgecolors="#000000", linewidths=0.7, zorder=3)
            if labels:
                ax.text(tx, y + 0.27, SHORT.get(t, t), rotation=40, ha="left", va="bottom", fontsize=5.6, color="#333")
            prev = tx
    return prev


Y = {"a1": 0.0}
for k, (p, *_r) in enumerate(rows):
    Y[p] = -1.35 * (k + 1)
t0 = 0
for t, i in enumerate(turn_end):          # turn bands from the full task
    x0 = xs[t0] - 0.45; x1 = xs[i] + 0.45
    if t % 2 == 0:
        ax.axvspan(x0, x1, ymin=0.09, color="#ececec", zorder=0)
    ax.text((x0 + x1) / 2, Y[order[-1]] - 0.62, "turn %d" % (t + 1), ha="center", fontsize=6, color="#666")
    t0 = i + 1
last = draw_row(0.0, a1, 0, -1, labels=True)
ax.scatter(last + 0.45, 0.0, marker="X", s=55, c=FAIL, zorder=4)
ax.text(last + 0.75, -0.3, "timeout", fontsize=6.5, color=FAIL, ha="left", va="center")
n_tool = lambda s: sum(len(tl) for _, tl in s)
ax.text(-0.9, 0.08, "Attempt 1", ha="right", va="center", fontsize=7.5, fontweight="bold")
ax.text(-0.9, -0.27, "%d model, %d tool calls" % (len(a1), n_tool(a1)), ha="right", va="center", fontsize=6.2, color="#555", style="italic")
ax.text(xend + 0.3, 0.0, "%.0f J" % float(first["board_j"]), va="center", fontsize=7.5, fontweight="bold")
ax.text(xend + 0.3, 0.42, "energy, checker", fontsize=6.2, color="#555", va="center")
for p, s, tot, ok in rows:
    y, start = Y[p], ntot - len(s)
    draw_row(y, s, start, nfail)
    tgt = xs[start]
    if start < nfail - 2:
        arrow(last + 0.3, -0.22, tgt, y + 0.28, col=FAIL, ls=(0, (3, 2)), rad=-0.05, lw=0.9)
    else:
        arrow(last + 0.3, -0.22, tgt + 0.05, y + 0.25, col=FAIL, ls=(0, (3, 2)), lw=0.9)
    if p.endswith("warm") and start > 0:
        ax.plot([xs[0], tgt - 0.4], [y, y], color="#4a90d9", lw=3, alpha=0.3, solid_capstyle="round", zorder=1)
    rep = max(0, nfail - start)
    ax.text(-0.9, y + 0.08, "%s (%s)" % (LABEL[p[:2]], p[3:]), ha="right", va="center", fontsize=7.5, fontweight="bold")
    ax.text(-0.9, y - 0.25, "%d model, %d tool calls" % (len(s), n_tool(s)), ha="right", va="center", fontsize=6.2, color="#555", style="italic")
    ax.text(-0.9, y - 0.52, ("repeats %d model call%s" % (rep, "" if rep == 1 else "s")) if rep else "repeats nothing", ha="right", va="center", fontsize=6.2,
            color="#c00000" if rep else "#2e7d32", style="italic")
    ax.text(xend + 0.3, y + 0.14, "%.0f J" % tot, va="center", fontsize=7.5, fontweight="bold")
    ax.text(xend + 0.3, y - 0.28, "correct" if ok else "wrong state", va="center", fontsize=6.8, color="#2e7d32" if ok else FAIL)
    u = unc.get(goal_of[p])
    if u not in (None, "", "NA"):
        ax.text(xend + 0.3, y - 0.62, "%s uncached tok" % format(int(float(u)), ","), va="center", fontsize=5.6, color="#555")
ax.set_xlim(-0.5, xend + 2.6); ax.set_ylim(Y[order[-1]] - 0.8, 1.15); ax.axis("off")
sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
cb = fig.colorbar(sm, cax=cax, orientation="horizontal"); cb.ax.tick_params(labelsize=6, length=2)
cax.set_title("Energy per model call (J, board)", fontsize=7, pad=2)
h = [plt.Line2D([], [], marker="o", ls="", mfc="#e8c46a", mec="#000000", label="model call (colour = energy)"),
     plt.Line2D([], [], marker="s", ls="", mfc=TOOL_C, mec="#000000", label="tool call"),
     plt.Line2D([], [], marker="o", ls="", mfc=(0.85, 0.85, 0.85, 1), mec="#000000", label="work repeated (faded)"),
     plt.Line2D([], [], color=FAIL, ls=(0, (3, 2)), label="recovery starts here"),
     plt.Line2D([], [], color="#4a90d9", lw=3, alpha=0.4, label="history from warm cache")]
fig.legend(handles=h, loc="upper right", bbox_to_anchor=(0.997, 0.995), fontsize=6, frameon=False)
from matplotlib.patches import FancyBboxPatch
from matplotlib.transforms import Bbox
fig.canvas.draw()
bb = fig.get_tightbbox(fig.canvas.get_renderer()); W, H = fig.get_size_inches()
box = Bbox.from_extents(bb.x0 - 0.06, bb.y0 - 0.06, bb.x1 + 0.06, bb.y1 + 0.06)
fig.patches.append(FancyBboxPatch(((box.x0 + 0.015) / W, (box.y0 + 0.015) / H), (box.width - 0.03) / W, (box.height - 0.03) / H,
                                  boxstyle="round,pad=0,rounding_size=0.006", transform=fig.transFigure, fc="none", ec="#000000", lw=0.9, zorder=10))
for ext in ("pdf", "svg", "png"):
    fig.savefig("%s.%s" % (out, ext), dpi=300, bbox_inches=box)
