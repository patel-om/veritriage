"""WaveformParser: waveform artifacts enter the Evidence Graph as observations.

This is the seam that lets `pipeline.analyze()` accept a `.vcd` or `.wave.json`
file with no pipeline change at all: the file is just another artifact claimed by
a registered `Parser`. Internally the parser dispatches to the matching adapter
(the only format-aware step), runs the format-agnostic observation engine, and
projects each observation into an evidence node carrying full provenance.

`can_parse` and the parser's advertised `file_patterns` are both derived from the
adapter registry, so adding a new simulator adapter automatically extends what
this parser claims: no edit here is required for a new format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from veritriage.graph.builder import GraphFragment
from veritriage.graph.model import ArtifactType, EvidenceNode, make_node_id
from veritriage.models import LogSummary
from veritriage.parsers.base import Parser, ParseResult
from veritriage.parsers.registry import register
from veritriage.waveform.adapters import find_adapter
from veritriage.waveform.adapters.registry import all_patterns
from veritriage.waveform.engine import ObservationResult, WaveformEngine
from veritriage.waveform.model import WaveformMetadata

_METADATA_KEY = "waveform_metadata"
_OBSERVATIONS_KEY = "waveform_observations"


class _AdapterPatterns:
    """Descriptor exposing the union of adapter file patterns as a class attr.

    Lets ``find_parser`` score this parser's specificity from the same patterns
    the adapters declare, so a new adapter's patterns are picked up with no edit
    to this module.
    """

    def __get__(self, obj: object, owner: type) -> tuple[str, ...]:
        return all_patterns()


@register
class WaveformParser(Parser):
    """Turns a waveform artifact into engineering-observation evidence."""

    name = "waveform"
    artifact_type = ArtifactType.WAVEFORM_METADATA
    file_patterns = _AdapterPatterns()  # type: ignore[assignment]

    @classmethod
    def can_parse(cls, path: Path) -> bool:
        """Claim the file when any registered waveform adapter handles it."""
        return find_adapter(path) is not None

    def parse(self, path: Path) -> ParseResult:
        adapter = find_adapter(path)
        if adapter is None:  # pragma: no cover - find_parser only routes matches here
            raise ValueError(f"No waveform adapter claims {path}")
        metadata = adapter.extract(path)
        observations = WaveformEngine().observe(metadata)
        return ParseResult(
            parser_name=self.name,
            source_path=str(path),
            summary=LogSummary(
                total_lines=len(metadata.signals),
                simulator=metadata.simulator,
                last_sim_time=str(metadata.dump_end) if metadata.dump_end is not None else None,
            ),
            metadata={_METADATA_KEY: metadata, _OBSERVATIONS_KEY: observations},
        )

    def emit_evidence(self, result: ParseResult) -> GraphFragment:
        observations = _stored_observations(result)
        nodes: list[EvidenceNode] = []
        for obs in observations.observations:
            attributes: dict[str, Any] = {
                "observation_id": obs.observation_id,
                "detector": obs.detector,
                "source_adapter": obs.source_adapter,
                "waveform_kind": obs.kind.value,
                "waveform_category": obs.category.value,
                "input_signals": obs.input_signals,
                **obs.attributes,
            }
            sim_time = obs.sim_time_end if obs.sim_time_end is not None else obs.sim_time_start
            nodes.append(
                EvidenceNode(
                    id=make_node_id(
                        self.artifact_type.value, result.source_path, obs.observation_id
                    ),
                    artifact_type=self.artifact_type,
                    description=obs.description,
                    severity=obs.severity,
                    confidence=obs.confidence,
                    sim_time=str(sim_time) if sim_time is not None else None,
                    source_path=result.source_path,
                    module=obs.scope,
                    attributes=attributes,
                )
            )
        return GraphFragment(nodes=nodes)


def _stored_observations(result: ParseResult) -> ObservationResult:
    """Read the ObservationResult the parser stashed during ``parse``."""
    stored = result.metadata.get(_OBSERVATIONS_KEY)
    if isinstance(stored, ObservationResult):
        return stored
    return ObservationResult()


def stored_metadata(result: ParseResult) -> WaveformMetadata | None:
    """The normalized metadata a waveform parse stashed, if any (for reports)."""
    stored = result.metadata.get(_METADATA_KEY)
    return stored if isinstance(stored, WaveformMetadata) else None


def stored_observations(result: ParseResult) -> ObservationResult:
    """Public accessor for the ObservationResult a waveform parse produced."""
    return _stored_observations(result)
