"""Formal property-verification result parser.

Formal tools (JasperGold, VC Formal, Questa PropCheck, ...) do not produce a
simulation log; they produce a per-property verdict: proven, falsified (with a
counterexample), vacuous, inconclusive at a bound, or a cover result. This
parser ingests those verdicts *natively* as first-class evidence, rather than
scraping them out of a tool log, by reading a simulator-independent
``*.formal.json`` any flow can export:

    {
      "tool": "JasperGold",
      "properties": [
        {"name": "p_grant_onehot", "status": "falsified", "engine": "Bmc",
         "depth": 12, "message": "grant not one-hot"},
        {"name": "p_no_deadlock",  "status": "inconclusive", "depth": 40},
        {"name": "p_req_ack",      "status": "vacuous",
         "message": "antecedent never satisfied"},
        {"name": "p_fifo_safe",    "status": "proven"},
        {"name": "c_wr_hit",       "status": "covered"}
      ]
    }

Each property becomes one FORMAL_RESULT evidence node; failing verdicts
(falsified / vacuous / inconclusive / unreachable) are flagged so the
correlator and the ``formal`` Knowledge Pack pick them up exactly like any
other failing evidence. The node descriptions are phrased so the existing
``formal`` pack patterns match, which is the "parser first, pack on top"
sequencing: ingestion here, domain knowledge in the pack.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from veritriage.graph.builder import GraphFragment
from veritriage.graph.model import ArtifactType, EvidenceNode, make_node_id
from veritriage.models import LogSummary, Severity
from veritriage.parsers.base import Parser, ParseResult
from veritriage.parsers.registry import register

_RESULTS_KEY = "formal_results"

#: Normalize the many spellings a tool may use into a canonical verdict.
_STATUS_ALIASES = {
    "proven": "proven", "proved": "proven", "pass": "proven", "passed": "proven", "holds": "proven",
    "falsified": "falsified", "failed": "falsified", "fail": "falsified",
    "cex": "falsified", "counterexample": "falsified",
    "vacuous": "vacuous", "vacuously": "vacuous", "vacuously_proven": "vacuous",
    "inconclusive": "inconclusive", "undetermined": "inconclusive", "unknown": "inconclusive",
    "covered": "covered", "reachable": "covered", "cover": "covered",
    "unreachable": "unreachable", "dead": "unreachable", "uncovered": "unreachable",
}

#: Verdicts that count as a failure (error) versus informational (info).
_FAILING_STATUSES = {"falsified", "vacuous", "inconclusive", "unreachable"}


class FormalProperty(BaseModel):
    """One property's verdict from a formal run."""

    name: str
    status: str = Field(description="Verdict; normalized against a broad alias table.")
    engine: str | None = None
    depth: int | None = Field(default=None, description="Proof/counterexample depth, if reported.")
    module: str | None = Field(default=None, description="Scope this property constrains.")
    message: str | None = None


class FormalResults(BaseModel):
    """A formal run: the tool and its per-property verdicts."""

    tool: str | None = None
    version: str | None = None
    properties: list[FormalProperty] = Field(default_factory=list)


def _normalize_status(raw: str) -> str:
    return _STATUS_ALIASES.get(raw.strip().lower().replace("-", "_"), raw.strip().lower())


def _describe(prop: FormalProperty, status: str) -> str:
    """A description phrased so the ``formal`` Knowledge Pack patterns match."""
    depth = f" at depth {prop.depth}" if prop.depth is not None else ""
    detail = f" ({prop.message})" if prop.message else ""
    if status == "falsified":
        return f"Formal property {prop.name} falsified: counterexample found{depth}{detail}"
    if status == "vacuous":
        reason = prop.message or "antecedent never satisfied"
        return f"Formal property {prop.name} proven vacuously: {reason}, vacuity detected"
    if status == "inconclusive":
        return (
            f"Formal property {prop.name} inconclusive at bound: bounded proof "
            f"inconclusive{depth}, proof depth insufficient"
        )
    if status == "unreachable":
        return f"Formal cover {prop.name} unreachable: cover target never reachable{detail}"
    if status == "covered":
        return f"Formal cover {prop.name} covered: cover target reachable"
    engine = f" (engine {prop.engine})" if prop.engine else ""
    return f"Formal property {prop.name} proven{engine}"


@register
class FormalResultParser(Parser):
    """Parses a canonical formal-results manifest into per-property evidence."""

    name = "formal_result"
    artifact_type = ArtifactType.FORMAL_RESULT
    file_patterns = ("*.formal.json",)

    def parse(self, path: Path) -> ParseResult:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        # Accept either a wrapped object or a bare list of properties.
        results = FormalResults.model_validate(
            raw if isinstance(raw, dict) else {"properties": raw}
        )
        return ParseResult(
            parser_name=self.name,
            source_path=str(path),
            summary=LogSummary(total_lines=len(results.properties)),
            metadata={_RESULTS_KEY: results},
        )

    def emit_evidence(self, result: ParseResult) -> GraphFragment:
        results = stored_results(result)
        if results is None:
            return GraphFragment()
        nodes: list[EvidenceNode] = []
        for ordinal, prop in enumerate(results.properties):
            status = _normalize_status(prop.status)
            failing = status in _FAILING_STATUSES
            attributes: dict[str, Any] = {"status": status, "property": prop.name}
            for key, value in (("engine", prop.engine), ("depth", prop.depth), ("tool", results.tool)):
                if value is not None:
                    attributes[key] = value
            nodes.append(
                EvidenceNode(
                    id=make_node_id(self.artifact_type.value, result.source_path, prop.name, status, str(ordinal)),
                    artifact_type=self.artifact_type,
                    description=_describe(prop, status),
                    severity=Severity.ERROR if failing else Severity.INFO,
                    source_path=result.source_path,
                    module=prop.module,
                    attributes=attributes,
                )
            )
        return GraphFragment(nodes=nodes)


def stored_results(result: ParseResult) -> FormalResults | None:
    """The normalized formal results a parse stashed, if any."""
    stored = result.metadata.get(_RESULTS_KEY)
    return stored if isinstance(stored, FormalResults) else None
