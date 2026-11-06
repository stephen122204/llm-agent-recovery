"""Shared style for writer figures: one strong colour per option, boxed panel, serif text."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

INK, MUT, EDGE, BOX, HEAD = "#000000", "#333333", "#000000", "#ffffff", "#ffffff"
OPT = {"FR": "#D55E00", "SR": "#0072B2", "RB": "#009E73", "SG": "#CC79A7"}
NAME = {"FR": "Restart", "SR": "Resume", "RB": "Roll back", "SG": "Grounded resume"}
CLS = {"json_parse": "Parse failure", "rate_limit": "Rate limit", "tool_error": "Tool error", "timeout": "Timeout"}
SIDE = {"json_parse": "model", "rate_limit": "model", "tool_error": "tool", "timeout": "tool"}
COL = 3.35


def apply():
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
                         "font.size": 7, "pdf.fonttype": 42, "svg.fonttype": "none", "axes.edgecolor": INK, "axes.linewidth": 0.8,
                         "xtick.color": INK, "ytick.color": INK, "xtick.major.width": 0.8, "ytick.major.width": 0.8, "xtick.labelsize": 6, "ytick.labelsize": 6})


def frame(fig, title=None, head=0.0):
    """MLSys rule: no title inside the figure and no text on grey. The box is drawn at save time around the content."""
    fig._boxed = True


def clean(ax):
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(False)
    ax.set_facecolor("none")


def save(fig, stem):
    """Crop to the content, draw a thin box around it, write pdf, svg and png."""
    from matplotlib.transforms import Bbox
    fig.canvas.draw()
    bb = fig.get_tightbbox(fig.canvas.get_renderer())
    pad = 0.06
    box = Bbox.from_extents(bb.x0 - pad, bb.y0 - pad, bb.x1 + pad, bb.y1 + pad)
    if getattr(fig, "_boxed", False):
        W, H = fig.get_size_inches()
        fig.patches.append(FancyBboxPatch(((box.x0 + 0.015) / W, (box.y0 + 0.015) / H), (box.width - 0.03) / W, (box.height - 0.03) / H,
                                          boxstyle="round,pad=0,rounding_size=0.01", transform=fig.transFigure,
                                          fc="none", ec=EDGE, lw=0.9, zorder=10))
    for ext in ("pdf", "svg", "png"):
        fig.savefig("%s.%s" % (stem, ext), dpi=300, bbox_inches=box)



def blend(ax):
    """x in axes fraction, y in data units."""
    from matplotlib.transforms import blended_transform_factory
    return blended_transform_factory(ax.transAxes, ax.transData)
