"""Shared loaders for the RAF follow-up analyses. Uses Deepak's paper_numbers.py definitions unchanged.
Opens the frozen DB read-only (immutable=1: the file is read-only and its WAL is empty)."""
import sys, os, glob, json, collections, sqlite3, random
from pathlib import Path
sys.dont_write_bytecode = True
RAF = os.environ.get("RAF_DATA_ROOT", "inputs")
sys.path.insert(0, os.environ.get("RAF_DEFINITION_DIR", str(Path(__file__).resolve().parents[3] / "scripts")))
import paper_numbers as pn  # noqa: E402

DB = RAF + "/data/frozen_oct23/experiments_frozen_oct23.db"
ART = RAF + "/data/frozen_oct23/ledgers"
CLS = list(pn.CLS_NAME)
TOOL = ("tool_error", "timeout")
MODEL = ("json_parse", "rate_limit")


class Store(pn.Store):
    def __init__(self, db=DB):
        self.c = sqlite3.connect("file:%s?immutable=1" % db, uri=True)
        self.idle = {}


def e1_goals():
    led = sorted(glob.glob(os.path.join(ART, "raf_e1", "raf_e1_run_ledger.jsonl")) +
                 glob.glob(os.path.join(ART, "raf_e1", "*rerun*ledger*.jsonl")))
    return pn.load_ledger(led)


def e1b_goals():
    return pn.load_ledger(glob.glob(os.path.join(ART, "raf_e1b", "raf_e1b_run_ledger.jsonl")))


def ledger_records(study):
    out = []
    for p in sorted(glob.glob(os.path.join(ART, study, "*ledger*.jsonl"))):
        if "smoke" in p:
            continue
        for l in open(p):
            out.append((os.path.basename(p), json.loads(l)))
    return out
