"""RISC-V interrupt architecture Knowledge Pack.

CLINT timer/software interrupts, the PLIC priority/claim/complete protocol,
and AIA (IMSIC/APLIC) message-signalled interrupts. These are the control
failures that leave an interrupt stuck pending, service them in the wrong
order, or take one that masking should have blocked.
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

_SPEC = "RISC-V PLIC / Advanced Interrupt Architecture Specification"


@register_pack
def riscv_interrupts_pack() -> KnowledgePack:
    return KnowledgePack(
        id="riscv-interrupts",
        name="RISC-V Interrupts (CLINT/PLIC/AIA)",
        version="1.0.0",
        domain="architecture",
        summary="Interrupt priority, the PLIC claim/complete handshake, and mie/mip masking.",
        concepts=[
            Concept(
                id="riscv-interrupts.plic",
                name="PLIC priority and claim/complete",
                summary=(
                    "The PLIC arbitrates external interrupt sources by priority and "
                    "threshold. A hart claims the highest-priority pending source by "
                    "reading the claim register, services it, then writes the same id "
                    "to complete, which clears the gateway. Missing either half leaves "
                    "the source stuck pending or lets it re-fire."
                ),
                markers=[r"\bplic\b", r"claim|complete", r"priority|threshold", r"gateway"],
                references=[Reference(source=_SPEC, section="PLIC 2", note="Interrupt priorities and claim/complete.")],
            ),
            Concept(
                id="riscv-interrupts.masking",
                name="Interrupt enable/pending masking",
                summary=(
                    "An interrupt is taken only when it is enabled (mie/sie plus the "
                    "per-cause mie bit), pending (mip), and the global interrupt-enable "
                    "for the mode is set. Taking a masked interrupt, or ignoring an "
                    "enabled pending one, breaks the interrupt-delivery contract."
                ),
                markers=[r"\bmie\b|\bmip\b|\bsie\b|\bsip\b", r"interrupt (?:enable|pending|masked)", r"global interrupt[- ]enable|\bmstatus\.mie\b"],
                references=[Reference(source=_SPEC, section="AIA 3", note="Interrupt enable and pending semantics.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="plic_claim", role="claimed interrupt id", channel="PLIC"),
            ProtocolSignal(name="plic_complete", role="completed interrupt id", channel="PLIC"),
            ProtocolSignal(name="mip", role="machine interrupt pending", channel="CSR"),
            ProtocolSignal(name="mie", role="machine interrupt enable", channel="CSR"),
        ],
        state_machines=[
            StateMachine(
                id="riscv-interrupts.plic-lifecycle",
                name="PLIC interrupt lifecycle",
                states=[
                    ProtocolState(name="Pending", description="Source asserted; gateway latched pending.", markers=[r"interrupt pending|source pending|gateway (?:latched|pending)"]),
                    ProtocolState(name="Claimed", description="Hart read the claim register for the highest-priority source.", markers=[r"claim (?:read|register)|interrupt claimed"]),
                    ProtocolState(name="Serviced", description="Handler ran for the claimed source.", markers=[r"handler (?:ran|serviced)|servicing interrupt"]),
                    ProtocolState(name="Completed", description="Complete written; gateway cleared.", markers=[r"complete (?:written|register)|gateway cleared|interrupt completed"]),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="riscv-interrupts.plic-priority-inversion",
                name="PLIC priority inversion",
                summary=(
                    "The PLIC granted a lower-priority interrupt while a "
                    "higher-priority source above threshold was pending, so the "
                    "wrong source was claimed first."
                ),
                required=[
                    EvidenceClause(
                        name="lower priority claimed first",
                        pattern=r"priority inversion|lower[- ]priority interrupt.*(?:before|serviced first|claimed first)|plic.*priority.*(?:wrong|violat)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="plic context", pattern=r"\bplic\b|claim|priority|threshold"),
                ],
                typical_causes=[
                    "Priority comparator tree resolves ties or magnitudes incorrectly",
                    "Threshold applied per-source instead of per-target context",
                    "Pending bit for the higher-priority source latched a cycle late",
                ],
                ownership="design",
                suggested_signals=["plic_claim", "source priority", "threshold"],
                playbook_id="riscv-interrupts.plic-debug",
                confidence_modifiers={"rtl_bug": 0.13},
                references=[Reference(source=_SPEC, section="PLIC 2", note="Highest-priority pending source is claimed.")],
            ),
            FailurePattern(
                id="riscv-interrupts.missed-claim-complete",
                name="PLIC claim/complete broken",
                summary=(
                    "The claim/complete handshake did not clear the gateway: the "
                    "interrupt stays pending after completion, or the source cannot "
                    "re-arm, stalling interrupt delivery."
                ),
                required=[
                    EvidenceClause(
                        name="interrupt stuck pending",
                        pattern=r"interrupt (?:stuck|remains|still) pending|claim/complete.*(?:broken|missed)|gateway not cleared|complete.*(?:no effect|ignored)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Complete write not matched against the claimed id, so the gateway never clears",
                    "Edge-triggered gateway not re-armed after completion",
                    "Claim register returns an id but does not deassert the pending bit",
                ],
                ownership="design",
                suggested_signals=["plic_claim", "plic_complete", "gateway state"],
                playbook_id="riscv-interrupts.plic-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="PLIC 2", note="Completion clears the gateway.")],
            ),
            FailurePattern(
                id="riscv-interrupts.mip-mie-mismatch",
                name="Interrupt taken while masked",
                summary=(
                    "An interrupt was trapped even though its enable was clear (or "
                    "the global mode interrupt-enable was off), violating the "
                    "mie/mip masking rules."
                ),
                required=[
                    EvidenceClause(
                        name="masked interrupt taken",
                        pattern=r"interrupt taken (?:while|despite).*(?:masked|disabled)|mie.*(?:clear|disabled).*(?:but|yet).*(?:trapped|taken)|masked interrupt.*(?:trapped|taken)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Interrupt-taken logic samples a stale mie/mstatus.MIE value",
                    "Per-cause enable bit indexed incorrectly",
                    "Global interrupt-enable for the mode not ANDed into the delivery condition",
                ],
                ownership="design",
                suggested_signals=["mie", "mip", "mstatus.MIE"],
                playbook_id="riscv-interrupts.mask-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="AIA 3", note="Interrupt delivery requires enable and pending.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="riscv-interrupts.plic-debug",
                name="PLIC priority / claim-complete debug",
                steps=[
                    PlaybookStep(action="List pending sources with their priorities and the target threshold at the failing cycle", signals=["source priority", "threshold"]),
                    PlaybookStep(action="Confirm the claim returned the highest-priority source above threshold", signals=["plic_claim"]),
                    PlaybookStep(action="Match the complete write id against the claimed id and check the gateway clears", signals=["plic_complete", "gateway state"]),
                    PlaybookStep(action="For edge sources, verify the gateway re-arms after completion"),
                ],
            ),
            DebugPlaybook(
                id="riscv-interrupts.mask-debug",
                name="Interrupt masking debug",
                steps=[
                    PlaybookStep(action="Sample mie, mip, and mstatus.MIE at the interrupt-taken cycle", signals=["mie", "mip", "mstatus.MIE"]),
                    PlaybookStep(action="Confirm the delivery condition ANDs pending, per-cause enable, and global enable"),
                    PlaybookStep(action="Check the per-cause enable indexing against the interrupt cause"),
                    PlaybookStep(action="Verify no stale CSR value is used due to a pipeline read hazard"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for the interrupt architecture.")],
    )
