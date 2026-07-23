"""The Waveform Intelligence Engine: normalized metadata to observations.

Format-agnostic by construction. The engine consumes only
:class:`WaveformMetadata` and a list of :class:`ObservationDetector`; it imports
no adapter, reads no file, and never names a simulator format. It runs each
detector whose required capability the producing adapter declared, and records
the rest as unavailable so the report can be honest about what could not be
analyzed (refinement 8).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from veritriage.waveform.model import (
    UnavailableAnalysis,
    WaveformMetadata,
    WaveformObservation,
)
from veritriage.waveform.observations import ObservationDetector, default_detectors


class ObservationResult(BaseModel):
    """Everything the engine produced for one waveform artifact."""

    observations: list[WaveformObservation] = Field(default_factory=list)
    unavailable: list[UnavailableAnalysis] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.observations and not self.unavailable


class WaveformEngine:
    """Runs observation detectors over normalized waveform metadata."""

    def __init__(self, detectors: list[ObservationDetector] | None = None) -> None:
        self._detectors = detectors if detectors is not None else default_detectors()

    def observe(self, metadata: WaveformMetadata) -> ObservationResult:
        """Produce observations, gating each detector on adapter capability.

        Pure function of ``metadata``: the same metadata always yields the same
        observations in the same order, byte for byte.
        """
        observations: list[WaveformObservation] = []
        unavailable: list[UnavailableAnalysis] = []
        for detector in self._detectors:
            capability = detector.required_capability
            if capability is not None and capability not in metadata.capabilities:
                unavailable.append(
                    UnavailableAnalysis(
                        detector=detector.name,
                        required_capability=capability,
                        adapter=metadata.adapter,
                        reason=(
                            f"the {metadata.adapter} adapter does not resolve "
                            f"{capability.value}, so {detector.name} could not run"
                        ),
                    )
                )
                continue
            observations.extend(detector.detect(metadata))
        return ObservationResult(observations=observations, unavailable=unavailable)
