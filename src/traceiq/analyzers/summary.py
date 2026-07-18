"""Optional AI summary, reasoning strictly over the Evidence Graph.

Design rules:

* The AI runs **after** deterministic parsing, graph building, and rule
  classification. It never reads raw artifacts: its entire input is the
  graph's bounded ``to_reasoning_view()`` plus the deterministic verdict.
  It cannot add facts, only narrate the ones the graph already holds, and
  every claim can be audited against node IDs.
* Because the reasoning view is artifact-agnostic (typed nodes and edges),
  adding new artifact types changes nothing here.
* The dependency is optional (``pip install traceiq[ai]``). Without the
  ``anthropic`` package or credentials, analysis works normally and the
  report simply has no AI summary.
"""

from __future__ import annotations

import json

from traceiq.graph.graph import EvidenceGraph
from traceiq.models import AnalysisReport

_DEFAULT_MODEL = "claude-opus-4-8"

_SYSTEM_PROMPT = """\
You are a senior semiconductor verification engineer reviewing a regression
failure analysis produced by a deterministic tool.

You are given an evidence graph (typed nodes with IDs, severities, times,
scopes, and typed relationships between them) plus a deterministic
classification derived from it.

Rules you must follow:
- Base every statement ONLY on the evidence graph provided. Never invent
  signals, times, components, or causes that are not present as nodes.
- When you make a claim, cite the supporting node id(s) in parentheses.
- Use the edges: precedes/causes chains describe how the failure unfolded;
  correlates_with links point at related coverage or metadata context.
- If the evidence is insufficient to conclude something, say so explicitly.
- Be concise: one short paragraph of narrative, then at most three bullet
  points of what to check next.
- Write for an engineer who will open the log and waveform next."""


class AISummaryError(RuntimeError):
    """Raised when an AI summary was requested but could not be produced."""


class AISummarizer:
    """Produces a short narrative grounded exclusively in the Evidence Graph."""

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self.model = model

    @staticmethod
    def available() -> bool:
        """True if the optional ``anthropic`` package is installed."""
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def summarize(self, report: AnalysisReport, graph: EvidenceGraph) -> str:
        """Return a narrative summary of the graph-backed findings.

        Args:
            report: The deterministic analysis (classification and stats).
            graph: The Evidence Graph; only its reasoning view is sent.

        Raises:
            AISummaryError: If the SDK is missing or the API call fails.
        """
        try:
            import anthropic
        except ImportError as exc:
            raise AISummaryError(
                "AI summary requested but the 'anthropic' package is not installed. "
                "Install with: pip install traceiq[ai]"
            ) from exc

        # The AI boundary: classification + graph reasoning view. No file
        # paths are opened here and no raw artifact text is transmitted.
        payload = {
            "classification": report.classification.model_dump(mode="json"),
            "alternatives": [a.model_dump(mode="json") for a in report.alternatives],
            "run_summary": report.summary.model_dump(mode="json"),
            "evidence_graph": graph.to_reasoning_view(),
        }
        try:
            client = anthropic.Anthropic()
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,  # summaries are deliberately short
                thinking={"type": "adaptive"},
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Summarize this verification failure analysis:\n\n"
                            f"{json.dumps(payload, indent=2)}"
                        ),
                    }
                ],
            )
        except anthropic.APIError as exc:
            raise AISummaryError(f"Anthropic API call failed: {exc}") from exc

        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise AISummaryError("Model returned an empty summary.")
        return text
