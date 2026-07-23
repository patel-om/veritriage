"""SystemVerilog Assertions methodology Knowledge Pack.

SVA knowledge is protocol-agnostic: it teaches VeriTriage what an assertion
*failure message shape* implies about the check itself, independent of
which protocol the assertion was written for. This is deliberately
complementary to the per-protocol packs, which teach what the checked
behavior means.
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

_SPEC = "IEEE 1800-2023 (SystemVerilog), Chapter 16 (Assertions)"


@register_pack
def sva_pack() -> KnowledgePack:
    return KnowledgePack(
        id="sva",
        name="SystemVerilog Assertions",
        version="1.0.0",
        domain="methodology",
        summary="Assertion failure semantics: immediate vs concurrent, stability, and liveness checks.",
        concepts=[
            Concept(
                id="sva.concurrent-vs-immediate",
                name="Concurrent vs immediate assertions",
                summary=(
                    "Immediate assertions check a condition procedurally, at a "
                    "point in simulation time; concurrent assertions (property/"
                    "sequence) check a temporal relationship across cycles, "
                    "clocked and often disabled during reset. A concurrent "
                    "assertion firing means a multi-cycle protocol relationship "
                    "was violated, not just one bad value."
                ),
                markers=[r"\bassert\b", r"\bproperty\b", r"\bsequence\b", r"concurrent assertion", r"immediate assertion"],
                references=[Reference(source=_SPEC, section="16.4", note="Concurrent assertions.")],
            ),
            Concept(
                id="sva.liveness-vs-safety",
                name="Safety vs liveness properties",
                summary=(
                    "A safety property says something bad never happens (a signal "
                    "never goes X, VALID never drops early); it fails at a "
                    "specific cycle. A liveness property says something good "
                    "eventually happens (a request eventually gets a response); "
                    "it fails only when bounded by a timeout, so a liveness "
                    "assertion firing is functionally a categorized timeout."
                ),
                markers=[r"\beventually\b", r"liveness", r"safety propert", r"\bs_eventually\b"],
                references=[Reference(source=_SPEC, section="16.12.8", note="Sequence and property eventually operators.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="sva.assertion-before-timeout",
                name="Assertion fires before the timeout that would have followed",
                summary=(
                    "A protocol assertion fired earlier in the run than the "
                    "eventual test timeout: the assertion already localizes the "
                    "root cause precisely, and the timeout is a downstream "
                    "consequence, not independent evidence."
                ),
                required=[
                    EvidenceClause(
                        name="assertion failure present",
                        pattern=r".",
                        artifact_types=["assertion"],
                        must_fail=True,
                    ),
                    EvidenceClause(
                        name="timeout also present",
                        pattern=r"time[- ]?out|watchdog|PH_TIMEOUT",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "The assertion pinpoints the true root cause; the timeout is the test giving up afterward",
                    "A second, unrelated hang coincidentally shares the run with an early assertion",
                ],
                ownership="design",
                suggested_signals=["signals named in the assertion's expression"],
                playbook_id="sva.assertion-first",
                confidence_modifiers={"rtl_bug": 0.06},
                references=[Reference(source=_SPEC, section="16.4", note="Concurrent assertion evaluation model.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="sva.assertion-first",
                name="Assertion-first triage",
                steps=[
                    PlaybookStep(action="Anchor debugging at the assertion's fire time, not the timeout", detail="The assertion is earlier and more specific evidence."),
                    PlaybookStep(action="Read the property expression and identify each signal it references"),
                    PlaybookStep(action="Check those signals at and just before the fire time", signals=["signals named in the assertion's expression"]),
                    PlaybookStep(action="Only after explaining the assertion, check whether the later timeout is a separate issue"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary methodology reference for this pack.")],
    )
