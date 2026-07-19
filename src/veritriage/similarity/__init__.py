"""Similar-failure search over the regression database.

Two-tier matching, cheapest first:

1. **Signature match.** Identical deterministic failure signatures are the
   same failure mode by construction; they score 1.0 with no math.
2. **Embedding similarity.** Every record carries a sparse feature embedding
   built from its Evidence Graph and reasoning output (failure category,
   affected modules, assertion names, fired signals, hypothesis mix, graph
   relationship shape). Cosine similarity over those features ranks
   near-misses: same modules but a different category, same signals under a
   different test, and so on.

The default embedding is deterministic and dependency-free, which keeps the
whole platform reproducible. ``EmbeddingProvider`` is the seam where a
learned text-embedding model can plug in later; only this package would
change.
"""

from __future__ import annotations

import math
from typing import Protocol

from veritriage.history.record import RegressionRecord
from veritriage.models import SimilarFailure
from veritriage.storage import RegressionStore

__all__ = [
    "EmbeddingProvider",
    "FeatureEmbedding",
    "SimilarFailureEngine",
    "cosine",
]


class EmbeddingProvider(Protocol):
    """Turns one regression record into a sparse feature vector."""

    def embed(self, record: RegressionRecord) -> dict[str, float]: ...


#: Feature-family weights: what "the same kind of failure" mostly depends on.
_WEIGHTS = {
    "category": 3.0,
    "assert": 2.5,
    "module": 2.0,
    "signal": 1.5,
    "hyp": 1.0,
    "rel": 0.5,
    "test": 0.5,
}


class FeatureEmbedding:
    """Deterministic embedding from a record's normalized evidence, not raw text."""

    def embed(self, record: RegressionRecord) -> dict[str, float]:
        sig = record.signature
        features: dict[str, float] = {f"category:{sig.category}": _WEIGHTS["category"]}
        for assertion in sig.assertions:
            features[f"assert:{assertion}"] = _WEIGHTS["assert"]
        for module in sig.modules:
            features[f"module:{module}"] = _WEIGHTS["module"]
        for signal in sig.signals:
            features[f"signal:{signal}"] = _WEIGHTS["signal"]
        for hyp in sig.hypotheses:
            features[f"hyp:{hyp}"] = _WEIGHTS["hyp"]
        for relation, count in sorted(record.report.graph_stats.edges_by_relation.items()):
            features[f"rel:{relation}"] = _WEIGHTS["rel"] * min(count, 5)
        if record.test_name:
            features[f"test:{record.test_name}"] = _WEIGHTS["test"]
        return _normalize(features)


def _normalize(features: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(v * v for v in features.values()))
    if norm == 0.0:
        return {}
    return {k: v / norm for k, v in features.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity of two sparse vectors (both assumed L2-normalized)."""
    if len(b) < len(a):
        a, b = b, a
    return sum(value * b.get(key, 0.0) for key, value in a.items())


class SimilarFailureEngine:
    """Answers "have we seen this before?" against the regression database."""

    def __init__(
        self, store: RegressionStore, provider: EmbeddingProvider | None = None
    ) -> None:
        self._store = store
        self._provider = provider or FeatureEmbedding()

    @property
    def provider(self) -> EmbeddingProvider:
        return self._provider

    def find_similar(
        self, record: RegressionRecord, top_k: int = 5, min_score: float = 0.25
    ) -> list[SimilarFailure]:
        """Most similar historical failures, best first.

        Signature-identical regressions always outrank embedding matches.
        The record being queried is excluded by ID, so this can run before
        or after the record itself is saved.
        """
        query = record.embedding or self._provider.embed(record)
        scored: list[tuple[float, bool, RegressionRecord]] = []
        for candidate in self._store.all_records():
            if candidate.regression_id == record.regression_id:
                continue
            if not candidate.is_failure:
                continue
            exact = candidate.signature.digest == record.signature.digest
            score = 1.0 if exact else cosine(query, candidate.embedding)
            if exact or score >= min_score:
                scored.append((score, exact, candidate))
        # Best score first; exact matches ahead of ties; newest ahead of older.
        scored.sort(key=lambda item: (item[0], item[1], item[2].created_at), reverse=True)

        results = []
        for score, exact, candidate in scored[:top_k]:
            root_cause = (
                self._store.confirmed_root_cause(candidate.regression_id)
                or candidate.top_hypothesis
                or candidate.report.classification.summary
            )
            results.append(
                SimilarFailure(
                    regression_id=candidate.regression_id,
                    created_at=candidate.created_at.isoformat(),
                    test_name=candidate.test_name,
                    classification=candidate.classification,
                    root_cause=root_cause,
                    score=round(score, 4),
                    signature_match=exact,
                )
            )
        return results
