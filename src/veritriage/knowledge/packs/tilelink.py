"""TileLink Knowledge Pack.

TileLink (TL-UL/TL-UH/TL-C) is the RISC-V ecosystem's coherent interconnect.
Its five channels (A through E) have a strict priority ordering that makes
deadlock-freedom provable, which means most TileLink hangs are a violation
of exactly those rules.
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

_SPEC = "SiFive TileLink Specification 1.9"


@register_pack
def tilelink_pack() -> KnowledgePack:
    return KnowledgePack(
        id="tilelink",
        name="TileLink",
        version="1.0.0",
        domain="protocol",
        summary="TileLink channel priorities, request/grant flows, and deadlock rules.",
        concepts=[
            Concept(
                id="tilelink.channels",
                name="Channel priority (A < B < C < D < E)",
                summary=(
                    "TileLink guarantees deadlock freedom by channel priority: a "
                    "message on a higher-priority channel must never wait on a "
                    "lower-priority one. An agent that blocks D responses behind "
                    "new A requests has broken the proof and will eventually hang."
                ),
                markers=[r"tilelink|\btl-?u[lh]\b|\btl-?c\b", r"channel [a-e]\b", r"\bacquire\b|\bgrant\b.*channel"],
                references=[Reference(source=_SPEC, section="3.2", note="Channel ordering and deadlock freedom.")],
            ),
            Concept(
                id="tilelink.acquire-grant",
                name="Acquire/Grant flow",
                summary=(
                    "A TL-C master gains a cache block with Acquire (channel A), "
                    "receives Grant/GrantData (channel D), and must acknowledge "
                    "with GrantAck (channel E) so the slave can retire the "
                    "transaction. A missing GrantAck stalls the slave's tracker, "
                    "not the master, making it look like an unrelated later hang."
                ),
                markers=[r"\bacquire\b", r"\bgrant(?:data|ack)?\b", r"\bprobe\b.*(?:ack|block)?", r"\brelease\b"],
                references=[Reference(source=_SPEC, section="9.3", note="Acquire transaction lifecycle.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="a_valid/a_ready", role="request channel handshake", channel="A"),
            ProtocolSignal(name="b_valid/b_ready", role="probe channel handshake", channel="B"),
            ProtocolSignal(name="c_valid/c_ready", role="release/probe-ack handshake", channel="C"),
            ProtocolSignal(name="d_valid/d_ready", role="response channel handshake", channel="D"),
            ProtocolSignal(name="e_valid/e_ready", role="grant-ack handshake", channel="E"),
        ],
        state_machines=[
            StateMachine(
                id="tilelink.acquire",
                name="TileLink Acquire lifecycle",
                states=[
                    ProtocolState(
                        name="Acquire sent",
                        description="Master issues Acquire on channel A.",
                        markers=[r"acquire (?:sent|issued)", r"channel a .*(?:sent|valid)"],
                    ),
                    ProtocolState(
                        name="Probes resolved",
                        description="Slave probes other masters; ProbeAcks return on C.",
                        markers=[r"probe (?:sent|issued)", r"probeack"],
                    ),
                    ProtocolState(
                        name="Grant returned",
                        description="Grant/GrantData arrives on channel D.",
                        markers=[r"grant(?:data)? (?:received|returned|seen)"],
                    ),
                    ProtocolState(
                        name="Acknowledged",
                        description="GrantAck on channel E retires the tracker.",
                        markers=[r"grantack", r"transaction (?:complete|retired)"],
                    ),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="tilelink.grant-missing",
                name="Grant never returned for Acquire",
                summary=(
                    "An Acquire was accepted on channel A but no Grant ever came "
                    "back on channel D; the master's miss handler is stuck and the "
                    "run timed out."
                ),
                required=[
                    EvidenceClause(
                        name="timeout observed",
                        pattern=r"time[- ]?out|watchdog",
                        must_fail=True,
                    ),
                    EvidenceClause(
                        name="acquire outstanding",
                        pattern=r"acquire.*(?:outstanding|pending|no grant|never)|grant.*(?:missing|never|awaited)",
                    ),
                ],
                typical_causes=[
                    "Slave tracker waits for a ProbeAck a master never sends",
                    "Channel D blocked behind channel A traffic (priority inversion)",
                    "Grant routed to the wrong source ID",
                ],
                ownership="design",
                suggested_signals=["a_valid/a_ready", "d_valid/d_ready", "tracker state", "source IDs"],
                playbook_id="tilelink.grant-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="9.3", note="Grant must follow an accepted Acquire.")],
            ),
            FailurePattern(
                id="tilelink.priority-inversion",
                name="Channel priority inversion",
                summary=(
                    "A higher-priority channel was made to wait on a lower-priority "
                    "one (e.g. D blocked by A), voiding TileLink's deadlock-freedom "
                    "guarantee; the hang may appear far from the offending agent."
                ),
                required=[
                    EvidenceClause(
                        name="priority violation observed",
                        pattern=r"priority inversion|channel [de] .*block.*channel [abc]|deadlock.*channel",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Shared buffer between channels without per-channel reservation",
                    "Arbiter picks strictly round-robin across channels instead of by priority",
                    "Response generation gated on acceptance of a new request",
                ],
                ownership="design",
                suggested_signals=["per-channel valid/ready", "shared buffer occupancy"],
                playbook_id="tilelink.priority-audit",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="3.2", note="Agents must not block priority-N on priority<N.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="tilelink.grant-debug",
                name="Missing Grant debug",
                steps=[
                    PlaybookStep(action="Find the accepted Acquire without a matching Grant", detail="Match by source ID.", signals=["a_valid/a_ready", "d_valid/d_ready"]),
                    PlaybookStep(action="Dump the slave tracker for that transaction", detail="What is it waiting on?"),
                    PlaybookStep(action="If waiting on probes, list outstanding Probes and missing ProbeAcks", signals=["b_valid", "c_valid"]),
                    PlaybookStep(action="Check D-channel backpressure at the master", detail="A master that never raises d_ready hangs itself.", signals=["d_ready"]),
                ],
            ),
            DebugPlaybook(
                id="tilelink.priority-audit",
                name="Channel priority audit",
                steps=[
                    PlaybookStep(action="For the stuck channel, find what its ready depends on", detail="Trace the ready term through the RTL."),
                    PlaybookStep(action="Flag any dependency on a lower-priority channel's progress", detail="That dependency is the violation."),
                    PlaybookStep(action="Check shared resources for per-channel reservations", detail="Every shared buffer needs a guaranteed slot per priority level."),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary protocol reference for this pack.")],
    )
