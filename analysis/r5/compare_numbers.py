"""RAF R5 (frozen rerun check): compare two r5_numbers.json files field by field.
Reports every {value, ci} field whose sign changed or whose CI changed between including and excluding zero,
plus fields present in only one file, booleans and integers that changed.
Usage: python compare_numbers.py <old_r5_numbers.json> <new_r5_numbers.json>
Exit code 0 always; read the report.
"""
import json
import sys


def flat(d, p=""):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict) and "value" in v and "ci" in v:
            out[p + k] = ("ci", v["value"], v["ci"])
        elif isinstance(v, dict):
            out.update(flat(v, p + k + "."))
        elif isinstance(v, bool):
            out[p + k] = ("bool", v, None)
        elif isinstance(v, int):
            out[p + k] = ("int", v, None)
        elif isinstance(v, float):
            out[p + k] = ("float", v, None)
    return out


def zero_in(ci):
    return ci is not None and len(ci) == 2 and ci[0] is not None and ci[1] is not None and ci[0] <= 0 <= ci[1]


def sign(x):
    return 0 if x is None or x == 0 else (1 if x > 0 else -1)


def main(a, b):
    A, Bn = flat(json.load(open(a))), flat(json.load(open(b)))
    flags = 0
    for k in sorted(set(A) | set(Bn)):
        if k not in A or k not in Bn:
            print(f"ONLY {'new' if k in Bn else 'old'}: {k}")
            continue
        ta, va, ca = A[k]
        tb, vb, cb = Bn[k]
        if ta == "ci":
            s = sign(va) != sign(vb)
            z = zero_in(ca) != zero_in(cb)
            tag = ("SIGN " if s else "") + ("SIGNIFICANCE " if z else "")
            if tag:
                flags += 1
            print(f"{tag or 'ok '}{k}: {va:.4g} {ca} -> {vb:.4g} {cb}")
        elif va != vb:
            if ta == "bool":
                flags += 1
                print(f"BOOL {k}: {va} -> {vb}")
            else:
                print(f"changed {k}: {va} -> {vb}")
    print(f"flags (sign, significance or boolean changes): {flags}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
