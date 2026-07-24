"""USB (2.0 / 3.x) Knowledge Pack.

The USB transaction model (token/data/handshake packets) and the USB3 link
layer (LTSSM training through Polling and Recovery). The failures are a
transaction that never gets its handshake and a link that cannot finish
training.
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

_SPEC = "Universal Serial Bus Specification"


@register_pack
def usb_pack() -> KnowledgePack:
    return KnowledgePack(
        id="usb",
        name="USB (2.0 / 3.x)",
        version="1.0.0",
        domain="protocol",
        summary="USB transaction handshakes and USB3 LTSSM link training.",
        concepts=[
            Concept(
                id="usb.transaction",
                name="Transaction handshakes",
                summary=(
                    "A USB transaction is a token packet, an optional data packet, "
                    "and a handshake (ACK/NAK/STALL/NYET). Every data phase that "
                    "expects a handshake must receive one; a missing handshake stalls "
                    "the endpoint and eventually times out."
                ),
                markers=[r"\busb\b", r"\back\b|\bnak\b|\bstall\b|\bnyet\b", r"token|data packet|handshake"],
                references=[Reference(source=_SPEC, section="Protocol", note="Transaction packet sequence.")],
            ),
            Concept(
                id="usb.ltssm",
                name="USB3 link training (LTSSM)",
                summary=(
                    "The USB3 Link Training and Status State Machine brings the link "
                    "up through Polling and can fall into Recovery to re-establish it. "
                    "An LTSSM that loops in Recovery or never completes Polling never "
                    "reaches U0 (operational)."
                ),
                markers=[r"\bltssm\b", r"polling|recovery|\bu0\b|\bu1\b|\bu2\b|\bu3\b", r"link training"],
                references=[Reference(source=_SPEC, section="Link Layer", note="LTSSM states and transitions.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="handshake_pid", role="handshake packet id", channel="USB"),
            ProtocolSignal(name="ltssm_state", role="USB3 LTSSM state", channel="USB3"),
        ],
        patterns=[
            FailurePattern(
                id="usb.handshake-missing",
                name="Transaction handshake missing",
                summary=(
                    "A data phase that expected a handshake never received an "
                    "ACK/NAK, so the endpoint stalls waiting for the transaction to "
                    "complete."
                ),
                required=[
                    EvidenceClause(
                        name="no handshake returned",
                        pattern=r"usb.*(?:ack|nak|handshake).*(?:missing|never)|no handshake.*(?:packet|transaction)|data packet.*no (?:ack|response|handshake)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="usb context", pattern=r"\busb\b|endpoint|token|handshake"),
                ],
                typical_causes=[
                    "Endpoint FSM does not emit a handshake for a valid data phase",
                    "CRC check result gates the handshake incorrectly",
                    "Handshake dropped by the SIE under a specific packet boundary",
                ],
                ownership="design",
                suggested_signals=["handshake_pid", "endpoint FSM", "CRC status"],
                playbook_id="usb.transaction-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="Protocol", note="Handshake follows the data phase.")],
            ),
            FailurePattern(
                id="usb.ltssm-stuck",
                name="USB3 LTSSM never reaches U0",
                summary=(
                    "The USB3 link never trained to U0: the LTSSM looped in Recovery "
                    "or never completed Polling, so the link is not operational."
                ),
                required=[
                    EvidenceClause(
                        name="ltssm training stuck",
                        pattern=r"usb3?.*(?:ltssm|link training).*(?:stuck|fail)|polling.*(?:stuck|timeout|never complet)|recovery.*(?:loop|stuck)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Training sequence (TS1/TS2) detection thresholds never satisfied",
                    "Recovery entry condition retriggers before Polling completes",
                    "Receiver detection or equalization never converges",
                ],
                ownership="design",
                suggested_signals=["ltssm_state", "training sequence detect", "link partner status"],
                playbook_id="usb.ltssm-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="Link Layer", note="Polling/Recovery to U0.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="usb.transaction-debug",
                name="USB transaction debug",
                steps=[
                    PlaybookStep(action="Identify the data phase missing its handshake and the endpoint", signals=["endpoint FSM"]),
                    PlaybookStep(action="Confirm the endpoint FSM emits a handshake for a valid data phase"),
                    PlaybookStep(action="Check the CRC status gating the handshake", signals=["CRC status"]),
                    PlaybookStep(action="Look for a packet-boundary case where the SIE drops the handshake"),
                ],
            ),
            DebugPlaybook(
                id="usb.ltssm-debug",
                name="USB3 LTSSM debug",
                steps=[
                    PlaybookStep(action="Trace the LTSSM state sequence and where it loops or stalls", signals=["ltssm_state"]),
                    PlaybookStep(action="Check TS1/TS2 detection thresholds", signals=["training sequence detect"]),
                    PlaybookStep(action="Confirm Recovery entry does not retrigger before Polling completes"),
                    PlaybookStep(action="Verify receiver detection/equalization convergence"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for USB.")],
    )
