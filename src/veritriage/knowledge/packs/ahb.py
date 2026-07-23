"""AMBA AHB Knowledge Pack.

AHB's pipelined address/data phases and single shared HREADY create failure
modes AXI does not have: one stalling slave freezes the whole bus, ERROR
responses need a two-cycle protocol, and bursts interact with arbitration.
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

_SPEC = "AMBA AHB Protocol Specification (IHI 0033)"


@register_pack
def ahb_pack() -> KnowledgePack:
    return KnowledgePack(
        id="ahb",
        name="AMBA AHB",
        version="1.0.0",
        domain="protocol",
        summary="AHB pipelined phases, HREADY stalling, ERROR responses, and bursts.",
        concepts=[
            Concept(
                id="ahb.pipeline",
                name="Pipelined address and data phases",
                summary=(
                    "AHB overlaps the address phase of transfer N+1 with the data "
                    "phase of transfer N; HREADY low extends the current data phase "
                    "and freezes the address phase behind it. Because HREADY is "
                    "shared, one slow slave stalls every master on the layer."
                ),
                markers=[r"\bahb\b", r"\bhtrans\b", r"\bhready\b", r"address phase", r"data phase"],
                references=[Reference(source=_SPEC, section="3.1", note="Basic transfer pipeline.")],
            ),
            Concept(
                id="ahb.response",
                name="Two-cycle ERROR response",
                summary=(
                    "An AHB slave signals ERROR over two cycles (HRESP=ERROR with "
                    "HREADY low, then high), giving the master one cycle to cancel "
                    "the following transfer. Slaves that assert it for one cycle, "
                    "and masters that ignore the cancel window, both corrupt the "
                    "pipeline."
                ),
                markers=[r"\bhresp\b", r"ahb .*error response", r"\bretry\b.*response|\bsplit\b.*response"],
                references=[Reference(source=_SPEC, section="5.1", note="Slave transfer responses.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="HTRANS", role="transfer type (IDLE/BUSY/NONSEQ/SEQ)"),
            ProtocolSignal(name="HREADY", role="shared transfer-done"),
            ProtocolSignal(name="HRESP", role="transfer response (OKAY/ERROR/RETRY/SPLIT)"),
            ProtocolSignal(name="HBURST", role="burst type"),
            ProtocolSignal(name="HGRANT", role="arbiter grant"),
        ],
        state_machines=[
            StateMachine(
                id="ahb.transfer",
                name="AHB transfer",
                states=[
                    ProtocolState(
                        name="Grant",
                        description="Arbiter grants the master the address phase.",
                        markers=[r"\bhgrant\b", r"bus grant"],
                    ),
                    ProtocolState(
                        name="Address phase",
                        description="HTRANS NONSEQ/SEQ drives address and controls.",
                        markers=[r"\bnonseq\b", r"\bhtrans\b", r"address phase"],
                    ),
                    ProtocolState(
                        name="Data phase",
                        description="Data transfers while HREADY high; wait states while low.",
                        markers=[r"data phase", r"wait state", r"hready.*low"],
                    ),
                    ProtocolState(
                        name="Response",
                        description="OKAY/ERROR/RETRY/SPLIT returned with HREADY high.",
                        markers=[r"\bOKAY\b", r"hresp (?:okay|error|retry|split)", r"transfer complete"],
                    ),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="ahb.hready-stall",
                name="Bus frozen by HREADY held low",
                summary=(
                    "A slave held HREADY low indefinitely; because HREADY is shared, "
                    "the entire layer (all masters, all pending transfers) froze "
                    "behind one data phase."
                ),
                required=[
                    EvidenceClause(
                        name="timeout or hang observed",
                        pattern=r"time[- ]?out|watchdog|hung|frozen|stuck",
                        must_fail=True,
                    ),
                    EvidenceClause(
                        name="AHB stall context",
                        pattern=r"\bahb\b.*(?:stall|wait|pending)|hready.*(?:low|stuck|never)|wait state",
                    ),
                ],
                typical_causes=[
                    "Slave wait-state counter never terminates (missing max-wait bound)",
                    "Default slave missing: access to a hole waits forever",
                    "SPLIT issued but the split-capable slave never un-splits",
                    "Bridge to a slower domain loses the transfer across the crossing",
                ],
                ownership="design",
                suggested_signals=["HREADY", "HTRANS", "HSEL per slave", "arbiter state"],
                playbook_id="ahb.stall",
                confidence_modifiers={"rtl_bug": 0.10},
                references=[Reference(source=_SPEC, section="5.1.1", note="Transfer done requires HREADY high.")],
            ),
            FailurePattern(
                id="ahb.retry-loop",
                name="Repeated RETRY loop",
                summary=(
                    "The master re-issues a transfer that keeps receiving RETRY "
                    "(or SPLIT) forever: no forward progress, often ending in a "
                    "watchdog timeout with the same address replayed."
                ),
                required=[
                    EvidenceClause(
                        name="repeated retry observed",
                        pattern=r"retry (?:loop|storm|repeat)|repeated retr|\bretry\b.*(?:again|forever|limit)",
                        must_fail=True,
                    ),
                ],
                optional=[
                    EvidenceClause(name="timeout follow-on", pattern=r"time[- ]?out|watchdog", must_fail=True),
                ],
                typical_causes=[
                    "Slave's busy condition never clears (dependent resource deadlock)",
                    "Retry issued instead of wait states for a permanently unavailable target",
                    "Arbiter re-grants the retried master immediately, starving the unblocking master",
                ],
                ownership="design",
                suggested_signals=["HRESP", "HTRANS", "arbiter grants", "slave busy condition"],
                playbook_id="ahb.retry",
                confidence_modifiers={"rtl_bug": 0.10, "infrastructure_issue": -0.03},
                references=[Reference(source=_SPEC, section="5.1.3", note="RETRY response and re-arbitration.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="ahb.stall",
                name="AHB bus stall",
                steps=[
                    PlaybookStep(action="Find which slave is selected in the stuck data phase", signals=["HSEL", "HADDR"]),
                    PlaybookStep(action="Inspect that slave's wait-state generation", detail="Look for an unbounded internal wait.", signals=["HREADY"]),
                    PlaybookStep(action="Check the address decodes to a mapped region", detail="A missing default slave turns holes into hangs."),
                    PlaybookStep(action="If a bridge is involved, trace the transfer across the domain crossing", detail="Lost-event CDC bugs surface exactly here."),
                    PlaybookStep(action="Add or verify a bus watchdog assertion on maximum wait states"),
                ],
            ),
            DebugPlaybook(
                id="ahb.retry",
                name="RETRY loop analysis",
                steps=[
                    PlaybookStep(action="Count RETRY responses per address", detail="Identify the address that never succeeds.", signals=["HRESP", "HADDR"]),
                    PlaybookStep(action="Find the slave condition that triggers RETRY", detail="What resource is it waiting on?"),
                    PlaybookStep(action="Check whether that resource depends on the retrying master", detail="Classic circular dependency: the retry blocks the unblock."),
                    PlaybookStep(action="Review arbiter fairness under RETRY", signals=["HGRANT"]),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary protocol reference for this pack.")],
    )
