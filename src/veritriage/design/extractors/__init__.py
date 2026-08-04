"""The built-in structure extractors.

Importing this package registers every built-in extractor. Each reaches the
builder through ``@register_extractor`` alone, so teaching the platform a new
structural facet means adding a module here (or anywhere else) and nothing more,
which ``test_new_extractor_needs_only_registration`` proves.
"""

from veritriage.design.extractors.hierarchy import HierarchyExtractor
from veritriage.design.extractors.topology import (
    AddressMapExtractor,
    ClockResetExtractor,
    InterfaceExtractor,
)
from veritriage.design.extractors.verification import (
    VerificationAssetExtractor,
    VerificationTopologyExtractor,
)

__all__ = [
    "AddressMapExtractor",
    "ClockResetExtractor",
    "HierarchyExtractor",
    "InterfaceExtractor",
    "VerificationAssetExtractor",
    "VerificationTopologyExtractor",
]
