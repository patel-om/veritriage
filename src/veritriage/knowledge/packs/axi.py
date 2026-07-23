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
                id="axi.write-transaction",
                name="AXI write transaction",
                summary=(
                    "A write is an AW-channel address handshake plus W-channel data "
                    "beats (WLAST on the final beat), acknowledged by a single "
                    "B-channel response. Address and data channels are decoupled: "
                    "data may arrive before the address, and the response must not "
                    "be given until both have completed."
                ),
                markers=[r"\baxi\b.*write", r"\bawvalid\b", r"\bwvalid\b", r"\bbvalid\b", r"\bwlast\b", r"write (?:addr|burst|data|response)"],
                references=[
                    Reference(source=_SPEC, section="A3.3", note="Write transaction dependencies: BVALID requires AWVALID/AWREADY and WVALID/WREADY/WLAST."),
                ],
            ),
            Concept(
                id="axi.exclusive",
                name="Exclusive access",
                summary=(
                    "An exclusive read/write pair implements atomic access: the "
                    "exclusive write succeeds (EXOKAY) only if no other master wrote "
                    "the location since the exclusive read. An OKAY response to an "
                    "exclusive write means the exclusivity was lost or the monitor "
                    "does not support the location."
                ),
                markers=[r"exclusive", r"\bEXOKAY\b", r"exokay"],
                references=[
                    Reference(source=_SPEC, section="A7.2", note="Exclusive access model and monitor requirements."),
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
            StateMachine(
                id="axi.write-lifecycle",
                name="AXI write lifecycle",
                states=[
                    ProtocolState(
                        name="Address issued",
                        description="Master drives AWVALID with the write address.",
                        markers=[r"\bawvalid\b", r"write addr .*issued", r"write issued"],
                    ),
                    ProtocolState(
                        name="Data beats",
                        description="W-channel beats transfer, ending with WLAST.",
                        markers=[r"\bwvalid\b", r"\bwlast\b", r"write (?:data|beat)"],
                    ),
                    ProtocolState(
                        name="Awaiting response",
                        description="Both channels complete; master waits for B.",
                        markers=[r"await(?:ing)? (?:write )?response", r"write outstanding", r"response pending"],
                    ),
                    ProtocolState(
                        name="Response",
                        description="BVALID returns the write status.",
                        markers=[r"bvalid (?:assert|seen|high)", r"write response (?:received|returned)", r"\bBRESP\b"],
                    ),
                    ProtocolState(
                        name="Complete",
                        description="Response accepted; write retires.",
                        markers=[r"write complete", r"write retir", r"\bOKAY\b", r"\bEXOKAY\b"],
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
            FailurePattern(
                id="axi.write-response-missing",
                name="Write response never returned",
                summary=(
                    "Address and data phases of a write completed but BVALID never "
                    "arrived; the slave accepted the write and then went silent."
                ),
                required=[
                    EvidenceClause(
                        name="timeout observed",
                        pattern=r"time[- ]?out|watchdog",
                        must_fail=True,
                    ),
                    EvidenceClause(
                        name="write awaiting response",
                        pattern=r"write .*(?:outstanding|pending|await)|await(?:ing)? (?:write )?response|\bbvalid\b.*(?:missing|never)",
                    ),
                ],
                optional=[
                    EvidenceClause(name="AXI write context", pattern=r"\bawvalid\b|\bwlast\b|\baxi\b.*write"),
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
                    "Slave waits for WLAST it already consumed (beat counting bug)",
                    "Write response queue full and never drained",
                    "B-channel arbiter starvation under concurrent masters",
                    "Interleaved write data associated with the wrong AWID",
                ],
                ownership="design",
                suggested_signals=["AWVALID", "WVALID", "WLAST", "BVALID", "BREADY", "wr_resp_q_level"],
                playbook_id="axi.write-response",
                confidence_modifiers={"rtl_bug": 0.12, "testbench_issue": -0.03},
                references=[
                    Reference(source=_SPEC, section="A3.3.1", note="Write response dependency: BVALID requires completed address and data phases."),
                ],
            ),
            FailurePattern(
                id="axi.exclusive-fail",
                name="Exclusive access never succeeds",
                summary=(
                    "Exclusive writes keep receiving OKAY instead of EXOKAY: the "
                    "exclusivity is always lost or the monitor never grants it."
                ),
                required=[
                    EvidenceClause(
                        name="exclusive failure observed",
                        pattern=r"exclusive .*(?:fail|okay instead|not granted|lost)|\bEXOKAY\b.*(?:expected|missing|never)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Exclusive monitor not implemented for the address region",
                    "Monitor granularity larger than the tested data size",
                    "Another master (or the same master's ID reuse) clears the reservation",
                    "Testbench issues the exclusive pair with mismatched ID/address/size",
                ],
                ownership="design",
                suggested_signals=["ARLOCK", "AWLOCK", "BRESP", "exclusive monitor state"],
                playbook_id="axi.exclusive-debug",
                confidence_modifiers={"rtl_bug": 0.10, "testbench_issue": 0.05},
                references=[
                    Reference(source=_SPEC, section="A7.2.4", note="EXOKAY conditions and monitor reset events."),
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
                id="axi.write-response",
                name="AXI write response missing",
                steps=[
                    PlaybookStep(action="Confirm both write phases completed", detail="AW handshake and the WLAST beat must both have occurred.", signals=["AWVALID", "AWREADY", "WVALID", "WREADY", "WLAST"]),
                    PlaybookStep(action="Check the slave's beat counter against the burst length", detail="An off-by-one here leaves the slave waiting for a beat that never comes."),
                    PlaybookStep(action="Inspect the write response queue occupancy", detail="Full-and-never-drained means the response was generated but stuck.", signals=["wr_resp_q_level"]),
                    PlaybookStep(action="Check B-channel arbitration under concurrent masters", signals=["BVALID", "BREADY"]),
                    PlaybookStep(action="Verify AWID/WID association for interleaved writes", detail="Data attributed to the wrong ID stalls the right one forever."),
                ],
            ),
            DebugPlaybook(
                id="axi.exclusive-debug",
                name="Exclusive access debug",
                steps=[
                    PlaybookStep(action="Log the exclusive read/write pair parameters", detail="ID, address, size, and length must match exactly between the pair.", signals=["ARLOCK", "AWLOCK"]),
                    PlaybookStep(action="Dump the exclusive monitor state between the pair", detail="Find what cleared the reservation.", signals=["exclusive monitor state"]),
                    PlaybookStep(action="Check monitor address granularity", detail="A reservation tracked at larger granularity is cleared by neighbors."),
                    PlaybookStep(action="Re-run with a single master", detail="If EXOKAY appears, interference clears the reservation; if not, the monitor itself is broken."),
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
