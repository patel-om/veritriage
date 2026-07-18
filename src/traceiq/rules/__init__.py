"""Deterministic rule engine: classify failures from parsed evidence.

Rules run before (and independently of) any AI. Each rule inspects the
normalized :class:`~traceiq.parsers.base.ParseResult` and either abstains or
returns a :class:`~traceiq.models.ClassificationResult` with confidence,
evidence, and suggested next steps. New rules plug in without modifying the
engine.
"""

from traceiq.rules.base import Rule
from traceiq.rules.builtin import default_rules
from traceiq.rules.engine import RuleEngine

__all__ = ["Rule", "RuleEngine", "default_rules"]
