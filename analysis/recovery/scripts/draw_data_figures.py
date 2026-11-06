"""Draw alternative recovery results, resume costs, and held-out policy figures."""
import json, math, os, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

if os.environ.get("RAF_FONT_DIR"):
    for font_file in Path(os.environ["RAF_FONT_DIR"]).glob("*.ttf"):
        font_manager.fontManager.addfont(str(font_file))
font_manager.findfont("Arial", fallback_to_default=False)

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
HERE = Path(__file__).resolve().parents[1] / "out"
A = json.load(open(HERE / "analyses.json"))
X = json.load(open(HERE / "extra.json"))
plt.rcParams.update({"font.family": "Arial", "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8,
                     "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8, "pdf.fonttype": 42,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": .6,
                     "xtick.major.width": .6, "ytick.major.width": .6, "savefig.facecolor": "white"})
C = {"FR": "#b8743c", "SR": "#3b5a8c", "RB": "#6e8b3d", "INK": "#333333", "MUTED": "#8c8c8c", "LIGHT": "#d9d9d9"}
CLS = {"model": ("json_parse", "rate_limit"), "tool": ("tool_error", "timeout")}
LABEL = {"json_parse": "Malformed reply", "rate_limit": "Rate limit", "tool_error": "Tool error", "timeout": "Timeout"}


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def save(fig, name):
    fig.savefig(OUT / (name + ".pdf"))
    fig.savefig(OUT / (name + ".png"), dpi=200)
    plt.close(fig)


# ---------- Figure: recovery results (full width, four panels) ----------
fig = plt.figure(figsize=(7, 2.2))
axa = fig.add_axes([0.06, 0.19, 0.22, 0.58])
axb = fig.add_axes([0.355, 0.19, 0.125, 0.58])
axc = fig.add_axes([0.525, 0.19, 0.125, 0.58])
axd = fig.add_axes([0.80, 0.19, 0.165, 0.58])
series = [("FR_warm", "Restart, warm", C["FR"], "o", True), ("SR_warm", "Resume, warm", C["SR"], "s", True),
          ("RB_warm", "Rollback, warm", C["RB"], "^", True), ("RB_cold", "Rollback, cold", C["RB"], "D", False)]
groups = [("early", "model"), ("early", "tool"), ("late", "model"), ("late", "tool")]
for gi, (pt, side) in enumerate(groups):
    for si, (pol, lab, col, mk, filled) in enumerate(series):
        r = A["tokens"]["%s|%s|%s" % (pol, pt, side)]
        lo, hi = wilson(r["ok"], r["n"])
        x = gi + (si - 1.5) * 0.17
        axa.errorbar(x, r["ok"], yerr=[[r["ok"] - 60 * lo], [60 * hi - r["ok"]]], fmt=mk, ms=4.2, color=col,
                     mfc=col if filled else "white", mew=.9, elinewidth=.7, capsize=0, label=lab if gi == 0 else None)
axa.set_xticks(range(4)); axa.set_xticklabels(["Early\nmodel", "Early\ntool", "Late\nmodel", "Late\ntool"])
axa.set_ylim(30, 61); axa.set_ylabel("Correct goals (of 60)"); axa.set_title("(a) Correctness", loc="left")
for ax, side, title in ((axb, "model", "(b) Model failures"), (axc, "tool", "(c) Tool failures")):
    for pol, lab, col, mk, filled in series:
        ys = [sum(A["best_of_six"]["%s|%s" % (cl, pt)]["ach"][pol] for cl in CLS[side]) / 2 / 1000 for pt in ("early", "late")]
        ax.plot([0, 1], ys, marker=mk, ms=4.2, color=col, mfc=col if filled else "white", mew=.9, lw=1.0,
                ls="-" if filled else "--")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Early", "Late"]); ax.set_xlim(-.25, 1.25)
    ax.set_ylim(1.2, 2.0); ax.set_title(title, loc="left")
axb.set_ylabel("Energy per successful goal (kJ)")
P = A["paired"]
rows = [("vs restart, early", P["RB_warm vs FR_warm | early tool"], C["FR"]),
        ("vs resume, early", P["RB_warm vs SR_warm | early tool"], C["SR"]),
        ("vs restart, late", P["RB_warm vs FR_warm | late tool"], C["FR"]),
        ("vs resume, late", P["RB_warm vs SR_warm | late tool"], C["SR"])]
for i, (lab, v, col) in enumerate(rows):
    y = len(rows) - 1 - i
    axd.plot([v["lo"], v["hi"]], [y, y], color=C["INK"], lw=.8)
    axd.plot(v["saving_pct"], y, "o", ms=4.2, color=col, mec="white", mew=.6)
axd.axvline(0, color=C["MUTED"], lw=.6, ls="--")
axd.set_yticks(range(len(rows))); axd.set_yticklabels([r[0] for r in reversed(rows)])
axd.set_ylim(-.6, len(rows) - .4); axd.set_xlim(-25, 45)
axd.set_xlabel("Warm rollback saving (%)"); axd.set_title("(d) Rollback, tool failures", loc="left")
axd.tick_params(axis="y", length=0); axd.spines["left"].set_visible(False)
fig.legend(loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.0), handletextpad=.3, columnspacing=1.4)
save(fig, "recovery-results")

# ---------- Figure: why an early resume loses (Equation 2 terms), one column ----------
fig = plt.figure(figsize=(3.4, 1.95))
axs = [fig.add_axes([0.25, 0.22, 0.34, 0.58]), fig.add_axes([0.64, 0.22, 0.34, 0.58])]
order = ("json_parse", "rate_limit", "tool_error", "timeout")
for ax, pt, title in zip(axs, ("early", "late"), ("Early failure", "Late failure")):
    for i, cl in enumerate(order):
        e = A["eq2"]["%s|%s" % (cl, pt)]
        y = len(order) - 1 - i
        s, x = e["success_term"] / 1000, e["extra_term"] / 1000
        ax.barh(y, s, height=.55, color=C["SR"], alpha=.45, lw=0, label="Lower success" if i == 0 else None)
        ax.barh(y, x, left=s, height=.55, color=C["SR"], lw=0, label="Extra work" if i == 0 else None)
        ax.plot([e["S"] / 1000] * 2, [y - .38, y + .38], color="black", lw=1.4,
                label="Energy already spent" if i == 0 else None)
    ax.set_xlim(0, .85); ax.set_xticks([0, .4, .8]); ax.set_ylim(-.6, len(order) - .4)
    ax.set_title(title, loc="left"); ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
axs[0].set_yticks(range(len(order))); axs[0].set_yticklabels([LABEL[c] for c in reversed(order)])
axs[1].set_yticks([])
fig.text(0.615, 0.04, "Energy per goal (kJ)", ha="center")
h, l = axs[0].get_legend_handles_labels()
h, l = h[1:] + h[:1], l[1:] + l[:1]
fig.legend(h, l, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.56, 1.0), handlelength=1.2,
           handletextpad=.35, columnspacing=.9, fontsize=7.5)
save(fig, "resume-cost")

# ---------- Figure: held-out rule, with the main-study cache gap as a reference ----------
H = {"Restart\n(warm)": (22.0, 11.9, 31.8), "Resume\n(warm)": (7.6, 2.0, 12.5), "Rollback\n(cold)": (3.2, -1.9, 6.6)}
fig = plt.figure(figsize=(3.4, 1.85))
ax = fig.add_axes([0.24, 0.24, 0.72, 0.7])
for i, (lab, (p, lo, hi)) in enumerate(H.items()):
    y = len(H) - i
    ax.plot([lo, hi], [y, y], color=C["INK"], lw=.8)
    ax.plot(p, y, "o", ms=5, color="black")
g = X["RBwarm_vs_RBcold_e3_situations"]
ax.plot([g[1], g[2]], [.35, .35], color=C["RB"], lw=.8)
ax.plot(g[0], .35, "D", ms=4.5, color="white", mec=C["RB"], mew=1)
ax.text(g[2] + 1, .35, "Main study, warm vs cold\nrollback (reference)", va="center", fontsize=7.5, color=C["RB"])
ax.axvline(0, color=C["MUTED"], lw=.6, ls="--")
ax.set_yticks([3, 2, 1]); ax.set_yticklabels(list(H)); ax.set_ylim(-.2, 3.5); ax.set_xlim(-6, 36)
ax.set_xlabel("EpG saving of the token rule versus fixed policy (%)")
ax.tick_params(axis="y", length=0); ax.spines["left"].set_visible(False)
save(fig, "heldout-policy")
print("figures written to", OUT)
