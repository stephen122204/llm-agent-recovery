#!/usr/bin/env python3
"""paper_extra.py: macros from checked files outside the live store (runs on the Mac mini, no GN100).

Writes, in --paper:
  numbers_extra.tex   \\providecommand plus \\renewcommand per macro (never edit by hand); \\input it after numbers_auto
  numbers_extra.json  values, provenance, sha256 of every input file
  tables/e2b_table.tex (when --db and --art are given)

Inputs (each optional; a missing input leaves its macros \\pending with the reason):
  --db, --art   store snapshot and artifacts folder: E2b via e2b_numbers.py
  --r7          r7_numbers.json: every entry under values, display text copied as is
  --r5tok       R5 _tok r5_numbers.json: token rule fields and lawCtx*, copied, never recomputed
  --r6          folder with R6 t1 to t6 json files
Expected sha256 values are checked; a mismatch stops the run unless --allow-sha-mismatch.

Usage (Mac mini):
  python3 paper_extra.py --paper inputs/paper_extra \\
    --db inputs/raf_snapshot_oct18.db --art inputs/artifacts \\
    --r7 inputs/r7/r7_numbers.json --r6 inputs \\
    --r5tok inputs/r5tok/r5_numbers.json
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paper_numbers as pn  # noqa: E402  (wilson, fmt0, sha256)

EXPECT = {
    "r7": "72c8a74464c1bf1b328fa50670c0ac3917b6e230ca1af88ca0b293d005dc13c9",
    "r5tok": "e8fd1266aec90ec39ff24c8c6d28acb7622973f3f0229fa25ec8de16b864752c",  # R5 frozen rerun, Oct 22
    "r5mid": "f5bdc59b0aed530272fba4883642d9531dfe33fd29bbd365464b925452b3a2cb",
    "r5m3": "6807687ea51c10e804c67013640a5a0caaacb06694dc7e99739a1c2b70b705fc",
    "r5m4": "0b3c4b329eff758b0d68a6a86c86985190bb9d9877598fb179316f6501d87927",
    "r5sweep": "73fb1e850cff75f39bb37d7f3c3b9361bd29de4e50ecf25eb1b77d433e35333b",
    "r5samp": "606c7203c1f978f427d0dff8012d9424fa267cb5a00430fdd3c11e13f44fcf18",
    "e3dec": "3537f813842af1a4387a46c6c24499cfe2aa1204f5dab21d160aef5613057c5d",
    "t1_ctrl_split_match.json": "52a0b7401ca697ab143a8af55285cc4990a0a71b72931acc6d725592d2286645",
    "t2_option_counts.json": "adc462c41f6821090edf5caf48c05a741e87d7362b630b10c358043eae58c477",
    "t3_ctrl_by_option.json": "666d8a8721b562bd9e0622ec0cfdc0c74c5007fb06726a72edf09c1404618b72",
    "t4_explore_cost.json": "bce7c54545a6719072abf96e09d220034d311ad06ac5b5ef99031761356f4508",
    "t5_learn_curve.json": "ea8397ee090bc1b80dcf9dc783c4f96ab6007d24a1cdd41215074f1f27cd7a2e",
    "t6_overhead.json": "e0a385d0cd614ba432131330e6d788067e004e7bcd2c35e002e6c23af1892375",
    "t3c_class_split.json": "5dcd2d99f032716380aad8c21d68e445b42e927e2d1351842306d8f63cb69ae5",
    "t7d_whatif_coverage.json": "2ae1965cfe23b4f34dc6ceadd3486030657261cadb04a0c50b6915d73478779b",
    "t7c_context_changed.json": "e14158da59e9d3dff9552a89960d84cd350b8578889212b6840493b113e6ba3f",
    "r7_changed_44.tsv": "6a1c851773dcc09831926ef71595f3a159d5b4113e78fda58b4853649f543d69",
}
R5_LABEL = "OFFLINE CALIBRATED RULE (R5, data_tag e1_e1b_e2_v2, token rules)"
R6_LABEL = "ONLINE LEARNING CONTROLLER (E3), R6 diagnosis"
R5MID_LABEL = "SLICE MIDDLE POSITIONS (R5, data_tag e1_e1b_e2_e2b_mid)"
R7_LABEL = "R7"


def e3_point_split(st, art, put, NOTE, shas):
    """ctrlVsTokenEarly and ctrlVsTokenLate: same rule and function as ctrlOnlineVsTokenRule in paper_numbers.py
    (E3 split ledgers, latest valid per (item, arm, policy), boot_saving of (ctrl_beta, token_rule) pairs over the
    situations of one point). Negative means the controller uses more board energy per successful goal."""
    import glob
    paths = sorted(glob.glob(os.path.join(art, "raf_e3", "raf_e3_items_raf_e3_split_*_ledger.jsonl")))
    label = "ONLINE LEARNING CONTROLLER (E3), point split"
    if not paths:
        for pt in ("Early", "Late"):
            for suf in ("", "Lo", "Hi"):
                put("ctrlVsToken" + pt + suf, "\\pending{ctrlVsToken%s%s}" % (pt, suf), "pending: no E3 ledgers")
        return
    best = {}
    for p in paths:
        shas[p] = pn.sha256(p)
        for line in open(p):
            d = json.loads(line)
            if not d.get("goal_id") or d.get("validity"):
                continue
            pl = d.get("plan", {})
            arm = pl.get("arm") or d.get("arm")
            lab = pl.get("policy") if arm == "fixed" else arm
            key = (d.get("item_id"), arm, pl.get("policy"))
            gid = int(d["goal_id"])
            if key not in best or gid > best[key][0]:
                best[key] = (gid, (pl.get("task"), pl.get("cls"), pl.get("point") or "", lab))
    c3 = pn.cells(st, dict(best.values()))
    src = "%s; E3 split ledgers, latest valid per (item, arm, policy), paired bootstrap over tasks, %d resamples, " \
          "seed %d, board per achieved; negative = controller above token rule" % (label, pn.BOOT_REPS, pn.BOOT_SEED)
    for pt in ("early", "late", None):
        sit = [(c, p) for (c, p, pol) in c3 if pol == "ctrl_beta" and (pt is None or p == pt)
               and (c, p, "token_rule") in c3]
        if not sit:
            continue
        p_, lo, hi, nt, nu = pn.boot_saving([(c3[(c, p, "ctrl_beta")], c3[(c, p, "token_rule")]) for c, p in sit])
        if pt is None:
            print("check: all points ctrl vs token_rule %.1f (%.1f to %.1f), must equal ctrlOnlineVsTokenRule" % (p_, lo, hi))
            continue
        name = "ctrlVsToken" + pt.capitalize()
        flag = "" if (lo > 0 or hi < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
        s = "%s, %s, %d situations, %d tasks, %d undefined draws%s" % (src, pt, len(sit), nt, nu, flag)
        for suf, v in (("", p_), ("Lo", lo), ("Hi", hi)):
            put(name + suf, "%.1f" % v, s)
            NOTE[name + suf] = label + flag

    # class split (coordinator Oct 19 17:12): early is a claim, late is appendix; same rule and boot_saving
    for pt in ("early", "late"):
        for cls, cam in (("tool_error", "Tool"), ("json_parse", "Json")):
            name = "ctrlVsToken%s%s" % (pt.capitalize(), cam)
            ca, cb = c3.get((cls, pt, "ctrl_beta")), c3.get((cls, pt, "token_rule"))
            if not ca or not cb:
                for suf in ("", "Lo", "Hi", "Blocks"):
                    put(name + suf, "\\pending{%s}" % (name + suf), "pending: E3 cell %s %s missing" % (cls, pt))
                continue
            p_, lo, hi, nt, nu = pn.boot_saving([(ca, cb)])
            flag = "" if (lo > 0 or hi < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
            tier = "claim" if pt == "early" else "appendix"
            s = "%s, %s %s (%s), %d tasks, %d undefined draws%s" % (src, cls, pt, tier, nt, nu, flag)
            for suf, v in (("", p_), ("Lo", lo), ("Hi", hi)):
                put(name + suf, "%.1f" % v, s)
                NOTE[name + suf] = label + ", " + tier + flag
            put(name + "Blocks", str(nt), s + ", blocks = tasks with a valid goal in both arms")
            NOTE[name + "Blocks"] = label + ", " + tier
            if (pt, cls) == ("late", "tool_error"):
                for arm, cv in (("CtrlBeta", ca), ("TokenRule", cb)):
                    nm = "ethreeLateTool%sOk" % arm
                    wl, wh = pn.wilson(cv["ok"], cv["n"])
                    put(nm, "%d of %d" % (cv["ok"], cv["n"]), src + ", tool_error late, appendix")
                    put(nm + "Lo", "%.0f" % (100 * wl), "Wilson 95, " + src + ", tool_error late")
                    put(nm + "Hi", "%.0f" % (100 * wh), "Wilson 95, " + src + ", tool_error late")
                    for x in ("", "Lo", "Hi"):
                        NOTE[nm + x] = label + ", appendix"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True, help="output folder (paper tex folder or a staging folder)")
    ap.add_argument("--db")
    ap.add_argument("--art")
    ap.add_argument("--r7")
    ap.add_argument("--r5tok")
    ap.add_argument("--r5m3", help="R5 Mistral r5_numbers.json (m3 prefixed fields only)")
    ap.add_argument("--r5m4", help="R5 gpt-oss r5_numbers.json (m4 prefixed fields only)")
    ap.add_argument("--r5sweep", help="R5 GN100 sweep law r5_numbers.json")
    ap.add_argument("--r5samp", help="R5 raf_samp r5_numbers.json")
    ap.add_argument("--r5mid", help="R5 mid r5_numbers.json: xstarMid*, silentDirect, silentResumeLowerAllPos only")
    ap.add_argument("--r6", help="folder with R6 t1 to t6 json files")
    ap.add_argument("--r7parity", help="R7 parity_e3.json (earParity, read by name)")
    ap.add_argument("--allow-sha-mismatch", action="store_true")
    ap.add_argument("--auto", help="numbers_auto.json written by paper_numbers.py: fail if any macro is defined in "
                                   "both, else merge this script's values and provenance into it")
    a = ap.parse_args()

    M, prov, NOTE, shas = {}, {}, {}, {}
    NOMACRO = {}  # files hashed into provenance that give no macro, with the reason

    def put(name, val, src):
        M[name] = val
        prov[name] = src

    def pend(name, why):
        put(name, "\\pending{%s}" % name, "pending: " + why)

    def check(key, path):
        h = pn.sha256(path)
        shas[path] = h
        want = EXPECT.get(key)
        if want and h != want:
            msg = "sha256 of %s is %s, expected %s" % (path, h, want)
            if not a.allow_sha_mismatch:
                raise SystemExit(msg)
            print("SHA MISMATCH: " + msg)
            return False
        return True

    # ---- E2b (store snapshot) ----
    if a.db and a.art:
        import e2b_numbers
        st = pn.Store(a.db)
        shas[a.db] = pn.sha256(a.db)
        e2b_numbers.add(st, a.art, put, NOTE, a.paper)
        for p in e2b_numbers.ledger_paths(a.art):
            shas[p] = pn.sha256(p)
        # ---- E3 controller vs token rule, early and late (R6 diagnosis, recomputed with boot_saving) ----
        e3_point_split(st, a.art, put, NOTE, shas)
        # ---- E3 controller choice shares (coordinator Oct 19 17:38), e3_decisions.jsonl ----
        dec_path = os.path.join(a.art, "raf_e3", "e3_decisions.jsonl")
        if os.path.exists(dec_path):
            check("e3dec", dec_path)
            decs = [json.loads(l) for l in open(dec_path) if l.strip()]
            ctrl = [d.get("option") for d in decs if d.get("arm") == "ctrl_beta"]
            src = ("ONLINE LEARNING CONTROLLER (E3); e3_decisions.jsonl sha256 %s, arm ctrl_beta, "
                   "field option, %d decisions" % (shas[dec_path], len(ctrl)))
            for opt, cam in (("SR_cold", "SrCold"), ("SG_warm", "SgWarm")):
                k, n = sum(1 for o in ctrl if o == opt), len(ctrl)
                nm = "ctrlChoice" + cam
                if not n:
                    pend(nm, "no ctrl_beta decisions in " + dec_path)
                    continue
                lo, hi = pn.wilson(k, n)
                put(nm, "%.1f" % (100.0 * k / n), src + ", option " + opt)
                put(nm + "N", "%d of %d" % (k, n), src + ", option " + opt)
                put(nm + "Lo", "%.0f" % (100 * lo), "Wilson 95, " + src + ", option " + opt)
                put(nm + "Hi", "%.0f" % (100 * hi), "Wilson 95, " + src + ", option " + opt)
                for x in ("", "N", "Lo", "Hi"):
                    NOTE[nm + x] = "ONLINE LEARNING CONTROLLER (E3), choice share"
            print("check: SR_cold plus SG_warm %d of %d, must equal ctrlRareOptionShareN"
                  % (sum(1 for o in ctrl if o in ("SR_cold", "SG_warm")), len(ctrl)))
        else:
            pend("ctrlChoiceSrCold", "no e3_decisions.jsonl under " + a.art)
            pend("ctrlChoiceSgWarm", "no e3_decisions.jsonl under " + a.art)
    else:
        pend("etwobSelfCorrect", "no --db and --art given")

    # ---- R7 (copied as is: display text) ----
    if a.r7 and os.path.exists(a.r7):
        check("r7", a.r7)
        vals = json.load(open(a.r7))["values"]
        for k, v in vals.items():
            label = v.get("label", R7_LABEL)
            put(k, v.get("display", v.get("value")), "R7 r7_numbers.json sha256 %s; source %s; kind %s; label %s"
                % (shas[a.r7], v.get("source"), v.get("kind"), label))
            NOTE[k] = "R7, " + label + ((", NO HASHED SOURCE" if k == "layaParams" else ""))
    else:
        pend("sweepCtxMax", "no --r7 file given")

    # ---- R7 EAR parity (by name) ----
    if a.r7parity and os.path.exists(a.r7parity):
        shas[a.r7parity] = pn.sha256(a.r7parity)
        pj = json.load(open(a.r7parity))
        v = pj.get("earParity", (pj.get("values") or {}).get("earParity"))
        if v is None and pj.get("name") == "earParity":
            v = pj.get("result")  # R7 file of record layout: {"name": "earParity", "result": "111 of 111"}
        if isinstance(v, dict):
            v = v.get("display", v.get("value"))
        if v is None:
            pend("earParity", "no earParity field in %s (top level or under values)" % a.r7parity)
        else:
            put("earParity", str(v), "R7 parity_e3.json sha256 %s, field earParity" % shas[a.r7parity])
            NOTE["earParity"] = "R7, EAR parity on E3 decisions"
    else:
        pend("earParity", "R7 parity_e3.json not given")

    # ---- R5 token rules (copied; R5 stores fractions for success, percent for savings and regret) ----
    r5names = {"ctrlSavingVsBilled": ("ci", 1.0, "%.1f"), "ctrlSavingVsUncached": ("ci", 1.0, "%.1f"),
               "uncachedRuleSucc": ("one", 100.0, "%.1f"), "billedRuleSucc": ("one", 100.0, "%.1f"),
               "uncachedRuleRegret": ("one", 1.0, "%.1f"), "billedRuleRegret": ("one", 1.0, "%.1f"),
               "tokenRuleDisagree": ("raw", 1.0, None),
               "xstarRuleRegret": ("one", 1.0, "%.1f"), "gbrBlocksActed": ("int", 1.0, None),
              "sgLowestCount": ("int", 1.0, None), "sgSituations": ("int", 1.0, None), "nCtrlBlocksTotal": ("int", 1.0, None),
"lawCtxMax": ("int", 1.0, None), "lawCtxPNinetyFive": ("int", 1.0, None), "lawCtxN": ("int", 1.0, None)}
    not_sig = ("ctrlSavingVsUncached",)
    if a.r5tok and os.path.exists(a.r5tok):
        check("r5tok", a.r5tok)
        g = json.load(open(a.r5tok))
        tag = (g.get("provenance") or {}).get("data_tag")
        base = "%s; r5 _tok sha256 %s, data_tag %s" % (R5_LABEL, shas[a.r5tok], tag)

        def get(name):
            v = g.get(name)
            if isinstance(v, dict):
                return v.get("value"), v.get("ci")
            return v, g.get(name + "CI")

        for nm, (kind, scale, fmt) in r5names.items():
            val, ci = get(nm)
            if val is None:
                for suf in ("", "Lo", "Hi") if kind == "ci" else ("",):
                    pend(nm + suf, "%s not in the _tok file" % nm)
                continue
            if kind == "int":
                txt = pn.fmt0(int(val))
            elif kind == "raw":
                txt = "%g" % val
            else:
                txt = fmt % (val * scale)
            put(nm, txt, base + ", key %s%s" % (nm, ", raw unit as in the file" if kind == "raw" else ""))
            NOTE[nm] = R5_LABEL
            if kind == "ci":
                if not ci or len(ci) != 2:
                    for suf in ("Lo", "Hi"):
                        pend(nm + suf, "%s has no two value CI in the _tok file" % nm)
                    continue
                for suf, x in (("Lo", ci[0]), ("Hi", ci[1])):
                    put(nm + suf, fmt % (x * scale), base + ", key %sCI[%d]" % (nm, 0 if suf == "Lo" else 1))
                    NOTE[nm + suf] = R5_LABEL
                sig0 = ci[0] <= 0 <= ci[1]
                if nm in not_sig and sig0:
                    for suf in ("", "Lo", "Hi"):
                        NOTE[nm + suf] += "; NOT SIGNIFICANT: 95 percent CI includes 0"
                        prov[nm + suf] += "; NOT SIGNIFICANT: 95 percent CI includes 0"
                elif nm in not_sig:
                    print("SIGNIFICANCE FLAG MISMATCH: %s CI %s excludes 0" % (nm, ci))
                elif sig0:
                    print("SIGNIFICANCE NOTE: %s CI %s includes 0 (stated as a claim)" % (nm, ci))
    else:
        for nm, (kind, _, _) in r5names.items():
            for suf in ("", "Lo", "Hi") if kind == "ci" else ("",):
                pend(nm + suf, "R5 _tok file not on this machine yet")

    # ---- R5 middle slice (coordinator Oct 19 18:16): xstarMid*, silentDirect, silentResumeLowerAllPos only ----
    mid_cls = (("JsonParse", "json_parse"), ("RateLimit", "rate_limit"), ("Timeout", "timeout"), ("ToolError", "tool_error"))
    mid_dir = [(pt, cam_pt, opt, cam_o) for pt, cam_pt in (("early", "Early"), ("middle", "Middle"))
               for opt, cam_o in (("FR_warm", "FrWarm"), ("RB_cold", "RbCold"))]
    if a.r5mid and os.path.exists(a.r5mid):
        check("r5mid", a.r5mid)
        mj = json.load(open(a.r5mid))
        mtag = (mj.get("xstarMidProvenance") or {}).get("data_tag")
        if mtag not in ("e1_e1b_e2_e2b_mid", "frozen_mid"):  # frozen_mid = R5 rerun on the frozen database (Oct 22)
            raise SystemExit("r5mid data_tag is %r, expected frozen_mid or e1_e1b_e2_e2b_mid" % mtag)
        mbase = "%s; r5 mid sha256 %s, data_tag %s" % (R5MID_LABEL, shas[a.r5mid], mtag)
        for cam, cls in mid_cls + (("SilentDetected", "silent_detected"),):
            nm = "xstarMid" + cam
            val, ci = mj.get(nm), mj.get(nm + "CI")
            if mj.get(nm + "Identified") is not True or val is None or not ci or len(ci) != 2:
                NOMACRO[nm] = "%s not identified in the mid file (%sIdentified %s), no macro (Rule C)" % (
                    cls, nm, mj.get(nm + "Identified"))
                continue
            for suf, x in (("", val), ("Lo", ci[0]), ("Hi", ci[1])):
                put(nm + suf, "%.1f" % x, mbase + ", key %s%s, calls" % (nm, "" if not suf else "CI[%d]" % (suf == "Hi")))
                NOTE[nm + suf] = R5MID_LABEL + (", O14: no middle data for this class; value carried from its same side class pair, not a middle measurement" if cam in ("JsonParse", "Timeout") else "")
        sd = mj.get("silentDirect") or {}
        for pt, cam_pt, opt, cam_o in mid_dir:
            nm = "silentDirect" + cam_pt + cam_o
            v = (sd.get(pt) or {}).get(opt)
            if not isinstance(v, dict) or v.get("saving_pct") is None or not v.get("ci") or len(v["ci"]) != 2:
                pend(nm, "silentDirect.%s.%s missing or without a two value ci" % (pt, opt))
                continue
            lo, hi = v["ci"]
            flag = "" if (lo > 0 or hi < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
            s = "%s, silentDirect.%s.%s, resume (SR_warm) vs %s, board per achieved, negative = resume above %s, " \
                "%s tasks, %s nan draws%s" % (mbase, pt, opt, opt, opt, v.get("tasks"), v.get("nan_draws"), flag)
            for suf, x in (("", v["saving_pct"]), ("Lo", lo), ("Hi", hi)):
                put(nm + suf, "%.1f" % x, s)
                NOTE[nm + suf] = R5MID_LABEL + ", negative = %s lower than resume (SR_warm), positive = resume lower" % opt + flag
            put(nm + "Tasks", str(v.get("tasks")), s)
            for key, cam_k in (("succ_resume", "SuccResume"), ("succ_other", "SuccOther")):
                txt = str(v.get(key) or "")
                put(nm + cam_k, txt.replace("/", " of ") if txt else "\\pending{%s}" % (nm + cam_k), s + ", " + key)
            for x in ("Tasks", "SuccResume", "SuccOther"):
                NOTE[nm + x] = R5MID_LABEL
        # positive form for Sec 5.3 (R8, Oct 23): the other option's saving against resume, early silent failures.
        # s = R5's saving of resume vs the other (fraction); the other's saving vs resume is 1 - 1/(1 - s), a monotone
        # map, so the percentile CI converts exactly with its ends swapped (old Hi gives new Lo).
        for opt, nm in (("FR_warm", "silentRestartSave"), ("RB_cold", "silentRollbackSave")):
            v = (sd.get("early") or {}).get(opt)
            if not isinstance(v, dict) or v.get("saving_pct") is None or not v.get("ci") or len(v["ci"]) != 2:
                pend(nm, "silentDirect.early.%s missing" % opt)
                continue
            t = lambda s: 100.0 * (1.0 - 1.0 / (1.0 - s / 100.0))
            vals = (t(v["saving_pct"]), t(v["ci"][1]), t(v["ci"][0]))
            flag = "" if (vals[1] > 0 or vals[2] < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
            s_ = ("%s, from silentDirect.early.%s (resume vs %s) by 1 - 1/(1 - s), CI ends swapped; positive = %s lower "
                  "energy per successful goal than resume (SR_warm) after early silent failures%s" % (mbase, opt, opt, opt, flag))
            for suf, x in (("", vals[0]), ("Lo", vals[1]), ("Hi", vals[2])):
                put(nm + suf, "%.1f" % x, s_)
                NOTE[nm + suf] = R5MID_LABEL + ", %s saving vs resume, early silent, positive = %s lower%s" % (opt, opt, flag)
        flag_all = mj.get("silentResumeLowerAllPos")
        if flag_all is None:
            pend("silentResumeLowerAllPos", "no silentResumeLowerAllPos in the mid file")
        else:
            put("silentResumeLowerAllPos", str(flag_all).lower(), mbase + ", key silentResumeLowerAllPos")
            NOTE["silentResumeLowerAllPos"] = R5MID_LABEL
    else:
        for cam, _ in mid_cls:
            pend("xstarMid" + cam, "R5 mid file not given")
        for pt, cam_pt, opt, cam_o in mid_dir:
            pend("silentDirect" + cam_pt + cam_o, "R5 mid file not given")
        pend("silentResumeLowerAllPos", "R5 mid file not given")

    # ---- R5 second and third model fits (R5 Oct 20 08:52): only the m3 and m4 prefixed fields ----
    for arg, px, mac, mlab in (
            (a.r5m3, "m3", "mTwo", "SECOND MODEL (Mistral Small 3.2 24B, 8 bit; raf_m3), OFFLINE CALIBRATED RULE (R5 v2)"),
            (a.r5m4, "m4", "mThree", "THIRD MODEL (gpt-oss 20B; raf_m4, task 105 removed), OFFLINE CALIBRATED RULE (R5 v2)")):
        sav = ["CtrlSavingVs" + x for x in ("Resume", "Restart", "Rollback", "XstarRule", "Gbr", "Uncached", "Billed")]
        suc = ["CtrlOfflineSucc", "FrOfflineSucc", "SrOfflineSucc", "RbOfflineSucc"]
        if not arg or not os.path.exists(arg):
            for n in sav + suc + ["LawA", "LawB", "QuadSupported"]:
                pend(mac + n, "R5 %s file not given" % px)
            continue
        check("r5" + px, arg)
        g5 = json.load(open(arg))
        base = "%s; r5 %s sha256 %s" % (mlab, px, shas[arg])

        def MP(n, v, s, note=""):
            put(mac + n, v, s)
            NOTE[mac + n] = mlab + note

        for n in sav + suc:
            v, pc = g5.get(px + n), n in suc
            if not isinstance(v, dict) or v.get("value") is None or not v.get("ci") or len(v["ci"]) != 2:
                pend(mac + n, "%s%s missing or without value and two value ci" % (px, n))
                continue
            if pc and not all(0 <= x <= 1 for x in [v["value"]] + list(v["ci"])):
                pend(mac + n, "%s%s is not a fraction: %s" % (px, n, json.dumps(v)[:80]))
                continue
            lo, hi = v["ci"]
            flag = "" if pc or lo > 0 or hi < 0 else "; NOT SIGNIFICANT: 95 percent CI includes 0"
            unit = ", percent (Wilson 95)" if pc else ", percent lower energy per successful goal for the controller"
            for suf, x in (("", v["value"]), ("Lo", lo), ("Hi", hi)):
                MP(n + suf, "%.1f" % (x * (100.0 if pc else 1.0)), base + ", key %s%s%s%s" % (px, n, ".ci" if suf else "", unit) + flag, flag)
        for n in ("NBlocks", "NGoals", "NTasks"):
            v = g5.get(px + n)
            if isinstance(v, int) and not isinstance(v, bool):
                MP("Ctrl" + n, pn.fmt0(v), base + ", key " + px + n)
            else:
                pend(mac + "Ctrl" + n, "%s%s missing or not an integer" % (px, n))
        law = g5.get(px + "EnergyLawLinear") or {}
        for nm, key, f, unit in (("LawA", "linear_a", "%.1f", "J"), ("LawB", "linear_b", "%.4f", "J per token")):
            ci = law.get(key + "_ci")
            if law.get(key) is None or not ci or len(ci) != 2:
                pend(mac + nm, "%sEnergyLawLinear.%s missing or without a two value ci" % (px, key))
                continue
            lflag = "" if (ci[0] > 0 or ci[1] < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
            for suf, x in (("", law[key]), ("Lo", ci[0]), ("Hi", ci[1])):
                MP(nm + suf, f % x, base + ", key %sEnergyLawLinear.%s%s, %s" % (px, key, "_ci" if suf else "", unit) + lflag, lflag)
        for nm, key in (("LawNCalls", "n_calls"), ("LawNTasks", "n_tasks")):
            if isinstance(law.get(key), int):
                MP(nm, pn.fmt0(law[key]), base + ", key %sEnergyLawLinear.%s" % (px, key))
        q = g5.get(px + "QuadSupported")
        if isinstance(q, bool):
            MP("QuadSupported", str(q).lower(), base + ", key " + px + "QuadSupported")
        else:
            pend(mac + "QuadSupported", "%sQuadSupported missing or not true or false" % px)

    # ---- R5 GN100 sweep law and raf_samp (R5 Oct 20 09:30): only the named fields ----
    SWLAB = "GN100 CONTEXT SWEEP LAW (R5)"
    SALAB = "SAMPLING SLICE (temperature 0.7, three seeds; R5)"

    def r5f(g5, name, label, base, fmt, frac=False, sigflag=False, words=""):
        """Copy field name of g5: dict {value, ci} or plain integer; fractions become percent; never recomputed."""
        v = g5.get(name)
        if isinstance(v, bool):
            put(name, str(v).lower(), base + ", key " + name)
            NOTE[name] = label
            return
        if isinstance(v, int):
            put(name, pn.fmt0(v), base + ", key " + name)
            NOTE[name] = label
            return
        if not isinstance(v, dict) or v.get("value") is None or not v.get("ci") or len(v["ci"]) != 2:
            pend(name, "%s missing or without value and two value ci" % name)
            return
        xs = [v["value"]] + list(v["ci"])
        if frac:
            if all(0 <= x <= 1 for x in xs):
                xs = [100.0 * x for x in xs]
            elif not all(0 <= x <= 100 for x in xs):
                pend(name, "%s is neither a fraction nor a percent: %s" % (name, json.dumps(v)[:80]))
                return
        lo, hi = v["ci"]
        flag = "; NOT SIGNIFICANT: 95 percent CI includes 0" if sigflag and lo <= 0 <= hi else ""
        for suf, x in zip(("", "Lo", "Hi"), xs):
            put(name + suf, fmt % x, base + ", key %s%s%s" % (name, ".ci" if suf else "", words) + flag)
            NOTE[name + suf] = label + words + flag

    if a.r5sweep and os.path.exists(a.r5sweep):
        check("r5sweep", a.r5sweep)
        gs = json.load(open(a.r5sweep))
        bs = "%s; r5 sweep sha256 %s" % (SWLAB, shas[a.r5sweep])
        for m in ("Gptoss", "Qwen"):
            for c in ("Uncached", "Cached"):
                p = "sweep%s%s" % (m, c)
                r5f(gs, p + "LinA", SWLAB, bs, "%.1f", sigflag=True, words=", linear intercept, J")
                r5f(gs, p + "LinB", SWLAB, bs, "%.4f", sigflag=True, words=", linear slope, J per token")
                for q in ("QuadA", "QuadB", "QuadD"):
                    r5f(gs, p + q, SWLAB, bs, "%.3g", sigflag=True, words=", quadratic fit term")
                for q in ("SlopeLow", "SlopeHigh"):
                    r5f(gs, p + q, SWLAB, bs, "%.4f", sigflag=True, words=", local slope, J per token")
                for k in ("QuadSupported", "NCalls", "CtxMax", "CtxPNinetyFive"):
                    r5f(gs, p + k, SWLAB, bs, "%s")
            for size, word in ((2048, "TwoK"), (4096, "FourK"), (8192, "EightK"), (16384, "SixteenK"),
                               (24576, "TwentyFourK"), (32672, "Long")):  # Long = largest size, 32,672 tokens (R8)
                key = "sweep%sCachedRatio%d" % (m, size)
                if key in gs:
                    gs["sweep%sCachedRatio%s" % (m, word)] = gs[key]  # LaTeX macro names cannot hold digits
                r5f(gs, "sweep%sCachedRatio%s" % (m, word), SWLAB, bs, "%.2f",
                    words=", cached over uncached energy per call at %d tokens (key %s)" % (size, key))
    else:
        pend("sweepGptossUncachedLinB", "R5 sweep file not given")
    if a.r5samp and os.path.exists(a.r5samp):
        check("r5samp", a.r5samp)
        gp = json.load(open(a.r5samp))
        bp = "%s; r5 samp sha256 %s" % (SALAB, shas[a.r5samp])
        for k in ("RateLimit", "ToolError"):  # the slice has no json_parse or timeout cells (R5)
            for pt in ("Early", "Late"):
                p = "samp%s%s" % (k, pt)
                r5f(gp, p + "ResumeVsRestart", SALAB, bp, "%.1f", sigflag=True,
                    words=", percent, positive = resume (SR_warm) lower energy per successful goal than restart (FR_warm)")
                r5f(gp, p + "SrSucc", SALAB, bp, "%.1f", frac=True, words=", SR_warm success percent, Wilson 95")
                r5f(gp, p + "FrSucc", SALAB, bp, "%.1f", frac=True, words=", FR_warm success percent, Wilson 95")
        for pt in ("Early", "Late"):
            r5f(gp, "samp%sResumeVsRestart" % pt, SALAB, bp, "%.1f", sigflag=True,
                words=", pooled classes, percent, positive = resume (SR_warm) lower energy per successful goal than restart (FR_warm)")
        r5f(gp, "sampSplitHolds", SALAB, bp, "%s")
        r5f(gp, "sampSameOutcome", SALAB, bp, "%.1f", frac=True, words=", outcome agreement across the three seeds, percent")
        for k in ("sampWinnerMatchesGreedy", "sampCells", "sampNTasks"):
            r5f(gp, k, SALAB, bp, "%s")
        # ---- tab:samp (R8 columns, Oct 21): k of n from the raf_samp ledgers, percent from R5, greedy winner from E1 ----
        if a.db and a.art:
            import glob
            stx = pn.Store(a.db)
            sg = {}
            for sd in ("raf_samp_s1", "raf_samp_s2", "raf_samp_s3"):
                sp = os.path.join(a.art, sd, "%s_run_ledger.jsonl" % sd)
                if os.path.exists(sp):
                    shas[sp] = pn.sha256(sp)
                    sg.update(pn.load_ledger([sp]))  # one seed per call: latest valid per (item, policy) within the seed
            stasks = {pn.norm_task(v[0]) for v in sg.values()}
            e1p = sorted(glob.glob(os.path.join(a.art, "raf_e1", "raf_e1_run_ledger.jsonl")) +
                         glob.glob(os.path.join(a.art, "raf_e1", "*rerun*ledger*.jsonl")))
            e1c = pn.cells(stx, {g: v for g, v in pn.load_ledger(e1p).items() if pn.norm_task(v[0]) in stasks}) if e1p else {}
            sc = pn.cells(stx, sg) if sg else {}
            rows, match, ncell = [], 0, 0
            for pt in ("early", "late"):
                kf = nf = kr = nr = 0
                for cls, cam in (("rate_limit", "RateLimit"), ("tool_error", "ToolError")):
                    f, r = sc.get((cls, pt, "FR_warm")), sc.get((cls, pt, "SR_warm"))
                    if not f or not r:
                        continue
                    kf += f["ok"]; nf += f["n"]; kr += r["ok"]; nr += r["n"]
                    val = gp.get("samp%s%sResumeVsRestart" % (cam, pt.capitalize()))
                    pct = "$%.1f$ ($%.1f$ to $%.1f$)" % (val["value"], val["ci"][0], val["ci"][1]) if isinstance(val, dict) else "\\pending{samp}"
                    cheaper = "resume" if isinstance(val, dict) and val["value"] > 0 else "restart"
                    gf, gr = e1c.get((cls, pt, "FR_warm")), e1c.get((cls, pt, "SR_warm"))
                    greedy = "resume" if (gf and gr and gr["ach_board"] and (not gf["ach_board"] or gr["ach_board"] < gf["ach_board"])) else "restart"
                    ncell += 1
                    match += greedy == cheaper
                    rows.append("%s & %s & %d/%d & %d/%d & %s & %s & %s \\\\" % (pn.CLS_NAME[cls], pt, f["ok"], f["n"], r["ok"], r["n"],
                                                                         pct, cheaper, "yes" if greedy == cheaper else "no"))
                val = gp.get("samp%sResumeVsRestart" % pt.capitalize())
                if nf and isinstance(val, dict):
                    rows.append("Pooled & %s & %d/%d & %d/%d & $%.1f$ ($%.1f$ to $%.1f$) & %s & \\\\" % (
                        pt, kf, nf, kr, nr, val["value"], val["ci"][0], val["ci"][1], "resume" if val["value"] > 0 else "restart"))
                if pt == "early":
                    rows.append("\\midrule")
            if rows:
                os.makedirs(os.path.join(a.paper, "tables"), exist_ok=True)
                open(os.path.join(a.paper, "tables", "samp_table.tex"), "w").write(
                    "% GENERATED by paper_extra.py; do not edit by hand. " + SALAB + "; k/n from the raf_samp ledgers (three seeds), "
                    "percent and CI from R5 (positive = resume lower energy per successful goal), greedy winner from E1 on the same tasks.\n"
                    + "\n".join(rows) + "\n\\bottomrule\n")
                want = gp.get("sampWinnerMatchesGreedy")
                print("tab:samp: %d cells, %d match greedy%s" % (ncell, match, "" if want in (None, match) else
                                                                  "  MISMATCH: R5 sampWinnerMatchesGreedy %s" % want))
    else:
        pend("sampCells", "R5 samp file not given")

    # ---- R6 diagnosis ----
    if a.r6 and os.path.isdir(a.r6):
        def load(fn):
            p = os.path.join(a.r6, fn)
            if not os.path.exists(p):
                return None
            check(fn, p)
            return json.load(open(p))

        def by_name(fn, name, obj, kind):
            """Ingest field `name` of obj by name. kind: share (k, n -> percent with Wilson), ci (value plus ci),
            text (copied as is). Unknown layouts go to \\pending with the layout in the reason."""
            v = obj.get(name)
            src = "%s; %s sha256 %s, field %s" % (R6_LABEL, fn, shas[os.path.join(a.r6, fn)], name)
            if v is None:
                pend(name, "no field %s in %s" % (name, fn))
                return
            if kind == "share":
                k = v.get("k") if isinstance(v, dict) else None
                n = v.get("n") if isinstance(v, dict) else None
                if k is None or not n:
                    pend(name, "%s in %s has no k and n: %s" % (name, fn, json.dumps(v)[:80]))
                    return
                lo, hi = pn.wilson(k, n)
                put(name, "%.1f" % (100.0 * k / n), src)
                put(name + "N", "%d of %d" % (k, n), src)
                put(name + "Lo", "%.0f" % (100 * lo), "Wilson 95, " + src)
                put(name + "Hi", "%.0f" % (100 * hi), "Wilson 95, " + src)
                for x in ("", "N", "Lo", "Hi"):
                    NOTE[name + x] = R6_LABEL
            elif kind == "ci":
                val = v.get("value") if isinstance(v, dict) else v
                ci = (v.get("ci") if isinstance(v, dict) else None) or obj.get(name + "CI")
                if val is None or not ci or len(ci) != 2:
                    pend(name, "%s in %s has no value and two value ci: %s" % (name, fn, json.dumps(v)[:80]))
                    return
                flag = "" if (ci[0] > 0 or ci[1] < 0) else "; NOT SIGNIFICANT: 95 percent CI includes 0"
                for suf, x in (("", val), ("Lo", ci[0]), ("Hi", ci[1])):
                    put(name + suf, "%.0f" % x, src + flag)
                    NOTE[name + suf] = R6_LABEL + flag
            else:
                if isinstance(v, dict):
                    v = v.get("display", v.get("value"))
                put(name, str(v), src)
                NOTE[name] = R6_LABEL

        t1 = load("t1_ctrl_split_match.json")
        if t1 is not None:
            for nm in ("ctrlSplitMatch", "ctrlSeedMatch", "ctrlEvidenceInvTwo", "ctrlEvidenceInvThree"):
                by_name("t1_ctrl_split_match.json", nm, t1, "text")
        t4 = load("t4_explore_cost.json")
        if t4 is not None:
            by_name("t4_explore_cost.json", "ctrlRareOptionShare", t4, "share")
            by_name("t4_explore_cost.json", "ctrlRareCostVsToken", t4, "ci")
        t5 = load("t5_learn_curve.json")
        if t5 is not None:
            by_name("t5_learn_curve.json", "ctrlExploreShare", t5, "share")
        t2 = load("t2_option_counts.json")
        if t2 is not None:
            e = ((t2.get("by_arm_point") or {}).get("ctrl_beta") or {}).get("early") or {}
            n = sum(e.values())
            k = sum(v for o, v in e.items() if o.startswith("FR"))
            if n:
                put("ctrlEarlyRestart", "%d of %d" % (k, n), "%s; t2 sha256 %s, by_arm_point.ctrl_beta.early, FR options"
                    % (R6_LABEL, shas[os.path.join(a.r6, "t2_option_counts.json")]))
                NOTE["ctrlEarlyRestart"] = R6_LABEL
        for fn in ("t3_ctrl_by_option.json", "t6_overhead.json", "t3c_class_split.json"):
            load(fn)  # hashed into provenance; no macros (t6 is a cross check of ctrlDecideMs)
        t7c = load("t7c_context_changed.json")  
        if t7c is not None:
            v = t7c.get("ctrlContextChangedDecisions") or {}
            src = "%s; t7c_context_changed.json sha256 %s, field ctrlContextChangedDecisions (k, n); %s; source %s sha256 %s" % (
                R6_LABEL, shas[os.path.join(a.r6, "t7c_context_changed.json")], v.get("meaning", ""),
                v.get("source"), v.get("source_sha256"))
            tsv = os.path.join(a.r6, "r7_changed_44.tsv")
            nrow = None
            if os.path.exists(tsv):
                check("r7_changed_44.tsv", tsv)
                nrow = sum(1 for l in open(tsv) if l.strip()) - 1  # minus the header
            if not isinstance(v.get("k"), int) or not v.get("n") or (nrow is not None and nrow != v["k"]):
                pend("ctrlContextChangedDecisions", "t7c k or n missing, or tsv rows %s differ from k" % nrow)
            else:
                put("ctrlContextChangedDecisions", str(v["k"]), src + ", count")
                put("ctrlContextChangedDecisionsN", "%d of %d" % (v["k"], v["n"]), src)
                put("ctrlContextChangedDecisionsPct", "%.1f" % (100.0 * v["k"] / v["n"]), src + ", percent")
                for x in ("", "N", "Pct"):
                    NOTE["ctrlContextChangedDecisions" + x] = "E3 replay diagnostic (R6, R7), all at decision attempt 2"
        t7c = load("t7c_context_changed.json")  # coordinator Oct 22, on behalf of R6; fields read as given
        if t7c is not None:
            v = t7c.get("ctrlContextChangedDecisions") or {}
            src = "%s; t7c_context_changed.json sha256 %s, field ctrlContextChangedDecisions (k, n); %s; source %s sha256 %s" % (
                R6_LABEL, shas[os.path.join(a.r6, "t7c_context_changed.json")], v.get("meaning", ""),
                v.get("source"), v.get("source_sha256"))
            tsv = os.path.join(a.r6, "r7_changed_44.tsv")
            nrow = None
            if os.path.exists(tsv):
                check("r7_changed_44.tsv", tsv)
                nrow = sum(1 for l in open(tsv) if l.strip()) - 1  # minus the header
            if not isinstance(v.get("k"), int) or not v.get("n") or (nrow is not None and nrow != v["k"]):
                pend("ctrlContextChangedDecisions", "t7c k or n missing, or tsv rows %s differ from k" % nrow)
            else:
                put("ctrlContextChangedDecisions", str(v["k"]), src + ", count")
                put("ctrlContextChangedDecisionsN", "%d of %d" % (v["k"], v["n"]), src)
                put("ctrlContextChangedDecisionsPct", "%.1f" % (100.0 * v["k"] / v["n"]), src + ", percent")
                for x in ("", "N", "Pct"):
                    NOTE["ctrlContextChangedDecisions" + x] = "E3 replay diagnostic (R6, R7), all at decision attempt 2"
        if load("t7d_whatif_coverage.json") is not None:  # coordinator Oct 19: hash only (Rule C)
            NOMACRO["t7d_whatif_coverage.json"] = "t7d what if coverage 29 of 44, appendix_eligible false, no macro (Rule C)"
    for n in ("ctrlEvidenceInvTwo", "ctrlEvidenceInvThree"):
        if n not in M:
            pend(n, "no R6 t1 file given")

    # ---- duplicate check against paper_numbers.py output (coordinator, Oct 19) ----
    auto = None
    if a.auto:
        auto = json.load(open(a.auto))
        dup = sorted(set(M) & set(auto.get("values", {})))
        if dup:
            raise SystemExit("macros defined by both paper_numbers.py and paper_extra.py (nothing written): "
                             + ", ".join(dup))

    # ---- write ----
    os.makedirs(a.paper, exist_ok=True)
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    head = "%% GENERATED by paper_extra.py at %s; do not edit by hand. \\input after numbers_auto.\n" % stamp
    body = "".join("\\providecommand{\\%s}{}\\renewcommand{\\%s}{%s}%s\n"
                   % (k, k, re.sub(r"(?<!\\)([%&#])", r"\\\1", str(v)), (" % " + NOTE[k]) if NOTE.get(k) else "")
                   for k, v in sorted(M.items()))
    open(os.path.join(a.paper, "numbers_extra.tex"), "w").write(head + body)
    json.dump({"generated": stamp, "inputs_sha256": shas, "values": M, "provenance": prov,
               "no_macro": NOMACRO},
              open(os.path.join(a.paper, "numbers_extra.json"), "w"), indent=1)
    if auto is not None:  # one provenance file for the paper: merge into numbers_auto.json
        auto.setdefault("values", {}).update(M)
        auto.setdefault("provenance", {}).update({k: "paper_extra.py: " + v for k, v in prov.items()})
        auto["paper_extra"] = {"generated": stamp, "inputs_sha256": shas, "macros": sorted(M),
                               "no_macro": NOMACRO}
        json.dump(auto, open(a.auto, "w"), indent=1)
        print("merged %d macros into %s" % (len(M), a.auto))
    print("wrote %d macros to %s" % (len(M), os.path.join(a.paper, "numbers_extra.tex")))
    for k in sorted(M):
        print("  %-30s %s" % (k, M[k]))


if __name__ == "__main__":
    main()
