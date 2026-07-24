"""UVM TLM connectivity Knowledge Pack.

Transaction-level modeling ports, exports, and analysis ports/FIFOs, and the
connections between them. The failures are a port left unconnected at
elaboration and analysis transactions dropped before a subscriber sees them.
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

_SPEC = "UVM (IEEE 1800.2) TLM"


@register_pack
def uvm_tlm_pack() -> KnowledgePack:
    return KnowledgePack(
        id="uvm-tlm",
        name="UVM TLM",
        version="1.0.0",
        domain="methodology",
        summary="TLM port/export connectivity and analysis-transaction delivery.",
        concepts=[
            Concept(
                id="uvm-tlm.connectivity",
                name="Port/export connectivity",
                summary=(
                    "TLM ports must be bound to a matching export or imp before the "
                    "end of elaboration; an unbound port has no target and any call "
                    "through it is a null-object error. Connectivity is checked once, "
                    "at end_of_elaboration."
                ),
                markers=[r"tlm", r"port|export|\bimp\b", r"connect|bind"],
                references=[Reference(source=_SPEC, section="TLM", note="Port binding and elaboration check.")],
            ),
            Concept(
                id="uvm-tlm.analysis",
                name="Analysis ports and FIFOs",
                summary=(
                    "An analysis port broadcasts a transaction to every connected "
                    "subscriber via write(); analysis FIFOs buffer them. A subscriber "
                    "connected late, or a bounded FIFO that overflows, drops "
                    "transactions the scoreboard needed."
                ),
                markers=[r"analysis (?:port|fifo)", r"\bwrite\(\)|subscriber", r"broadcast|monitor"],
                references=[Reference(source=_SPEC, section="TLM", note="Analysis port broadcast semantics.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="uvm-tlm.port-not-connected",
                name="TLM port not connected",
                summary=(
                    "A TLM port was left unbound at the end of elaboration, so any "
                    "transaction issued through it hits a null target."
                ),
                required=[
                    EvidenceClause(
                        name="port unconnected",
                        pattern=r"tlm.*port.*(?:not connected|unconnected)|(?:analysis )?port.*no (?:connection|export|imp)|port.*(?:bind|connect).*(?:fail|missing)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="tlm context", pattern=r"\btlm\b|analysis port|export"),
                ],
                typical_causes=[
                    "connect_phase omits the port.connect(export) call",
                    "Hierarchy path to the export is wrong after a refactor",
                    "Conditional build leaves the producer or consumer out",
                ],
                ownership="testbench",
                suggested_signals=["port handle", "export handle", "connect_phase"],
                playbook_id="uvm-tlm.connect-debug",
                confidence_modifiers={"testbench_issue": 0.12},
                references=[Reference(source=_SPEC, section="TLM", note="Ports must be connected by elaboration.")],
            ),
            FailurePattern(
                id="uvm-tlm.transaction-dropped",
                name="Analysis transaction dropped",
                summary=(
                    "A transaction broadcast on an analysis port never reached a "
                    "subscriber, or an analysis FIFO overflowed, so the scoreboard "
                    "missed an item it needed to check."
                ),
                required=[
                    EvidenceClause(
                        name="transaction lost",
                        pattern=r"tlm.*(?:transaction|item).*(?:dropped|lost)|analysis.*(?:write|transaction).*(?:not received|lost)|(?:analysis )?fifo.*overflow",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Subscriber connected after the first transactions were broadcast",
                    "Bounded analysis FIFO too small for the burst and not drained",
                    "Monitor writes to the wrong analysis port instance",
                ],
                ownership="testbench",
                suggested_signals=["analysis port", "fifo occupancy", "subscriber count"],
                playbook_id="uvm-tlm.analysis-debug",
                confidence_modifiers={"testbench_issue": 0.11},
                references=[Reference(source=_SPEC, section="TLM", note="Analysis write reaches all subscribers.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="uvm-tlm.connect-debug",
                name="TLM connectivity debug",
                steps=[
                    PlaybookStep(action="Print the port/export handles and their connections at end_of_elaboration", signals=["port handle", "export handle"]),
                    PlaybookStep(action="Confirm connect_phase issues the port.connect(export) call", signals=["connect_phase"]),
                    PlaybookStep(action="Verify the hierarchical path to the export"),
                    PlaybookStep(action="Check no conditional build omitted the producer or consumer"),
                ],
            ),
            DebugPlaybook(
                id="uvm-tlm.analysis-debug",
                name="Analysis delivery debug",
                steps=[
                    PlaybookStep(action="Count transactions written vs received by each subscriber", signals=["subscriber count"]),
                    PlaybookStep(action="Confirm subscribers connect before the first broadcast"),
                    PlaybookStep(action="Check analysis FIFO occupancy against its bound", signals=["fifo occupancy"]),
                    PlaybookStep(action="Verify the monitor writes to the correct analysis port instance", signals=["analysis port"]),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for UVM TLM.")],
    )
