"""Waveform Intelligence Engine (Milestone 6).

Turns simulator-specific waveform artifacts into normalized engineering
observations that enter the Evidence Graph as ordinary evidence. The platform's
core never learns a waveform format exists; adapters isolate every simulator
difference, and the observation engine is format-agnostic.

Public surface:

* ``WaveformMetadata`` and friends: the normalized model adapters produce.
* ``WaveformEngine`` / detectors: metadata to engineering observations.
* ``WaveformAdapter`` + registry: the one-class-per-simulator extension point.
* ``WaveformParser``: the Evidence Graph seam (registered as an ordinary parser).
* ``waveform_reasoning_rules`` / ``build_waveform_context``: additive reasoning
  and report integration.

Importing this package registers the built-in adapters and the waveform parser,
so ``pipeline.analyze()`` handles a ``.vcd`` or ``.wave.json`` file with no other
setup.
"""

from veritriage.waveform.adapters import (
    WaveformAdapter,
    WaveformAdapterError,
    all_patterns,
    available_adapters,
    find_adapter,
    register_adapter,
    unregister_adapter,
)
from veritriage.waveform.engine import ObservationResult, WaveformEngine
from veritriage.waveform.inference import (
    WaveformObservationRule,
    build_waveform_context,
    waveform_reasoning_rules,
)
from veritriage.waveform.model import (
    HandshakeRef,
    ObservationCategory,
    ObservationKind,
    SignalRole,
    TransactionRef,
    WaveformCapability,
    WaveformMetadata,
    WaveformObservation,
    WaveformSignal,
)
from veritriage.waveform.observations import ObservationDetector, default_detectors
from veritriage.waveform.parser import WaveformParser

__all__ = [
    "HandshakeRef",
    "ObservationCategory",
    "ObservationDetector",
    "ObservationKind",
    "ObservationResult",
    "SignalRole",
    "TransactionRef",
    "WaveformAdapter",
    "WaveformAdapterError",
    "WaveformCapability",
    "WaveformEngine",
    "WaveformMetadata",
    "WaveformObservation",
    "WaveformObservationRule",
    "WaveformParser",
    "WaveformSignal",
    "all_patterns",
    "available_adapters",
    "build_waveform_context",
    "default_detectors",
    "find_adapter",
    "register_adapter",
    "unregister_adapter",
    "waveform_reasoning_rules",
]
