"""AMBA ACE / ACE-Lite Knowledge Pack.

The coherency extension to AXI: snoop channels (AC address-in, CR response,
CD data), cache-line states, and barrier transactions. ACE failures are
coherence failures - a snoop that goes unanswered, or a barrier whose
ordering the interconnect does not honor.
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

_SPEC = "AMBA AXI/ACE Protocol Specification"


@register_pack
def ace_pack() -> KnowledgePack:
    return KnowledgePack(
        id="ace",
        name="AMBA ACE / ACE-Lite",
        version="1.0.0",
        domain="protocol",
        summary="ACE snoop channels, cache-line coherency, and barrier ordering.",
        concepts=[
            Concept(
                id="ace.snoop",
                name="Snoop channels (AC/CR/CD)",
                summary=(
                    "A snooping master receives a snoop address on AC, must return "
                    "a snoop response on CR, and, if it holds dirty data, provides it "
                    "on CD. Every snoop on AC requires exactly one CR response; a "
                    "missing CR hangs the requesting master waiting for coherence."
                ),
                markers=[r"\bsnoop\b", r"\bac\b channel|\bcr\b response|\bcd\b (?:channel|data)", r"coherent (?:read|transaction)"],
                references=[Reference(source=_SPEC, section="C3", note="Snoop channel handshakes.")],
            ),
            Concept(
                id="ace.barrier",
                name="Barrier transactions",
                summary=(
                    "ACE barrier transactions order memory accesses across the "
                    "coherent interconnect. Transactions issued before a barrier "
                    "must be observed before those issued after; an interconnect "
                    "that lets a post-barrier access pass a pre-barrier one violates "
                    "the ordering the barrier exists to guarantee."
                ),
                markers=[r"\bbarrier\b", r"memory barrier|dmb|dsb", r"ordering (?:before|after) barrier"],
                references=[Reference(source=_SPEC, section="C8", note="Barrier transaction ordering.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="ACVALID", role="snoop address valid", channel="AC"),
            ProtocolSignal(name="CRVALID", role="snoop response valid", channel="CR"),
            ProtocolSignal(name="CDVALID", role="snoop data valid", channel="CD"),
        ],
        patterns=[
            FailurePattern(
                id="ace.snoop-response-missing",
                name="Snoop issued but no CR response",
                summary=(
                    "A snoop was driven on the AC channel but the snooped master "
                    "never returned a CR response, so the coherent transaction that "
                    "triggered the snoop can never complete."
                ),
                required=[
                    EvidenceClause(
                        name="cr response never returned",
                        pattern=r"snoop (?:response|cr) (?:missing|never)|\bac\b.*\bcr\b.*never|snoop.*no response|crvalid never",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="ace context", pattern=r"\bsnoop\b|coherent|\bace\b"),
                ],
                typical_causes=[
                    "Snoop filter forwards AC but the master's CR path is not wired",
                    "Snoop response FSM stuck waiting for a CD it will never send",
                    "Snoop accepted for a line the cache controller does not track",
                ],
                ownership="design",
                suggested_signals=["ACVALID", "CRVALID", "snoop response FSM"],
                playbook_id="ace.snoop-debug",
                confidence_modifiers={"rtl_bug": 0.13},
                references=[Reference(source=_SPEC, section="C3.1", note="Every snoop requires a CR response.")],
            ),
            FailurePattern(
                id="ace.barrier-ordering-violation",
                name="Barrier ordering violated",
                summary=(
                    "A transaction issued after a barrier was observed before a "
                    "transaction issued before it, so the interconnect did not "
                    "honor the barrier's ordering guarantee."
                ),
                required=[
                    EvidenceClause(
                        name="barrier ordering broken",
                        pattern=r"barrier.*(?:ordering|violat)|ace barrier.*(?:not|reorder)|memory barrier.*(?:bypass|passed)|post[- ]barrier.*before pre[- ]barrier",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Barrier not propagated to every downstream ordering domain",
                    "Reordering buffer allows post-barrier transactions to drain first",
                    "Barrier completion signaled before pre-barrier transactions retire",
                ],
                ownership="design",
                suggested_signals=["barrier transaction id", "transaction issue order", "ordering domain"],
                playbook_id="ace.barrier-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="C8.1", note="Barrier ordering requirements.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="ace.snoop-debug",
                name="Snoop response debug",
                steps=[
                    PlaybookStep(action="Confirm the AC snoop reached the target master's snoop port", signals=["ACVALID"]),
                    PlaybookStep(action="Trace the snoop response FSM to where it stalls before CR", signals=["snoop response FSM"]),
                    PlaybookStep(action="Check whether the FSM is waiting on a CD data phase that is not required", signals=["CRVALID"]),
                    PlaybookStep(action="Verify the snooped line is actually tracked by that cache"),
                ],
            ),
            DebugPlaybook(
                id="ace.barrier-debug",
                name="Barrier ordering debug",
                steps=[
                    PlaybookStep(action="Identify the pre- and post-barrier transactions and their observed order", signals=["transaction issue order"]),
                    PlaybookStep(action="Confirm the barrier propagated to every downstream ordering domain", signals=["ordering domain"]),
                    PlaybookStep(action="Check the reordering buffer does not drain post-barrier work early"),
                    PlaybookStep(action="Verify barrier completion waits for all pre-barrier retirements"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for ACE coherency.")],
    )
