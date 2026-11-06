"""style.py: house style for every RAF paper figure (MLSys 2027).

Imported by every figure script. Change a color or size here and run make_all.sh;
every figure follows. Palette validated with the dataviz validator (light surface):
FR, SR, RB, controller pass lightness, chroma, CVD (worst 9.3) and contrast checks.
B0 gray is a neutral reference, never a category.
"""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# sizes in inches (MLSys two column template)
COL = 3.33
FULL = 6.9

C = {
    "FR": "#D55E00",   # full restart, vermillion
    "SR": "#0072B2",   # step resume, blue
    "RB": "#009E73",   # roll back, bluish green
    "SG": "#E69F00",   # state grounded resume, orange (optional)
    "CTRL": "#A8478A",  # our controller, darkened magenta (passes contrast)
    "B0": "#7F7F7F",   # no failure reference, gray
    "INK": "#1A1A1A",
    "MUTED": "#6B6B6B",
    "GRID": "#E6E6E6",
    "PANEL": "#F5F5F2",  # tinted background for composite figures
    "FAIL": "#C0392B",
}
COLD_HATCH = "////"  # cold cache = same hue, light fill plus hatch (survives grayscale)

OPT_LABEL = {"FR_warm": "Restart warm", "FR_cold": "Restart cold", "SR_warm": "Resume warm",
             "SR_cold": "Resume cold", "RB_warm": "Roll back warm", "RB_cold": "Roll back cold",
             "SG_warm": "Grounded warm", "SG_cold": "Grounded cold",
             "ctrl_beta": "Controller (ours)", "xstar_rule": "x* rule", "token_rule": "Token rule"}
OPT_SHORT = {"FR_warm": "FR w", "FR_cold": "FR c", "SR_warm": "SR w", "SR_cold": "SR c",
             "RB_warm": "RB w", "RB_cold": "RB c"}
CLS_LABEL = {"json_parse": "JSON parse", "rate_limit": "Rate limit", "tool_error": "Tool error",
             "timeout": "Timeout"}
SIDE = {"json_parse": "model", "rate_limit": "model", "tool_error": "tool", "timeout": "tool"}


def opt_color(opt):
    """Fill color and hatch of an option or arm (cold = tinted plus hatch)."""
    fam = opt.split("_")[0]
    if opt in ("ctrl_beta",):
        return C["CTRL"], None
    if opt in ("xstar_rule", "token_rule"):
        return C["MUTED"], None
    base = C.get(fam, C["B0"])
    if opt.endswith("_cold"):
        return lighten(base, 0.55), COLD_HATCH
    return base, None


def lighten(hexc, f):
    """Mix a hex color with white by fraction f."""
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (int(v + (255 - v) * f) for v in (r, g, b))
    return "#%02X%02X%02X" % (r, g, b)


def apply():
    """Matplotlib settings: live text in SVG, Type 42 fonts in PDF, recessive axes."""
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 7,
        "axes.titlesize": 7.5,
        "axes.labelsize": 7,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "legend.fontsize": 6.5,
        "axes.linewidth": 0.8,
        "axes.edgecolor": "black",
        "axes.labelcolor": C["INK"],
        "text.color": C["INK"],
        "xtick.color": "black",
        "ytick.color": "black",
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "grid.color": C["GRID"],
        "grid.linewidth": 0.5,
        "hatch.linewidth": 0.5,
        "hatch.color": "white",
        "legend.frameon": False,
        "svg.fonttype": "none",   # text stays editable in Figma or Inkscape
        "pdf.fonttype": 42,       # no Type 3 fonts (HotCRP)
        "ps.fonttype": 42,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "figure.dpi": 150,
    })


def save(fig, name, out, data, demo=False):
    """Write <name>.svg, <name>.pdf and <name>_data.json (every plotted number)."""
    os.makedirs(out, exist_ok=True)
    if demo:
        fig.text(0.995, 0.995, "DEMO DATA, NOT FOR THE PAPER", ha="right", va="top",
                 fontsize=6, color=C["FAIL"], alpha=0.8)
    for ext in ("svg", "pdf", "png"):
        fig.savefig(os.path.join(out, "%s.%s" % (name, ext)))
    data = dict(data)
    data["demo"] = demo
    with open(os.path.join(out, name + "_data.json"), "w") as f:
        json.dump(data, f, indent=1, default=float)
    plt.close(fig)


def direction(ax, text):
    """Metric title with the direction a reader should prefer."""
    ax.set_title(text, loc="left", fontweight="bold", pad=4)
