"""VCD metadata adapter.

VCD is the open, textual, universally available waveform format, which makes it
the right second adapter to prove the "new simulator is a new adapter only"
property against a real format.

What this adapter does, faithful to the lossy-by-design law:

* Parses the VCD header ($timescale, $scope/$upscope, $var) for the signal list,
  hierarchy, and bus widths.
* Streams the value-change section once, keeping ONLY per-signal counters
  (toggle count, first edge, last edge) and the final timestamp. It never stores
  the transition stream, so memory is O(number of signals), not O(number of
  transitions). Initial values (the first timestamp's dump) are not counted as
  toggles, so a signal that only ever receives its reset value is correctly seen
  as never toggling.

What it does NOT do: it declares no TRANSACTIONS or PROTOCOL_ANNOTATIONS
capability, because raw VCD carries neither a transaction database nor declared
handshakes. Detectors needing those are honestly reported as unavailable rather
than silently passing (see docs/WAVEFORM_ENGINE.md, capability declaration).
"""

from __future__ import annotations

from pathlib import Path

from veritriage.waveform.adapters.base import WaveformAdapter, WaveformAdapterError
from veritriage.waveform.adapters.registry import register_adapter
from veritriage.waveform.model import (
    SignalRole,
    WaveformCapability,
    WaveformMetadata,
    WaveformSignal,
)


def _infer_role(name: str) -> SignalRole:
    """Conservatively infer a signal's role from its name.

    Order matters: "state"/"fsm" is checked before reset, because names like
    "arstate" contain the substring "rst" and would otherwise be misread as a
    reset. Clock is checked early since "clk" collides with nothing else.
    """
    lowered = name.lower()
    if "state" in lowered or "fsm" in lowered:
        return SignalRole.STATE
    if "clk" in lowered or "clock" in lowered:
        return SignalRole.CLOCK
    if "reset" in lowered or "rst" in lowered:
        return SignalRole.RESET
    if "valid" in lowered:
        return SignalRole.VALID
    if "ready" in lowered:
        return SignalRole.READY
    if "req" in lowered:
        return SignalRole.REQ
    if "ack" in lowered:
        return SignalRole.ACK
    return SignalRole.OTHER


class _SignalAccumulator:
    """Mutable per-signal counters during the streaming activity scan.

    Holds only summary counters and the last observed value, never a history.
    """

    __slots__ = ("scope", "name", "width", "toggle_count", "first_edge", "last_edge", "last_value")

    def __init__(self, scope: str, name: str, width: int) -> None:
        self.scope = scope
        self.name = name
        self.width = width
        self.toggle_count = 0
        self.first_edge: int | None = None
        self.last_edge: int | None = None
        self.last_value: str | None = None

    def record(self, time: int, value: str) -> None:
        """Record a real transition (value differs from the last one)."""
        if value == self.last_value:
            return
        self.toggle_count += 1
        if self.first_edge is None:
            self.first_edge = time
        self.last_edge = time
        self.last_value = value


@register_adapter
class VcdAdapter(WaveformAdapter):
    """Extracts signal-activity metadata from a VCD file."""

    name = "vcd"
    format = "vcd"
    file_patterns = ("*.vcd",)
    capabilities = frozenset(
        {
            WaveformCapability.ACTIVITY,
            WaveformCapability.CLOCK_DETECTION,
            WaveformCapability.RESET_DETECTION,
            WaveformCapability.FSM,
            WaveformCapability.HIERARCHY,
        }
    )

    def extract(self, path: Path) -> WaveformMetadata:
        accumulators: dict[str, _SignalAccumulator] = {}
        scope_stack: list[str] = []
        timescale: str | None = None
        pending_timescale = False
        in_header = True
        first_ts: int | None = None
        current_time: int | None = None
        last_ts = 0

        try:
            handle = path.open(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise WaveformAdapterError(f"cannot open {path}: {exc}") from exc

        with handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue

                if in_header:
                    if pending_timescale and not line.startswith("$"):
                        timescale = line.split("$")[0].strip() or timescale
                        pending_timescale = False
                        continue
                    if line.startswith("$scope"):
                        parts = line.split()
                        if len(parts) >= 3:
                            scope_stack.append(parts[2])
                    elif line.startswith("$upscope"):
                        if scope_stack:
                            scope_stack.pop()
                    elif line.startswith("$var"):
                        self._add_var(line, scope_stack, accumulators)
                    elif line.startswith("$timescale"):
                        timescale, pending_timescale = _parse_timescale(line)
                    elif line.startswith("$enddefinitions"):
                        in_header = False
                    continue

                # Value-change section: counters only, no transition storage.
                if line[0] == "#":
                    try:
                        current_time = int(line[1:])
                    except ValueError:
                        continue
                    if first_ts is None:
                        first_ts = current_time
                    last_ts = max(last_ts, current_time)
                    continue

                code, value = _parse_value_change(line)
                if code is None:
                    continue
                acc = accumulators.get(code)
                if acc is None:
                    continue
                is_initial = current_time is None or current_time == first_ts
                if is_initial:
                    acc.last_value = value  # seed initial value, not a toggle
                else:
                    acc.record(current_time, value)

        if not accumulators:
            raise WaveformAdapterError(f"{path}: no $var declarations found (not a VCD header?)")

        signals = [
            WaveformSignal(
                name=acc.name,
                scope=acc.scope,
                width=acc.width,
                role=_infer_role(acc.name),
                first_edge=acc.first_edge,
                last_edge=acc.last_edge,
                toggle_count=acc.toggle_count,
            )
            for acc in accumulators.values()
        ]
        return WaveformMetadata(
            source_path=str(path),
            format=self.format,
            adapter=self.name,
            simulator=None,
            timescale=timescale,
            dump_start=first_ts if first_ts is not None else 0,
            dump_end=last_ts,
            signals=signals,
            handshakes=[],  # raw VCD declares none; capability withheld
            transactions=[],  # raw VCD has no transaction DB; capability withheld
            capabilities=self.capabilities,
        )

    @staticmethod
    def _add_var(
        line: str, scope_stack: list[str], accumulators: dict[str, "_SignalAccumulator"]
    ) -> None:
        """Parse a ``$var <type> <width> <code> <name> [range] $end`` line."""
        parts = line.split()
        # parts: ['$var', type, width, code, name, (maybe [range]), '$end']
        if len(parts) < 6:
            return
        try:
            width = int(parts[2])
        except ValueError:
            width = 1
        code = parts[3]
        name = parts[4]
        scope = ".".join(scope_stack)
        # Multiple codes can alias to the same name across scopes; last wins,
        # which is fine for an activity summary.
        accumulators[code] = _SignalAccumulator(scope=scope, name=name, width=max(width, 1))


def _parse_timescale(line: str) -> tuple[str | None, bool]:
    """Return (timescale, pending) for a ``$timescale`` line.

    Handles both the single-line ``$timescale 1ns $end`` form and the split
    form where the value is on the following line (pending=True).
    """
    body = line[len("$timescale"):]
    if "$end" in body:
        return (body.split("$end")[0].strip() or None, False)
    stripped = body.strip()
    if stripped:
        return (stripped, False)
    return (None, True)


def _parse_value_change(line: str) -> tuple[str | None, str]:
    """Return (id_code, value) for a value-change line, or (None, '') to skip."""
    first = line[0]
    if first in "bBrR":  # vector or real: '<value> <code>'
        value, _, code = line.partition(" ")
        code = code.strip()
        return (code or None, value)
    if first in "01xXzZ":  # scalar: '<value><code>'
        return (line[1:].strip() or None, first)
    return (None, "")
