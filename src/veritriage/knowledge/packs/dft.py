"""Design-for-Test (DFT) Knowledge Pack.

Scan-based test and memory BIST: scan-chain integrity (shift/capture) and
MBIST signatures. DFT failures block manufacturing test and often surface in
simulation as a scan miscompare or a BIST failure signature.
"""

from __future__ import annotations

from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    PlaybookStep,
    Reference,
)
from veritriage.knowledge.registry import register_pack

_SPEC = "Design-for-Test (scan / MBIST) methodology"


@register_pack
def dft_pack() -> KnowledgePack:
    return KnowledgePack(
        id="dft",
        name="Design-for-Test (scan / MBIST)",
        version="1.0.0",
        domain="dft",
        summary="Scan-chain integrity and memory BIST failure signatures.",
        concepts=[
            Concept(
                id="dft.scan",
                name="Scan chains",
                summary=(
                    "In shift mode, flops form scan chains loaded and unloaded serially; "
                    "in capture mode they sample functional logic. Chain integrity "
                    "requires the shifted-out pattern to match the shifted-in one; a "
                    "broken or wrong-length chain miscompares."
                ),
                markers=[r"scan (?:chain|shift|capture)", r"scan[- ]?in|scan[- ]?out|\bsi\b|\bso\b", r"miscompare|shift mode|capture mode"],
                references=[Reference(source=_SPEC, section="Scan", note="Scan shift/capture integrity.")],
            ),
            Concept(
                id="dft.mbist",
                name="Memory BIST",
                summary=(
                    "MBIST runs march algorithms against embedded memories and "
                    "compares against an expected signature (often MISR-compressed). "
                    "A signature miscompare or a per-cell fail flags a defective or "
                    "mis-modeled memory."
                ),
                markers=[r"\bmbist\b|memory bist", r"march|\bmisr\b|signature", r"bist (?:fail|done|status)"],
                references=[Reference(source=_SPEC, section="MBIST", note="March test and signature compare.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="dft.scan-chain-broken",
                name="Scan chain integrity failure",
                summary=(
                    "A scan chain did not shift cleanly: the unloaded pattern did not "
                    "match the loaded one, or the chain length was wrong, so the chain "
                    "is broken or misconfigured."
                ),
                required=[
                    EvidenceClause(
                        name="scan miscompare",
                        pattern=r"scan chain.*(?:broken|integrity|length).*(?:fail|mismatch)|scan.*(?:stuck|miscompare)|shift.*scan.*(?:mismatch|fail)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="dft context", pattern=r"scan|\bdft\b|shift mode"),
                ],
                typical_causes=[
                    "A flop not on the scan chain (clock or scan-enable not connected)",
                    "Chain reordered without updating the expected length",
                    "Scan-enable timing lets a capture corrupt the shift",
                ],
                ownership="design",
                suggested_signals=["scan_out", "scan_enable", "chain length"],
                playbook_id="dft.scan-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="Scan", note="Shifted-out must match shifted-in.")],
            ),
            FailurePattern(
                id="dft.mbist-failure",
                name="MBIST signature miscompare",
                summary=(
                    "Memory BIST reported a failure: the computed signature did not "
                    "match the expected one, or a march step miscompared, indicating "
                    "a defective or mis-modeled memory."
                ),
                required=[
                    EvidenceClause(
                        name="bist failed",
                        pattern=r"mbist.*(?:fail|error|fault)|memory bist.*(?:fail|detected)|bist.*(?:signature|misr).*(?:miscompare|mismatch)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Genuine memory defect the march algorithm caught",
                    "BIST wrapper addressing or data path miswired",
                    "Expected signature computed for the wrong memory configuration",
                ],
                ownership="design",
                suggested_signals=["bist_done", "bist_fail", "signature"],
                playbook_id="dft.mbist-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="MBIST", note="Signature compare semantics.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="dft.scan-debug",
                name="Scan chain debug",
                steps=[
                    PlaybookStep(action="Compare the shifted-out vector to the shifted-in vector bit by bit", signals=["scan_out"]),
                    PlaybookStep(action="Confirm every intended flop is on the chain (clock, scan-enable connected)", signals=["scan_enable"]),
                    PlaybookStep(action="Check the expected chain length against the actual", signals=["chain length"]),
                    PlaybookStep(action="Verify scan-enable timing does not let capture corrupt the shift"),
                ],
            ),
            DebugPlaybook(
                id="dft.mbist-debug",
                name="MBIST debug",
                steps=[
                    PlaybookStep(action="Read the BIST status and the failing address/step", signals=["bist_fail"]),
                    PlaybookStep(action="Confirm the expected signature matches the memory configuration", signals=["signature"]),
                    PlaybookStep(action="Check the BIST wrapper address and data connections"),
                    PlaybookStep(action="Correlate with the march algorithm to classify the fault"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for DFT scan/MBIST.")],
    )
