"""AMBA AXI4-Stream Knowledge Pack.

The streaming subset of AXI: a TVALID/TREADY handshake carrying packetized
data framed by TLAST, with TKEEP/TSTRB byte qualifiers and TUSER sideband.
The failure modes are framing (a packet that never terminates) and flow
control (a stream that deadlocks under backpressure).
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
    Reference,
)
from veritriage.knowledge.registry import register_pack

_SPEC = "AMBA AXI4-Stream Protocol Specification"


@register_pack
def axi_stream_pack() -> KnowledgePack:
    return KnowledgePack(
        id="axi-stream",
        name="AMBA AXI4-Stream",
        version="1.0.0",
        domain="protocol",
        summary="AXI4-Stream handshake, TLAST packet framing, and backpressure flow control.",
        concepts=[
            Concept(
                id="axi-stream.handshake",
                name="Stream handshake and framing",
                summary=(
                    "A transfer happens when TVALID and TREADY are both high. TLAST "
                    "marks the final beat of a packet; TKEEP/TSTRB qualify which "
                    "bytes are data. A source must hold TVALID and its payload stable "
                    "until TREADY, and must eventually assert TLAST to close a packet."
                ),
                markers=[r"\btvalid\b|\btready\b", r"\btlast\b", r"\btkeep\b|\btstrb\b", r"stream (?:beat|transfer|packet)"],
                references=[Reference(source=_SPEC, section="2.1", note="Stream handshake and packet framing.")],
            ),
            Concept(
                id="axi-stream.backpressure",
                name="Backpressure",
                summary=(
                    "A destination applies backpressure by holding TREADY low. This "
                    "is legal indefinitely, but a downstream that never asserts "
                    "TREADY while the source holds TVALID stalls the stream; if the "
                    "readiness depends circularly on the source, the stream deadlocks."
                ),
                markers=[r"backpressure", r"\btready\b (?:low|deassert|never)", r"stream (?:stall|deadlock)"],
                references=[Reference(source=_SPEC, section="2.2", note="TREADY backpressure semantics.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="TVALID", role="stream data valid", channel="T"),
            ProtocolSignal(name="TREADY", role="stream data ready", channel="T"),
            ProtocolSignal(name="TLAST", role="last beat of packet", channel="T"),
            ProtocolSignal(name="TKEEP", role="byte qualifier", channel="T"),
        ],
        patterns=[
            FailurePattern(
                id="axi-stream.tlast-missing",
                name="Packet never terminated (TLAST missing)",
                summary=(
                    "A stream packet was never closed: TLAST was never asserted, so "
                    "the packet boundary is lost and the sink waits forever for the "
                    "end of frame."
                ),
                required=[
                    EvidenceClause(
                        name="tlast never asserted",
                        pattern=r"tlast (?:never|missing|not asserted)|packet (?:never terminated|boundary lost|never closed)|stream.*no tlast",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="stream context", pattern=r"\btvalid\b|\btlast\b|stream packet"),
                ],
                typical_causes=[
                    "Beat counter that should drive TLAST off by one or never reaching the frame length",
                    "TLAST gated by a condition that the last beat does not satisfy",
                    "Packet length metadata lost between the packing and framing stages",
                ],
                ownership="design",
                suggested_signals=["TLAST", "TVALID", "beat counter"],
                playbook_id="axi-stream.framing-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="2.1", note="TLAST marks the packet boundary.")],
            ),
            FailurePattern(
                id="axi-stream.tready-stall",
                name="Stream deadlock under backpressure",
                summary=(
                    "The source held TVALID but the destination never asserted "
                    "TREADY, and the readiness depended on forward progress that "
                    "cannot occur, deadlocking the stream."
                ),
                required=[
                    EvidenceClause(
                        name="tready never asserts",
                        pattern=r"tready (?:never|stuck low|deadlock)|stream.*(?:stall|backpressure deadlock)|tvalid.*tready never",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Downstream FIFO full condition never clears (drain path stalled)",
                    "TREADY generation depends on a credit that is never returned",
                    "Circular readiness between two stream stages",
                ],
                ownership="design",
                suggested_signals=["TREADY", "TVALID", "downstream FIFO level"],
                playbook_id="axi-stream.flow-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="2.2", note="Backpressure and forward-progress.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="axi-stream.framing-debug",
                name="Stream framing debug",
                steps=[
                    PlaybookStep(action="Count beats in the stuck packet and compare to the intended frame length", signals=["beat counter"]),
                    PlaybookStep(action="Confirm the condition that drives TLAST is reachable on the final beat", signals=["TLAST"]),
                    PlaybookStep(action="Check that packet-length metadata survives to the framing stage"),
                    PlaybookStep(action="Verify TKEEP/TSTRB on the final beat match the residue bytes"),
                ],
            ),
            DebugPlaybook(
                id="axi-stream.flow-debug",
                name="Stream flow-control debug",
                steps=[
                    PlaybookStep(action="Confirm the source is holding TVALID and stable payload", signals=["TVALID"]),
                    PlaybookStep(action="Trace why TREADY stays low: FIFO level, credit, or gating condition", signals=["TREADY", "downstream FIFO level"]),
                    PlaybookStep(action="Check the drain path of the downstream buffer for a separate stall"),
                    PlaybookStep(action="Look for a circular readiness dependency between stages"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for AXI4-Stream.")],
    )
