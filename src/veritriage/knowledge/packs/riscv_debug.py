"""RISC-V Debug (external debug) Knowledge Pack.

The Debug Module halt/resume protocol, abstract commands for register and
memory access, and hardware triggers. Debug bugs strand a hart in the wrong
run state or return the wrong cmderr, which blocks bring-up and defeats the
very tool used to diagnose everything else.
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

_SPEC = "RISC-V Debug Specification"


@register_pack
def riscv_debug_pack() -> KnowledgePack:
    return KnowledgePack(
        id="riscv-debug",
        name="RISC-V Debug",
        version="1.0.0",
        domain="architecture",
        summary="Debug Module halt/resume, abstract commands, and their error reporting.",
        concepts=[
            Concept(
                id="riscv-debug.halt-resume",
                name="Halt/resume protocol",
                summary=(
                    "The debugger halts a hart by asserting haltreq in dmcontrol and "
                    "waits for dmstatus.allhalted; it resumes by asserting resumereq "
                    "and waits for allresumeack. A hart that never reaches the "
                    "requested state, or reports the wrong dmstatus, breaks debugger "
                    "control."
                ),
                markers=[r"\bhaltreq\b|\bresumereq\b", r"\bdmcontrol\b|\bdmstatus\b", r"allhalted|allresumeack|halted"],
                references=[Reference(source=_SPEC, section="3.5", note="Run control and dmstatus fields.")],
            ),
            Concept(
                id="riscv-debug.abstract-command",
                name="Abstract commands",
                summary=(
                    "Abstract commands access GPRs, CSRs, and (optionally) memory "
                    "while halted; command status and failures are reported in "
                    "abstractcs.cmderr. A nonzero cmderr that the RTL sets "
                    "incorrectly, or fails to set, misreports whether the access "
                    "succeeded."
                ),
                markers=[r"abstract command|\bcommand\b register", r"\babstractcs\b|\bcmderr\b", r"\bdata0\b|\bdata1\b"],
                references=[Reference(source=_SPEC, section="3.6", note="Abstract commands and cmderr.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="haltreq", role="halt request", channel="DM"),
            ProtocolSignal(name="allhalted", role="all harts halted", channel="DM"),
            ProtocolSignal(name="cmderr", role="abstract command error", channel="DM"),
        ],
        state_machines=[
            StateMachine(
                id="riscv-debug.hart-lifecycle",
                name="Hart debug run-control lifecycle",
                states=[
                    ProtocolState(name="Running", description="Hart executing normally.", markers=[r"hart running|running state|resumed"]),
                    ProtocolState(name="Halt requested", description="Debugger asserted haltreq.", markers=[r"\bhaltreq\b (?:assert|set)|halt requested"]),
                    ProtocolState(name="Halted", description="dmstatus.allhalted set.", markers=[r"allhalted|hart halted|entered debug mode"]),
                    ProtocolState(name="Resume requested", description="Debugger asserted resumereq.", markers=[r"\bresumereq\b|resume requested"]),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="riscv-debug.abstract-command-fail",
                name="Abstract command reports failure",
                summary=(
                    "An abstract command returned a cmderr (busy, not-supported, or "
                    "exception) for an access the debugger expected to succeed, so "
                    "register/memory access over the Debug Module is unreliable."
                ),
                required=[
                    EvidenceClause(
                        name="cmderr set unexpectedly",
                        pattern=r"abstract command.*(?:failed|cmderr)|cmderr\s*=?\s*[1-7]|cmderr.*(?:busy|not supported|exception)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="debug context", pattern=r"\babstractcs\b|abstract command|\bdata0\b"),
                ],
                typical_causes=[
                    "Command issued while busy because abstractcs.busy is cleared too early",
                    "GPR access attempted without the required program buffer or autoexec setup",
                    "cmderr latched from a previous command and never cleared",
                ],
                ownership="design",
                suggested_signals=["cmderr", "abstractcs.busy", "command register"],
                playbook_id="riscv-debug.abstract-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="3.6.1", note="cmderr encodings.")],
            ),
            FailurePattern(
                id="riscv-debug.halt-request-timeout",
                name="Hart never halts after haltreq",
                summary=(
                    "haltreq was asserted but dmstatus.allhalted never set: the "
                    "hart did not enter debug mode within the expected window, "
                    "stranding the debugger."
                ),
                required=[
                    EvidenceClause(
                        name="halt never acknowledged",
                        pattern=r"halt request.*(?:timeout|never)|hart.*(?:did not|never) halt|haltreq.*(?:no|never).*(?:allhalted|halted)|allhalted never (?:set|asserted)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Hart stuck in a state (WFI, stalled load) where the halt request is not sampled",
                    "haltreq to debug-entry handshake missing an acknowledge path",
                    "dmstatus.allhalted aggregation logic gated by the wrong hart mask",
                ],
                ownership="design",
                suggested_signals=["haltreq", "allhalted", "hart run state"],
                playbook_id="riscv-debug.runcontrol-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="3.5", note="Halt handshake and dmstatus.allhalted.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="riscv-debug.abstract-debug",
                name="Abstract command debug",
                steps=[
                    PlaybookStep(action="Read cmderr and decode the failure class (busy/not-supported/exception)", signals=["cmderr"]),
                    PlaybookStep(action="Confirm abstractcs.busy is held for the full command duration", signals=["abstractcs.busy"]),
                    PlaybookStep(action="Verify cmderr is cleared (write 1s) before issuing the next command"),
                    PlaybookStep(action="For GPR/CSR access, check the required aarsize/transfer setup in the command"),
                ],
            ),
            DebugPlaybook(
                id="riscv-debug.runcontrol-debug",
                name="Halt/resume run-control debug",
                steps=[
                    PlaybookStep(action="Confirm haltreq reaches the hart and is sampled in its current state", signals=["haltreq", "hart run state"]),
                    PlaybookStep(action="Check the debug-entry handshake completes and drives the halted status", signals=["allhalted"]),
                    PlaybookStep(action="For WFI or stalled harts, verify the halt request forces an exit"),
                    PlaybookStep(action="Verify the dmstatus.allhalted aggregation uses the correct hart selection mask"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for external debug.")],
    )
