"""Optional AI summary of a completed analysis.

Design rules:

* The AI runs **after** deterministic parsing and rule classification, and it
  only ever sees the extracted evidence — never the raw log. It cannot add
  facts, only narrate the ones the rule engine established.
* The dependency is optional (``pip install traceiq[ai]``). Without the
  ``anthropic`` package or credentials, analysis works normally and the
  report simply has no AI summary.
"""

from __future__ import annotations

import json

from traceiq.models import AnalysisReport

_DEFAULT_MODEL = "claude-opus-4-8"

_SYSTEM_PROMPT = """\
You are a senior semiconductor verification engineer reviewing a regression
failure analysis produced by a deterministic tool.

Rules you must follow:
- Base every statement ONLY on the JSON evidence provided. Never invent
  signals, times, components, or causes that are not in the evidence.
- If the evidence is insufficient to conclude something, say so explicitly.
- Be concise: one short paragraph of narrative, then at most three bullet
  points of what to check next, referencing evidence line numbers.
- Write for an engineer who will open the log and waveform next."""


class AISummaryError(RuntimeError):
    """Raised when an AI summary was requested but could not be produced."""


class AISummarizer:
    """Produces a short, evidence-grounded narrative for a report."""

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

    def summarize(self, report: AnalysisReport) -> str:
        """Return a narrative summary of the report's findings.

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

        # Only the deterministic findings are sent — never the raw log.
        payload = report.model_dump(
            mode="json",
            include={"summary", "classification", "alternatives", "input_file"},
        )
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
