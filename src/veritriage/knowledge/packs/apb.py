"""AMBA APB Knowledge Pack.

APB is the simple two-phase peripheral bus: SETUP then ACCESS, extended by
PREADY. Its failure modes are correspondingly simple and correspondingly
common: a peripheral that never raises PREADY, an enable-phase protocol
slip, or an ignored PSLVERR.
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

_SPEC = "AMBA APB Protocol Specification (IHI 0024)"


@register_pack
def apb_pack() -> KnowledgePack:
    return KnowledgePack(
        id="apb",
        name="AMBA APB",
        version="1.0.0",
        domain="protocol",
        summary="APB setup/access phasing, PREADY wait states, and PSLVERR handling.",
        concepts=[
            Concept(
                id="apb.phasing",
                name="SETUP and ACCESS phases",
                summary=(
                    "Every APB transfer is exactly one SETUP cycle (PSEL high, "
                    "PENABLE low) followed by an ACCESS phase (PSEL and PENABLE "
                    "high) that lasts until the peripheral asserts PREADY. PENABLE "
                    "high for more or less than the transfer, or PSEL changing "
                    "mid-transfer, is a protocol violation."
                ),
                markers=[r"\bapb\b", r"\bpsel\b", r"\bpenable\b", r"setup phase", r"access phase"],
                references=[Reference(source=_SPEC, section="4.1", note="Transfer phases and timing.")],
            ),
            Concept(
                id="apb.pslverr",
                name="PSLVERR error response",
                summary=(
                    "PSLVERR high with PREADY signals a failed transfer. Masters "
                    "and testbenches that ignore it convert addressing bugs into "
                    "silent data corruption."
                ),
                markers=[r"\bpslverr\b", r"apb .*error response"],
                references=[Reference(source=_SPEC, section="4.4", note="Error response.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="PSEL", role="peripheral select"),
            ProtocolSignal(name="PENABLE", role="access-phase enable"),
            ProtocolSignal(name="PREADY", role="peripheral ready (wait states)"),
            ProtocolSignal(name="PSLVERR", role="transfer error"),
            ProtocolSignal(name="PWRITE", role="direction select"),
        ],
        state_machines=[
            StateMachine(
                id="apb.transfer",
                name="APB transfer",
                states=[
                    ProtocolState(
                        name="Idle",
                        description="No transfer selected.",
                        markers=[r"apb idle"],
                    ),
                    ProtocolState(
                        name="Setup",
                        description="PSEL asserted, PENABLE low, address/controls driven.",
                        markers=[r"setup phase", r"\bpsel\b.*assert"],
                    ),
                    ProtocolState(
                        name="Access",
                        description="PENABLE high; wait states while PREADY low.",
                        markers=[r"access phase", r"\bpenable\b.*assert", r"wait state"],
                    ),
                    ProtocolState(
                        name="Complete",
                        description="PREADY high ends the transfer.",
                        markers=[r"pready (?:assert|seen|high)", r"apb .*complete"],
                    ),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="apb.pready-stuck",
                name="PREADY never asserted",
                summary=(
                    "An APB access phase never completed: the peripheral held "
                    "PREADY low (or never sampled the select) and the bus hung in "
                    "wait states until a timeout."
                ),
                required=[
                    EvidenceClause(
                        name="timeout or hang observed",
                        pattern=r"time[- ]?out|watchdog|hung|stuck",
                        must_fail=True,
                    ),
                    EvidenceClause(
                        name="APB access pending",
                        pattern=r"\bapb\b.*(?:pending|wait|stuck|access)|pready.*(?:low|stuck|never)|wait state",
                    ),
                ],
                typical_causes=[
                    "Peripheral clock gated off while selected",
                    "Register block decode miss: PSEL points at an unmapped hole",
                    "Peripheral FSM requires an internal event that never happens",
                    "Synchronizer between bus and peripheral domain drops the enable",
                ],
                ownership="design",
                suggested_signals=["PSEL", "PENABLE", "PREADY", "peripheral clock/clock-enable"],
                playbook_id="apb.hang",
                confidence_modifiers={"rtl_bug": 0.10},
                references=[Reference(source=_SPEC, section="4.2.1", note="PREADY extends the access phase.")],
            ),
            FailurePattern(
                id="apb.ignored-slverr",
                name="PSLVERR ignored",
                summary=(
                    "A transfer completed with PSLVERR asserted but downstream "
                    "checks treated the data as valid; later mismatches are "
                    "symptoms of this earlier ignored error."
                ),
                required=[
                    EvidenceClause(
                        name="error response observed",
                        pattern=r"\bpslverr\b|apb .*error response",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Access to a read-only/write-only or unmapped register",
                    "Peripheral in a state that legally rejects the access (e.g. busy)",
                    "Testbench register model out of sync with the RTL address map",
                ],
                ownership="testbench",
                suggested_signals=["PSLVERR", "PADDR", "PWRITE"],
                playbook_id="apb.slverr",
                confidence_modifiers={"testbench_issue": 0.08, "rtl_bug": 0.05},
                references=[Reference(source=_SPEC, section="4.4", note="PSLVERR semantics.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="apb.hang",
                name="APB access hang",
                steps=[
                    PlaybookStep(action="Capture PSEL/PENABLE/PREADY around the hang", signals=["PSEL", "PENABLE", "PREADY"]),
                    PlaybookStep(action="Check the peripheral clock and clock-enable during the access", detail="A gated clock while selected is the most common cause.", signals=["peripheral clk", "clk_en"]),
                    PlaybookStep(action="Verify the address decodes to a real register", detail="Compare PADDR against the block's address map.", signals=["PADDR"]),
                    PlaybookStep(action="Walk the peripheral's internal ready-generation FSM", detail="Find the internal condition PREADY is waiting on."),
                ],
            ),
            DebugPlaybook(
                id="apb.slverr",
                name="PSLVERR investigation",
                steps=[
                    PlaybookStep(action="Log every transfer that completed with PSLVERR", signals=["PSLVERR", "PADDR"]),
                    PlaybookStep(action="Classify each: unmapped, permission, or state-dependent rejection"),
                    PlaybookStep(action="Sync the register model with the RTL address map", detail="Most PSLVERR storms are a stale testbench map."),
                    PlaybookStep(action="Make the scoreboard treat PSLVERR transfers as errors, not data"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary protocol reference for this pack.")],
    )
