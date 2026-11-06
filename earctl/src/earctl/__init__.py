"""earctl: energy aware recovery for agentic LLM workflows (RAF controller)."""

from .classify import CLASSES, classify
from .controller import ABANDON, MODES, OPTIONS, Controller, record_outcome

__version__ = "0.1.0"
__all__ = ["Controller", "record_outcome", "classify", "CLASSES", "OPTIONS", "ABANDON", "MODES"]
