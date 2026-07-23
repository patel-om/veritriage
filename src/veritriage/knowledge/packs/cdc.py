"""Clock Domain Crossing Knowledge Pack.

Distinct from reset sequencing (see the ``reset-clocking`` pack): this pack
covers signal crossings between asynchronous clock domains, synchronizer
methodology, and the failure signatures a crossing bug leaves in simulation
even though metastability itself is not simulatable.
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

_CDC_REF = "Clifford Cummings, \"Clock Domain Crossing (CDC) Design & Verification Techniques\" (SNUG)"


@register_pack
def cdc_pack() -> KnowledgePack:
    return KnowledgePack(
        id="cdc",
        name="Clock Domain Crossing",
        version="1.0.0",
        domain="clocking",
        summary="Synchronizer methodology, multi-bit crossing hazards, and CDC-specific failure signatures.",
        concepts=[
            Concept(
                id="cdc.synchronizer",
                name="Two-flop synchronizer",
                summary=(
                    "A single-bit signal crossing domains needs at least a "
                    "two-flop synchronizer in the destination domain to resolve "
                    "metastability before the value is used. A direct connection "
                    "(no synchronizer) is invisible in RTL simulation, since "
                    "simulators never model metastable states, and shows up only "
                    "as sporadic corruption in silicon or under gate-level timing."
                ),
                markers=[r"\bcdc\b", r"synchronizer", r"two[- ]flop|dual[- ]flop", r"metastab"],
                references=[Reference(source=_CDC_REF, note="Two-flop synchronizer methodology.")],
            ),
            Concept(
                id="cdc.multibit",
                name="Multi-bit bus crossing",
                summary=(
                    "A multi-bit value crossing domains cannot use independent "
                    "per-bit synchronizers: different bits can resolve on "
                    "different cycles, producing a transient value that was never "
                    "valid on either side. Gray coding (one bit changes per "
                    "transition) or a handshake/FIFO is required."
                ),
                markers=[r"gray[- ]cod", r"multi-?bit crossing", r"async fifo"],
                references=[Reference(source=_CDC_REF, note="Multi-bit signal and bus crossing.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="cdc.unsynchronized-crossing",
                name="Signal crossed without synchronization",
                summary=(
                    "Simulation evidence (a lint/CDC-checker message, or a "
                    "same-cycle causal relationship between domains with "
                    "different clocks) points at a signal crossing domains "
                    "without a synchronizer."
                ),
                required=[
                    EvidenceClause(
                        name="CDC violation observed",
                        pattern=r"cdc (?:violation|error|check)|unsynchronized crossing|missing synchronizer|async(?:hronous)? crossing.*(?:violat|error)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Signal routed directly between domains without any synchronizer",
                    "Synchronizer present but with insufficient stages for the target MTBF",
                    "Reset deasserts asynchronously into a domain without a reset synchronizer",
                ],
                ownership="design",
                suggested_signals=["crossing signal in both domains", "synchronizer flop chain"],
                playbook_id="cdc.crossing-audit",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_CDC_REF, note="CDC checker methodology and required structures.")],
            ),
            FailurePattern(
                id="cdc.multibit-glitch",
                name="Multi-bit crossing without gray coding or a handshake",
                summary=(
                    "A multi-bit bus crossed domains with independent bit "
                    "synchronizers instead of gray coding or a handshake/FIFO, "
                    "producing a transiently invalid combined value on the "
                    "receiving side."
                ),
                required=[
                    EvidenceClause(
                        name="multi-bit crossing issue observed",
                        pattern=r"multi-?bit crossing|bus crossing.*(?:glitch|invalid|transient)|gray cod.*(?:missing|violat)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Counter or pointer crossed domains in binary instead of Gray code",
                    "Per-bit synchronizers used on a bus instead of a qualifying handshake",
                    "FIFO pointer comparison logic assumes single-bit-change encoding that was not used",
                ],
                ownership="design",
                suggested_signals=["source/destination bus value", "pointer encoding"],
                playbook_id="cdc.multibit-audit",
                confidence_modifiers={"rtl_bug": 0.10},
                references=[Reference(source=_CDC_REF, note="Gray-coded pointers for async FIFOs.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="cdc.crossing-audit",
                name="Unsynchronized crossing audit",
                steps=[
                    PlaybookStep(action="Identify the crossing signal and both clock domains involved"),
                    PlaybookStep(action="Check for a synchronizer structure in the destination domain", signals=["synchronizer flop chain"]),
                    PlaybookStep(action="If present, count stages against the project's MTBF requirement"),
                    PlaybookStep(action="Re-run the CDC lint/structural checker on this path if not already clean"),
                ],
            ),
            DebugPlaybook(
                id="cdc.multibit-audit",
                name="Multi-bit crossing audit",
                steps=[
                    PlaybookStep(action="Identify the crossing bus and its encoding at the source", signals=["source bus value"]),
                    PlaybookStep(action="Check whether the encoding guarantees single-bit change per transition", detail="Binary counters do not; Gray code does."),
                    PlaybookStep(action="If not gray-coded, check for a handshake or FIFO structure instead"),
                    PlaybookStep(action="Compare the destination-domain value against source at each crossing edge for transient mismatches"),
                ],
            ),
        ],
        references=[Reference(source=_CDC_REF, note="Primary methodology reference for this pack.")],
    )
