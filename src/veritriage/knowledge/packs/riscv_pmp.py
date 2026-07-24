"""RISC-V Physical Memory Protection (PMP/PMA) Knowledge Pack.

PMP region configuration (pmpcfg/pmpaddr, the A field's TOR/NA4/NAPOT modes,
the L lock bit) and the PMA attributes. A PMP bug is a security bug: an access
that should fault but does not, or a region boundary decoded to the wrong
size, quietly widens what software can reach.
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

_SPEC = "RISC-V Privileged Architecture Specification"


@register_pack
def riscv_pmp_pack() -> KnowledgePack:
    return KnowledgePack(
        id="riscv-pmp",
        name="RISC-V PMP / PMA",
        version="1.0.0",
        domain="architecture",
        summary="Physical memory protection regions, NAPOT/TOR decoding, and access-fault checks.",
        concepts=[
            Concept(
                id="riscv-pmp.config",
                name="PMP region configuration",
                summary=(
                    "Each PMP entry pairs a pmpaddr with a pmpcfg byte selecting an "
                    "address-matching mode (OFF/TOR/NA4/NAPOT), R/W/X permissions, "
                    "and a lock bit L. Entries are matched in index order; the "
                    "lowest matching entry decides the access. A locked entry also "
                    "applies to M-mode and cannot be reprogrammed."
                ),
                markers=[r"\bpmp(?:cfg|addr)?\b", r"\bnapot\b|\btor\b|\bna4\b", r"lock bit|pmp lock|\bL bit\b"],
                references=[Reference(source=_SPEC, section="3.7", note="PMP registers and matching modes.")],
            ),
            Concept(
                id="riscv-pmp.checks",
                name="Access-fault checks",
                summary=(
                    "An access failing the matched entry's permissions (or matching "
                    "no entry in a mode that requires one) must raise an "
                    "access-fault exception. Silently permitting it is a protection "
                    "escape; faulting a legal access is a false denial."
                ),
                markers=[r"access[- ]fault", r"permission (?:denied|check)", r"\br/?w/?x\b|read/write/execute permission"],
                references=[Reference(source=_SPEC, section="3.7.1", note="PMP access-fault generation.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="pmp_match", role="index of matched PMP entry", channel="PMP"),
            ProtocolSignal(name="pmp_fault", role="PMP access fault raised", channel="PMP"),
        ],
        patterns=[
            FailurePattern(
                id="riscv-pmp.access-fault-missed",
                name="PMP access-fault missed",
                summary=(
                    "An access that violates the matched PMP entry's permissions "
                    "(or matches no entry where one is required) completed instead "
                    "of raising an access fault, escaping protection."
                ),
                required=[
                    EvidenceClause(
                        name="protected access allowed",
                        pattern=r"pmp.*(?:access[- ]fault|violation).*(?:not|missed|never)|access.*(?:without|no) (?:permission|w permission|x permission).*(?:allowed|completed|succeeded)|pmp check.*(?:bypassed|not applied)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="pmp context", pattern=r"\bpmp\b|access[- ]fault|permission"),
                ],
                typical_causes=[
                    "Priority-order matching picks a higher-index entry, missing a lower-index deny",
                    "Permission bits not checked for the current privilege mode",
                    "Access straddling a region boundary checked against only one entry",
                ],
                ownership="design",
                suggested_signals=["pmp_match", "pmp_fault", "current privilege mode"],
                playbook_id="riscv-pmp.fault-debug",
                confidence_modifiers={"rtl_bug": 0.13},
                references=[Reference(source=_SPEC, section="3.7.1", note="Failing accesses must fault.")],
            ),
            FailurePattern(
                id="riscv-pmp.napot-granularity",
                name="PMP NAPOT/TOR boundary decoded wrong",
                summary=(
                    "A PMP region's decoded address range does not match its "
                    "pmpaddr/pmpcfg encoding: a NAPOT size or TOR boundary is off, "
                    "so the protected region is larger or smaller than intended."
                ),
                required=[
                    EvidenceClause(
                        name="region boundary mismatch",
                        pattern=r"napot.*(?:granularity|boundary|size).*(?:wrong|incorrect|mismatch)|pmp region.*(?:size|boundary).*(?:mismatch|off|wrong)|tor.*(?:boundary|match).*(?:incorrect|wrong)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "NAPOT size derived from the wrong number of trailing pmpaddr ones",
                    "TOR upper bound compared inclusively instead of exclusively",
                    "Sub-granularity address bits not masked before the range compare",
                ],
                ownership="design",
                suggested_signals=["pmp_match", "decoded region base/size", "pmpaddr"],
                playbook_id="riscv-pmp.region-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="3.7.1", note="NAPOT/TOR address encoding.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="riscv-pmp.fault-debug",
                name="PMP access-fault debug",
                steps=[
                    PlaybookStep(action="Capture the access address, type, privilege mode, and the matched entry index", signals=["pmp_match", "current privilege mode"]),
                    PlaybookStep(action="Confirm the lowest-index matching entry is the one applied"),
                    PlaybookStep(action="Check the R/W/X permission bits of that entry against the access type", signals=["pmp_fault"]),
                    PlaybookStep(action="For boundary-straddling accesses, verify every covered entry is checked"),
                ],
            ),
            DebugPlaybook(
                id="riscv-pmp.region-debug",
                name="PMP region decode debug",
                steps=[
                    PlaybookStep(action="Compute the expected base/size from pmpaddr and the A field", signals=["pmpaddr"]),
                    PlaybookStep(action="Compare against the RTL's decoded region base/size", signals=["decoded region base/size"]),
                    PlaybookStep(action="For NAPOT, verify the trailing-ones count drives the size correctly"),
                    PlaybookStep(action="For TOR, confirm the upper bound is exclusive"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for PMP/PMA.")],
    )
