"""Universal Chiplet Interconnect Express (UCIe) Knowledge Pack.

The die-to-die interconnect for chiplet designs: a link bring-up sequence
over the main-band and sideband, lane repair/mapping to tolerate defective
bumps, and flit-level transport. The failures are bring-up (training stuck)
and resilience (lane repair unable to recover a degraded link).
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

_SPEC = "UCIe (Universal Chiplet Interconnect Express) Specification"


@register_pack
def ucie_pack() -> KnowledgePack:
    return KnowledgePack(
        id="ucie",
        name="UCIe die-to-die",
        version="1.0.0",
        domain="interconnect",
        summary="UCIe link bring-up, sideband handshakes, and lane repair/degrade.",
        concepts=[
            Concept(
                id="ucie.bringup",
                name="Link bring-up and sideband",
                summary=(
                    "A UCIe link trains through a defined sequence coordinated over "
                    "the always-on sideband: parameter exchange, calibration, and "
                    "main-band training. The sideband handshake gates each stage; a "
                    "missing sideband acknowledge stalls bring-up before the "
                    "main-band is usable."
                ),
                markers=[r"\bucie\b", r"sideband", r"link (?:training|bring[- ]?up)|main[- ]?band"],
                references=[Reference(source=_SPEC, section="Link Init", note="Bring-up sequence and sideband handshakes.")],
            ),
            Concept(
                id="ucie.lane-repair",
                name="Lane repair and mapping",
                summary=(
                    "UCIe tolerates defective bumps by remapping data to spare lanes "
                    "(repair) or by running at reduced width (degrade). Repair "
                    "resources are finite; if a link has more faulty lanes than "
                    "spares and cannot degrade, bring-up must fail cleanly rather "
                    "than run corrupt."
                ),
                markers=[r"lane (?:repair|remap|map)", r"spare lane|redundan(?:t|cy) lane", r"(?:width )?degrade|reduced width"],
                references=[Reference(source=_SPEC, section="Lane Repair", note="Lane repair and width degrade.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="sb_ack", role="sideband acknowledge", channel="sideband"),
            ProtocolSignal(name="link_state", role="UCIe link training state", channel="mainband"),
            ProtocolSignal(name="lane_map", role="active lane mapping", channel="mainband"),
        ],
        patterns=[
            FailurePattern(
                id="ucie.link-training-stuck",
                name="UCIe link training stuck",
                summary=(
                    "The die-to-die link never completed bring-up: a training stage "
                    "did not advance, typically because a sideband handshake was "
                    "never acknowledged."
                ),
                required=[
                    EvidenceClause(
                        name="training never advances",
                        pattern=r"ucie.*(?:link training|bring[- ]?up).*(?:stuck|fail|timeout)|die[- ]to[- ]die.*training.*(?:stuck|fail)|sideband.*(?:no|not|never).*(?:handshake|ack)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="ucie context", pattern=r"\bucie\b|sideband|die[- ]to[- ]die"),
                ],
                typical_causes=[
                    "Sideband acknowledge for a stage never returns (clocking or reset skew across dies)",
                    "Parameter exchange disagreement leaves the FSMs in different states",
                    "Main-band calibration fails to converge and never signals done",
                ],
                ownership="design",
                suggested_signals=["sb_ack", "link_state", "parameter exchange"],
                playbook_id="ucie.bringup-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="Link Init", note="Sideband gates each training stage.")],
            ),
            FailurePattern(
                id="ucie.lane-repair-failed",
                name="Lane repair/degrade failed",
                summary=(
                    "A faulty lane could not be recovered: repair resources were "
                    "exhausted or width degrade did not engage, so the link either "
                    "brought up corrupt or failed without a clean fallback."
                ),
                required=[
                    EvidenceClause(
                        name="repair unable to recover",
                        pattern=r"lane repair (?:fail|exhausted|insufficient)|lane (?:degrade|remap).*fail|faulty lane.*not (?:repaired|remapped|degraded)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "More faulty lanes than available spares, with no degrade path taken",
                    "Repair mux control programmed with a stale defect map",
                    "Degrade negotiated to a width the other die did not accept",
                ],
                ownership="design",
                suggested_signals=["lane_map", "spare lane count", "defect map"],
                playbook_id="ucie.repair-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="Lane Repair", note="Repair resources are finite; degrade must be clean.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="ucie.bringup-debug",
                name="UCIe bring-up debug",
                steps=[
                    PlaybookStep(action="Identify the training stage that never advanced", signals=["link_state"]),
                    PlaybookStep(action="Check the sideband handshake for that stage on both dies", signals=["sb_ack"]),
                    PlaybookStep(action="Compare the exchanged parameters for a disagreement", signals=["parameter exchange"]),
                    PlaybookStep(action="For a calibration stall, verify the convergence/done signaling"),
                ],
            ),
            DebugPlaybook(
                id="ucie.repair-debug",
                name="UCIe lane repair debug",
                steps=[
                    PlaybookStep(action="Read the defect map and count faulty lanes vs available spares", signals=["defect map", "spare lane count"]),
                    PlaybookStep(action="Confirm the repair mux control matches the current defect map", signals=["lane_map"]),
                    PlaybookStep(action="If spares are exhausted, verify the degrade path engages"),
                    PlaybookStep(action="Check the degraded width is one the partner die accepted"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for UCIe die-to-die.")],
    )
