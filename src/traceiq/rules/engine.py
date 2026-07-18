"""Rule engine: run all rules, rank verdicts, guarantee a classification."""

from __future__ import annotations

from typing import Iterable

from traceiq.models import (
    ClassificationResult,
    Evidence,
    FailureCategory,
    Recommendation,
)
from traceiq.parsers.base import ParseResult
from traceiq.rules.base import Rule
from traceiq.rules.builtin import default_rules


class RuleEngine:
    """Evaluates a set of rules and always produces a primary classification.

    The engine itself contains no failure knowledge — that lives in the rules.
    Extend by passing extra rules to the constructor or calling
    :meth:`register`; no engine changes needed.
    """

    def __init__(self, rules: Iterable[Rule] | None = None) -> None:
        self._rules: list[Rule] = list(rules) if rules is not None else default_rules()

    @property
    def rules(self) -> tuple[Rule, ...]:
        return tuple(self._rules)

    def register(self, rule: Rule) -> None:
        """Add a rule to this engine instance."""
        self._rules.append(rule)

    def classify(
        self, parse_result: ParseResult
    ) -> tuple[ClassificationResult, list[ClassificationResult]]:
        """Run every rule and return ``(primary, alternatives)``.

        The primary verdict is the highest-confidence rule result. When no
        rule fires, a deterministic fallback is produced: ``NO_FAILURE`` for
        clean logs, ``UNKNOWN_FAILURE`` when errors exist but nothing matched.
        """
        results = [r for rule in self._rules if (r := rule.evaluate(parse_result)) is not None]
        # Stable sort: ties keep rule-registration order, so output is deterministic.
        results.sort(key=lambda r: -r.confidence)
        if results:
            return results[0], results[1:]
        return self._fallback(parse_result), []

    @staticmethod
    def _fallback(parse_result: ParseResult) -> ClassificationResult:
        failing = parse_result.failing_events
        if not failing:
            return ClassificationResult(
                category=FailureCategory.NO_FAILURE,
                confidence=95,
                rule_name="fallback",
                summary="No errors, fatals, or failed assertions detected",
                evidence=[],
                recommendations=[
                    Recommendation(
                        action="No debug action needed.",
                        rationale="The log contains no failing messages.",
                        priority=1,
                    )
                ],
            )
        return ClassificationResult(
            category=FailureCategory.UNKNOWN_FAILURE,
            confidence=30,
            rule_name="fallback",
            summary="Errors present but no known failure signature matched",
            evidence=[Evidence.from_event(e) for e in failing[:5]],
            recommendations=[
                Recommendation(
                    action="Read the first error in the log and work forward from there.",
                    rationale="Unrecognized signatures need manual triage; the first error is the usual root.",
                    priority=1,
                ),
                Recommendation(
                    action="Consider adding a TraceIQ rule for this signature.",
                    rationale="Once diagnosed, encoding the signature classifies it automatically next time.",
                    priority=2,
                ),
            ],
        )
