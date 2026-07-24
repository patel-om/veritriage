"""Low-power / UPF Knowledge Pack.

Power-domain sequencing as defined by a UPF power intent: isolation of
signals crossing a boundary, state retention across a power cycle, and the
On -> Isolate -> Retain -> Off lifecycle. These are a distinct failure class
from ordinary reset sequencing, and the pack carries the power-domain state
machine that makes 'where did the sequence stop?' answerable.
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

_SPEC = "IEEE 1801 (UPF) Unified Power Format"


@register_pack
def low_power_pack() -> KnowledgePack:
    return KnowledgePack(
        id="low-power",
        name="Low-power / UPF",
        version="1.0.0",
        domain="low-power",
        summary="Power-domain isolation, retention, and the power-down/up sequence.",
        concepts=[
            Concept(
                id="low-power.isolation",
                name="Isolation",
                summary=(
                    "Signals leaving a power domain that will shut down must be "
                    "clamped by isolation cells to a defined value before power-off, "
                    "so a powered-on receiver does not sample a floating output. "
                    "Isolation must be enabled before, and released after, the domain "
                    "is powered."
                ),
                markers=[r"isolation", r"clamp|isolation cell", r"power (?:domain|down|off)"],
                references=[Reference(source=_SPEC, section="Isolation", note="Isolation cell strategy.")],
            ),
            Concept(
                id="low-power.retention",
                name="State retention",
                summary=(
                    "Retention registers preserve selected state across a power-off "
                    "using an always-on supply; save happens before power-down and "
                    "restore after power-up. A retention control mis-sequenced against "
                    "the power switch loses or corrupts the retained state."
                ),
                markers=[r"retention", r"save|restore", r"always[- ]on|retention register"],
                references=[Reference(source=_SPEC, section="Retention", note="Retention save/restore sequencing.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="iso_enable", role="isolation enable", channel="PMU"),
            ProtocolSignal(name="save_restore", role="retention save/restore control", channel="PMU"),
            ProtocolSignal(name="power_switch", role="domain power switch", channel="PMU"),
        ],
        state_machines=[
            StateMachine(
                id="low-power.domain-lifecycle",
                name="Power domain lifecycle",
                states=[
                    ProtocolState(name="On", description="Domain fully powered and active.", markers=[r"power (?:on|up)|domain active|fully powered"]),
                    ProtocolState(name="Isolate", description="Outputs clamped by isolation cells.", markers=[r"isolation (?:enabled|asserted)|outputs clamped"]),
                    ProtocolState(name="Retain", description="State saved to retention registers.", markers=[r"retention save|state saved|save asserted"]),
                    ProtocolState(name="Off", description="Domain power switched off.", markers=[r"power (?:off|down)|domain off|switch opened"]),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="low-power.isolation-missing",
                name="Isolation missing before power-down",
                summary=(
                    "A signal crossing a power-domain boundary was not isolated "
                    "before the source domain powered down, so a powered receiver can "
                    "sample a corrupt or floating value."
                ),
                required=[
                    EvidenceClause(
                        name="isolation not applied",
                        pattern=r"isolation (?:missing|not (?:enabled|active|applied))|(?:signal|output) crossing.*(?:not isolated|no isolation)|power[- ]down.*without isolation",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="low-power context", pattern=r"isolation|power domain|\bupf\b"),
                ],
                typical_causes=[
                    "Isolation enable asserted after, not before, the power switch opens",
                    "Isolation strategy misses a crossing signal in the UPF",
                    "Clamp value or sense wrong for the receiving logic",
                ],
                ownership="design",
                suggested_signals=["iso_enable", "power_switch", "crossing signal"],
                playbook_id="low-power.isolation-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="Isolation", note="Isolate before power-off.")],
            ),
            FailurePattern(
                id="low-power.retention-failure",
                name="Retention state lost across power cycle",
                summary=(
                    "A retention register did not preserve or restore its value "
                    "across a power-off/on cycle, so the domain woke with corrupt "
                    "state."
                ),
                required=[
                    EvidenceClause(
                        name="retention lost",
                        pattern=r"retention.*(?:fail|lost|not restored)|(?:register|state) (?:not retained|lost).*power|restore.*(?:corrupt|wrong).*retention",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Save asserted after the power switch already removed the main supply",
                    "Restore released before the domain supply is stable",
                    "Retention register on the switched supply instead of always-on",
                ],
                ownership="design",
                suggested_signals=["save_restore", "power_switch", "retained value"],
                playbook_id="low-power.retention-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="Retention", note="Save/restore ordering vs power switch.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="low-power.isolation-debug",
                name="Isolation debug",
                steps=[
                    PlaybookStep(action="Confirm isolation enable asserts before the power switch opens", signals=["iso_enable", "power_switch"]),
                    PlaybookStep(action="Check the UPF isolation strategy covers every crossing signal", signals=["crossing signal"]),
                    PlaybookStep(action="Verify the clamp value matches what the receiver expects"),
                    PlaybookStep(action="Confirm isolation releases only after the domain is powered"),
                ],
            ),
            DebugPlaybook(
                id="low-power.retention-debug",
                name="Retention debug",
                steps=[
                    PlaybookStep(action="Check save asserts before the main supply is removed", signals=["save_restore", "power_switch"]),
                    PlaybookStep(action="Confirm restore is released only after supply is stable"),
                    PlaybookStep(action="Verify retention cells are on the always-on supply", signals=["retained value"]),
                    PlaybookStep(action="Compare retained values before and after the power cycle"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for UPF power intent.")],
    )
