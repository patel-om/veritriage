"""Ethernet MAC / PCS Knowledge Pack.

The MAC frame (preamble, SFD, header, payload, FCS) and the PCS sublayer
(64b/66b encoding, block lock, alignment). The failures are a frame whose FCS
does not check and a PCS that loses block lock, both of which drop the link's
usable data.
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

_SPEC = "IEEE 802.3 Ethernet Standard"


@register_pack
def ethernet_pack() -> KnowledgePack:
    return KnowledgePack(
        id="ethernet",
        name="Ethernet MAC / PCS",
        version="1.0.0",
        domain="protocol",
        summary="Ethernet MAC framing/FCS and PCS 64b/66b block lock.",
        concepts=[
            Concept(
                id="ethernet.mac",
                name="MAC framing and FCS",
                summary=(
                    "A MAC frame begins with preamble and SFD, carries addresses, "
                    "length/type, and payload, and ends with a 32-bit FCS (CRC) over "
                    "the frame. A receiver whose recomputed FCS does not match the "
                    "received one must drop the frame as corrupt."
                ),
                markers=[r"\bmac\b frame|ethernet frame", r"\bfcs\b|frame check sequence", r"preamble|\bsfd\b"],
                references=[Reference(source=_SPEC, section="MAC", note="Frame format and FCS.")],
            ),
            Concept(
                id="ethernet.pcs",
                name="PCS 64b/66b block lock",
                summary=(
                    "The PCS encodes data as 64b/66b blocks with a two-bit sync "
                    "header; the receiver achieves block lock by finding valid sync "
                    "headers. Losing block lock, or never achieving alignment across "
                    "lanes, breaks the link's ability to recover data."
                ),
                markers=[r"\bpcs\b", r"64b/66b|block lock|sync header", r"alignment|lane align"],
                references=[Reference(source=_SPEC, section="PCS", note="64b/66b block lock and alignment.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="fcs_ok", role="frame FCS check result", channel="MAC"),
            ProtocolSignal(name="block_lock", role="PCS block lock status", channel="PCS"),
        ],
        patterns=[
            FailurePattern(
                id="ethernet.fcs-error",
                name="Frame FCS mismatch",
                summary=(
                    "A received frame's recomputed FCS did not match the transmitted "
                    "value, so the frame is corrupt and must be dropped; a systematic "
                    "FCS error points at the datapath, not the medium."
                ),
                required=[
                    EvidenceClause(
                        name="fcs check failed",
                        pattern=r"fcs (?:error|mismatch|fail)|crc.*(?:error|mismatch).*frame|frame check sequence.*(?:fail|mismatch)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="ethernet context", pattern=r"ethernet|\bmac\b|\bfcs\b|frame"),
                ],
                typical_causes=[
                    "CRC polynomial or bit order wrong in the FCS engine",
                    "Payload byte inserted/dropped before the FCS is computed",
                    "FCS computed over the wrong frame span (includes or excludes a field)",
                ],
                ownership="design",
                suggested_signals=["fcs_ok", "CRC engine", "frame byte count"],
                playbook_id="ethernet.mac-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="MAC", note="FCS coverage and computation.")],
            ),
            FailurePattern(
                id="ethernet.block-lock-lost",
                name="PCS block lock lost",
                summary=(
                    "The PCS lost 64b/66b block lock (or never achieved lane "
                    "alignment), so the receiver can no longer delineate blocks and "
                    "the link drops data."
                ),
                required=[
                    EvidenceClause(
                        name="block lock lost",
                        pattern=r"block lock (?:lost|not achieved)|pcs.*(?:align|lock).*(?:lost|fail)|64b/66b.*(?:sync|lock).*(?:lost|fail)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Sync-header validation state machine too sensitive to a single bad block",
                    "Descrambler seeded incorrectly after a rate change",
                    "Lane deskew unable to align within its buffer depth",
                ],
                ownership="design",
                suggested_signals=["block_lock", "sync header validity", "lane deskew"],
                playbook_id="ethernet.pcs-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="PCS", note="Block lock state machine.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="ethernet.mac-debug",
                name="MAC FCS debug",
                steps=[
                    PlaybookStep(action="Recompute the FCS offline over the captured frame and compare", signals=["fcs_ok"]),
                    PlaybookStep(action="Check the CRC polynomial and bit ordering in the FCS engine", signals=["CRC engine"]),
                    PlaybookStep(action="Verify no byte is inserted or dropped before FCS computation", signals=["frame byte count"]),
                    PlaybookStep(action="Confirm the FCS spans exactly the required fields"),
                ],
            ),
            DebugPlaybook(
                id="ethernet.pcs-debug",
                name="PCS block-lock debug",
                steps=[
                    PlaybookStep(action="Trace the sync-header validity leading up to lock loss", signals=["sync header validity"]),
                    PlaybookStep(action="Check the block-lock state machine's tolerance to isolated errors", signals=["block_lock"]),
                    PlaybookStep(action="Verify the descrambler seed after any rate change"),
                    PlaybookStep(action="Confirm lane deskew fits within the buffer depth", signals=["lane deskew"]),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for Ethernet MAC/PCS.")],
    )
