"""PCI Express Knowledge Pack.

PCIe knowledge at the layers DV teams actually debug: the LTSSM link
training state machine, TLP/flow-control credits, and completion timeouts.
Most PCIe "it just doesn't link up" or "it hangs after a while" bugs live in
exactly these three mechanisms.
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

_SPEC = "PCI Express Base Specification"


@register_pack
def pcie_pack() -> KnowledgePack:
    return KnowledgePack(
        id="pcie",
        name="PCI Express",
        version="1.0.0",
        domain="protocol",
        summary="PCIe LTSSM link training, TLP/flow-control credits, and completion timeouts.",
        concepts=[
            Concept(
                id="pcie.ltssm",
                name="LTSSM link training",
                summary=(
                    "The Link Training and Status State Machine brings a PCIe link "
                    "up through Detect, Polling, Configuration, L0, and (on idle) "
                    "the low-power L-states. A link stuck retraining, or one that "
                    "never reaches L0, is a physical/logical layer problem, not a "
                    "transaction-layer one."
                ),
                markers=[r"\bltssm\b", r"link training", r"\bl0\b.*(?:state|entry)", r"polling\.(?:active|config)", r"recovery\.(?:rcvrlock|speed)"],
                references=[Reference(source=_SPEC, section="4.2", note="LTSSM states and transitions.")],
            ),
            Concept(
                id="pcie.flow-control",
                name="TLP flow control credits",
                summary=(
                    "Each TLP type (posted, non-posted, completion) consumes "
                    "receiver buffer credits advertised during initialization and "
                    "returned via UpdateFC DLLPs. A stalled receiver that stops "
                    "returning credits silently throttles the link to zero without "
                    "any link-layer error."
                ),
                markers=[r"flow control|\bupdatefc\b", r"\bfc credit\b", r"posted|non-posted|completion credit"],
                references=[Reference(source=_SPEC, section="2.6", note="Flow control.")],
            ),
            Concept(
                id="pcie.completion-timeout",
                name="Completion timeout",
                summary=(
                    "A requester that issues a non-posted request (memory read, "
                    "config read) starts a completion timer; no completion before "
                    "it expires is a Completion Timeout, reported as an "
                    "uncorrectable error and usually surfacing as a hung driver."
                ),
                markers=[r"completion timeout|\bcto\b", r"no completion (?:received|returned)"],
                references=[Reference(source=_SPEC, section="2.9", note="Completion timeout mechanism.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="LTSSM state", role="link training state"),
            ProtocolSignal(name="TLP header/valid", role="transaction layer packet"),
            ProtocolSignal(name="UpdateFC DLLP", role="flow-control credit return"),
            ProtocolSignal(name="ACK/NAK DLLP", role="data link layer retry protocol"),
        ],
        state_machines=[
            StateMachine(
                id="pcie.link-training",
                name="PCIe link training",
                states=[
                    ProtocolState(
                        name="Detect",
                        description="Receiver detection on each lane.",
                        markers=[r"detect\.(?:quiet|active)", r"receiver detect"],
                    ),
                    ProtocolState(
                        name="Polling",
                        description="Bit/symbol lock and lane polarity established.",
                        markers=[r"polling\.(?:active|compliance|config)"],
                    ),
                    ProtocolState(
                        name="Configuration",
                        description="Lane numbering and link width/speed negotiated.",
                        markers=[r"configuration\.(?:linkwidth|lanenum|complete)"],
                    ),
                    ProtocolState(
                        name="L0",
                        description="Link up; normal TLP/DLLP traffic flows.",
                        markers=[r"\bl0\b(?! s)", r"link up", r"link (?:active|training complete)"],
                    ),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="pcie.link-training-stuck",
                name="LTSSM never reaches L0",
                summary=(
                    "Link training stalled or kept retraining before reaching L0: "
                    "the transaction layer never got a chance to run, so any "
                    "traffic-layer failure downstream is a symptom, not the cause."
                ),
                required=[
                    EvidenceClause(
                        name="LTSSM stall observed",
                        pattern=r"ltssm.*(?:stuck|stall|loop|retrain|never reach|timeout)|link training (?:fail|timeout|stuck)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Reference clock or reset sequencing violates the spec's timing budget",
                    "Lane polarity or bit-lock failure on one or more lanes",
                    "Speed/width negotiation mismatch between link partners",
                    "Equalization (Gen3+) never converges",
                ],
                ownership="design",
                suggested_signals=["LTSSM state", "per-lane bit/symbol lock", "negotiated width/speed"],
                playbook_id="pcie.link-training-debug",
                confidence_modifiers={"rtl_bug": 0.12, "infrastructure_issue": 0.04},
                references=[Reference(source=_SPEC, section="4.2.5", note="Link training must converge to L0.")],
            ),
            FailurePattern(
                id="pcie.completion-timeout-hang",
                name="Completion timeout on outstanding request",
                summary=(
                    "A non-posted request never received its completion before "
                    "the timer expired; the requester is stuck waiting and the run "
                    "eventually times out at a higher level too."
                ),
                required=[
                    EvidenceClause(
                        name="completion timeout observed",
                        pattern=r"completion timeout|\bcto\b|no completion (?:received|returned)",
                        must_fail=True,
                    ),
                ],
                optional=[
                    EvidenceClause(name="flow control implicated", pattern=r"flow control|credit"),
                ],
                typical_causes=[
                    "Completer's request queue full and the request was silently dropped",
                    "Completion routed with the wrong requester ID / tag",
                    "Flow-control credit starvation prevents the completion from ever posting",
                    "Multi-function device returns the completion to the wrong function",
                ],
                ownership="design",
                suggested_signals=["TLP tag/requester ID", "completer queue occupancy", "UpdateFC DLLP"],
                playbook_id="pcie.completion-debug",
                confidence_modifiers={"rtl_bug": 0.10, "testbench_issue": 0.03},
                references=[Reference(source=_SPEC, section="2.9", note="Completion timeout detection.")],
            ),
            FailurePattern(
                id="pcie.credit-starvation",
                name="Flow-control credit starvation",
                summary=(
                    "One TLP class stopped moving while others kept flowing: "
                    "UpdateFC returns for that class stalled, throttling it to "
                    "zero without any reported link error."
                ),
                required=[
                    EvidenceClause(
                        name="credit stall observed",
                        pattern=r"(?:fc|flow.control) credit.*(?:stall|starv|exhaust|never return)|updatefc.*(?:missing|stopped)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Receiver buffer drain path stuck for one TLP class",
                    "UpdateFC scheduler starved by higher-priority DLLPs",
                    "Credit accounting bug double-consumes or under-reports a class",
                ],
                ownership="design",
                suggested_signals=["per-class credit counters", "UpdateFC DLLP cadence"],
                playbook_id="pcie.credit-debug",
                confidence_modifiers={"rtl_bug": 0.10},
                references=[Reference(source=_SPEC, section="2.6.1", note="Flow control credit types and updates.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="pcie.link-training-debug",
                name="LTSSM link training debug",
                steps=[
                    PlaybookStep(action="Capture the LTSSM state trace from reset to the stall", signals=["LTSSM state"]),
                    PlaybookStep(action="Identify the last state reached and the state it should transition to", detail="Cross-reference against the spec's LTSSM diagram."),
                    PlaybookStep(action="Check per-lane bit lock, symbol lock, and polarity", signals=["per-lane lock status"]),
                    PlaybookStep(action="Verify reference clock and reset timing against the budget"),
                    PlaybookStep(action="For Gen3+, check equalization convergence per lane"),
                ],
            ),
            DebugPlaybook(
                id="pcie.completion-debug",
                name="Completion timeout debug",
                steps=[
                    PlaybookStep(action="Identify the outstanding request's tag and requester ID", signals=["TLP tag/requester ID"]),
                    PlaybookStep(action="Check the completer's request queue for that tag", detail="Was it accepted, and did it ever get processed?"),
                    PlaybookStep(action="Confirm the completion TLP (if any) was routed back correctly", detail="Wrong tag/requester ID routing is the most common miss."),
                    PlaybookStep(action="Check flow-control credits on the completion class at the time", signals=["UpdateFC DLLP"]),
                ],
            ),
            DebugPlaybook(
                id="pcie.credit-debug",
                name="Flow-control credit debug",
                steps=[
                    PlaybookStep(action="Plot per-class credit counters across the run", signals=["per-class credit counters"]),
                    PlaybookStep(action="Find the class that stopped receiving UpdateFC returns"),
                    PlaybookStep(action="Trace that class's receiver buffer drain path", detail="A stuck consumer explains the missing credit return."),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary protocol reference for this pack.")],
    )
