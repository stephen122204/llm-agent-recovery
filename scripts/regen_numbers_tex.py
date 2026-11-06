#!/usr/bin/env python3
"""Rebuild numbers_auto.tex from saved numbers_auto.json without store access.

Escapes LaTeX special characters in macro values (a raw % in a value comments out the closing brace and
breaks the build) and carries the R5 or E3 label and significance flags from provenance as comments.
paper_numbers.py writes the same format from now on; this script repairs an existing output in place.

Usage: python3 scripts/regen_numbers_tex.py OUTPUT_FOLDER
"""
import datetime
import json
import os
import re
import sys


def esc(v):
    """Escape % & # in plain text values; leave LaTeX commands (\\pending{...}, {,}) intact."""
    return re.sub(r"(?<!\\)([%&#])", r"\\\1", str(v))


def note(src):
    for key in ("OFFLINE CALIBRATED RULE", "E3 RULE BASELINE", "ONLINE LEARNING CONTROLLER", "E3 FIXED POLICY"):
        if key in src:
            tag = key
            if "NOT SIGNIFICANT" in src:
                tag += "; NOT SIGNIFICANT: 95 percent CI includes 0"
            return " % " + tag
    return ""


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: regen_numbers_tex.py OUTPUT_FOLDER (containing numbers_auto.json)")
    d = sys.argv[1]
    j = json.load(open(os.path.join(d, "numbers_auto.json")))
    vals, prov = j["values"], j.get("provenance", {})
    head = "%% GENERATED from numbers_auto.json (%s) at %s; do not edit by hand.\n" % (
        j.get("generated"), datetime.datetime.now().isoformat(timespec="seconds"))
    body = "".join("\\providecommand{\\%s}{}\\renewcommand{\\%s}{%s}%s\n"
                   % (k, k, esc(v), note(prov.get(k, ""))) for k, v in sorted(vals.items()))
    open(os.path.join(d, "numbers_auto.tex"), "w").write(head + body)
    print("wrote %d macros to %s" % (len(vals), os.path.join(d, "numbers_auto.tex")))


if __name__ == "__main__":
    main()
