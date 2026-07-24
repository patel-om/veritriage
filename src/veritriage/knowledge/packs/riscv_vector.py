"""RISC-V 'V' (vector) extension Knowledge Pack.

Vector configuration (vsetvl/vtype/vl), tail and mask policies, and the
element-count contract. Vector bugs rarely announce themselves as a crash;
they corrupt a subset of elements or silently accept an illegal
configuration, which is exactly what these patterns pin down.
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

_SPEC = "RISC-V Vector Extension Specification"


@register_pack
def riscv_vector_pack() -> KnowledgePack:
    return KnowledgePack(
        id="riscv-vector",
        name="RISC-V Vector (V)",
        version="1.0.0",
        domain="architecture",
        summary="Vector configuration, tail/mask policies, and the vl element-count contract.",
        concepts=[
            Concept(
                id="riscv-vector.config",
                name="Vector configuration (vsetvl/vtype/vl)",
                summary=(
                    "vsetvl{i} sets vtype (SEW, LMUL, tail/mask policy) and returns "
                    "the granted vector length vl. A reserved or unsupported SEW/LMUL "
                    "combination must set vtype.vill and force vl to zero rather than "
                    "execute with an undefined configuration."
                ),
                markers=[r"\bvsetvl\b|\bvsetvli\b|\bvtype\b", r"\bsew\b|\blmul\b", r"\bvill\b"],
                references=[Reference(source=_SPEC, section="6", note="Configuration-setting instructions.")],
            ),
            Concept(
                id="riscv-vector.tail-mask",
                name="Tail and mask policies",
                summary=(
                    "Elements past vl (the tail) and elements disabled by the mask "
                    "(inactive body elements) follow the agnostic/undisturbed policy "
                    "in vtype. Undisturbed means those destination elements must keep "
                    "their prior value; writing them is a correctness violation."
                ),
                markers=[r"tail[- ](?:agnostic|undisturbed)|\bta\b|\btu\b", r"mask[- ](?:agnostic|undisturbed)|\bma\b|\bmu\b", r"inactive element"],
                references=[Reference(source=_SPEC, section="5.4", note="Tail and mask agnostic/undisturbed policies.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="vtype", role="vector type configuration", channel="CSR"),
            ProtocolSignal(name="vl", role="active vector length", channel="CSR"),
            ProtocolSignal(name="vill", role="illegal configuration flag", channel="CSR"),
            ProtocolSignal(name="vmask", role="per-element mask", channel="VRF"),
        ],
        state_machines=[
            StateMachine(
                id="riscv-vector.instr-lifecycle",
                name="Vector instruction lifecycle",
                states=[
                    ProtocolState(name="Configured", description="vtype/vl set by vsetvl.", markers=[r"\bvsetvl", r"vtype (?:set|written)"]),
                    ProtocolState(name="Operands read", description="Vector register operands read from the VRF.", markers=[r"vector operands? read|vrf read"]),
                    ProtocolState(name="Executed", description="Element operations performed under mask.", markers=[r"vector (?:op|execute)|element operation"]),
                    ProtocolState(name="Written back", description="Active elements written; tail/masked follow policy.", markers=[r"vector writeback|elements? written back"]),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="riscv-vector.illegal-vtype",
                name="Illegal vtype not flagged",
                summary=(
                    "vsetvl was given a reserved or unsupported SEW/LMUL "
                    "combination but vtype.vill was not set, so the core executed "
                    "vector instructions with an undefined configuration."
                ),
                required=[
                    EvidenceClause(
                        name="illegal vtype accepted",
                        pattern=r"vill (?:not set|was not|missing)|illegal vtype (?:accepted|not flagged)|reserved (?:sew|lmul).*(?:accepted|not flagged)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="vset context", pattern=r"\bvsetvl|\bvtype\b|\bsew\b|\blmul\b"),
                ],
                typical_causes=[
                    "vill decode table missing a reserved SEW/LMUL combination",
                    "vl not forced to zero when vill should assert",
                    "Custom LMUL fraction not covered by the legality check",
                ],
                ownership="design",
                suggested_signals=["vtype", "vill", "vl"],
                playbook_id="riscv-vector.config-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="6.3", note="vill and reserved vtype encodings.")],
            ),
            FailurePattern(
                id="riscv-vector.tail-mask-corruption",
                name="Tail/mask undisturbed policy violated",
                summary=(
                    "Destination elements that the undisturbed policy requires to "
                    "keep their prior value (tail elements past vl, or mask-inactive "
                    "body elements) were overwritten."
                ),
                required=[
                    EvidenceClause(
                        name="inactive elements modified",
                        pattern=r"(?:tail|mask)[- ]undisturbed.*(?:violat|corrupt)|inactive element.*(?:modified|written|corrupt)|masked elements? (?:modified|overwritten)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Write-enable for the destination VRF ignores the mask bits",
                    "Tail elements written because the vl boundary is off by one",
                    "Agnostic vs undisturbed policy bit sampled from the wrong vtype",
                ],
                ownership="design",
                suggested_signals=["vmask", "vl", "VRF write enable"],
                playbook_id="riscv-vector.policy-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="5.4", note="Undisturbed elements must be preserved.")],
            ),
            FailurePattern(
                id="riscv-vector.vl-mismatch",
                name="Effective vector length mismatch",
                summary=(
                    "A vector instruction operated on a different number of "
                    "elements than the vl granted by vsetvl, processing too many "
                    "or too few elements."
                ),
                required=[
                    EvidenceClause(
                        name="vl element-count mismatch",
                        pattern=r"vector length mismatch|\bvl\b.*(?:mismatch|incorrect)|element count.*(?:mismatch|exceed|short)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Element counter compares against a stale vl from a previous vsetvl",
                    "LMUL grouping miscomputed, changing the effective element count",
                    "vstart not honored on a resumed vector instruction",
                ],
                ownership="design",
                suggested_signals=["vl", "vtype", "element counter"],
                playbook_id="riscv-vector.config-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="6.2", note="vl semantics and element processing.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="riscv-vector.config-debug",
                name="Vector configuration debug",
                steps=[
                    PlaybookStep(action="Dump vtype and vl at the failing instruction and compare to the vsetvl inputs", signals=["vtype", "vl"]),
                    PlaybookStep(action="Check the vill legality table for the exact SEW/LMUL encoding", signals=["vill"]),
                    PlaybookStep(action="Confirm vl is forced to zero whenever vill is set"),
                    PlaybookStep(action="Verify the element counter samples the current vl, not a stale value"),
                ],
            ),
            DebugPlaybook(
                id="riscv-vector.policy-debug",
                name="Tail/mask policy debug",
                steps=[
                    PlaybookStep(action="Identify which destination elements were incorrectly written", signals=["VRF write enable"]),
                    PlaybookStep(action="Confirm the VRF write-enable includes the per-element mask", signals=["vmask"]),
                    PlaybookStep(action="Check the vl boundary comparison for an off-by-one on the tail", signals=["vl"]),
                    PlaybookStep(action="Verify the undisturbed/agnostic policy bit is read from the active vtype"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for the V extension.")],
    )
