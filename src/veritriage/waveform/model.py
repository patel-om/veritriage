"""Normalized, simulator-independent waveform models (Milestone 6).

This module is the boundary between "format-aware" and "format-agnostic" code.
Adapters (which know VCD, FSDB, ...) fill in :class:`WaveformMetadata`; the
observation engine reads only these models and never learns a format existed.

Deliberately absent: any list of value changes. We keep per-signal counts,
first/last edge times, and the dump window, never the transition stream. This
is the "metadata not data" rule (see docs/WAVEFORM_ENGINE.md), and it is what
keeps the Evidence Graph small no matter how large the waveform was.

This module imports nothing from :mod:`veritriage.graph` or the adapters: it is
pure normalized data, so the engine that consumes it stays format-agnostic.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from veritriage.models.events import Severity


class SignalRole(str, Enum):
    """The verification role a signal plays, independent of any simulator.

    Adapters tag signals with a role (from a manifest, or inferred from the
    name); detectors reason about roles, never about raw names, so the same
    detector works across simulators.
    """

    CLOCK = "clock"
    RESET = "reset"
    VALID = "valid"
    READY = "ready"
    REQ = "req"
    ACK = "ack"
    STATE = "state"
    DATA = "data"
    OTHER = "other"


class WaveformCapability(str, Enum):
    """What an adapter is able to resolve from its format.

    Declared per adapter and carried on each :class:`WaveformMetadata`. A
    detector that needs a capability the adapter did not provide is skipped and
    reported as unavailable, never silently reported as "no problem found".
    """

    ACTIVITY = "activity"  # per-signal toggle counts / first-last edge times
    CLOCK_DETECTION = "clock_detection"
    RESET_DETECTION = "reset_detection"
    FSM = "fsm"
    TRANSACTIONS = "transactions"
    HIERARCHY = "hierarchy"
    PROTOCOL_ANNOTATIONS = "protocol_annotations"  # declared handshakes / phases


class ObservationCategory(str, Enum):
    """Coarse classification of an observation, so consumers can select by
    concern ("give me all PROTOCOL observations") without matching concrete
    kinds."""

    ACTIVITY = "activity"
    TIMING = "timing"
    PROTOCOL = "protocol"
    FSM = "fsm"
    CLOCK = "clock"
    RESET = "reset"
    TRANSACTION = "transaction"
    INTEGRITY = "integrity"


class ObservationKind(str, Enum):
    """The engineering observations the waveform engine can make.

    Each kind is a conclusion a senior verification engineer would draw from a
    waveform, not a raw transition. New kinds are added here plus a detector.
    """

    SIGNAL_NEVER_TOGGLED = "signal_never_toggled"
    CLOCK_STOPPED = "clock_stopped"
    HANDSHAKE_INCOMPLETE = "handshake_incomplete"
    HANDSHAKE_COMPLETED = "handshake_completed"
    FSM_STALLED = "fsm_stalled"
    TRANSACTION_NOT_RETIRED = "transaction_not_retired"
    UNEXPECTED_RESET = "unexpected_reset"
    REPEATED_RETRIES = "repeated_retries"
    PROTOCOL_SEQUENCE_INCOMPLETE = "protocol_sequence_incomplete"


class WaveformSignal(BaseModel):
    """One signal reduced to metadata: identity, role, and activity summary.

    Activity is a summary (counts and edge times), never a transition list.
    """

    name: str = Field(description="Leaf signal name, e.g. 'arvalid'.")
    scope: str = Field(description="Hierarchical path, e.g. 'tb.dut.axi_if'.")
    width: int = Field(default=1, ge=1)
    role: SignalRole = SignalRole.OTHER
    first_edge: int | None = Field(
        default=None, description="Time of first transition; None if it never toggled."
    )
    last_edge: int | None = Field(default=None, description="Time of last transition.")
    toggle_count: int = Field(default=0, ge=0, description="Transitions in the dump window.")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def full_name(self) -> str:
        """Fully qualified signal name (scope.leaf)."""
        return f"{self.scope}.{self.name}" if self.scope else self.name

    @property
    def is_constant(self) -> bool:
        """True when the signal never transitioned in the dump window."""
        return self.toggle_count == 0


class HandshakeRef(BaseModel):
    """A req/ack style pair (valid/ready, req/ack) to check for completion."""

    name: str = Field(description="Label, e.g. 'AR channel'.")
    scope: str | None = Field(default=None, description="Scope the handshake lives in.")
    initiator: str = Field(description="Signal that requests (valid/req).")
    responder: str = Field(description="Signal that grants (ready/ack).")


class TransactionRef(BaseModel):
    """A higher-level transaction summarized from the waveform, if available."""

    id: str
    kind: str = Field(description="Transaction kind, e.g. 'read', 'write', 'snoop'.")
    scope: str | None = None
    start: int
    end: int | None = Field(default=None, description="Retirement time; None if never retired.")
    retry_count: int = Field(default=0, ge=0)


class WaveformMetadata(BaseModel):
    """The normalized, simulator-independent view of one waveform artifact.

    Filling this in is the entire job of an adapter. Everything downstream reads
    only this, so a new simulator is a new adapter and nothing else.
    """

    source_path: str
    format: str = Field(description="Format tag for provenance only, e.g. 'vcd'.")
    adapter: str = Field(description="Adapter name that produced this metadata.")
    simulator: str | None = None
    timescale: str | None = None
    dump_start: int | None = None
    dump_end: int | None = None
    signals: list[WaveformSignal] = Field(default_factory=list)
    handshakes: list[HandshakeRef] = Field(default_factory=list)
    transactions: list[TransactionRef] = Field(default_factory=list)
    capabilities: frozenset[WaveformCapability] = Field(default_factory=frozenset)

    def signals_with_role(self, *roles: SignalRole) -> list[WaveformSignal]:
        """Signals carrying any of the given roles, in declaration order."""
        wanted = set(roles)
        return [s for s in self.signals if s.role in wanted]

    def signal(self, name: str) -> WaveformSignal | None:
        """Look a signal up by leaf name or fully qualified name."""
        for candidate in self.signals:
            if name in (candidate.name, candidate.full_name):
                return candidate
        return None

    def has_window(self) -> bool:
        """True when a non-empty dump window is known."""
        return (
            self.dump_start is not None
            and self.dump_end is not None
            and self.dump_end > self.dump_start
        )


def make_observation_id(kind: ObservationKind, scope: str | None, signals: list[str]) -> str:
    """Deterministic observation ID from identifying content.

    Same waveform metadata always yields the same observation IDs, byte for
    byte, so the whole waveform stage stays reproducible like the rest of the
    platform.
    """
    parts = [kind.value, scope or "", "|".join(sorted(signals))]
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()
    return f"wobs-{digest[:12]}"


class WaveformObservation(BaseModel):
    """One engineering conclusion drawn from normalized waveform metadata.

    Carries full provenance (which detector made it, which adapter the metadata
    came from, which signals it was derived from) so the conclusion is walkable
    back to its inputs, and a confidence that propagates into evidence and
    hypotheses exactly like every other signal on the platform.
    """

    observation_id: str = Field(description="Deterministic content-derived ID.")
    detector: str = Field(description="Generation method: the detector that produced this.")
    source_adapter: str = Field(description="Adapter/format the input metadata came from.")
    input_signals: list[str] = Field(
        default_factory=list, description="Metadata objects this observation was derived from."
    )
    kind: ObservationKind
    category: ObservationCategory
    description: str = Field(description="Engineering statement, shown in the report.")
    severity: Severity
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    scope: str | None = Field(default=None, description="Scope, for correlating to failures.")
    sim_time_start: int | None = None
    sim_time_end: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class UnavailableAnalysis(BaseModel):
    """An analysis the engine could not run because the adapter lacked a
    capability. Surfaced in the report so degradation is honest, not silent."""

    detector: str
    required_capability: WaveformCapability
    adapter: str
    reason: str
