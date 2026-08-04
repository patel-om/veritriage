"""The built-in provider library.

Importing this package registers every built-in provider. A vendor integration
reaches the platform through ``@register_llm_provider`` alone, which
``test_new_provider_needs_only_registration`` proves.
"""

from veritriage.ai.providers.builtin import (
    DeterministicEchoProvider,
    MockProvider,
    NullProvider,
    ReferenceProvider,
)

__all__ = [
    "DeterministicEchoProvider",
    "MockProvider",
    "NullProvider",
    "ReferenceProvider",
]
