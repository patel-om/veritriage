"""Models for regression history: what past runs tell us about this one.

Only the models that travel inside an AnalysisReport live here (this package
must stay import-light; see the models package docstring). The full
RegressionRecord, which embeds a whole report and graph, lives in
``veritriage.history``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SimilarFailure(BaseModel):
    """One historical regression that resembles the current failure."""

    regression_id: str
    created_at: str = Field(description="ISO timestamp of the historical run.")
    test_name: str | None = None
    classification: str = Field(description="Failure category of the historical run.")
    root_cause: str = Field(
        description="Best available root-cause statement: feedback-confirmed cause "
        "when an engineer recorded one, else the top-ranked hypothesis."
    )
    score: float = Field(ge=0.0, le=1.0, description="Similarity score; 1.0 = identical signature.")
    signature_match: bool = Field(
        default=False, description="True when the deterministic failure signatures are identical."
    )


class HistoricalContext(BaseModel):
    """What the regression database knows about failures like this one.

    Attached to the report by the history layer, strictly after (and outside)
    the reasoning engine: history augments reasoning, it never replaces it.
    """

    regression_id: str = Field(description="ID assigned to the current run in the database.")
    signature: str = Field(description="Deterministic failure-signature digest of this run.")
    seen_before: bool = Field(description="True when an identical signature exists in history.")
    times_seen: int = Field(
        ge=0, description="How many prior regressions share this exact signature."
    )
    similar: list[SimilarFailure] = Field(
        default_factory=list, description="Most similar historical failures, best first."
    )
