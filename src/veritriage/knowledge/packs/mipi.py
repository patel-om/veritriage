"""MIPI CSI-2 / DSI over D-PHY Knowledge Pack.

The MIPI camera/display serial interfaces and their D-PHY physical layer:
low-power (LP) and high-speed (HS) modes, HS entry with a sync word, and
CSI-2 packet integrity (header ECC, payload CRC). The failures are an HS lane
that never synchronizes and a packet that fails its ECC/CRC.
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

_SPEC = "MIPI CSI-2 / DSI / D-PHY Specification"


@register_pack
def mipi_pack() -> KnowledgePack:
    return KnowledgePack(
        id="mipi",
        name="MIPI CSI-2 / DSI (D-PHY)",
        version="1.0.0",
        domain="protocol",
        summary="D-PHY LP/HS mode entry and CSI-2 packet ECC/CRC integrity.",
        concepts=[
            Concept(
                id="mipi.dphy",
                name="D-PHY LP/HS modes",
                summary=(
                    "D-PHY lanes idle in low-power (LP) and burst data in high-speed "
                    "(HS). HS entry is a defined LP sequence followed by a sync word "
                    "the receiver must detect to align the byte boundary; a missed "
                    "sync leaves the lane unable to receive HS data."
                ),
                markers=[r"d-?phy", r"\blp\b mode|\bhs\b mode|high[- ]speed", r"sync (?:word|sequence)|hs entry"],
                references=[Reference(source=_SPEC, section="D-PHY", note="LP/HS transitions and sync.")],
            ),
            Concept(
                id="mipi.csi2",
                name="CSI-2 packet integrity",
                summary=(
                    "CSI-2 uses short and long packets; the long-packet header is "
                    "protected by ECC (single-bit correct, double-bit detect) and the "
                    "payload by a CRC. An uncorrectable header ECC or a payload CRC "
                    "mismatch means the frame data cannot be trusted."
                ),
                markers=[r"csi-?2", r"\becc\b|packet header ecc", r"payload crc|\bcrc\b"],
                references=[Reference(source=_SPEC, section="CSI-2", note="Packet header ECC and payload CRC.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="hs_active", role="lane in high-speed mode", channel="D-PHY"),
            ProtocolSignal(name="ecc_status", role="packet header ECC result", channel="CSI-2"),
        ],
        patterns=[
            FailurePattern(
                id="mipi.hs-sync-fail",
                name="HS entry / sync word not detected",
                summary=(
                    "A D-PHY lane attempted HS entry but the receiver never detected "
                    "the sync word, so the byte boundary is not aligned and no HS data "
                    "is received."
                ),
                required=[
                    EvidenceClause(
                        name="hs sync not detected",
                        pattern=r"mipi.*(?:hs|high[- ]speed).*(?:sync|entry).*(?:fail|not)|sync (?:word|sequence).*not (?:detected|found)|lane.*hs.*(?:not|fail)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="mipi context", pattern=r"mipi|d-?phy|csi|high[- ]speed"),
                ],
                typical_causes=[
                    "LP-to-HS timing (T-HS-SETTLE) window mismatched to the receiver",
                    "Sync-word detector threshold or pattern wrong",
                    "Clock lane not in HS before data lanes attempt entry",
                ],
                ownership="design",
                suggested_signals=["hs_active", "sync detector", "clock lane state"],
                playbook_id="mipi.dphy-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="D-PHY", note="HS entry and sync detection.")],
            ),
            FailurePattern(
                id="mipi.ecc-crc-error",
                name="CSI-2 header ECC / payload CRC error",
                summary=(
                    "A CSI-2 packet failed integrity: the header ECC was "
                    "uncorrectable or the payload CRC did not match, so the packet's "
                    "data type/length or contents cannot be trusted."
                ),
                required=[
                    EvidenceClause(
                        name="packet integrity failed",
                        pattern=r"csi-?2?.*(?:ecc|crc).*(?:error|fail)|packet header ecc.*(?:error|uncorrect)|payload crc.*(?:error|mismatch)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "ECC computed over the wrong header bytes",
                    "CRC initial value or bit order incorrect",
                    "Byte misalignment from an earlier sync error shifting the payload",
                ],
                ownership="design",
                suggested_signals=["ecc_status", "CRC engine", "byte alignment"],
                playbook_id="mipi.csi-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="CSI-2", note="Header ECC and payload CRC rules.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="mipi.dphy-debug",
                name="D-PHY HS entry debug",
                steps=[
                    PlaybookStep(action="Check the LP-to-HS sequence timing against the receiver settle window", signals=["hs_active"]),
                    PlaybookStep(action="Verify the sync-word detector pattern and threshold", signals=["sync detector"]),
                    PlaybookStep(action="Confirm the clock lane is in HS before data lanes", signals=["clock lane state"]),
                    PlaybookStep(action="Look for an earlier LP escape that left the lane mis-sequenced"),
                ],
            ),
            DebugPlaybook(
                id="mipi.csi-debug",
                name="CSI-2 integrity debug",
                steps=[
                    PlaybookStep(action="Recompute the header ECC over the captured header bytes", signals=["ecc_status"]),
                    PlaybookStep(action="Check the CRC initial value and bit order", signals=["CRC engine"]),
                    PlaybookStep(action="Confirm payload byte alignment against the packet length", signals=["byte alignment"]),
                    PlaybookStep(action="Rule out an upstream sync error shifting the byte boundary"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for MIPI CSI-2/DSI/D-PHY.")],
    )
