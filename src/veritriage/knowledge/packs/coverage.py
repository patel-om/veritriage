"""Functional coverage Knowledge Pack.

Coverage evidence changes the meaning of both failures and passes: a hole
near a failure marks under-tested logic; a hole in a passing regression
means the pass proves less than it appears to.
"""

from __future__ import annotations

from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    PlaybookStep,
    Reference,
)
from veritriage.knowledge.registry import register_pack

_SPEC = "IEEE 1800-2023 (SystemVerilog), Chapter 19 (Functional Coverage)"


@register_pack
def coverage_pack() -> KnowledgePack:
    return KnowledgePack(
        id="coverage",
        name="Functional coverage",
        version="1.0.0",
        domain="coverage",
        summary="What coverage holes mean next to failures and next to passes.",
        concepts=[
            Concept(
                id="coverage.hole",
                name="Coverage hole",
                summary=(
                    "A covergroup or scope below target means scenarios the plan calls "
                    "for were never exercised. Holes are not failures, but they bound "
                    "how much any green run actually demonstrates."
                ),
                markers=[r"coverage", r"covergroup", r"\bhole\b", r"\d+(?:\.\d+)?%"],
                references=[Reference(source=_SPEC, section="19.5", note="Coverage group and coverpoint semantics.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="coverage.hole-near-failure",
                name="Coverage hole overlapping a failure",
                summary=(
                    "The failing scope is also under-covered: the logic around the "
                    "failure has not been exercised enough for its behavior to be "
                    "trusted, and the stimulus may be missing the very scenarios that "
                    "would have caught this earlier."
                ),
                required=[
                    EvidenceClause(
                        name="coverage hole present",
                        pattern=r".",
                        artifact_types=["coverage"],
                    ),
                    EvidenceClause(
                        name="failure present",
                        pattern=r".",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Stimulus constraints exclude the corner the bug lives in",
                    "New RTL landed without matching coverage-driven tests",
                ],
                ownership="testbench",
                suggested_signals=["covergroup bins for the failing scope"],
                playbook_id="coverage.hole-review",
                confidence_modifiers={"rtl_bug": 0.04, "testbench_issue": 0.03},
                references=[Reference(source=_SPEC, section="19.5", note="Coverage as a measure of verification completeness, not correctness.")],
            ),
            FailurePattern(
                id="coverage.hole-in-passing-run",
                name="Coverage hole in an otherwise passing regression",
                summary=(
                    "The run reported no failure, but coverage holes remain in "
                    "scope: the pass demonstrates less than it appears to, since "
                    "the untested scenarios were never actually exercised."
                ),
                required=[
                    EvidenceClause(
                        name="coverage hole present",
                        pattern=r".",
                        artifact_types=["coverage"],
                    ),
                ],
                forbidden=[
                    EvidenceClause(
                        name="no failing evidence in the run",
                        pattern=r".",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Verification plan bins not yet reachable by any existing test",
                    "A recently added feature has no directed or constrained-random coverage yet",
                    "Coverage collection disabled or misconfigured for part of the design",
                ],
                ownership="testbench",
                suggested_signals=["covergroup bins still unhit"],
                playbook_id="coverage.plan-gap-review",
                confidence_modifiers={},
                references=[Reference(source=_SPEC, section="19.1", note="Functional coverage measures plan completion, independent of pass/fail.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="coverage.hole-review",
                name="Coverage hole review",
                steps=[
                    PlaybookStep(action="List the unhit bins in the failing scope"),
                    PlaybookStep(action="Map each unhit bin to the stimulus constraint that should reach it"),
                    PlaybookStep(action="Add or relax constraints to target the hole, then re-run", detail="A directed test at the hole often reproduces the failure faster."),
                ],
            ),
            DebugPlaybook(
                id="coverage.plan-gap-review",
                name="Coverage plan gap review",
                steps=[
                    PlaybookStep(action="List every unhit bin still open in the verification plan"),
                    PlaybookStep(action="Triage each bin: reachable-but-untested vs currently unreachable"),
                    PlaybookStep(action="File or prioritize directed tests for the reachable, high-risk bins"),
                    PlaybookStep(action="Flag unreachable bins for a plan review", detail="An unreachable bin may mean the plan or the design changed."),
                ],
            ),
        ],
    )
