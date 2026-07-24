"""RISC-V memory consistency (RVWMO) Knowledge Pack.

The RISC-V Weak Memory Ordering model and the fences that enforce it. These
are the hardest verification failures to catch because a wrong result depends
on the interleaving of two harts; the patterns here translate a litmus-test
outcome into a concrete ordering or fence-enforcement bug.
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

_SPEC = "RISC-V Unprivileged ISA Specification (RVWMO)"


@register_pack
def riscv_memory_model_pack() -> KnowledgePack:
    return KnowledgePack(
        id="riscv-memory-model",
        name="RISC-V Memory Model (RVWMO)",
        version="1.0.0",
        domain="architecture",
        summary="RVWMO ordering rules and FENCE enforcement, and how litmus tests expose breaks.",
        concepts=[
            Concept(
                id="riscv-memory-model.rvwmo",
                name="RVWMO ordering rules",
                summary=(
                    "RVWMO defines when one hart must observe another hart's memory "
                    "accesses in program order. Same-address dependencies, syntactic "
                    "dependencies, and explicit ordering (fences, .aq/.rl) constrain "
                    "the global memory order; a load observing a value that violates "
                    "those constraints is an ordering bug, not a race."
                ),
                markers=[r"\brvwmo\b", r"memory (?:model|ordering|consistency)", r"global memory order|program order"],
                references=[Reference(source=_SPEC, section="14.1", note="RVWMO preserved program order rules.")],
            ),
            Concept(
                id="riscv-memory-model.fence",
                name="FENCE enforcement",
                summary=(
                    "FENCE orders the predecessor set of accesses before the "
                    "successor set for all harts; FENCE.I orders instruction fetch "
                    "with prior stores. A fence that a later access can bypass, or "
                    "that does not drain the store buffer, leaves the ordering "
                    "software depends on unenforced."
                ),
                markers=[r"\bfence(?:\.i)?\b", r"predecessor|successor set", r"store buffer drain"],
                references=[Reference(source=_SPEC, section="2.7", note="FENCE and FENCE.I semantics.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="store_buffer_drained", role="store buffer fully drained", channel="LSU"),
            ProtocolSignal(name="fence_active", role="fence in progress", channel="LSU"),
        ],
        patterns=[
            FailurePattern(
                id="riscv-memory-model.ordering-violation",
                name="RVWMO ordering violation",
                summary=(
                    "A litmus test observed a memory-access outcome forbidden by "
                    "RVWMO: an access was made globally visible out of the order the "
                    "model preserves."
                ),
                required=[
                    EvidenceClause(
                        name="ordering outcome forbidden",
                        pattern=r"rvwmo.*violat|memory (?:model|ordering) violation|(?:load|store).*(?:reordered|observed out of order|forbidden outcome)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="litmus context", pattern=r"litmus|two[- ]hart|program order"),
                ],
                typical_causes=[
                    "Load-load ordering to the same address not preserved (missing hazard check)",
                    "Store buffer forwarding that bypasses a required ordering dependency",
                    "Speculative load not squashed when an ordering-relevant store commits",
                ],
                ownership="design",
                suggested_signals=["store_buffer_drained", "load queue ordering", "hazard check"],
                playbook_id="riscv-memory-model.order-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="14.1", note="Preserved program order.")],
            ),
            FailurePattern(
                id="riscv-memory-model.missing-fence",
                name="FENCE not enforced",
                summary=(
                    "A FENCE (or FENCE.I) did not order the accesses around it: a "
                    "successor access was observed before the predecessor set "
                    "completed, so the barrier had no effect."
                ),
                required=[
                    EvidenceClause(
                        name="fence bypassed",
                        pattern=r"fence (?:not|never) (?:enforced|drained|effective)|missing fence|fence\.i.*(?:no|not).*(?:effect|flush)|access bypassed the fence",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Fence does not stall issue until the store buffer drains",
                    "FENCE.I fails to invalidate the instruction fetch path after a store",
                    "Predecessor/successor masks decoded from the wrong fence operand bits",
                ],
                ownership="design",
                suggested_signals=["fence_active", "store_buffer_drained", "ifetch invalidate"],
                playbook_id="riscv-memory-model.fence-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="2.7", note="FENCE ordering guarantees.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="riscv-memory-model.order-debug",
                name="Memory-ordering violation debug",
                steps=[
                    PlaybookStep(action="Reduce the failure to the minimal litmus test that reproduces it"),
                    PlaybookStep(action="Identify which preserved-program-order rule the outcome violates", detail="Map the observed values to the RVWMO ppo table."),
                    PlaybookStep(action="Trace the load/store queue to find where the reordering became visible", signals=["load queue ordering"]),
                    PlaybookStep(action="Check store-buffer forwarding for a bypass of the required dependency"),
                ],
            ),
            DebugPlaybook(
                id="riscv-memory-model.fence-debug",
                name="Fence enforcement debug",
                steps=[
                    PlaybookStep(action="Confirm the fence stalls younger accesses until the predecessor set completes", signals=["fence_active"]),
                    PlaybookStep(action="Verify the store buffer fully drains before successors are released", signals=["store_buffer_drained"]),
                    PlaybookStep(action="For FENCE.I, confirm the fetch path is invalidated after prior stores", signals=["ifetch invalidate"]),
                    PlaybookStep(action="Check the predecessor/successor bit decode against the fence encoding"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for RVWMO and fences.")],
    )
