"""Bundle validation: deterministic integrity and consistency verification.

Every check is a pure function of the bundle, so the same bundle always
produces the same :class:`ValidationResult`, byte for byte
(``test_bundle_validation_is_reproducible``). Findings are severity-tagged so
the CLI, the report, and MCP all render the same verdict; a bundle is ``ok``
when it has no error-severity findings (warnings, e.g. unknown forward-compat
extensions, do not fail it).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from veritriage.collab.annotation import available_targets, target_exists
from veritriage.collab.model import (
    BUNDLE_SCHEMA_VERSION,
    InvestigationBundle,
    compute_fingerprint,
    make_bundle_id,
)

#: Fields the bundle model defines; anything else is a forward-compat extension.
_KNOWN_BUNDLE_FIELDS = {
    "schema_version",
    "bundle_id",
    "session",
    "reviews",
    "annotations",
    "metadata",
}


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ValidationFinding(BaseModel):
    severity: Severity
    code: str
    message: str


class ValidationResult(BaseModel):
    bundle_id: str
    schema_version: str
    findings: list[ValidationFinding] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity is Severity.ERROR for f in self.findings)

    @property
    def errors(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationFinding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]


def validate_bundle(bundle: InvestigationBundle) -> ValidationResult:
    """Verify a bundle's schema, integrity, and referential consistency."""
    findings: list[ValidationFinding] = []

    def error(code: str, message: str) -> None:
        findings.append(ValidationFinding(severity=Severity.ERROR, code=code, message=message))

    def warn(code: str, message: str) -> None:
        findings.append(ValidationFinding(severity=Severity.WARNING, code=code, message=message))

    # Schema compatibility: major must match; a newer minor is a warning.
    major = bundle.schema_version.split(".")[0]
    if major != BUNDLE_SCHEMA_VERSION.split(".")[0]:
        error(
            "schema-incompatible",
            f"bundle schema major {bundle.schema_version} is not understood "
            f"(this build speaks {BUNDLE_SCHEMA_VERSION})",
        )
    elif bundle.schema_version != BUNDLE_SCHEMA_VERSION:
        warn(
            "schema-newer-minor",
            f"bundle schema {bundle.schema_version} is newer than {BUNDLE_SCHEMA_VERSION}; "
            "reading forward-compatibly",
        )

    # Integrity: recompute the fingerprint and the content-derived IDs.
    expected_fp = compute_fingerprint(bundle)
    if bundle.metadata.fingerprint != expected_fp:
        error(
            "fingerprint-mismatch",
            "integrity fingerprint does not match the bundle content (tampered or corrupt)",
        )
    expected_id = make_bundle_id(
        bundle.session.session_id, bundle.reviews, bundle.annotations, bundle.schema_version
    )
    if bundle.bundle_id != expected_id:
        error("bundle-id-mismatch", "bundle_id does not match its content")
    if bundle.metadata.session_id != bundle.session.session_id:
        error("metadata-session-mismatch", "metadata.session_id does not match the embedded session")

    # Referential integrity: annotations must resolve to real objects.
    known_targets = set(available_targets())
    for annotation in bundle.annotations:
        if annotation.target_type not in known_targets:
            warn(
                "annotation-unknown-target",
                f"annotation {annotation.id} targets unknown kind {annotation.target_type!r}",
            )
        elif not target_exists(bundle.session, annotation.target_type, annotation.target_id):
            error(
                "annotation-dangling",
                f"annotation {annotation.id} targets missing "
                f"{annotation.target_type}:{annotation.target_id}",
            )

    # Broken relationships: graph edges and cited evidence must exist.
    graph = bundle.session.graph
    for edge in graph.edges:
        if edge.source_id not in graph.nodes or edge.target_id not in graph.nodes:
            error("edge-dangling", f"edge references a missing node ({edge.source_id} -> {edge.target_id})")
    reasoning = bundle.session.report.reasoning
    if reasoning is not None:
        for hypothesis in reasoning.hypotheses:
            missing = [i for i in hypothesis.evidence_ids if i not in graph.nodes]
            if missing:
                error(
                    "hypothesis-dangling",
                    f"hypothesis {hypothesis.id} cites missing evidence {missing}",
                )

    # Forward-compatibility: unknown top-level fields are warnings, not errors.
    extra = set(getattr(bundle, "model_extra", None) or {}) - _KNOWN_BUNDLE_FIELDS
    for field in sorted(extra):
        warn("unknown-extension", f"bundle carries an unknown extension field {field!r} (ignored)")

    return ValidationResult(
        bundle_id=bundle.bundle_id,
        schema_version=bundle.schema_version,
        findings=findings,
    )
