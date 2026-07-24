"""X-propagation Knowledge Pack.

Unknown (X) values from uninitialized state and their propagation through
control paths. RTL simulation can be X-optimistic (an X on a mux select picks
a definite branch) while gate-level is X-pessimistic; a design that depends on
an uninitialized value hides a real bug behind that optimism.
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

_SPEC = "X-propagation and initialization methodology"


@register_pack
def x_propagation_pack() -> KnowledgePack:
    return KnowledgePack(
        id="x-propagation",
        name="X-propagation",
        version="1.0.0",
        domain="methodology",
        summary="Uninitialized-X reads and X leaking through control/select paths.",
        concepts=[
            Concept(
                id="x-propagation.init",
                name="Initialization and unknown values",
                summary=(
                    "Flops and memories without an explicit reset start as X in "
                    "simulation. Reading such state before it is written propagates an "
                    "unknown; a design that reaches a decision based on an "
                    "uninitialized value is relying on undefined behavior."
                ),
                markers=[r"uninitial", r"\bx\b (?:value|state|propagat)|unknown value", r"reset|power-?up state"],
                references=[Reference(source=_SPEC, section="Init", note="Uninitialized state is X.")],
            ),
            Concept(
                id="x-propagation.optimism",
                name="X-optimism vs pessimism",
                summary=(
                    "RTL simulation can be X-optimistic: an X on a mux select or a "
                    "condition may resolve to a definite branch, masking a bug that "
                    "gate-level (X-pessimistic) would expose. X reaching a control or "
                    "select path is the dangerous case."
                ),
                markers=[r"x-?(?:optim|pessim)", r"x on (?:the )?(?:select|control|enable)", r"mux select|control path|fsm state"],
                references=[Reference(source=_SPEC, section="Optimism", note="RTL X-optimism vs gate pessimism.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="x-propagation.uninitialized",
                name="Uninitialized value read as X",
                summary=(
                    "An uninitialized register or memory was read as X before being "
                    "written, propagating an unknown value into the datapath."
                ),
                required=[
                    EvidenceClause(
                        name="uninitialized x read",
                        pattern=r"uninitialized.*(?:register|memory|flop|value)|x[- ]?(?:propagation|pessimism|optimism)|read (?:an )?x .*(?:uninitial|before reset|before write)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="x context", pattern=r"uninitial|unknown value|x-?prop"),
                ],
                typical_causes=[
                    "Register with no reset relied upon before its first functional write",
                    "Memory read before initialization at power-up",
                    "Reset not connected to a flop that needs a known start value",
                ],
                ownership="design",
                suggested_signals=["signal driven X", "reset connectivity", "first-write time"],
                playbook_id="x-propagation.init-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="Init", note="Reading uninitialized state.")],
            ),
            FailurePattern(
                id="x-propagation.x-through-control",
                name="X propagated through a control path",
                summary=(
                    "An unknown value reached a control or select path (a mux select, "
                    "enable, or FSM state), where X-optimism can mask a functional "
                    "bug that gate-level would expose."
                ),
                required=[
                    EvidenceClause(
                        name="x on control path",
                        pattern=r"x (?:on|through).*(?:control|select|enable|state|mux)|unknown value.*(?:control|select|fsm)|x-?propagat.*(?:control|fsm|select)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Uninitialized value feeding a mux select the design assumed defined",
                    "FSM entered from an X-valued next-state due to missing reset",
                    "Enable derived from unknown state gating a critical action",
                ],
                ownership="design",
                suggested_signals=["select signal", "fsm state", "enable signal"],
                playbook_id="x-propagation.control-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="Optimism", note="X on control is the dangerous case.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="x-propagation.init-debug",
                name="Uninitialized-X debug",
                steps=[
                    PlaybookStep(action="Trace the X back to the flop/memory that produced it", signals=["signal driven X"]),
                    PlaybookStep(action="Determine whether that state needs a reset", signals=["reset connectivity"]),
                    PlaybookStep(action="Confirm the first functional write happens before the read", signals=["first-write time"]),
                    PlaybookStep(action="Consider X-injection or a reset to expose the dependency"),
                ],
            ),
            DebugPlaybook(
                id="x-propagation.control-debug",
                name="Control-path X debug",
                steps=[
                    PlaybookStep(action="Identify the control/select signal carrying X", signals=["select signal", "enable signal"]),
                    PlaybookStep(action="Check whether RTL X-optimism is masking the effect"),
                    PlaybookStep(action="Re-run with X-propagation/X-prop settings enabled"),
                    PlaybookStep(action="Add reset or a known default to the offending control state", signals=["fsm state"]),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for X-propagation methodology.")],
    )
