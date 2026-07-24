"""JTAG / IEEE 1149.1 boundary-scan Knowledge Pack.

The TAP (Test Access Port) state machine, IR/DR scan chains, and boundary
scan. JTAG is the transport under debug and test; its failures strand the TAP
in the wrong state or corrupt a scan, blocking bring-up and test access.
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

_SPEC = "IEEE 1149.1 (JTAG) Standard"


@register_pack
def jtag_pack() -> KnowledgePack:
    return KnowledgePack(
        id="jtag",
        name="JTAG / IEEE 1149.1",
        version="1.0.0",
        domain="boundary-scan",
        summary="TAP state machine navigation and IR/DR scan-chain integrity.",
        concepts=[
            Concept(
                id="jtag.tap",
                name="TAP state machine",
                summary=(
                    "The 16-state TAP controller is navigated purely by TMS on TCK "
                    "rising edges. Reaching Shift-IR or Shift-DR requires the exact "
                    "TMS sequence; a wrong TMS pattern or a missed TCK leaves the TAP "
                    "in an unexpected state and every subsequent scan is invalid."
                ),
                markers=[r"\btap\b", r"\btms\b|\btck\b|\btdi\b|\btdo\b", r"shift-?(?:ir|dr)|run-?test|test-?logic-?reset"],
                references=[Reference(source=_SPEC, section="6", note="TAP controller state diagram.")],
            ),
            Concept(
                id="jtag.scan",
                name="IR/DR scan chains",
                summary=(
                    "Instructions are shifted through the Instruction Register (IR) "
                    "and data through a Data Register (DR); the chain length and the "
                    "capture values are fixed by the design. A length mismatch or a "
                    "wrong capture value means the scan chain does not match "
                    "expectation."
                ),
                markers=[r"(?:ir|dr) scan|instruction register|data register", r"scan chain", r"capture|shift|update"],
                references=[Reference(source=_SPEC, section="7", note="IR/DR scan operations.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="tms", role="test mode select", channel="JTAG"),
            ProtocolSignal(name="tap_state", role="TAP controller state", channel="JTAG"),
            ProtocolSignal(name="tdo", role="test data out", channel="JTAG"),
        ],
        state_machines=[
            StateMachine(
                id="jtag.tap-lifecycle",
                name="JTAG TAP scan sequence",
                states=[
                    ProtocolState(name="Test-Logic-Reset", description="Reset state entered by five TMS-high clocks.", markers=[r"test-?logic-?reset|tap reset"]),
                    ProtocolState(name="Run-Test-Idle", description="Idle/run-test state.", markers=[r"run-?test-?idle|\brti\b"]),
                    ProtocolState(name="Shift", description="Shift-IR or Shift-DR shifting bits.", markers=[r"shift-?(?:ir|dr)|shifting"]),
                    ProtocolState(name="Update", description="Update-IR or Update-DR latches the shifted value.", markers=[r"update-?(?:ir|dr)|latched"]),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="jtag.tap-stuck",
                name="TAP controller in the wrong state",
                summary=(
                    "The TAP controller did not reach the intended state: a wrong TMS "
                    "sequence or a missed TCK left it stuck, so scans issued from "
                    "there are invalid."
                ),
                required=[
                    EvidenceClause(
                        name="tap navigation wrong",
                        pattern=r"jtag.*(?:tap|state machine).*(?:stuck|wrong)|tap (?:fsm|controller).*(?:stuck|not reach)|tms sequence.*(?:wrong|stuck)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="jtag context", pattern=r"\bjtag\b|\btap\b|\btms\b"),
                ],
                typical_causes=[
                    "TMS sequence generator off by one clock",
                    "TCK glitch or missed edge advancing the state incorrectly",
                    "TAP not reset with the required five TMS-high clocks before use",
                ],
                ownership="design",
                suggested_signals=["tms", "tap_state", "tck"],
                playbook_id="jtag.tap-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="6", note="TMS-driven state transitions.")],
            ),
            FailurePattern(
                id="jtag.ir-dr-mismatch",
                name="Scan-chain length or capture mismatch",
                summary=(
                    "An IR or DR scan did not match expectation: the shifted length "
                    "was wrong or the captured value differed, so the scan chain does "
                    "not reflect the intended register."
                ),
                required=[
                    EvidenceClause(
                        name="scan mismatch",
                        pattern=r"(?:ir|dr) scan.*(?:mismatch|length|wrong)|instruction register.*(?:capture|mismatch)|scan chain.*(?:length|integrity).*(?:mismatch|fail)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "A TAP added to or removed from the chain without updating the expected length",
                    "Capture value of a register does not match its specified reset pattern",
                    "Bypass register not inserted for an unselected device",
                ],
                ownership="design",
                suggested_signals=["tdo", "expected chain length", "capture value"],
                playbook_id="jtag.scan-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="7", note="Scan chain length and capture.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="jtag.tap-debug",
                name="JTAG TAP navigation debug",
                steps=[
                    PlaybookStep(action="Replay the TMS/TCK sequence and track the TAP state each clock", signals=["tms", "tap_state"]),
                    PlaybookStep(action="Confirm the TAP was reset with five TMS-high clocks before use"),
                    PlaybookStep(action="Check for TCK glitches or missed edges", signals=["tck"]),
                    PlaybookStep(action="Verify the TMS sequence generator alignment"),
                ],
            ),
            DebugPlaybook(
                id="jtag.scan-debug",
                name="JTAG scan-chain debug",
                steps=[
                    PlaybookStep(action="Compare the observed shift length to the expected chain length", signals=["expected chain length"]),
                    PlaybookStep(action="Check each register's capture value against its specified pattern", signals=["capture value"]),
                    PlaybookStep(action="Confirm bypass registers are inserted for unselected devices"),
                    PlaybookStep(action="Trace TDO against the expected shifted-out sequence", signals=["tdo"]),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for JTAG/boundary-scan.")],
    )
