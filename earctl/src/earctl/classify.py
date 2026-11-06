"""
Map a raw failure to an observable failure class.

The classes are the ones the controller was calibrated on: timeout,
rate_limit, tool_error, json_parse and silent_detected. A silent wrong output
leaves no error text, so silent_detected is never inferred here; a detector
passes it explicitly. Anything unrecognised becomes "unknown", which the
parameters answer with their pooled _default class.
"""

import re
from typing import Optional

CLASSES = ("timeout", "rate_limit", "tool_error", "json_parse", "silent_detected")
UNKNOWN = "unknown"

_RULES = (
    ("rate_limit", re.compile(r"\b429\b|rate.?limit|too many requests|quota", re.I)),
    ("timeout", re.compile(r"time.?out|timed out|deadline exceeded|\b504\b|\b408\b", re.I)),
    ("json_parse", re.compile(r"json|decod|pars(e|ing)|malformed|expecting (value|property)", re.I)),
    ("tool_error", re.compile(r"tool|function call|exception|traceback|\b5\d\d\b|error", re.I)),
)


def observable(cls: str) -> str:
    """Strip plan only prefixes so a calibration label becomes observable."""
    c = cls.strip()
    for prefix in ("injected ", "persistent_"):
        if c.startswith(prefix):
            c = c[len(prefix):]
    if c in ("silent_tool_output", "wrong_model_step"):
        c = "silent_detected"
    return c


def classify(error: Optional[str]) -> str:
    """Observable class of an error message; 'unknown' when nothing matches."""
    if not error:
        return UNKNOWN
    text = str(error).strip()
    exact = observable(text)
    if exact in CLASSES:
        return exact
    for name, rx in _RULES:
        if rx.search(text):
            return name
    return UNKNOWN
