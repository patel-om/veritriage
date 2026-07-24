"""RISC-V 'A' (atomics) extension Knowledge Pack.

Load-Reserved/Store-Conditional and atomic memory operations (AMO) with
their acquire/release ordering bits. These are the failure modes that turn a
correct-looking datapath into a broken synchronization primitive: an SC that
can never succeed (livelock), or an AMO whose ordering annotations the memory
system quietly ignores.
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

_SPEC = "RISC-V Unprivileged ISA Specification"


@register_pack
def riscv_atomics_pack() -> KnowledgePack:
    return KnowledgePack(
        id="riscv-atomics",
        name="RISC-V Atomics (A)",
        version="1.0.0",
        domain="architecture",
        summary="LR/SC reservations and AMO acquire/release ordering, and how they break.",
        concepts=[
            Concept(
                id="riscv-atomics.lr-sc",
                name="Load-Reserved / Store-Conditional",
                summary=(
                    "LR registers a reservation on an address; a subsequent SC "
                    "succeeds only if that reservation is still valid. Any store "
                    "to the reservation set, a context switch, or an intervening "
                    "trap must invalidate it. Forward progress requires that a "
                    "constrained LR/SC loop eventually succeeds; a reservation "
                    "that is lost on every attempt is a livelock, not a retry."
                ),
                markers=[r"\blr\.[wd]\b|\bsc\.[wd]\b", r"reservation", r"store[- ]conditional|load[- ]reserved"],
                references=[Reference(source=_SPEC, section="8.2", note="LR/SC and reservation sets.")],
            ),
            Concept(
                id="riscv-atomics.amo-ordering",
                name="AMO acquire/release ordering",
                summary=(
                    "Atomic memory operations carry aq (acquire) and rl (release) "
                    "bits. Acquire forbids later memory accesses from being "
                    "observed before the AMO; release forbids earlier accesses "
                    "from being observed after it. A memory system that reorders "
                    "around a .aq/.rl annotation violates the intended "
                    "synchronization even though the AMO itself is atomic."
                ),
                markers=[r"\bamo(?:add|swap|and|or|xor|min|max)\b", r"\b\.aqrl\b|\.aq\b|\.rl\b", r"acquire|release"],
                references=[Reference(source=_SPEC, section="8.1", note="AMO ordering annotations.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="reservation_valid", role="LR reservation still held", channel="LSU"),
            ProtocolSignal(name="sc_success", role="store-conditional succeeded", channel="LSU"),
            ProtocolSignal(name="amo_aqrl", role="AMO ordering annotation", channel="LSU"),
        ],
        patterns=[
            FailurePattern(
                id="riscv-atomics.sc-never-succeeds",
                name="Store-Conditional never succeeds",
                summary=(
                    "An LR/SC loop cannot make progress: the reservation is "
                    "invalidated before every SC, so SC always fails and the "
                    "hart livelocks instead of completing the atomic update."
                ),
                required=[
                    EvidenceClause(
                        name="sc always fails / reservation lost",
                        pattern=r"store[- ]conditional (?:never succeeds|always fail|failed every)|sc\.[wd].*(?:never|always fail)|reservation lost (?:before|on every)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="livelock context", pattern=r"livelock|no forward progress|retry loop"),
                ],
                typical_causes=[
                    "Reservation invalidated by an unrelated store to the same cache line (false sharing of the reservation granule)",
                    "Reservation cleared by the pipeline on speculative flushes it should have ignored",
                    "SC success condition wired to the wrong address-match comparator",
                ],
                ownership="design",
                suggested_signals=["reservation_valid", "sc_success", "reservation address"],
                playbook_id="riscv-atomics.sc-debug",
                confidence_modifiers={"rtl_bug": 0.13},
                references=[Reference(source=_SPEC, section="8.3", note="LR/SC forward-progress guarantee.")],
            ),
            FailurePattern(
                id="riscv-atomics.amo-ordering-violation",
                name="AMO acquire/release ordering violated",
                summary=(
                    "A memory operation was observed on the wrong side of an AMO "
                    "carrying an .aq or .rl annotation, so the acquire/release "
                    "ordering the software relied on was not enforced."
                ),
                required=[
                    EvidenceClause(
                        name="amo ordering violation",
                        pattern=r"amo.*ordering violation|atomic.*(?:acquire|release).*(?:violat|reorder)|\.(?:aq|rl|aqrl).*(?:not enforced|ignored|reordered)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Ordering annotation dropped between decode and the LSU",
                    "Store buffer drains around a release AMO instead of before it",
                    "Acquire barrier not applied to speculatively issued later loads",
                ],
                ownership="design",
                suggested_signals=["amo_aqrl", "store buffer drain", "load queue ordering"],
                playbook_id="riscv-atomics.amo-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="8.1", note="Ordering effect of aq/rl on AMOs.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="riscv-atomics.sc-debug",
                name="Failing store-conditional debug",
                steps=[
                    PlaybookStep(action="Capture the reservation address and the reservation-valid signal across the LR..SC window", signals=["reservation_valid"]),
                    PlaybookStep(action="Identify what clears the reservation before SC", detail="Look for stores to the same reservation granule, flushes, or traps.", signals=["reservation address"]),
                    PlaybookStep(action="Confirm the SC address-match comparator uses the reservation granule, not the exact byte address"),
                    PlaybookStep(action="Check that speculative pipeline events do not spuriously invalidate the reservation"),
                ],
            ),
            DebugPlaybook(
                id="riscv-atomics.amo-debug",
                name="AMO ordering debug",
                steps=[
                    PlaybookStep(action="Confirm the aq/rl bits survive from decode to the LSU issue point", signals=["amo_aqrl"]),
                    PlaybookStep(action="For a release violation, verify the store buffer fully drains before the AMO is globally visible", signals=["store buffer drain"]),
                    PlaybookStep(action="For an acquire violation, verify later loads are held until the AMO completes", signals=["load queue ordering"]),
                    PlaybookStep(action="Cross-check against the litmus test that exposed the reordering"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for the A extension.")],
    )
