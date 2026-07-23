"""Built-in waveform adapters.

Importing this package registers every built-in adapter (side effect of the
``@register_adapter`` decorators). A new simulator adds one module here and
one import line; nothing else in the platform changes.
"""

from veritriage.waveform.adapters.base import WaveformAdapter, WaveformAdapterError
from veritriage.waveform.adapters.registry import (
    all_patterns,
    available_adapters,
    find_adapter,
    register_adapter,
    unregister_adapter,
)

# Importing an adapter module registers it. Add new adapter imports here.
from veritriage.waveform.adapters.manifest import ManifestAdapter
from veritriage.waveform.adapters.vcd import VcdAdapter

__all__ = [
    "ManifestAdapter",
    "VcdAdapter",
    "WaveformAdapter",
    "WaveformAdapterError",
    "all_patterns",
    "available_adapters",
    "find_adapter",
    "register_adapter",
    "unregister_adapter",
]
