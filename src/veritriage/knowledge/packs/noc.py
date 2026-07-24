"""Network-on-Chip (NoC) fundamentals Knowledge Pack.

Protocol-agnostic on-chip interconnect knowledge: routing and virtual
channels, credit-based flow control, and quality-of-service arbitration. The
failure modes here are the classic network hazards - deadlock from cyclic
dependencies, credit accounting that starves a link, and head-of-line
blocking that violates QoS.
"""

from __future__ import annotations

from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    PlaybookStep,
    ProtocolSignal,
    ProtocolState,
    Reference,
    StateMachine,
)
from veritriage.knowledge.registry import register_pack

_SPEC = "NoC design fundamentals (routing, flow control, QoS)"


@register_pack
def noc_pack() -> KnowledgePack:
    return KnowledgePack(
        id="noc",
        name="Network-on-Chip fundamentals",
        version="1.0.0",
        domain="interconnect",
        summary="NoC routing/deadlock, credit-based flow control, and QoS head-of-line blocking.",
        concepts=[
            Concept(
                id="noc.routing",
                name="Routing and virtual channels",
                summary=(
                    "Packets traverse routers hop by hop; virtual channels (VCs) "
                    "share a physical link while keeping separate buffer queues. A "
                    "routing function with a cyclic channel-dependency graph can "
                    "deadlock: each packet holds a buffer another needs, and none "
                    "can advance."
                ),
                markers=[r"\brout(?:e|ing)\b", r"virtual channel|\bvc\b", r"\bhop\b|\bflit\b|\brouter\b"],
                references=[Reference(source=_SPEC, section="Routing", note="Deadlock-free routing and channel dependencies.")],
            ),
            Concept(
                id="noc.flow-control",
                name="Credit-based flow control",
                summary=(
                    "A sender holds credits representing free buffer slots downstream "
                    "and consumes one per flit; the receiver returns credits as it "
                    "drains. If credits leak or underflow, the sender either stalls "
                    "forever or overruns the receiver's buffer."
                ),
                markers=[r"\bcredit\b", r"flow control", r"buffer (?:slot|occupancy)|backpressure"],
                references=[Reference(source=_SPEC, section="FlowControl", note="Credit accounting invariants.")],
            ),
            Concept(
                id="noc.qos",
                name="Quality of service",
                summary=(
                    "QoS arbitration prioritizes traffic classes so latency-critical "
                    "flows are not blocked by bulk traffic. Head-of-line blocking - a "
                    "stalled packet at the front of a shared queue holding up ready "
                    "packets behind it - defeats QoS and starves a class."
                ),
                markers=[r"\bqos\b|quality of service", r"head[- ]of[- ]line", r"priority (?:class|arbitrat)|traffic class"],
                references=[Reference(source=_SPEC, section="QoS", note="Priority arbitration and HOL blocking.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="credit_count", role="downstream credits held", channel="link"),
            ProtocolSignal(name="vc_grant", role="virtual channel granted", channel="router"),
            ProtocolSignal(name="flit_valid", role="flit valid on link", channel="link"),
        ],
        state_machines=[
            StateMachine(
                id="noc.packet-lifecycle",
                name="NoC packet lifecycle",
                states=[
                    ProtocolState(name="Injected", description="Packet injected at the source NI.", markers=[r"packet injected|injected at (?:source|ni)"]),
                    ProtocolState(name="Routed", description="Route computed; output port selected.", markers=[r"route computed|routing decision|output port"]),
                    ProtocolState(name="Switched", description="VC and switch allocated; flits traverse.", markers=[r"vc allocat|switch allocat|traversing"]),
                    ProtocolState(name="Ejected", description="Packet ejected at the destination NI.", markers=[r"packet ejected|delivered at destination|ejected at ni"]),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="noc.routing-deadlock",
                name="Routing deadlock",
                summary=(
                    "Packets are permanently blocked in a cyclic buffer-dependency: "
                    "each holds a channel another needs, so no packet can advance and "
                    "the network wedges."
                ),
                required=[
                    EvidenceClause(
                        name="cyclic dependency deadlock",
                        pattern=r"(?:routing |network )?deadlock|cyclic (?:channel |buffer )?dependency|packets? blocked.*(?:cycle|circular)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="noc context", pattern=r"\bnoc\b|\brouter\b|virtual channel|\bflit\b"),
                ],
                typical_causes=[
                    "Routing function is not provably deadlock-free (no acyclic channel-dependency graph)",
                    "Insufficient escape VCs for the routing algorithm used",
                    "Protocol-level dependency (request waits on response in the same VC)",
                ],
                ownership="design",
                suggested_signals=["vc_grant", "buffer occupancy", "routing decision"],
                playbook_id="noc.deadlock-debug",
                confidence_modifiers={"rtl_bug": 0.13},
                references=[Reference(source=_SPEC, section="Routing", note="Cyclic channel dependencies cause deadlock.")],
            ),
            FailurePattern(
                id="noc.credit-underflow",
                name="Credit-based flow-control breakdown",
                summary=(
                    "Credit accounting is broken: credits underflowed or leaked, so "
                    "a link either stalls with flits ready to send or the sender "
                    "overruns the receiver's buffer."
                ),
                required=[
                    EvidenceClause(
                        name="credit accounting broken",
                        pattern=r"credit (?:underflow|leak|starv|overflow)|no credits.*(?:stall|stuck)|flow control credit.*(?:lost|underflow|mismatch)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Credit return path drops returns under a burst (return FIFO overflow)",
                    "Credit counter reset out of sync with the buffer it tracks",
                    "Double-counted credit on a speculative flit that was cancelled",
                ],
                ownership="design",
                suggested_signals=["credit_count", "buffer occupancy", "credit return path"],
                playbook_id="noc.credit-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="FlowControl", note="Credit conservation invariant.")],
            ),
            FailurePattern(
                id="noc.hol-blocking",
                name="Head-of-line blocking / QoS starvation",
                summary=(
                    "A stalled packet at the head of a shared queue held up ready "
                    "packets behind it, and a low-priority flow blocked a "
                    "latency-critical one, so the QoS guarantee was violated."
                ),
                required=[
                    EvidenceClause(
                        name="hol blocking / qos starvation",
                        pattern=r"head[- ]of[- ]line blocking|hol blocking|qos.*(?:starv|violat)|(?:low[- ]priority|bulk).*(?:starv|block).*(?:high|critical)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Traffic classes share a single queue instead of separate VCs",
                    "Arbiter does not preempt a stalled head packet for ready ones",
                    "Priority inversion in the switch allocator",
                ],
                ownership="design",
                suggested_signals=["vc_grant", "queue occupancy per class", "arbiter priority"],
                playbook_id="noc.qos-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="QoS", note="HOL blocking defeats QoS.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="noc.deadlock-debug",
                name="NoC deadlock debug",
                steps=[
                    PlaybookStep(action="Snapshot every blocked packet's held and requested channel", signals=["vc_grant", "buffer occupancy"]),
                    PlaybookStep(action="Build the channel-dependency graph and find the cycle"),
                    PlaybookStep(action="Confirm the routing function has an acyclic dependency graph or enough escape VCs"),
                    PlaybookStep(action="Check for a protocol dependency (request/response sharing a VC)"),
                ],
            ),
            DebugPlaybook(
                id="noc.credit-debug",
                name="NoC credit debug",
                steps=[
                    PlaybookStep(action="Reconcile credit count against actual downstream buffer occupancy", signals=["credit_count", "buffer occupancy"]),
                    PlaybookStep(action="Check the credit-return path for drops under burst", signals=["credit return path"]),
                    PlaybookStep(action="Verify credit counter reset aligns with buffer reset"),
                    PlaybookStep(action="Look for double-counting on cancelled speculative flits"),
                ],
            ),
            DebugPlaybook(
                id="noc.qos-debug",
                name="NoC QoS debug",
                steps=[
                    PlaybookStep(action="Identify the stalled head packet and the ready packets behind it", signals=["queue occupancy per class"]),
                    PlaybookStep(action="Confirm traffic classes use separate VCs, not a shared queue"),
                    PlaybookStep(action="Check the switch allocator honors priority and can preempt a stalled head", signals=["arbiter priority"]),
                    PlaybookStep(action="Trace for priority inversion in the allocator"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for NoC fundamentals.")],
    )
