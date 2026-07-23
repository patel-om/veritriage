"""The waveform adapter interface: the ONLY format-aware code in the platform.

An adapter's whole and only job is to turn one simulator's waveform artifact
into normalized :class:`~veritriage.waveform.model.WaveformMetadata`. It may
inspect raw waveform data, but under the lossy-by-design law it may only emit
normalized metadata: raw transitions are never retained, cached, or exposed
outside the adapter. Adapters never touch the Evidence Graph, reasoning, or AI.

Add a new simulator by writing a new ``WaveformAdapter`` subclass and
registering it. Nothing else in the platform changes; the architecture tests in
``tests/test_waveform.py`` prove it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from fnmatch import fnmatch
from pathlib import Path
from typing import ClassVar

from veritriage.waveform.model import WaveformCapability, WaveformMetadata


class WaveformAdapterError(RuntimeError):
    """Raised when an adapter cannot read the artifact it was handed."""


class WaveformAdapter(ABC):
    """Base class for every waveform format adapter.

    Subclasses set :attr:`name`, :attr:`format`, :attr:`file_patterns`, and
    :attr:`capabilities`, implement :meth:`extract`, and register with
    ``@register_adapter``.
    """

    #: Unique adapter name (used in provenance and the ``waveform`` CLI table).
    name: ClassVar[str]

    #: Short format tag recorded on the metadata for provenance, e.g. "vcd".
    format: ClassVar[str]

    #: Glob patterns this adapter claims.
    file_patterns: ClassVar[tuple[str, ...]] = ()

    #: What this adapter can resolve. Detectors needing a missing capability are
    #: skipped and reported as unavailable rather than silently passing.
    capabilities: ClassVar[frozenset[WaveformCapability]] = frozenset()

    @classmethod
    def can_handle(cls, path: Path) -> bool:
        """Whether this adapter claims the given file (by filename pattern)."""
        return any(fnmatch(path.name, pattern) for pattern in cls.file_patterns)

    @abstractmethod
    def extract(self, path: Path) -> WaveformMetadata:
        """Read ``path`` and return normalized metadata.

        Implementations must set ``format``, ``adapter`` (to :attr:`name`), and
        ``capabilities`` (to :attr:`capabilities`) on the returned model, and
        must not retain raw transition data.
        """
        raise NotImplementedError
