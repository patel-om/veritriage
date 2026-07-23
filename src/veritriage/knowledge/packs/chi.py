"""AMBA CHI Knowledge Pack.

CHI is the coherent hub interface: credited channels, request/snoop/data/
response flows between RN/HN/SN nodes. Its characteristic failures are
credit starvation, snoop-response deadlocks, and ordering violations that
only appear under concurrent coherent traffic.
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

_SPEC = "AMBA CHI Architecture Specification (IHI 0050)"


@register_pack
def chi_pack() -> KnowledgePack:
    return KnowledgePack(
        id="chi",
        name="AMBA CHI",
        version="1.0.0",
        domain="protocol",
        summary="CHI credited channels, transaction flows, snoops, and retry semantics.",
        concepts=[
            Concept(
                id="chi.credits",
                name="Link-layer credits (L-credits)",
                summary=(
                    "Every CHI channel is credited: a flit may only be sent when the "
                    "receiver has granted an L-credit. Lost or leaked credits are "
                    "invisible in any single transaction and appear only as gradual "
                    "throughput collapse or a full stop once the pool empties."
                ),
                markers=[r"\bchi\b.*credit|l-?credit", r"credit (?:starv|leak|exhaust|underflow|return)"],
                references=[Reference(source=_SPEC, section="12.2", note="Link flit control and L-credits.")],
            ),
            Concept(
                id="chi.transaction-flow",
                name="Request/response/data flows",
                summary=(
                    "A CHI transaction is a REQ flit answered by RSP/DAT flits, "
                    "possibly after the home node snoops other RNs (SNP channel). "
                    "Completion rules (Comp, CompData, CompAck) define when the "
                    "requester may consider the transaction done and when the home "
                    "node may free its tracker entry."
                ),
                markers=[r"\bchi\b", r"\breqflit\b|\brspflit\b|\bdatflit\b", r"\bcompack\b|\bcompdata\b|\bcomp\b.*flit", r"home node|\bhn-?f\b|\brn-?f\b"],
                references=[Reference(source=_SPEC, section="2.3", note="Transaction structure.")],
            ),
            Concept(
                id="chi.retry",
                name="Retry and P-credits",
                summary=(
                    "A home node without a free tracker returns RetryAck and later "
                    "grants a P-credit (PCrdGrant); the requester must re-send with "
                    "that credit type. A PCrdGrant that never arrives, or arrives "
                    "with the wrong credit type, strands the request forever."
                ),
                markers=[r"retryack", r"p-?credit|pcrdgrant|pcrdtype"],
                references=[Reference(source=_SPEC, section="2.11", note="Retry mechanism.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="TXREQFLITV", role="request flit valid", channel="REQ"),
            ProtocolSignal(name="RXRSPFLITV", role="response flit valid", channel="RSP"),
            ProtocolSignal(name="RXDATFLITV", role="data flit valid", channel="DAT"),
            ProtocolSignal(name="RXSNPFLITV", role="snoop flit valid", channel="SNP"),
            ProtocolSignal(name="LCRDV", role="link credit valid (per channel)"),
        ],
        state_machines=[
            StateMachine(
                id="chi.read-flow",
                name="CHI read flow",
                states=[
                    ProtocolState(
                        name="Request sent",
                        description="RN sends ReadShared/ReadUnique on REQ.",
                        markers=[r"read(?:shared|unique|once|clean)", r"req(?:uest)? (?:sent|issued)", r"\breqflit\b"],
                    ),
                    ProtocolState(
                        name="Snoops issued",
                        description="HN snoops other RNs for the line.",
                        markers=[r"snoop (?:sent|issued)", r"\bsnpflit\b", r"snp(?:shared|unique|clean)"],
                    ),
                    ProtocolState(
                        name="Data returned",
                        description="CompData beats arrive at the requester.",
                        markers=[r"compdata", r"data flit (?:received|returned)", r"\bdatflit\b.*(?:received|returned)"],
                    ),
                    ProtocolState(
                        name="Complete",
                        description="CompAck sent; HN frees the tracker entry.",
                        markers=[r"compack", r"transaction complete", r"tracker (?:freed|deallocat)"],
                    ),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="chi.credit-starvation",
                name="Link credit starvation",
                summary=(
                    "A channel ran out of L-credits and never received returns: "
                    "traffic on that channel stopped while the rest of the system "
                    "looked idle, ending in a timeout."
                ),
                required=[
                    EvidenceClause(
                        name="credit exhaustion observed",
                        pattern=r"credit (?:starv|exhaust|leak|underflow)|no .*credit|l-?credit.*(?:zero|empty|never)",
                        must_fail=True,
                    ),
                ],
                optional=[
                    EvidenceClause(name="timeout follow-on", pattern=r"time[- ]?out|watchdog", must_fail=True),
                ],
                typical_causes=[
                    "Receiver frees the buffer but skips the credit return (leak)",
                    "Credit counter reset to the wrong initial value",
                    "Credit returned on the wrong virtual channel",
                    "Flit accepted without a credit check, corrupting the accounting",
                ],
                ownership="design",
                suggested_signals=["LCRDV per channel", "credit counters", "flit valid/accept per channel"],
                playbook_id="chi.credit-audit",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="12.2.2", note="Credit return rules.")],
            ),
            FailurePattern(
                id="chi.snoop-no-response",
                name="Snoop never answered",
                summary=(
                    "The home node issued a snoop and the snooped RN never "
                    "responded; the original transaction (and everything ordered "
                    "behind its tracker entry) is stuck."
                ),
                required=[
                    EvidenceClause(
                        name="snoop outstanding",
                        pattern=r"snoop .*(?:outstanding|pending|no resp|never|stuck|timeout)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "RN's snoop handler deadlocked against its own outstanding request (same address)",
                    "Snoop filter directory says the RN holds a line it silently evicted",
                    "SnpResp lost across a clock/power domain boundary",
                ],
                ownership="design",
                suggested_signals=["SNP channel flits", "RN snoop handler state", "snoop filter entry for the address"],
                playbook_id="chi.snoop-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="4.7", note="Snoop request and response rules.")],
            ),
            FailurePattern(
                id="chi.retry-without-grant",
                name="RetryAck without PCrdGrant",
                summary=(
                    "A request received RetryAck but the matching PCrdGrant never "
                    "arrived (or carried the wrong credit type), stranding the "
                    "request at the requester forever."
                ),
                required=[
                    EvidenceClause(
                        name="retry without grant observed",
                        pattern=r"retryack.*(?:no|without|missing).*(?:grant|credit)|pcrdgrant.*(?:missing|never|wrong)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "HN tracker frees without issuing the promised grant",
                    "PCrdType mismatch between grant and re-request",
                    "Grant sent to the wrong requester ID",
                ],
                ownership="design",
                suggested_signals=["RetryAck flits", "PCrdGrant flits", "requester pending-retry state"],
                playbook_id="chi.retry-debug",
                confidence_modifiers={"rtl_bug": 0.10},
                references=[Reference(source=_SPEC, section="2.11.2", note="P-credit grant and use.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="chi.credit-audit",
                name="CHI credit audit",
                steps=[
                    PlaybookStep(action="Plot credit counters per channel over the whole run", detail="A monotonic drift toward zero is a leak; a cliff is a reset/accounting bug.", signals=["credit counters"]),
                    PlaybookStep(action="Count LCRDV grants vs flits sent per channel", detail="The difference must equal the initial pool.", signals=["LCRDV", "flit valid"]),
                    PlaybookStep(action="Find the first buffer-free without a credit return", detail="That is the leaking path."),
                    PlaybookStep(action="Check virtual-channel mapping of returns", detail="Credits returned to the wrong VC starve one channel while over-crediting another."),
                ],
            ),
            DebugPlaybook(
                id="chi.snoop-debug",
                name="Snoop deadlock debug",
                steps=[
                    PlaybookStep(action="Identify the snooped RN and the address", signals=["SNP flit fields"]),
                    PlaybookStep(action="Dump that RN's outstanding requests for the same line", detail="Same-address request/snoop interlock is the classic deadlock."),
                    PlaybookStep(action="Compare the snoop filter entry against the RN's actual cache state", detail="A stale directory snoops a line nobody holds."),
                    PlaybookStep(action="Trace the SnpResp path across domain boundaries", detail="Lost responses at crossings look identical to a hung handler."),
                ],
            ),
            DebugPlaybook(
                id="chi.retry-debug",
                name="Retry/P-credit debug",
                steps=[
                    PlaybookStep(action="Match every RetryAck to a later PCrdGrant by requester and type", signals=["RetryAck", "PCrdGrant"]),
                    PlaybookStep(action="For unmatched RetryAcks, dump the HN tracker at that time", detail="Find why the grant was never generated."),
                    PlaybookStep(action="Check PCrdType consistency between grant and re-issued request"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary protocol reference for this pack.")],
    )
