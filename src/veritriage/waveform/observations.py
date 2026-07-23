"""Observation detectors: turn normalized metadata into engineering conclusions.

Each detector is a pure, deterministic function of :class:`WaveformMetadata`,
exactly like a reasoning rule or a graph correlation pass. A detector reasons
about signal *roles* and *activity summaries*, never about a simulator format or
a raw transition, which is why the same detector works across every adapter.

This module (and engine.py, model.py) is the format-agnostic core: it imports no
adapter, reads no file, and contains no format string. That is pinned by
``test_waveform.py::test_waveform_core_is_format_agnostic``.

Detectors declare a ``required_capability``; the engine skips a detector whose
capability the adapter did not provide and reports it as unavailable, so
degradation is honest rather than silent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from veritriage.models.events import Severity
from veritriage.waveform.model import (
    ObservationCategory,
    ObservationKind,
    SignalRole,
    WaveformCapability,
    WaveformMetadata,
    WaveformObservation,
    make_observation_id,
)

#: Fixed classification of each observation kind (refinement 4).
KIND_CATEGORY: dict[ObservationKind, ObservationCategory] = {
    ObservationKind.SIGNAL_NEVER_TOGGLED: ObservationCategory.ACTIVITY,
    ObservationKind.CLOCK_STOPPED: ObservationCategory.CLOCK,
    ObservationKind.HANDSHAKE_INCOMPLETE: ObservationCategory.PROTOCOL,
    ObservationKind.HANDSHAKE_COMPLETED: ObservationCategory.PROTOCOL,
    ObservationKind.FSM_STALLED: ObservationCategory.FSM,
    ObservationKind.TRANSACTION_NOT_RETIRED: ObservationCategory.TRANSACTION,
    ObservationKind.UNEXPECTED_RESET: ObservationCategory.RESET,
    ObservationKind.REPEATED_RETRIES: ObservationCategory.TRANSACTION,
    ObservationKind.PROTOCOL_SEQUENCE_INCOMPLETE: ObservationCategory.PROTOCOL,
}

#: A transaction is "retried a lot" at or above this count.
_RETRY_THRESHOLD = 3


class ObservationDetector(ABC):
    """One deterministic observation over normalized waveform metadata."""

    #: Detector name, recorded as observation provenance.
    name: ClassVar[str]

    #: The adapter capability this detector needs; None means always runnable.
    required_capability: ClassVar[WaveformCapability]

    #: The observation kinds this detector may emit (for schema validation).
    emits: ClassVar[frozenset[ObservationKind]]

    @abstractmethod
    def detect(self, metadata: WaveformMetadata) -> list[WaveformObservation]:
        """Return zero or more observations for this metadata."""
        raise NotImplementedError

    def _observe(
        self,
        *,
        kind: ObservationKind,
        description: str,
        severity: Severity,
        confidence: float,
        metadata: WaveformMetadata,
        scope: str | None = None,
        input_signals: list[str] | None = None,
        sim_time_start: int | None = None,
        sim_time_end: int | None = None,
        attributes: dict | None = None,
    ) -> WaveformObservation:
        """Build a fully provenanced observation (refinements 3, 5, 9)."""
        signals = input_signals or []
        return WaveformObservation(
            observation_id=make_observation_id(kind, scope, signals),
            detector=self.name,
            source_adapter=metadata.adapter,
            input_signals=signals,
            kind=kind,
            category=KIND_CATEGORY[kind],
            description=description,
            severity=severity,
            confidence=confidence,
            scope=scope,
            sim_time_start=sim_time_start,
            sim_time_end=sim_time_end,
            attributes=attributes or {},
        )


def _window_len(metadata: WaveformMetadata) -> int | None:
    if metadata.dump_start is None or metadata.dump_end is None:
        return None
    return metadata.dump_end - metadata.dump_start


class SignalNeverToggledDetector(ObservationDetector):
    """A handshake-role signal that never transitioned over a non-empty window.

    A valid/ready/req/ack that never moves is almost always a stuck interface:
    nothing was ever driven, or the producer never fired.
    """

    name = "signal-never-toggled"
    required_capability = WaveformCapability.ACTIVITY
    emits = frozenset({ObservationKind.SIGNAL_NEVER_TOGGLED})
    _ROLES = (SignalRole.VALID, SignalRole.READY, SignalRole.REQ, SignalRole.ACK)

    def detect(self, metadata: WaveformMetadata) -> list[WaveformObservation]:
        if not metadata.has_window():
            return []
        out: list[WaveformObservation] = []
        for signal in metadata.signals_with_role(*self._ROLES):
            if signal.toggle_count == 0:
                out.append(
                    self._observe(
                        kind=ObservationKind.SIGNAL_NEVER_TOGGLED,
                        description=(
                            f"Signal {signal.full_name} ({signal.role.value}) never toggled over "
                            f"the entire dump window; the interface appears stuck or undriven."
                        ),
                        severity=Severity.WARNING,
                        confidence=0.9,
                        metadata=metadata,
                        scope=signal.scope,
                        input_signals=[signal.full_name],
                        sim_time_start=metadata.dump_start,
                        sim_time_end=metadata.dump_end,
                        attributes={"role": signal.role.value, "toggle_count": 0},
                    )
                )
        return out


class ClockStoppedDetector(ObservationDetector):
    """A clock that never toggled, or stopped well before the dump ended."""

    name = "clock-stopped"
    required_capability = WaveformCapability.CLOCK_DETECTION
    emits = frozenset({ObservationKind.CLOCK_STOPPED})

    def detect(self, metadata: WaveformMetadata) -> list[WaveformObservation]:
        window = _window_len(metadata)
        if not window:
            return []
        out: list[WaveformObservation] = []
        for clock in metadata.signals_with_role(SignalRole.CLOCK):
            if clock.toggle_count == 0:
                out.append(
                    self._observe(
                        kind=ObservationKind.CLOCK_STOPPED,
                        description=(
                            f"Clock {clock.full_name} never toggled: the clock is dead for the "
                            f"whole run, so no synchronous logic could advance."
                        ),
                        severity=Severity.FATAL,
                        confidence=0.98,
                        metadata=metadata,
                        scope=clock.scope,
                        input_signals=[clock.full_name],
                        sim_time_start=metadata.dump_start,
                        sim_time_end=metadata.dump_end,
                        attributes={"toggle_count": 0},
                    )
                )
                continue
            if clock.last_edge is not None and (metadata.dump_end - clock.last_edge) > window * 0.1:
                out.append(
                    self._observe(
                        kind=ObservationKind.CLOCK_STOPPED,
                        description=(
                            f"Clock {clock.full_name} stopped toggling at {clock.last_edge} and "
                            f"stayed quiet through the end of the dump at {metadata.dump_end}; "
                            f"forward progress halted while the clock was gated or stuck."
                        ),
                        severity=Severity.ERROR,
                        confidence=0.9,
                        metadata=metadata,
                        scope=clock.scope,
                        input_signals=[clock.full_name],
                        sim_time_start=clock.last_edge,
                        sim_time_end=metadata.dump_end,
                        attributes={
                            "last_edge": clock.last_edge,
                            "dump_end": metadata.dump_end,
                            "toggle_count": clock.toggle_count,
                        },
                    )
                )
        return out


class UnexpectedResetDetector(ObservationDetector):
    """A reset that asserts late in the run rather than only at time zero."""

    name = "unexpected-reset"
    required_capability = WaveformCapability.RESET_DETECTION
    emits = frozenset({ObservationKind.UNEXPECTED_RESET})

    def detect(self, metadata: WaveformMetadata) -> list[WaveformObservation]:
        window = _window_len(metadata)
        if not window or metadata.dump_start is None:
            return []
        threshold = metadata.dump_start + window * 0.2
        out: list[WaveformObservation] = []
        for reset in metadata.signals_with_role(SignalRole.RESET):
            if reset.last_edge is not None and reset.last_edge > threshold:
                out.append(
                    self._observe(
                        kind=ObservationKind.UNEXPECTED_RESET,
                        description=(
                            f"Reset {reset.full_name} toggled at {reset.last_edge}, well after the "
                            f"initial reset phase; an unexpected mid-run reset can silently discard "
                            f"in-flight state and mask the real failure."
                        ),
                        severity=Severity.WARNING,
                        confidence=0.7,
                        metadata=metadata,
                        scope=reset.scope,
                        input_signals=[reset.full_name],
                        sim_time_start=reset.first_edge,
                        sim_time_end=reset.last_edge,
                        attributes={
                            "last_edge": reset.last_edge,
                            "toggle_count": reset.toggle_count,
                        },
                    )
                )
        return out


class FsmStalledDetector(ObservationDetector):
    """A state signal that never advanced, or froze well before the dump end."""

    name = "fsm-stalled"
    required_capability = WaveformCapability.FSM
    emits = frozenset({ObservationKind.FSM_STALLED})

    def detect(self, metadata: WaveformMetadata) -> list[WaveformObservation]:
        window = _window_len(metadata)
        if not window:
            return []
        out: list[WaveformObservation] = []
        for state in metadata.signals_with_role(SignalRole.STATE):
            if state.toggle_count == 0:
                out.append(
                    self._observe(
                        kind=ObservationKind.FSM_STALLED,
                        description=(
                            f"FSM state {state.full_name} never left its initial value; the state "
                            f"machine never started or is wedged in its reset state."
                        ),
                        severity=Severity.ERROR,
                        confidence=0.85,
                        metadata=metadata,
                        scope=state.scope,
                        input_signals=[state.full_name],
                        sim_time_start=metadata.dump_start,
                        sim_time_end=metadata.dump_end,
                        attributes={"toggle_count": 0},
                    )
                )
            elif state.last_edge is not None and (metadata.dump_end - state.last_edge) > window * 0.2:
                out.append(
                    self._observe(
                        kind=ObservationKind.FSM_STALLED,
                        description=(
                            f"FSM state {state.full_name} stopped transitioning at "
                            f"{state.last_edge} and never advanced before the dump ended at "
                            f"{metadata.dump_end}; the state machine stalled mid-sequence."
                        ),
                        severity=Severity.WARNING,
                        confidence=0.8,
                        metadata=metadata,
                        scope=state.scope,
                        input_signals=[state.full_name],
                        sim_time_start=state.last_edge,
                        sim_time_end=metadata.dump_end,
                        attributes={"last_edge": state.last_edge, "dump_end": metadata.dump_end},
                    )
                )
        return out


class HandshakeDetector(ObservationDetector):
    """Check declared req/ack pairs for completion, stall, or a start that
    never happened."""

    name = "handshake"
    required_capability = WaveformCapability.PROTOCOL_ANNOTATIONS
    emits = frozenset(
        {
            ObservationKind.HANDSHAKE_COMPLETED,
            ObservationKind.HANDSHAKE_INCOMPLETE,
            ObservationKind.PROTOCOL_SEQUENCE_INCOMPLETE,
        }
    )

    def detect(self, metadata: WaveformMetadata) -> list[WaveformObservation]:
        out: list[WaveformObservation] = []
        for hs in metadata.handshakes:
            initiator = metadata.signal(hs.initiator)
            responder = metadata.signal(hs.responder)
            if initiator is None or responder is None:
                continue
            names = [initiator.full_name, responder.full_name]
            if initiator.toggle_count == 0:
                out.append(
                    self._observe(
                        kind=ObservationKind.PROTOCOL_SEQUENCE_INCOMPLETE,
                        description=(
                            f"Handshake '{hs.name}' never started: initiator {initiator.full_name} "
                            f"never asserted, so no transfer was ever requested on this channel."
                        ),
                        severity=Severity.WARNING,
                        confidence=0.85,
                        metadata=metadata,
                        scope=hs.scope,
                        input_signals=names,
                        attributes={"handshake": hs.name},
                    )
                )
            elif responder.toggle_count == 0:
                out.append(
                    self._observe(
                        kind=ObservationKind.HANDSHAKE_INCOMPLETE,
                        description=(
                            f"Handshake '{hs.name}' stalled: initiator {initiator.full_name} "
                            f"asserted (first at {initiator.first_edge}) but responder "
                            f"{responder.full_name} never acknowledged; the transfer never completed."
                        ),
                        severity=Severity.ERROR,
                        confidence=0.9,
                        metadata=metadata,
                        scope=hs.scope,
                        input_signals=names,
                        sim_time_start=initiator.first_edge,
                        sim_time_end=metadata.dump_end,
                        attributes={
                            "handshake": hs.name,
                            "initiator_first_edge": initiator.first_edge,
                        },
                    )
                )
            else:
                out.append(
                    self._observe(
                        kind=ObservationKind.HANDSHAKE_COMPLETED,
                        description=(
                            f"Handshake '{hs.name}' completed: both {initiator.full_name} and "
                            f"{responder.full_name} were active, so transfers progressed on this "
                            f"channel (positive evidence of forward progress)."
                        ),
                        severity=Severity.INFO,
                        confidence=0.8,
                        metadata=metadata,
                        scope=hs.scope,
                        input_signals=names,
                        attributes={"handshake": hs.name},
                    )
                )
        return out


class TransactionRetireDetector(ObservationDetector):
    """A transaction that started but never retired within the dump window."""

    name = "transaction-not-retired"
    required_capability = WaveformCapability.TRANSACTIONS
    emits = frozenset({ObservationKind.TRANSACTION_NOT_RETIRED})

    def detect(self, metadata: WaveformMetadata) -> list[WaveformObservation]:
        out: list[WaveformObservation] = []
        for txn in metadata.transactions:
            if txn.end is None:
                out.append(
                    self._observe(
                        kind=ObservationKind.TRANSACTION_NOT_RETIRED,
                        description=(
                            f"{txn.kind} transaction '{txn.id}' started at {txn.start} and never "
                            f"retired before the dump ended; an outstanding transaction that never "
                            f"completes points at a stalled or dropped response in the design."
                        ),
                        severity=Severity.ERROR,
                        confidence=0.95,
                        metadata=metadata,
                        scope=txn.scope,
                        input_signals=[txn.id],
                        sim_time_start=txn.start,
                        sim_time_end=metadata.dump_end,
                        attributes={"transaction_id": txn.id, "kind": txn.kind},
                    )
                )
        return out


class RepeatedRetriesDetector(ObservationDetector):
    """A transaction retried an unusual number of times."""

    name = "repeated-retries"
    required_capability = WaveformCapability.TRANSACTIONS
    emits = frozenset({ObservationKind.REPEATED_RETRIES})

    def detect(self, metadata: WaveformMetadata) -> list[WaveformObservation]:
        out: list[WaveformObservation] = []
        for txn in metadata.transactions:
            if txn.retry_count >= _RETRY_THRESHOLD:
                out.append(
                    self._observe(
                        kind=ObservationKind.REPEATED_RETRIES,
                        description=(
                            f"{txn.kind} transaction '{txn.id}' was retried {txn.retry_count} times; "
                            f"repeated retries usually mean a persistently rejected request or a "
                            f"congested/flaky responder."
                        ),
                        severity=Severity.WARNING,
                        confidence=0.85,
                        metadata=metadata,
                        scope=txn.scope,
                        input_signals=[txn.id],
                        sim_time_start=txn.start,
                        attributes={"transaction_id": txn.id, "retry_count": txn.retry_count},
                    )
                )
        return out


def default_detectors() -> list[ObservationDetector]:
    """The built-in detectors, in deterministic execution order."""
    return [
        ClockStoppedDetector(),
        UnexpectedResetDetector(),
        SignalNeverToggledDetector(),
        FsmStalledDetector(),
        HandshakeDetector(),
        TransactionRetireDetector(),
        RepeatedRetriesDetector(),
    ]
