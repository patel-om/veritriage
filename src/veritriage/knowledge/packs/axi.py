"""AXI protocol Knowledge Pack.

Teaches VeriTriage the AMBA AXI handshake rules, the read/write transaction
lifecycle, and the failure modes DV teams hit most: response never arriving
after an accepted address, outstanding transactions that never retire, and
VALID deasserting before READY.
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

_SPEC = "AMBA AXI Protocol Specification"


@register_pack
def axi_pack() -> KnowledgePack:
    return KnowledgePack(
        id="axi",
        name="AMBA AXI",
        version="1.0.0",
        domain="protocol",
        summary="AXI channel handshakes, transaction lifecycle, and common failure modes.",
        concepts=[
            Concept(
                id="axi.handshake",
                name="VALID/READY handshake",
                summary=(
                    "Every AXI channel transfers when VALID and READY are high in the same "
                    "cycle. A source must keep VALID asserted (with stable payload) until "
                    "the handshake completes; dropping VALID early is a protocol violation."
                ),
                markers=[r"\bvalid\b.*\bready\b", r"handshake", r"\barvalid\b", r"\bawvalid\b"],
                references=[
                    Reference(source=_SPEC, section="A3.2.1", note="Handshake process rules."),
                ],
            ),
            Concept(
                id="axi.read-transaction",
                name="AXI read transaction",
                summary=(
                    "A read is an AR-channel address handshake followed by one or more "
                    "R-channel data beats; the transaction stays outstanding until the "
                    "last beat (RLAST) is accepted."
                ),
                markers=[r"\baxi\b.*read", r"\barvalid\b", r"\brvalid\b", r"read (?:addr|burst|data)"],
                references=[
                    Reference(source=_SPEC, section="A3.4", note="Read transaction dependencies."),
                ],
            ),
            Concept(
                id="axi.outstanding",
                name="Outstanding transactions",
                summary=(
                    "Accepted addresses without completed responses are outstanding. A DUT "
                    "that accepts addresses but never responds deadlocks the master; "
                    "outstanding counters are the first thing to check on an AXI hang."
                ),
                markers=[r"outstanding", r"in flight", r"await(?:ing)? (?:completion|response)", r"never retir"],
                references=[
                    Reference(source=_SPEC, section="A5.3", note="Ordering and outstanding limits."),
                ],
            ),
        ],
        signals=[
            ProtocolSignal(name="ARVALID", role="read address valid", channel="AR"),
            ProtocolSignal(name="ARREADY", role="read address ready", channel="AR"),
            ProtocolSignal(name="RVALID", role="read data valid", channel="R"),
            ProtocolSignal(name="RREADY", role="read data ready", channel="R"),
            ProtocolSignal(name="RLAST", role="last read beat", channel="R"),
            ProtocolSignal(name="AWVALID", role="write address valid", channel="AW"),
            ProtocolSignal(name="WVALID", role="write data valid", channel="W"),
            ProtocolSignal(name="BVALID", role="write response valid", channel="B"),
        ],
        state_machines=[
            StateMachine(
                id="axi.read-lifecycle",
                name="AXI read lifecycle",
                states=[
                    ProtocolState(
                        name="Address issued",
                        description="Master drives ARVALID with the read address.",
                        markers=[r"issued", r"\barvalid\b", r"read addr", r"\bsent\b", r"descriptor \d+"],
                    ),
                    ProtocolState(
                        name="Address accepted",
                        description="ARREADY seen: the address handshake completed.",
                        markers=[r"\barready\b", r"accept", r"handshake complete"],
                    ),
                    ProtocolState(
                        name="Outstanding",
                        description="Transaction in flight, awaiting response data.",
                        markers=[r"outstanding", r"await", r"pending", r"in flight"],
                    ),
                    ProtocolState(
                        name="Response",
                        description="RVALID data beats returning to the master.",
                        # Positive observations only: "no RVALID" style negations
                        # must not count as the response stage being reached.
                        markers=[
                            r"rvalid (?:assert|seen|high)",
                            r"response (?:beat|received|returned)",
                            r"data (?:beat|received|returned)",
                            r"\brlast\b",
                        ],
                    ),
                    ProtocolState(
                        name="Complete",
                        description="Last beat accepted; transaction retires.",
                        markers=[r"transaction complete", r"retir", r"\bOKAY\b", r"\ball beats\b"],
                    ),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="axi.no-response-after-accept",
                name="No response after accepted address",
                summary=(
                    "An address handshake completed but no response beat ever arrived; the "
                    "run timed out with the transaction still outstanding."
                ),
                required=[
                    EvidenceClause(
                        name="timeout observed",
                        pattern=r"time[- ]?out|watchdog|PH_TIMEOUT",
                        must_fail=True,
                    ),
                    EvidenceClause(
                        name="transaction outstanding",
                        pattern=r"outstanding|await(?:ing)?|pending|in flight|issued",
                    ),
                ],
                optional=[
                    EvidenceClause(name="AXI context", pattern=r"\baxi\b|\barvalid\b|\brvalid\b"),
                ],
                forbidden=[
                    EvidenceClause(
                        name="no protocol assertion fired",
                        pattern=r".",
                        artifact_types=["assertion"],
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Response FSM stuck (missing arc back to a ready state)",
                    "Outstanding-transaction counter overflow or leak",
                    "Response multiplexer never selects the completing source",
                    "Credit/token starvation between clock domains",
                ],
                ownership="design",
                suggested_signals=["ARVALID", "ARREADY", "RVALID", "RREADY", "RLAST"],
                playbook_id="axi.read-timeout",
                confidence_modifiers={"rtl_bug": 0.12, "testbench_issue": -0.03},
                references=[
                    Reference(source=_SPEC, section="A3.4.1", note="Read response dependency: RVALID must eventually follow an accepted AR."),
                ],
            ),
            FailurePattern(
                id="axi.valid-drop-before-ready",
                name="VALID deasserted before READY",
                summary=(
                    "A source dropped VALID before the handshake completed; AXI requires "
                    "VALID to stay high until READY accepts the transfer."
                ),
                required=[
                    EvidenceClause(
                        name="stability assertion fired",
                        pattern=r"valid.*(?:drop|deassert|unstable|before ready)|(?:drop|deassert).*valid",
                        must_fail=True,
                    ),
                ],
                optional=[
                    EvidenceClause(name="assertion evidence", pattern=r".", artifact_types=["assertion"]),
                ],
                typical_causes=[
                    "Source FSM leaves the asserting state on an unqualified condition",
                    "Payload/valid registered in different pipeline stages",
                    "Reset or flush deasserts VALID mid-handshake",
                ],
                ownership="design",
                suggested_signals=["ARVALID", "ARREADY", "AWVALID", "WVALID"],
                playbook_id="axi.handshake-stability",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[
                    Reference(source=_SPEC, section="A3.2.1", note="Once VALID is asserted it must remain asserted until the handshake occurs."),
                ],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="axi.read-timeout",
                name="AXI read timeout",
                steps=[
                    PlaybookStep(action="Check ARVALID at the master boundary", detail="Confirm the master actually issued the read.", signals=["ARVALID"]),
                    PlaybookStep(action="Check ARREADY from the slave", detail="Did the address handshake complete, or is the slave back-pressuring forever?", signals=["ARREADY"]),
                    PlaybookStep(action="Inspect the outstanding counter", detail="Compare issued vs retired counts; a leak here explains a hang without a violation.", signals=["outstanding_cnt"]),
                    PlaybookStep(action="Walk the response FSM state", detail="Find the state it parked in and which arc should have fired.", signals=["resp_fsm_state"]),
                    PlaybookStep(action="Check the response multiplexer select", detail="A mis-selected source returns no beats to the waiting master.", signals=["rresp_mux_sel"]),
                    PlaybookStep(action="Re-run with protocol assertions enabled", detail="A handshake assertion may localize the stall to one channel."),
                    PlaybookStep(action="Pull waveforms for the R channel", detail="Confirm whether RVALID ever pulsed anywhere in the fabric.", signals=["RVALID", "RREADY", "RLAST"]),
                ],
            ),
            DebugPlaybook(
                id="axi.handshake-stability",
                name="VALID/READY stability violation",
                steps=[
                    PlaybookStep(action="Locate the first violating cycle in the waveform", signals=["ARVALID", "ARREADY"]),
                    PlaybookStep(action="Trace VALID back to its generating FSM", detail="Find the condition that deasserted it early."),
                    PlaybookStep(action="Check reset/flush terms in that FSM", detail="Mid-handshake flushes are the most common cause."),
                    PlaybookStep(action="Confirm payload stability over the same window", detail="Unstable payload with stable VALID is the sibling bug."),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary protocol reference for this pack.")],
    )
