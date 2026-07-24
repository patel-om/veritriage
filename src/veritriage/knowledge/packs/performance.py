"""Performance verification Knowledge Pack.

Latency and bandwidth SLA checking. This is the first pack to use numeric
clauses: a pattern here does not just look for the word "latency", it parses
the measured number out of the evidence and compares it to a budget, so a
report at 3200 ns fires the SLA-miss and one at 200 ns does not. The budgets
below are representative canonical thresholds; a deployment tunes them per
project.
"""

from __future__ import annotations

from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    NumericConstraint,
    PlaybookStep,
    Reference,
)
from veritriage.knowledge.registry import register_pack

_SPEC = "Performance verification methodology (SLA / QoS budgets)"


@register_pack
def performance_pack() -> KnowledgePack:
    return KnowledgePack(
        id="performance",
        name="Performance verification",
        version="1.0.0",
        domain="performance",
        summary="Latency and bandwidth SLA checks using numeric evidence thresholds.",
        concepts=[
            Concept(
                id="performance.latency",
                name="Latency budgets",
                summary=(
                    "A latency SLA bounds how long an operation may take (a read "
                    "return, an interrupt-to-service delay). Verification measures "
                    "the actual latency and compares it to the budget; a measured "
                    "value over budget is a real miss, not a functional failure, so "
                    "it needs a numeric comparison rather than a keyword match."
                ),
                markers=[r"latency", r"\bsla\b|budget|deadline", r"\bns\b|\bus\b|cycles"],
                references=[Reference(source=_SPEC, section="Latency", note="Latency budget verification.")],
            ),
            Concept(
                id="performance.bandwidth",
                name="Bandwidth / throughput floors",
                summary=(
                    "A bandwidth SLA sets a minimum sustained throughput. Measuring "
                    "the achieved rate and comparing it to the floor catches "
                    "microarchitectural bottlenecks (arbitration starvation, buffer "
                    "sizing) that leave functionality correct but performance short."
                ),
                markers=[r"bandwidth|throughput", r"gb/s|mb/s|gbps", r"sustained|achieved rate"],
                references=[Reference(source=_SPEC, section="Bandwidth", note="Throughput floor verification.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="performance.latency-sla-miss",
                name="Latency SLA miss",
                summary=(
                    "A measured latency exceeded its budget. The pattern parses the "
                    "reported latency and fires only when the number is over the "
                    "threshold, so a within-budget measurement does not match."
                ),
                required=[
                    EvidenceClause(
                        name="latency over budget",
                        pattern=r"latency[^0-9]{0,30}(\d+)\s*(?:ns|cycles)",
                        numeric=NumericConstraint(op="gt", value=1000.0),
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="sla context", pattern=r"\bsla\b|budget|deadline|exceeds"),
                ],
                typical_causes=[
                    "Arbitration or scheduling adds cycles under contention",
                    "A pipeline stall path not covered by the timing budget",
                    "Outstanding-transaction limit too low, serializing requests",
                ],
                ownership="design",
                suggested_signals=["measured latency", "request-to-response path", "arbiter"],
                playbook_id="performance.latency-debug",
                confidence_modifiers={"rtl_bug": 0.10},
                references=[Reference(source=_SPEC, section="Latency", note="Measured vs budget comparison.")],
            ),
            FailurePattern(
                id="performance.bandwidth-sla-miss",
                name="Bandwidth SLA miss",
                summary=(
                    "A sustained bandwidth measurement fell below its floor. The "
                    "pattern parses the achieved rate and fires only when the number "
                    "is under the threshold."
                ),
                required=[
                    EvidenceClause(
                        name="bandwidth under floor",
                        pattern=r"bandwidth[^0-9]{0,30}(\d+)\s*(?:gb/s|mb/s|gbps)",
                        numeric=NumericConstraint(op="lt", value=8.0),
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="throughput context", pattern=r"throughput|sustained|floor|below"),
                ],
                typical_causes=[
                    "Insufficient outstanding transactions to cover the round-trip",
                    "Buffer/FIFO too small, stalling the pipeline between bursts",
                    "Arbitration weighting starves the measured traffic class",
                ],
                ownership="design",
                suggested_signals=["achieved bandwidth", "outstanding count", "buffer occupancy"],
                playbook_id="performance.bandwidth-debug",
                confidence_modifiers={"rtl_bug": 0.10},
                references=[Reference(source=_SPEC, section="Bandwidth", note="Achieved vs floor comparison.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="performance.latency-debug",
                name="Latency SLA debug",
                steps=[
                    PlaybookStep(action="Confirm the measured latency and the budget it is compared against", signals=["measured latency"]),
                    PlaybookStep(action="Decompose the latency into pipeline stages to find the dominant contributor"),
                    PlaybookStep(action="Check arbitration/scheduling delay under the contended scenario", signals=["arbiter"]),
                    PlaybookStep(action="Raise the outstanding-transaction limit if requests serialize"),
                ],
            ),
            DebugPlaybook(
                id="performance.bandwidth-debug",
                name="Bandwidth SLA debug",
                steps=[
                    PlaybookStep(action="Confirm the achieved bandwidth and the floor", signals=["achieved bandwidth"]),
                    PlaybookStep(action="Check the outstanding-transaction count covers the round-trip latency", signals=["outstanding count"]),
                    PlaybookStep(action="Inspect buffer occupancy for stalls between bursts", signals=["buffer occupancy"]),
                    PlaybookStep(action="Review arbitration weighting for the measured traffic class"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for performance verification.")],
    )
