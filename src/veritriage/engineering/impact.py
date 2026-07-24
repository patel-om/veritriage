"""Test impact analysis: which tests are most likely affected by a change.

Two deterministic tiers, both pure functions of their inputs:

* **In-run** (:func:`impacted_tests_in_run`): does the *current* run's test
  touch a changed module? Uses only the context and the Evidence Graph, so it
  can run inside the pure pipeline with no storage access.

* **Historical** (:func:`impacted_tests_from_history`): which tests have
  *historically* failed in the changed modules? Takes pre-extracted
  :class:`HistoricalRegression` slices (the CLI maps stored records into
  these), so this package never imports the storage layer.

Impact output is evidence-shaped: scores with reasons and citations, never a
verdict. Same inputs, same output, byte for byte
(``test_impact_is_deterministic`` pins it).
"""

from __future__ import annotations

from veritriage.engineering.model import EngineeringContext, HistoricalRegression
from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType
from veritriage.models.engineering import ImpactedTestView

#: Historical scoring: each failure in a changed module contributes this much,
#: saturating at 1.0. Deliberately simple and inspectable.
_PER_FAILURE_WEIGHT = 0.25


def _overlap(changed_modules: list[str], haystack: str) -> list[str]:
    """Changed modules whose token appears in the haystack, in order."""
    lowered = haystack.lower()
    return [m for m in changed_modules if len(m) >= 3 and m.lower() in lowered]


def impacted_tests_in_run(
    context: EngineeringContext, graph: EvidenceGraph
) -> list[ImpactedTestView]:
    """Impact for the current run: its test vs the changed modules.

    A hit means the run's failing evidence lives in scopes that recent
    commits touched: the strongest possible in-run impact signal, cited by
    the overlapping module names.
    """
    changed = context.changed_modules()
    if not changed:
        return []

    test_name = None
    for node in graph.nodes_of_type(ArtifactType.TEST_METADATA):
        test_name = node.attributes.get("test_name") or node.module
        if test_name:
            break
    if not test_name:
        return []

    overlapping: dict[str, None] = {}
    for node in graph.failing():
        haystack = f"{node.module or ''} {node.attributes.get('source_file') or ''}"
        for module in _overlap(changed, haystack):
            overlapping.setdefault(module, None)
    if not overlapping:
        return []

    modules = list(overlapping)
    return [
        ImpactedTestView(
            test_name=str(test_name),
            score=min(1.0, 0.5 + 0.1 * len(modules)),
            reason=(
                f"this run's failing evidence sits in recently changed "
                f"module{'s' if len(modules) != 1 else ''} {', '.join(modules)}"
            ),
            changed_modules=modules,
            regression_ids=[],
        )
    ]


def impacted_tests_from_history(
    context: EngineeringContext,
    history: list[HistoricalRegression],
    limit: int = 10,
) -> list[ImpactedTestView]:
    """Tests that historically failed in the changed modules, ranked.

    Score saturates with failure count; ties break by test name so the
    ranking is total and deterministic. Every entry cites the regression IDs
    it derived from.
    """
    changed = context.changed_modules()
    if not changed:
        return []

    per_test: dict[str, dict[str, object]] = {}
    for record in history:
        if not record.test_name:
            continue
        haystack = " ".join(record.failing_modules)
        hits = _overlap(changed, haystack)
        if not hits:
            continue
        entry = per_test.setdefault(
            record.test_name, {"count": 0, "modules": {}, "regressions": []}
        )
        entry["count"] = int(entry["count"]) + 1
        for module in hits:
            entry["modules"].setdefault(module, None)  # type: ignore[union-attr]
        entry["regressions"].append(record.regression_id)  # type: ignore[union-attr]

    ranked = sorted(
        per_test.items(), key=lambda item: (-int(item[1]["count"]), item[0])
    )
    return [
        ImpactedTestView(
            test_name=name,
            score=min(1.0, _PER_FAILURE_WEIGHT * int(entry["count"])),
            reason=(
                f"failed {entry['count']} time{'s' if int(entry['count']) != 1 else ''} in "
                f"regressions touching {', '.join(entry['modules'])}"  # type: ignore[arg-type]
            ),
            changed_modules=list(entry["modules"]),  # type: ignore[arg-type]
            regression_ids=list(entry["regressions"]),  # type: ignore[arg-type]
        )
        for name, entry in ranked[:limit]
    ]
