"""Deterministic rule engine: classify failures from parsed evidence.

Rules run before (and independently of) any AI. Each rule inspects the
normalized :class:`~veritriage.parsers.base.ParseResult` and either abstains or
returns a :class:`~veritriage.models.ClassificationResult` with confidence,
evidence, and suggested next steps. New rules plug in without modifying the
engine.
"""

from veritriage.rules.base import Rule
from veritriage.rules.builtin import default_rules
from veritriage.rules.engine import RuleEngine

__all__ = ["Rule", "RuleEngine", "default_rules"]
