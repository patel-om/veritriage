"""Collaborative Investigation Platform (Milestone 10).

Turns an investigation into a portable, reviewable, reproducible engineering
artifact: the immutable Investigation Session wrapped in a versioned,
content-addressed, integrity-checked Investigation Bundle that also carries the
collaboration layer (reviews and annotations that sit on top of the session
and never touch it). An engineer can export a bundle, hand it to another with
no access to the original regression environment, and have them import, review,
annotate, validate, compare, and continue it.

Public surface (reached by clients through WorkspaceServices, never directly):
bundle model + sealing, export/import, validation, reviews, annotations (with
a registry so a new annotation type is one registration), and explanatory
comparison.

Dependencies point outward: this package imports only the workspace (the
session type) and the models vocabulary. No engine, parser, provider, or the
pipeline is importable here, and no existing subsystem imports this package.
Importing it registers the built-in annotation target kinds.
"""

from veritriage.collab.annotation import (
    add_annotation,
    available_targets,
    register_annotation_target,
    register_builtin_targets,
    target_exists,
    unregister_annotation_target,
)
from veritriage.collab.comparison import BundleComparison, FacetDelta, compare_bundles
from veritriage.collab.exchange import (
    BundleFormatError,
    export_bundle,
    export_bytes,
    import_bundle,
    import_bytes,
)
from veritriage.collab.model import (
    Annotation,
    BundleMetadata,
    InvestigationBundle,
    Review,
    ReviewVerdict,
    make_bundle,
    seal_bundle,
)
from veritriage.collab.review import add_review, review_status
from veritriage.collab.validation import (
    Severity,
    ValidationFinding,
    ValidationResult,
    validate_bundle,
)

# Registering the built-in annotation targets is a side effect of import, so
# the workspace's bundle methods and MCP tools see them without extra setup.
register_builtin_targets()

__all__ = [
    "Annotation",
    "BundleComparison",
    "BundleFormatError",
    "BundleMetadata",
    "FacetDelta",
    "InvestigationBundle",
    "Review",
    "ReviewVerdict",
    "Severity",
    "ValidationFinding",
    "ValidationResult",
    "add_annotation",
    "add_review",
    "available_targets",
    "compare_bundles",
    "export_bundle",
    "export_bytes",
    "import_bundle",
    "import_bytes",
    "make_bundle",
    "register_annotation_target",
    "register_builtin_targets",
    "review_status",
    "seal_bundle",
    "target_exists",
    "unregister_annotation_target",
    "validate_bundle",
]
