#!/usr/bin/env python3
"""provenance_table.py: tables/provenance_table.tex from the frozen archive's provenance_all.json (R8, Oct 22).

Rows only (no leading \\midrule), ending with \\bottomrule. Columns:
  study (paper name) & engine & model & precision & tool parser & temperature & seed \\\\
No commit ids, paths or internal names in the table. Engine letters are copied verbatim from R2's
provenance_studies.tsv (never reassigned); its sha256 is written in the file's first comment line.
Stops (nothing written) if: either input sha256 differs, a study is not in the name map or the tsv, a precision or
model is unknown, or two archive studies merged into one paper row disagree on any column other than seed.

Usage:
  python3 provenance_table.py --prov inputs/run/frozen_oct23/final/provenance_all.json \\
    --out ./tex/tables/provenance_table.tex
"""
import argparse
import hashlib
import json
import re
import sys

EXPECT = "ba6d13846cb65acb56ff3b50aba8caba02385655130796d9fc9cb2d112ea1702"  # MANIFEST_SHA256.txt, final/provenance_all.json
ENGINES_SHA = "60ec7af3"  # R2 provenance_studies.tsv: engine letters are R2's, never reassigned (coordinator, Oct 22)
TSV_NAME = {"raf_samp s1": "raf_samp", "raf_samp s2": "raf_samp", "raf_samp s3": "raf_samp",
            "GB10 sweep gpt-oss": "GB10 sweep, gpt-oss", "GB10 sweep Qwen": "GB10 sweep, Qwen"}

# archive study name -> paper name (R8 list, Oct 22); several archive studies may share one paper row
NAMES = {
    "E1": "Main study restart and resume",
    "E1b": "Main study roll back and grounded resume",
    "E2": "First contaminating study",
    "E2b r2": "Second contaminating study",
    "E3": "Online study",
    "raf_mid": "Middle positions",
    "raf_m3": "Second model",
    "raf_m4": "Third model",
    "raf_samp s1": "Sampling",
    "raf_samp s2": "Sampling",
    "raf_samp s3": "Sampling",
    "GB10 sweep gpt-oss": "Context sweep",
    "GB10 sweep Qwen": "Context sweep",
}
# precision text in the archive -> table text
PREC = {
    "FP8 weights (repo)": "FP8",
    "bf16 repo, FP8 at load (--quantization fp8)": "FP8 at load (bf16 weights)",
    "MXFP4 (repo native)": "MXFP4",
}
# model text in the archive -> table text (precision has its own column)
MODEL = {
    "Qwen3 30B A3B Instruct 2507 FP8": "Qwen3 30B",
    "Mistral Small 3.2 24B Instruct 2506, dense, 8 bit": "Mistral 24B",
    "gpt-oss 20B, MXFP4": "gpt-oss 20B",
}
CODE = {"Main study restart and resume": "M1", "Main study roll back and grounded resume": "M2",
        "First contaminating study": "C1", "Second contaminating study": "C2", "Online study": "O",
        "Middle positions": "Mid", "Second model": "Mis", "Third model": "Gpt", "Sampling": "T"}


def code(name, model):
    """R8's short study codes (Oct 23); same codes as audit_table.tex and study_counts.json."""
    if name == "Context sweep":
        return "Sw1" if model == "Qwen3 30B" else "Sw2"
    return CODE[name]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def temperature(text):
    """Sampling temperature from the archive's free text: 'T 0.7 ...' wins, else the leading number."""
    m = re.search(r"\bT (\d+(?:\.\d+)?)", text or "")
    if not m:
        m = re.match(r"\s*(\d+(?:\.\d+)?)", text or "")
    if not m:
        raise SystemExit("no temperature in %r" % text)
    return "%g" % float(m.group(1))


def parser(cmd):
    m = re.search(r"--tool-call-parser\s+(\S+)", cmd or "")
    return m.group(1) if m else "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prov", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--engines", required=True, help="R2 provenance_studies.tsv (engine letters)")
    ap.add_argument("--counts", required=True, help="data/figdata/study_counts.json (tasks, valid goals per study)")
    a = ap.parse_args()
    he = sha256(a.engines)
    if not he.startswith(ENGINES_SHA):
        raise SystemExit("provenance_studies.tsv sha256 %s, expected %s...; nothing written" % (he, ENGINES_SHA))
    tsv = [l.rstrip("\n").split("\t") for l in open(a.engines) if l.strip()]
    engine_of = {r[0]: r[1] for r in tsv[1:]}
    h = sha256(a.prov)
    if h != EXPECT:
        raise SystemExit("provenance_all.json sha256 %s, expected %s; nothing written" % (h, EXPECT))
    studies = json.load(open(a.prov))
    counts = json.load(open(a.counts))

    letters = {}  # commit -> letter, in order of first use
    rows = {}  # (paper name, model) -> merged row
    order = []
    for s in studies:
        name = NAMES.get(s["study"])
        if not name:
            raise SystemExit("study %r not in the name map; nothing written" % s["study"])
        if s.get("model") not in MODEL or s.get("precision") not in PREC:
            raise SystemExit("unknown model or precision in %s: %r, %r" % (s["study"], s.get("model"), s.get("precision")))
        tname = TSV_NAME.get(s["study"], s["study"])
        if tname not in engine_of:
            raise SystemExit("study %r (%r) not in provenance_studies.tsv; nothing written" % (s["study"], tname))
        seeds = {json.loads(x)["model_seed"] for x in s.get("seeds", [])}
        row = {"engine": ", ".join(dict.fromkeys(re.findall(r"\b[A-Z]\b", engine_of[tname]))),  # letters only (R8, Oct 22)
               "model": MODEL[s["model"]], "prec": PREC[s["precision"]],
               "parser": parser(s.get("vllm_command")), "temp": temperature(s.get("temperature")), "seeds": seeds}
        key = (name, row["model"])  # the context sweep has one row per model
        if key not in rows:
            rows[key] = row
            order.append(key)
            continue
        old = rows[key]
        for k in ("engine", "model", "prec", "parser", "temp"):
            if old[k] != row[k]:
                raise SystemExit("%s: %s differs between merged archive studies (%r vs %r); nothing written"
                                 % (name, k, old[k], row[k]))
        old["seeds"] |= seeds

    lines = []
    for key in order:
        r = rows[key]
        seed = ", ".join(str(x) for x in sorted(r["seeds"]))
        sc = code(key[0], r["model"])
        cn = counts.get(sc)
        if cn is None:
            raise SystemExit("no counts for %s in study_counts.json; nothing written" % sc)
        lines.append("%s & %s & %s & %s & %s & %s & %s & %d & %s \\\\" % (sc, r["engine"], r["model"], r["prec"],
                     r["parser"], r["temp"], seed, cn["tasks"], "{:,}".format(cn["valid"]).replace(",", "{,}")))
    head = ("% GENERATED by provenance_table.py; do not edit by hand. Source provenance_all.json sha256 " + h +
            "; engine letters from R2 provenance_studies.tsv sha256 " + he + ".\n")
    open(a.out, "w").write(head + "\n".join(lines) + "\n\\bottomrule\n")
    print("wrote %d rows to %s" % (len(lines), a.out))


if __name__ == "__main__":
    main()
