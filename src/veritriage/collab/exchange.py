"""Bundle exchange: deterministic, lossless export and import.

Export canonicalizes the bundle (sorted keys, tight separators) and gzips it
with a zeroed mtime, so the same bundle always produces the same bytes. Import
transparently handles gzipped (``.vtb``) or plain JSON. The round-trip is
lossless: ``import_bundle(export_bundle(b)) == b`` and the recovered session
equals the original.

Only the normalized session travels; no raw waveform or log file is embedded.
Per-evidence-node ``raw_line`` provenance (a single captured log line already
in the graph) travels as part of the normalized evidence, so a shared bundle
is self-contained and identical to the live session it came from.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from veritriage.collab.model import InvestigationBundle

#: gzip magic number; import sniffs this to auto-detect compression.
_GZIP_MAGIC = b"\x1f\x8b"


class BundleFormatError(RuntimeError):
    """Raised when a bundle file cannot be read as a VeriTriage bundle."""


def _canonical_bytes(bundle: InvestigationBundle) -> bytes:
    """The bundle's full canonical JSON (fingerprint included), as bytes."""
    return json.dumps(
        bundle.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def export_bytes(bundle: InvestigationBundle, compress: bool = True) -> bytes:
    """Serialize a bundle to deterministic bytes (gzipped by default)."""
    payload = _canonical_bytes(bundle)
    return gzip.compress(payload, compresslevel=9, mtime=0) if compress else payload


def export_bundle(bundle: InvestigationBundle, path: Path, compress: bool = True) -> Path:
    """Write a bundle to ``path``; returns the path written.

    Deterministic: exporting the same bundle twice yields identical bytes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(export_bytes(bundle, compress=compress))
    return path


def import_bytes(data: bytes) -> InvestigationBundle:
    """Parse bundle bytes (gzipped or plain) back into a bundle.

    Raises:
        BundleFormatError: If the bytes are not a readable bundle.
    """
    raw = gzip.decompress(data) if data[:2] == _GZIP_MAGIC else data
    try:
        return InvestigationBundle.model_validate_json(raw)
    except Exception as exc:  # noqa: BLE001 - surfaced as a format error
        raise BundleFormatError(f"not a valid VeriTriage bundle: {exc}") from exc


def import_bundle(path: Path) -> InvestigationBundle:
    """Read a bundle from ``path`` (auto-detecting compression).

    Raises:
        BundleFormatError: If the file cannot be read as a bundle.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise BundleFormatError(f"cannot read {path}: {exc}") from exc
    return import_bytes(data)
