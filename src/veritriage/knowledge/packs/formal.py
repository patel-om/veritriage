"""Formal property verification (FPV) Knowledge Pack.

Assertion-based formal: assert/assume/cover properties, vacuity, and bounded
proofs. This pack encodes the domain knowledge (counterexample, vacuous pass,
inconclusive bound); the verdicts it matches arrive as first-class evidence
either from a tool log or, since v1.6.0, natively via the ``formal_result``
parser (ArtifactType.FORMAL_RESULT), which ingests a ``*.formal.json`` and
phrases each node so these patterns match. Parser first, pack on top.
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

_SPEC = "SystemVerilog Assertions / formal property verification methodology"


@register_pack
def formal_pack() -> KnowledgePack:
    return KnowledgePack(
        id="formal",
        name="Formal property verification",
        version="1.0.0",
        domain="formal",
        summary="FPV counterexamples, vacuity, and inconclusive bounded proofs.",
        concepts=[
            Concept(
                id="formal.properties",
                name="Assert / assume / cover",
                summary=(
                    "Formal proves assertions hold for all legal inputs constrained "
                    "by assumptions, and that cover properties are reachable. An "
                    "assertion that fails produces a counterexample trace; the "
                    "constraint set (assumes) determines what 'legal' means, so "
                    "over-constraint can hide real failures."
                ),
                markers=[r"\bassert\b|\bassume\b|\bcover\b", r"property|formal", r"counterexample|\bcex\b"],
                references=[Reference(source=_SPEC, section="FPV", note="Assert/assume/cover semantics.")],
            ),
            Concept(
                id="formal.vacuity",
                name="Vacuity and proof bound",
                summary=(
                    "A property passes vacuously when its antecedent is never "
                    "satisfied, so it proves nothing. Bounded proofs establish a "
                    "property only up to a depth; an inconclusive result at the bound "
                    "is not a proof. Both are 'green' that is not actually coverage."
                ),
                markers=[r"vacu(?:ous|ity)", r"proof (?:bound|depth)|bounded proof", r"inconclusive|unreachable"],
                references=[Reference(source=_SPEC, section="FPV", note="Vacuity and bounded-proof caveats.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="formal.counterexample",
                name="Property falsified with a counterexample",
                summary=(
                    "A formal assertion was disproven: the tool produced a "
                    "counterexample trace showing legal inputs that violate the "
                    "property."
                ),
                required=[
                    EvidenceClause(
                        name="counterexample found",
                        pattern=r"formal.*(?:counterexample|cex)|property.*(?:failed|falsified).*(?:cex|counterexample)|assertion.*proven false",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="formal context", pattern=r"formal|property|assert|counterexample"),
                ],
                typical_causes=[
                    "Genuine RTL bug the counterexample exercises",
                    "Property written stronger than the design intends",
                    "Missing assumption that the counterexample relies on (under-constraint)",
                ],
                ownership="design",
                suggested_signals=["counterexample trace", "property expression", "constraint set"],
                playbook_id="formal.cex-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="FPV", note="Counterexample interpretation.")],
            ),
            FailurePattern(
                id="formal.vacuous-pass",
                name="Property passed vacuously",
                summary=(
                    "A property reported pass but did so vacuously: its antecedent "
                    "was never satisfied (or a cover was unreachable), so it verified "
                    "nothing and the green result is misleading."
                ),
                required=[
                    EvidenceClause(
                        name="vacuous result",
                        pattern=r"vacuous(?:ly)?|(?:antecedent|precondition) never (?:true|satisfied|reached)|cover.*unreachable|vacuity (?:detected|check)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Over-constraint (an assume) makes the antecedent unreachable",
                    "Property antecedent references a condition the design never produces",
                    "Cover target genuinely dead code",
                ],
                ownership="testbench",
                suggested_signals=["antecedent reachability", "assumption set", "cover status"],
                playbook_id="formal.vacuity-debug",
                confidence_modifiers={"testbench_issue": 0.10},
                references=[Reference(source=_SPEC, section="FPV", note="Vacuous pass proves nothing.")],
            ),
            FailurePattern(
                id="formal.inconclusive-bound",
                name="Proof inconclusive at bound",
                summary=(
                    "A bounded proof did not converge: the property is neither proven "
                    "nor falsified within the explored depth, so it must not be "
                    "reported as fully verified."
                ),
                required=[
                    EvidenceClause(
                        name="inconclusive proof",
                        pattern=r"inconclusive.*(?:bound|depth|proof)|bounded proof.*(?:inconclusive|not full)|proof depth.*(?:insufficient|reached).*(?:inconclusive|limit)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "State space too large to converge without abstraction",
                    "Proof depth set too shallow for the property's latency",
                    "Missing helper assertions/lemmas to bound the problem",
                ],
                ownership="testbench",
                suggested_signals=["proof depth", "engine status", "abstraction"],
                playbook_id="formal.bound-debug",
                confidence_modifiers={"testbench_issue": 0.08},
                references=[Reference(source=_SPEC, section="FPV", note="Bounded proofs are not full proofs.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="formal.cex-debug",
                name="Counterexample debug",
                steps=[
                    PlaybookStep(action="Walk the counterexample trace to the first cycle the property breaks", signals=["counterexample trace"]),
                    PlaybookStep(action="Decide whether the trace is a legal scenario or an under-constraint", signals=["constraint set"]),
                    PlaybookStep(action="If legal, treat as an RTL bug; if illegal, add the missing assumption"),
                    PlaybookStep(action="Re-run and confirm the counterexample no longer appears"),
                ],
            ),
            DebugPlaybook(
                id="formal.vacuity-debug",
                name="Vacuity debug",
                steps=[
                    PlaybookStep(action="Check antecedent reachability with a cover on the precondition", signals=["antecedent reachability"]),
                    PlaybookStep(action="Review assumptions for over-constraint", signals=["assumption set"]),
                    PlaybookStep(action="Confirm the design can actually produce the trigger condition"),
                    PlaybookStep(action="Rule out genuinely dead cover targets"),
                ],
            ),
            DebugPlaybook(
                id="formal.bound-debug",
                name="Bounded-proof debug",
                steps=[
                    PlaybookStep(action="Note the depth reached and the engine status", signals=["proof depth", "engine status"]),
                    PlaybookStep(action="Increase depth or apply abstraction to reach convergence", signals=["abstraction"]),
                    PlaybookStep(action="Add helper lemmas to shrink the state space"),
                    PlaybookStep(action="Do not sign off the property until it is proven or bounded-covered"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for formal methodology.")],
    )
