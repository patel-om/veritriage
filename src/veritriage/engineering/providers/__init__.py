"""Built-in engineering context providers.

Importing this package registers every built-in provider (side effect of the
``@register_provider`` decorators). A new engineering system adds one module
here and one import line; nothing else in the platform changes.
"""

from veritriage.engineering.providers.base import ContextProvider, ContextProviderError
from veritriage.engineering.providers.registry import (
    available_providers,
    collect_context,
    register_provider,
    unregister_provider,
)

# Importing a provider module registers it. Add new provider imports here.
from veritriage.engineering.providers.git import GitProvider
from veritriage.engineering.providers.manifest import ManifestProvider

__all__ = [
    "ContextProvider",
    "ContextProviderError",
    "GitProvider",
    "ManifestProvider",
    "available_providers",
    "collect_context",
    "register_provider",
    "unregister_provider",
]
