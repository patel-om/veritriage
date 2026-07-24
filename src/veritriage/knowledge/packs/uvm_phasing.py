"""UVM phasing and objections Knowledge Pack.

The UVM phase schedule, objection-based run control, and drain time. The
failures are an objection that is raised and never dropped (the run phase
hangs to timeout) and phases that execute out of their defined order.
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

_SPEC = "UVM (IEEE 1800.2) phasing"


@register_pack
def uvm_phasing_pack() -> KnowledgePack:
    return KnowledgePack(
        id="uvm-phasing",
        name="UVM phasing",
        version="1.0.0",
        domain="methodology",
        summary="UVM phase schedule, objection run control, and drain time.",
        concepts=[
            Concept(
                id="uvm-phasing.objections",
                name="Objections and drain",
                summary=(
                    "A time-consuming phase (run_phase) stays alive while any "
                    "component raises an objection; the phase ends after all "
                    "objections drop plus the drain time. An objection raised and "
                    "never dropped hangs the phase until the global timeout."
                ),
                markers=[r"objection", r"drain time", r"run_phase|phase (?:end|done)"],
                references=[Reference(source=_SPEC, section="Phasing", note="Objection-based phase control.")],
            ),
            Concept(
                id="uvm-phasing.schedule",
                name="Phase schedule",
                summary=(
                    "UVM runs a fixed schedule of build/connect/end_of_elaboration/"
                    "run/report phases (with sub-phases). Components must do phase-"
                    "appropriate work; connecting in build, or expecting run-phase "
                    "state during elaboration, is a phase-order error."
                ),
                markers=[r"build_phase|connect_phase|end_of_elaboration|run_phase|report_phase", r"phase (?:order|schedule)", r"elaboration"],
                references=[Reference(source=_SPEC, section="Phasing", note="Standard phase order.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="uvm-phasing.objection-not-dropped",
                name="Objection never dropped (phase hangs)",
                summary=(
                    "A component raised an objection and never dropped it, so the "
                    "run phase could not end and the simulation ran to its global "
                    "timeout."
                ),
                required=[
                    EvidenceClause(
                        name="objection leaked",
                        pattern=r"objection.*(?:never dropped|not dropped|leaked|still raised)|phase.*(?:hang|stuck).*objection|run_phase.*did not (?:end|complete)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="phasing context", pattern=r"objection|run_phase|drain"),
                ],
                typical_causes=[
                    "Sequence ends early leaving a raised objection un-dropped",
                    "Exception between raise and drop skips the drop",
                    "Objection dropped on a different phase object than it was raised on",
                ],
                ownership="testbench",
                suggested_signals=["objection count", "raising component", "drain time"],
                playbook_id="uvm-phasing.objection-debug",
                confidence_modifiers={"testbench_issue": 0.13},
                references=[Reference(source=_SPEC, section="Phasing", note="Phase ends when objections reach zero.")],
            ),
            FailurePattern(
                id="uvm-phasing.phase-order-violation",
                name="Phase order violation",
                summary=(
                    "Work was performed in the wrong phase, or phases executed out "
                    "of their defined order, so a component saw state that was not "
                    "yet established (or already torn down)."
                ),
                required=[
                    EvidenceClause(
                        name="phase order wrong",
                        pattern=r"phase (?:order|jump).*(?:wrong|violat|unexpected)|(?:build|connect|run) phase.*(?:out of order|before|after)|phase.*executed.*wrong order",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Port connection attempted in build instead of connect phase",
                    "Custom phase jump misconfigured",
                    "Component assumes run-phase state during end_of_elaboration",
                ],
                ownership="testbench",
                suggested_signals=["current phase", "component phase method"],
                playbook_id="uvm-phasing.schedule-debug",
                confidence_modifiers={"testbench_issue": 0.11},
                references=[Reference(source=_SPEC, section="Phasing", note="Phase-appropriate work.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="uvm-phasing.objection-debug",
                name="Objection debug",
                steps=[
                    PlaybookStep(action="Dump the objection count and the components still objecting at timeout", signals=["objection count", "raising component"]),
                    PlaybookStep(action="Trace the raising sequence/component for a missing drop"),
                    PlaybookStep(action="Check for an exception between raise and drop"),
                    PlaybookStep(action="Confirm raise and drop use the same phase object"),
                ],
            ),
            DebugPlaybook(
                id="uvm-phasing.schedule-debug",
                name="Phase schedule debug",
                steps=[
                    PlaybookStep(action="Identify the phase in which the offending work ran", signals=["current phase"]),
                    PlaybookStep(action="Move connection/setup work to its correct phase"),
                    PlaybookStep(action="Review any custom phase jumps for correctness"),
                    PlaybookStep(action="Confirm no component reads run-phase state during elaboration"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for UVM phasing.")],
    )
