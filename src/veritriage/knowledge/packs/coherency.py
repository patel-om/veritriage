"""Cache coherency Knowledge Pack.

Protocol-agnostic MESI/MOESI coherency knowledge, complementary to the
interconnect-specific CHI pack: state-transition legality, ordering, and the
failure signatures a broken coherency implementation leaves regardless of
which physical protocol carries the messages.
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

_REF = "Sorin, Hill & Wood, \"A Primer on Memory Consistency and Cache Coherence\""


@register_pack
def coherency_pack() -> KnowledgePack:
    return KnowledgePack(
        id="coherency",
        name="Cache coherency",
        version="1.0.0",
        domain="coherency",
        summary="MESI/MOESI state legality, coherence ordering, and multi-copy consistency failures.",
        concepts=[
            Concept(
                id="coherency.mesi",
                name="MESI/MOESI cache states",
                summary=(
                    "Every cache line is Modified, Exclusive, Shared, Invalid (or "
                    "Owned, under MOESI). Only one cache may hold Modified/"
                    "Exclusive at a time; any coherent read must observe the most "
                    "recent write. A state-transition table violation is a "
                    "coherency bug regardless of which interconnect carries the "
                    "messages."
                ),
                markers=[r"\bmesi\b|\bmoesi\b", r"\bmodified\b.*\bcache\b|\bexclusive\b.*\bcache\b|\bshared\b.*\bcache\b", r"coherenc(?:e|y) state"],
                references=[Reference(source=_REF, note="MESI/MOESI state machines.")],
            ),
            Concept(
                id="coherency.multi-copy",
                name="Multi-copy atomicity",
                summary=(
                    "A coherent write must appear to happen at a single point in "
                    "time to every observer; two masters must never simultaneously "
                    "believe they hold exclusive/modified ownership of the same "
                    "line. Violating this is invisible in a single-master test and "
                    "appears only under concurrent multi-master traffic."
                ),
                markers=[r"multi-?copy atomic", r"dual ownership|two masters.*(?:exclusive|modified)", r"coherency violation"],
                references=[Reference(source=_REF, note="Multi-copy atomicity requirement.")],
            ),
        ],
        state_machines=[
            StateMachine(
                id="coherency.line-lifecycle",
                name="Coherent line lifecycle (miss to eviction)",
                states=[
                    ProtocolState(
                        name="Miss detected",
                        description="Local cache misses and issues a coherence request.",
                        markers=[r"cache miss", r"coherence request (?:sent|issued)"],
                    ),
                    ProtocolState(
                        name="Directory/snoop resolved",
                        description="Directory lookup or broadcast snoop determines sharers.",
                        markers=[r"directory looked? up|directory hit|snoop (?:resolved|complete)"],
                    ),
                    ProtocolState(
                        name="Data granted",
                        description="Data returns with the granted state.",
                        markers=[r"data granted|line (?:filled|returned)"],
                    ),
                    ProtocolState(
                        name="Stable",
                        description="Line settles into a stable coherence state until the next request.",
                        markers=[r"line stable|coherence state (?:settled|stable)"],
                    ),
                ],
            ),
        ],
        patterns=[
            FailurePattern(
                id="coherency.illegal-transition",
                name="Illegal coherence state transition",
                summary=(
                    "A cache line moved between states in a way the coherence "
                    "protocol does not permit (e.g. Invalid directly to Modified "
                    "without a request, or two caches both reaching Modified for "
                    "the same line)."
                ),
                required=[
                    EvidenceClause(
                        name="illegal transition observed",
                        pattern=r"illegal (?:coherence )?(?:state )?transition|coherence (?:state )?violation|invalid state transition",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "State-transition table implemented with a missing or swapped case",
                    "Race between an incoming snoop and a local request updating the same state register",
                    "Directory entry not updated atomically with the data response",
                ],
                ownership="design",
                suggested_signals=["cache line state register", "directory entry for the line", "concurrent request/snoop timing"],
                playbook_id="coherency.transition-debug",
                confidence_modifiers={"rtl_bug": 0.14},
                references=[Reference(source=_REF, note="Legal state-transition tables.")],
            ),
            FailurePattern(
                id="coherency.stale-read",
                name="Read observes stale data after a coherent write",
                summary=(
                    "A read completed successfully at the protocol level but "
                    "returned data older than a write that coherence rules say it "
                    "must observe: the transport succeeded while the coherence "
                    "guarantee did not."
                ),
                required=[
                    EvidenceClause(
                        name="scoreboard mismatch",
                        pattern=r"scoreboard|mismatch|miscompare|expected\b.*\b(?:got|actual)",
                        must_fail=True,
                    ),
                    EvidenceClause(
                        name="coherency context",
                        pattern=r"coherenc|\bmesi\b|\bmoesi\b|multiple (?:masters|caches)",
                    ),
                ],
                typical_causes=[
                    "Write-back ordering allows a later read to race ahead of the eviction",
                    "Snoop response returns before the local write it should reflect has committed",
                    "Directory serves a stale sharer list",
                ],
                ownership="design",
                suggested_signals=["write-back queue", "snoop response timing vs local commit"],
                playbook_id="coherency.stale-read-debug",
                confidence_modifiers={"rtl_bug": 0.10, "testbench_issue": 0.03},
                references=[Reference(source=_REF, note="Coherence invariant: reads observe the most recent write.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="coherency.transition-debug",
                name="Illegal coherence transition debug",
                steps=[
                    PlaybookStep(action="Identify the line address and the two states involved", signals=["cache line state register"]),
                    PlaybookStep(action="Check the directory/snoop-filter entry for that line at the same time", signals=["directory entry for the line"]),
                    PlaybookStep(action="Look for a concurrent request and snoop touching the same line", detail="Most illegal transitions are races, not simple logic bugs."),
                    PlaybookStep(action="Re-run with only one master active", detail="If the violation disappears, it is concurrency-dependent."),
                ],
            ),
            DebugPlaybook(
                id="coherency.stale-read-debug",
                name="Stale-read-after-write debug",
                steps=[
                    PlaybookStep(action="Find the write and the read that observed stale data, in address and time order"),
                    PlaybookStep(action="Check the write-back/commit timing relative to the read's snoop or directory lookup"),
                    PlaybookStep(action="Verify the sharer list used to serve the read was current at request time"),
                    PlaybookStep(action="Re-run with reduced concurrency to confirm the ordering dependency"),
                ],
            ),
        ],
        references=[Reference(source=_REF, note="Primary methodology reference for this pack.")],
    )
