#!/usr/bin/env python3
"""F0 system overview (hero figure): agent, recovery controller, serving engine, recovery options, measurement.

Hand drawn vector icons in plain SVG (no third party art, no license questions), house palette,
live text. Writes F0_overview.svg and F0_overview.pdf (cairosvg). Full width (6.9 in).
Layout, top to bottom:
  row 1  Agent  <->  Recovery controller  <->  Serving engine (vLLM, prefix cache)
  row 2  Recovery options 1 to 5 (restart, resume, roll back, grounded resume, abandon), warm or cold cache
  row 3  Measurement (A-LEMS): board power, package power, idle baseline, store, checker
"""
import argparse
import os

import style as S

W, H = 690, 345
FONT = "Times New Roman, Times, Nimbus Roman, serif"
INK, MUTED = S.C["INK"], S.C["MUTED"]


def t(x, y, s, size=11, w="normal", c=INK, anchor="middle"):
    return ('<text x="%.1f" y="%.1f" font-family="%s" font-size="%.1f" font-weight="%s" fill="%s" '
            'text-anchor="%s">%s</text>' % (x, y, FONT, size, w, c, anchor, s))


def panel(x, y, w, h, fill, stroke, dash=False, r=12):
    d = ' stroke-dasharray="4 3"' if dash else ""
    return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%d" fill="%s" stroke="%s" '
            'stroke-width="1.1"%s/>' % (x, y, w, h, r, fill, stroke, d))


def tile(x, y, w, h):
    return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="7" fill="white" stroke="%s" '
            'stroke-width="0.9"/>' % (x, y, w, h, S.lighten(MUTED, 0.55)))


# ---------- icons, drawn in a 40 x 40 box centered at (cx, cy) ----------

def robot(cx, cy, accent):
    a = accent
    return "".join([
        '<g transform="translate(%.1f %.1f)">' % (cx - 20, cy - 20),
        '<line x1="20" y1="3" x2="20" y2="8" stroke="%s" stroke-width="1.6"/>' % INK,
        '<circle cx="20" cy="3" r="2.2" fill="%s"/>' % a,
        '<rect x="7" y="8" width="26" height="18" rx="7" fill="white" stroke="%s" stroke-width="1.6"/>' % INK,
        '<rect x="11" y="12" width="18" height="10" rx="4" fill="%s"/>' % S.lighten(a, 0.75),
        '<circle cx="16" cy="17" r="1.9" fill="%s"/><circle cx="24" cy="17" r="1.9" fill="%s"/>' % (INK, INK),
        '<path d="M17 20.5 Q20 22.5 23 20.5" stroke="%s" stroke-width="1" fill="none"/>' % INK,
        '<rect x="4" y="13" width="3" height="7" rx="1.5" fill="%s"/>' % a,
        '<rect x="33" y="13" width="3" height="7" rx="1.5" fill="%s"/>' % a,
        '<rect x="10" y="27" width="20" height="11" rx="4" fill="%s" stroke="%s" stroke-width="1.4"/>' % (S.lighten(a, 0.55), INK),
        '<circle cx="20" cy="32.5" r="2" fill="white"/>',
        '</g>'])


def gpu(cx, cy, accent):
    pins = "".join('<line x1="%d" y1="6" x2="%d" y2="10" stroke="%s" stroke-width="1.3"/>'
                   '<line x1="%d" y1="30" x2="%d" y2="34" stroke="%s" stroke-width="1.3"/>'
                   % (x, x, INK, x, x, INK) for x in (13, 18, 23, 28))
    pins += "".join('<line x1="6" y1="%d" x2="10" y2="%d" stroke="%s" stroke-width="1.3"/>'
                    '<line x1="30" y1="%d" x2="34" y2="%d" stroke="%s" stroke-width="1.3"/>'
                    % (y, y, INK, y, y, INK) for y in (13, 18, 23, 28))
    return ('<g transform="translate(%.1f %.1f)">%s'
            '<rect x="10" y="10" width="20" height="20" rx="3" fill="white" stroke="%s" stroke-width="1.6"/>'
            '<rect x="14" y="14" width="12" height="12" rx="2" fill="%s"/></g>'
            % (cx - 20, cy - 20, pins, INK, accent))


def cache_stack(cx, cy, accent):
    out = ['<g transform="translate(%.1f %.1f)">' % (cx - 20, cy - 20)]
    for i, f in enumerate((0.35, 0.55, 0.75)):
        y = 8 + i * 8
        out.append('<rect x="8" y="%d" width="24" height="7" rx="2" fill="%s" stroke="%s" stroke-width="1.1"/>'
                   % (y, S.lighten(accent, f), INK))
    out.append('<path d="M26 34 l4 -4 l-4 -4" stroke="%s" stroke-width="1.4" fill="none"/>' % INK)
    out.append('</g>')
    return "".join(out)


def brain(cx, cy, accent):
    return ('<g transform="translate(%.1f %.1f)">'
            '<circle cx="20" cy="20" r="15" fill="%s" stroke="%s" stroke-width="1.6"/>'
            '<path d="M20 7 V33 M12 13 Q16 17 12 21 Q16 25 12 29 M28 13 Q24 17 28 21 Q24 25 28 29" '
            'stroke="%s" stroke-width="1.2" fill="none"/>'
            '<circle cx="31" cy="9" r="5" fill="white" stroke="%s" stroke-width="1.2"/>'
            '<path d="M31 6 v3 l2 1.5" stroke="%s" stroke-width="1.1" fill="none"/></g>'
            % (cx - 20, cy - 20, S.lighten(accent, 0.75), INK, INK, INK, INK))


def gauge(cx, cy, accent):
    return ('<g transform="translate(%.1f %.1f)">'
            '<path d="M7 27 A13 13 0 0 1 33 27" stroke="%s" stroke-width="1.6" fill="none"/>'
            '<path d="M24 16 A13 13 0 0 1 33 27" stroke="%s" stroke-width="3" fill="none"/>'
            '<line x1="20" y1="27" x2="27" y2="18" stroke="%s" stroke-width="1.6"/>'
            '<circle cx="20" cy="27" r="2.2" fill="%s"/>'
            '</g>' % (cx - 20, cy - 20, INK, accent, INK, INK))


def flatline(cx, cy, accent):
    return ('<g transform="translate(%.1f %.1f)">'
            '<polyline points="6,26 13,26 16,14 20,30 24,20 27,26 34,26" stroke="%s" stroke-width="1.6" fill="none"/>'
            '<line x1="6" y1="31" x2="34" y2="31" stroke="%s" stroke-width="1.2" stroke-dasharray="2 2"/></g>'
            % (cx - 20, cy - 20, accent, MUTED))


def cylinder(cx, cy, accent):
    return ('<g transform="translate(%.1f %.1f)">'
            '<path d="M9 11 V29 A11 4 0 0 0 31 29 V11" fill="%s" stroke="%s" stroke-width="1.5"/>'
            '<ellipse cx="20" cy="11" rx="11" ry="4" fill="white" stroke="%s" stroke-width="1.5"/>'
            '<path d="M9 20 A11 4 0 0 0 31 20" fill="none" stroke="%s" stroke-width="1.1"/></g>'
            % (cx - 20, cy - 20, S.lighten(accent, 0.75), INK, INK, INK))


def checkdoc(cx, cy, accent):
    return ('<g transform="translate(%.1f %.1f)">'
            '<path d="M10 6 H25 L31 12 V34 H10 Z" fill="white" stroke="%s" stroke-width="1.5"/>'
            '<line x1="14" y1="15" x2="24" y2="15" stroke="%s" stroke-width="1.1"/>'
            '<line x1="14" y1="20" x2="27" y2="20" stroke="%s" stroke-width="1.1"/>'
            '<circle cx="27" cy="29" r="6" fill="%s"/>'
            '<path d="M24.3 29 l2 2 l3.5 -4" stroke="white" stroke-width="1.5" fill="none"/></g>'
            % (cx - 20, cy - 20, INK, MUTED, MUTED, accent))


def opt_icon(kind, cx, cy, col):
    g = '<g transform="translate(%.1f %.1f)">' % (cx - 16, cy - 16)
    if kind == "restart":
        body = ('<path d="M15 6 A10 10 0 1 0 26 15" stroke="%s" stroke-width="2.4" fill="none"/>'
                '<path d="M14 1.5 L21 6 L14 10.5 Z" fill="%s"/>' % (col, col))
    elif kind == "resume":
        body = '<path d="M11 8 L25 16 L11 24 Z" fill="%s"/>' % col
    elif kind == "rollback":
        body = ('<path d="M17 8 L7 16 L17 24 Z" fill="%s"/><path d="M27 8 L17 16 L27 24 Z" fill="%s"/>'
                % (col, S.lighten(col, 0.4)))
    elif kind == "grounded":
        body = ('<rect x="8" y="6" width="16" height="20" rx="2" fill="white" stroke="%s" stroke-width="1.8"/>'
                '<path d="M12 16 l3 3 l6 -7" stroke="%s" stroke-width="2" fill="none"/>' % (col, col))
    else:
        body = ('<path d="M11 5 H21 L27 11 V21 L21 27 H11 L5 21 V11 Z" fill="%s"/>'
                '<rect x="11" y="14.5" width="10" height="3" fill="white"/>' % col)
    return g + body + "</g>"


def badge(cx, cy, n, col):
    return ('<circle cx="%.1f" cy="%.1f" r="7" fill="%s"/>' % (cx, cy, col)
            + t(cx, cy + 3.6, str(n), 9.5, "bold", "white"))


def arrow(x1, y, x2, color=INK):
    return ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1.6" '
            'marker-end="url(#ah)"/>' % (x1, y, x2, y, color))


def build():
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="6.9in" height="%.2fin" viewBox="0 0 %d %d">'
           % (6.9 * H / W, W, H),
           '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="%s"/></marker></defs>' % INK,
           '<rect width="%d" height="%d" fill="white"/>' % (W, H)]
    blue, mag, grn = S.C["SR"], S.C["CTRL"], S.C["RB"]
    soft = lambda c: S.lighten(c, 0.9)
    # row 1: three agents of the system
    boxes = ((15, "Agent", "multi turn tool use", blue, robot),
             (255, "Recovery controller", "decides at each failure", mag, brain),
             (495, "Serving engine", "vLLM, prefix cache", blue, None))
    for x, title, sub, col, icon in boxes:
        out.append(panel(x, 12, 180, 112, soft(col), S.lighten(col, 0.45)))
        out.append(t(x + 90, 32, title, 13, "bold"))
        out.append(t(x + 90, 46, sub, 9.5, "normal", MUTED))
        if icon is robot:
            out.append(robot(x + 62, 88, col))
            out.append('<g transform="translate(%d 72)">' % (x + 98)
                       + '<rect x="0" y="0" width="44" height="30" rx="4" fill="white" stroke="%s"/>' % INK
                       + '<line x1="6" y1="9" x2="30" y2="9" stroke="%s" stroke-width="1.2"/>' % MUTED
                       + '<line x1="6" y1="16" x2="38" y2="16" stroke="%s" stroke-width="1.2"/>' % MUTED
                       + '<line x1="6" y1="23" x2="24" y2="23" stroke="%s" stroke-width="1.2"/>' % MUTED
                       + '<circle cx="37" cy="7" r="5" fill="%s"/>' % S.C["FAIL"]
                       + '<path d="M34.5 4.5 l5 5 M39.5 4.5 l-5 5" stroke="white" stroke-width="1.3"/></g>')
            out.append(t(x + 120, 115, "tool error, timeout, ...", 8.5, "normal", MUTED))
        elif icon is brain:
            out.append(brain(x + 60, 88, col))
            out.append(robot(x + 115, 88, mag))
            out.append(t(x + 90, 117, "Beta posterior + energy law", 8.5, "normal", MUTED))
        else:
            out.append(gpu(x + 60, 88, col))
            out.append(cache_stack(x + 118, 88, col))
            out.append(t(x + 90, 117, "warm or cold KV prefix", 8.5, "normal", MUTED))
    out.append(arrow(197, 60, 253)); out.append(arrow(253, 78, 197))
    out.append(arrow(437, 60, 493)); out.append(arrow(493, 78, 437))
    # row 2: recovery options
    ox, ow = 150, 390
    out.append(panel(ox, 136, ow, 84, "white", S.lighten(MUTED, 0.5), r=10))
    out.append(t(ox + ow / 2, 152, "Recovery options (warm or cold cache)", 11, "bold"))
    opts = (("restart", "Restart", S.C["FR"]), ("resume", "Resume", S.C["SR"]),
            ("rollback", "Roll back", S.C["RB"]), ("grounded", "Grounded", S.C["SG"]),
            ("abandon", "Abandon", MUTED))
    step = ow / 5
    for i, (k, name, col) in enumerate(opts):
        cx = ox + step * (i + 0.5)
        if i:
            out.append('<line x1="%.1f" y1="160" x2="%.1f" y2="212" stroke="%s" stroke-dasharray="2 2"/>'
                       % (ox + step * i, ox + step * i, S.lighten(MUTED, 0.5)))
        out.append(badge(cx - 22, 166, i + 1, INK))
        out.append(opt_icon(k, cx, 184, col))
        out.append(t(cx, 212, name, 9.5))
    out.append('<line x1="345" y1="124" x2="345" y2="134" stroke="%s" stroke-width="1.6" marker-end="url(#ah)"/>'
               % INK)
    # row 3: measurement
    out.append(panel(15, 232, 660, 104, soft(grn), S.lighten(grn, 0.4), dash=True))
    out.append(t(345, 250, "Measurement (A-LEMS): every attempt in its own window", 11, "bold"))
    items = (("Board power", gauge, grn), ("Package power", lambda x, y, c: gpu(x, y, c), grn),
             ("Idle baseline", flatline, grn), ("Store (read only)", cylinder, grn),
             ("Checker verdict", checkdoc, grn))
    tw, gap = 112, 16
    x0 = (W - (5 * tw + 4 * gap)) / 2
    for i, (name, fn, col) in enumerate(items):
        x = x0 + i * (tw + gap)
        out.append(tile(x, 260, tw, 66))
        out.append('<g transform="translate(%.1f 286) scale(1.3) translate(%.1f -286)">' % (x + tw / 2, -(x + tw / 2))
                   + fn(x + tw / 2, 286, col) + "</g>")
        out.append(t(x + tw / 2, 319, name, 9.5))
    out.append("</svg>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="figures")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    svg = build()
    p = os.path.join(a.out, "F0_overview.svg")
    open(p, "w").write(svg)
    try:
        import cairosvg
        cairosvg.svg2pdf(bytestring=svg.encode(), write_to=os.path.join(a.out, "F0_overview.pdf"))
        cairosvg.svg2png(bytestring=svg.encode(), write_to=os.path.join(a.out, "F0_overview.png"), scale=2.5)
    except ImportError:
        print("cairosvg missing: pip install cairosvg, or export the SVG to PDF with Inkscape")


if __name__ == "__main__":
    main()
