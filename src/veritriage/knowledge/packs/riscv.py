"""RISC-V privilege architecture Knowledge Pack.

Privilege-mode, trap, and CSR knowledge: the mechanisms that distinguish a
RISC-V core's control-plane bugs (wrong mode after a trap, mis-delegated
exception, faulty CSR read/write) from ordinary datapath bugs.
"""

from __future__ import annotations

from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    PlaybookStep,
    ProtocolState,
    Reference,
    StateMachine,
)
from veritriage.knowledge.registry import register_pack

_SPEC = "RISC-V Privileged Architecture Specification"


@register_pack
def riscv_pack() -> KnowledgePack:
    return KnowledgePack(
        id="riscv-privilege",
        name="RISC-V Privilege",
        version="1.0.0",
        domain="architecture",
        summary="Privilege modes, trap/exception delegation, and CSR access-fault semantics.",
        concepts=[
            Concept(
                id="riscv.privilege-modes",
                name="Privilege modes (M/S/U)",
                summary=(
                    "RISC-V defines Machine, Supervisor, and User privilege "
                    "modes; an instruction or CSR access illegal for the current "
                    "mode must raise an illegal-instruction or access-fault "
                    "exception, not execute. A core that silently allows a "
                    "lower-privilege access has broken the security model, not "
                    "just failed a check."
                ),
                markers=[r"privilege mode", r"\bm-?mode\b|\bs-?mode\b|\bu-?mode\b", r"machine mode|supervisor mode|user mode"],
                references=[Reference(source=_SPEC, section="1.2", note="Privilege levels.")],
            ),
            Concept(
                id="riscv.traps",
                name="Traps and exception delegation",
                summary=(
                    "A trap (interrupt or exception) transfers control to the "
                    "configured handler mode, saving PC/cause/status in the "
                    "matching CSRs (mepc/mcause/mstatus or their s-mode "
                    "equivalents). Delegation registers (medeleg/mideleg) route "
                    "specific causes to S-mode; a mis-delegated cause traps into "
                    "the wrong handler entirely."
                ),
                markers=[r"\btrap\b", r"\bmepc\b|\bmcause\b|\bmstatus\b|\bsepc\b|\bscause\b", r"medeleg|mideleg", r"exception (?:raised|taken)"],
                references=[Reference(source=_SPEC, section="3.1.7", note="Trap handling and delegation.")],
            ),
            Concept(
                id="riscv.csr",
                name="CSR access semantics",
                summary=(
                    "Control and Status Register accesses are checked against "
                    "the current privilege level and the register's own "
                    "read/write/reserved-field rules; writing a WPRI (reserved) "
                    "field or accessing a CSR above the current mode must fault "
                    "rather than silently succeed or corrupt state."
                ),
                markers=[r"\bcsr\b", r"\bcsrrw\b|\bcsrrs\b|\bcsrrc\b", r"illegal (?:csr|instruction)"],
                references=[Reference(source=_SPEC, section="2.2", note="CSR instruction semantics.")],
            ),
        ],
        state_machines=[
            StateMachine(
                id="riscv.trap-lifecycle",
                name="RISC-V trap lifecycle",
                states=[
                    ProtocolState(
                        name="Cause detected",
                        description="Interrupt pending or exception condition detected.",
                        markers=[r"exception (?:detected|condition)", r"interrupt pending"],
                    ),
                    ProtocolState(
                        name="Delegation checked",
                        description="medeleg/mideleg determines the target privilege mode.",
                        markers=[r"delegat", r"medeleg|mideleg"],
                    ),
                    ProtocolState(
                        name="State saved",
                        description="PC/cause/status saved to the target mode's trap CSRs.",
                        markers=[r"mepc (?:written|saved)|sepc (?:written|saved)", r"mcause (?:written|saved)|scause (?:written|saved)"],
                    ),
                    ProtocolState(
                        name="Handler entered",
                        description="PC redirected to the trap vector in the target mode.",
                        markers=[r"trap vector|handler entered|jumped to (?:mtvec|stvec)"],
                    ),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="riscv.trap-wrong-mode",
                name="Trap delegated to the wrong privilege mode",
                summary=(
                    "A trap fired but control transferred to a different "
                    "privilege mode than the delegation configuration (medeleg/"
                    "mideleg) specifies for that cause."
                ),
                required=[
                    EvidenceClause(
                        name="delegation mismatch observed",
                        pattern=r"trap.*wrong mode|delegat.*(?:mismatch|violat|incorrect)|handler entered.*(?:wrong|unexpected) mode",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Delegation register read at the wrong pipeline stage (stale value)",
                    "Cause-to-delegation-bit mapping implemented off by one",
                    "M-mode-only cause incorrectly made delegable",
                ],
                ownership="design",
                suggested_signals=["medeleg/mideleg value", "mcause/scause", "mode transition signal"],
                playbook_id="riscv.trap-debug",
                confidence_modifiers={"rtl_bug": 0.14},
                references=[Reference(source=_SPEC, section="3.1.8", note="Delegation of traps to S-mode.")],
            ),
            FailurePattern(
                id="riscv.csr-access-fault-missed",
                name="Illegal CSR access not faulted",
                summary=(
                    "A CSR access that the spec requires to fault (wrong "
                    "privilege level, or a reserved/WPRI field write) instead "
                    "completed silently, letting incorrect state through."
                ),
                required=[
                    EvidenceClause(
                        name="missed illegal-access fault",
                        pattern=r"csr access.*(?:not faulted|should have faulted|missed)|illegal (?:csr )?access.*(?:allowed|succeeded)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Privilege check on the CSR address decode incomplete for a subset of registers",
                    "WPRI/WLRL field masking not applied on write",
                    "Custom CSR added without wiring the access-check logic",
                ],
                ownership="design",
                suggested_signals=["CSR address", "current privilege mode", "CSR access-check logic"],
                playbook_id="riscv.csr-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="2.2", note="CSR privilege and field-type checks.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="riscv.trap-debug",
                name="Trap delegation debug",
                steps=[
                    PlaybookStep(action="Read the cause value and expected target mode from the spec table", signals=["mcause/scause"]),
                    PlaybookStep(action="Sample medeleg/mideleg at the trap-taken cycle", detail="A stale or mistimed read explains most mis-delegations.", signals=["medeleg/mideleg value"]),
                    PlaybookStep(action="Confirm the cause-to-bit mapping used by the RTL matches the spec table exactly"),
                    PlaybookStep(action="Trace the mode-transition signal to find where it diverged from the expected mode"),
                ],
            ),
            DebugPlaybook(
                id="riscv.csr-debug",
                name="CSR access-fault debug",
                steps=[
                    PlaybookStep(action="Identify the CSR address and the privilege mode at the time of access", signals=["CSR address", "current privilege mode"]),
                    PlaybookStep(action="Check the access-check table for that address against current mode"),
                    PlaybookStep(action="For reserved-field writes, check WPRI/WLRL masking logic on the write path"),
                    PlaybookStep(action="If the CSR is custom, confirm it is wired into the shared access-check logic"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary architecture reference for this pack.")],
    )
