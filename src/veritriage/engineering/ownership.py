"""Ownership: who to loop in, computed deterministically, never used for ranking.

Ownership entries arrive from providers (v1: the context manifest; future:
CODEOWNERS or Perforce-protections providers). This module's single output is
one extra :class:`EngineeringRecommendation` naming the owner whose scope
matches the failing evidence, appended additively after reasoning completed.

The law (architecture-test enforced): the reasoning and rules packages never
import this module, and no ownership-derived ReasoningSignal exists anywhere.
Ownership routes people; it never weighs hypotheses.
"""

from __future__ import annotations

from veritriage.engineering.model import Ownership
from veritriage.graph.graph import EvidenceGraph
from veritriage.models import AnalysisReport, EngineeringRecommendation


def match_owner(scope_haystack: str, ownership: tuple[Ownership, ...]) -> Ownership | None:
    """The first ownership entry whose scope token appears in the haystack.

    Scope matching is deliberately conservative: the entry's scope, lowercased,
    must appear verbatim in the failing evidence's module path or source file.
    First declared match wins, so manifests can order by specificity.
    """
    lowered = scope_haystack.lower()
    for entry in ownership:
        token = entry.scope.lower()
        if len(token) >= 3 and token in lowered:
            return entry
    return None


def ownership_recommendation(
    report: AnalysisReport,
    graph: EvidenceGraph,
    ownership: tuple[Ownership, ...],
) -> EngineeringRecommendation | None:
    """One routing recommendation for the failing scope's owner, or None.

    Haystacks come from the evidence the top hypothesis cites (the most
    specific signal available), resolved through the graph to their module
    paths and source files; classification evidence is the fallback when
    reasoning produced nothing. Priority is assigned by the caller (appended
    last); confidence is the ownership entry's own confidence discounted, as
    routing advice sits below anything evidential.
    """
    cited_ids: list[str] = []
    if report.reasoning is not None and report.reasoning.hypotheses:
        cited_ids.extend(report.reasoning.hypotheses[0].evidence_ids)
    cited_ids.extend(
        item.node_id for item in report.classification.evidence if item.node_id
    )

    for node_id in cited_ids:
        node = graph.nodes.get(node_id)
        if node is None:
            continue
        haystack = f"{node.module or ''} {node.attributes.get('source_file') or ''}".strip()
        if not haystack:
            continue
        entry = match_owner(haystack, ownership)
        if entry is not None:
            return EngineeringRecommendation(
                action=(
                    f"Loop in {entry.owner} ({entry.role} owner of '{entry.scope}'): "
                    f"the failing scope falls under their ownership"
                ),
                rationale=(
                    f"Ownership metadata from the {entry.source} provider maps "
                    f"'{entry.scope}' to {entry.owner}; routing advice only, not a diagnosis."
                ),
                priority=1,  # caller reassigns to append after existing steps
                effort="low",
                confidence=round(entry.confidence * 0.8, 4),
                module=entry.scope,
                evidence_ids=[node_id],
            )
    return None
