"""Report-facing waveform models (Milestone 6).

These are the normalized, serializable views embedded in the analysis report's
``waveform`` field. Like every model in this package, they are plain data and
import nothing from :mod:`veritriage.graph` or :mod:`veritriage.waveform`, so the
models package stays below the graph and engine layers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WaveformCapabilityView(BaseModel):
    """What one waveform artifact contributed, and what its adapter could
    resolve. Makes capability-limited degradation visible in the report."""

    adapter: str
    format: str
    source: str
    simulator: str | None = None
    signal_count: int = 0
    dump_start: int | None = None
    dump_end: int | None = None
    capabilities: list[str] = Field(default_factory=list)


class WaveformObservationView(BaseModel):
    """One engineering observation as shown in the report, with provenance."""

    observation_id: str
    kind: str
    category: str
    description: str
    severity: str
    confidence: float
    detector: str
    source_adapter: str
    scope: str | None = None
    signals: list[str] = Field(default_factory=list)
    sim_time_start: int | None = None
    sim_time_end: int | None = None


class WaveformUnavailableView(BaseModel):
    """An analysis that could not run because the adapter lacked a capability."""

    detector: str
    required_capability: str
    adapter: str
    reason: str


class WaveformContext(BaseModel):
    """The Waveform Intelligence Engine's contribution to one report."""

    adapters: list[WaveformCapabilityView] = Field(default_factory=list)
    observations: list[WaveformObservationView] = Field(default_factory=list)
    unavailable: list[WaveformUnavailableView] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.observations and not self.unavailable
