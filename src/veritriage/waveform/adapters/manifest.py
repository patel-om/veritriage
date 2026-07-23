"""Canonical waveform metadata adapter (simulator-independent JSON).

This is the reference format: the contract any tool or exporter can target to
feed VeriTriage without VeriTriage learning that tool's binary format. It is
also the full-fidelity path, declaring every capability, so it exercises every
observation detector. Fixtures written against it are trivial and deterministic.

Schema (all times are integers in the file's timescale units):

    {
      "simulator": "vcs",
      "timescale": "1ns",
      "dump": {"start": 0, "end": 20000},
      "signals": [
        {"name": "clk", "scope": "tb", "role": "clock",
         "toggle_count": 2000, "first_edge": 0, "last_edge": 20000, "width": 1}
      ],
      "handshakes": [
        {"name": "AR", "scope": "tb.dut.axi_if",
         "initiator": "arvalid", "responder": "arready"}
      ],
      "transactions": [
        {"id": "rd0", "kind": "read", "scope": "tb.dut",
         "start": 40, "end": null, "retry_count": 0}
      ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from veritriage.waveform.adapters.base import WaveformAdapter, WaveformAdapterError
from veritriage.waveform.adapters.registry import register_adapter
from veritriage.waveform.model import (
    HandshakeRef,
    SignalRole,
    TransactionRef,
    WaveformCapability,
    WaveformMetadata,
    WaveformSignal,
)


def _role(value: Any) -> SignalRole:
    """Map a manifest role string to a SignalRole, defaulting to OTHER."""
    try:
        return SignalRole(str(value).lower())
    except ValueError:
        return SignalRole.OTHER


def _int_or_none(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


@register_adapter
class ManifestAdapter(WaveformAdapter):
    """Reads a simulator-independent JSON waveform manifest."""

    name = "waveform_manifest"
    format = "manifest"
    file_patterns = ("*.wave.json", "waveform*.json", "*.wavemeta.json")
    capabilities = frozenset(WaveformCapability)  # canonical: resolves everything

    def extract(self, path: Path) -> WaveformMetadata:
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WaveformAdapterError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise WaveformAdapterError(f"{path}: expected a JSON object at the top level")

        dump = data.get("dump") or {}
        signals = [
            WaveformSignal(
                name=str(s["name"]),
                scope=str(s.get("scope", "")),
                width=int(s.get("width", 1)),
                role=_role(s.get("role")),
                first_edge=_int_or_none(s.get("first_edge")),
                last_edge=_int_or_none(s.get("last_edge")),
                toggle_count=int(s.get("toggle_count", 0)),
                metadata={k: v for k, v in s.items() if k not in _SIGNAL_KEYS},
            )
            for s in data.get("signals", [])
        ]
        handshakes = [
            HandshakeRef(
                name=str(h["name"]),
                scope=h.get("scope"),
                initiator=str(h["initiator"]),
                responder=str(h["responder"]),
            )
            for h in data.get("handshakes", [])
        ]
        transactions = [
            TransactionRef(
                id=str(t["id"]),
                kind=str(t.get("kind", "unknown")),
                scope=t.get("scope"),
                start=int(t["start"]),
                end=_int_or_none(t.get("end")),
                retry_count=int(t.get("retry_count", 0)),
            )
            for t in data.get("transactions", [])
        ]
        return WaveformMetadata(
            source_path=str(path),
            format=self.format,
            adapter=self.name,
            simulator=str(data["simulator"]) if data.get("simulator") else None,
            timescale=str(data["timescale"]) if data.get("timescale") else None,
            dump_start=_int_or_none(dump.get("start")),
            dump_end=_int_or_none(dump.get("end")),
            signals=signals,
            handshakes=handshakes,
            transactions=transactions,
            capabilities=self.capabilities,
        )


_SIGNAL_KEYS = {"name", "scope", "width", "role", "first_edge", "last_edge", "toggle_count"}
