"""Security verification Knowledge Pack.

Access-control and secure-boot checks. This is the first pack to use omission
clauses: a security failure is often the *absence* of an expected check
firing (a privileged access that completes with no access-control check, a
boot stage that runs with no signature verification). An ``absent`` required
clause states that directly, instead of the old must_fail/pattern="." trick.
"""

from __future__ import annotations

from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    PlaybookStep,
    Reference,
)
from veritriage.knowledge.registry import register_pack

_SPEC = "Hardware security verification methodology"


@register_pack
def security_pack() -> KnowledgePack:
    return KnowledgePack(
        id="security",
        name="Security verification",
        version="1.0.0",
        domain="security",
        summary="Access-control bypass and unverified secure boot, expressed as omissions.",
        concepts=[
            Concept(
                id="security.access-control",
                name="Access control",
                summary=(
                    "A protected resource may only be reached after an access-control "
                    "check authorizes the requester's privilege/security state. The "
                    "telltale of a bypass is an accepted access with no corresponding "
                    "check having fired, so the signature is an absence, not a "
                    "presence."
                ),
                markers=[r"access control|access[- ]control", r"secure (?:region|state|world)|privileged", r"authoriz|permission"],
                references=[Reference(source=_SPEC, section="AccessControl", note="Check-before-access requirement.")],
            ),
            Concept(
                id="security.secure-boot",
                name="Secure boot chain of trust",
                summary=(
                    "Each boot stage must be authenticated (signature/measurement) "
                    "before it executes, extending the chain of trust. A stage that "
                    "runs without a preceding verification breaks the chain; again "
                    "the failure is the missing verification, an omission."
                ),
                markers=[r"secure boot|chain of trust", r"signature|authenticat|attest", r"boot (?:stage|image|rom)"],
                references=[Reference(source=_SPEC, section="SecureBoot", note="Verify-before-execute requirement.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="security.access-control-bypassed",
                name="Access-control check bypassed",
                summary=(
                    "A protected access was accepted while no access-control check "
                    "fired: the presence of the accepted access plus the absence of "
                    "any authorization check is the bypass signature."
                ),
                required=[
                    EvidenceClause(
                        name="protected access accepted",
                        pattern=r"(?:secure|privileged|protected) (?:region|resource|access|write|read).*(?:accepted|allowed|succeeded|completed)|unauthorized access.*(?:allowed|succeeded)",
                        must_fail=True,
                    ),
                    EvidenceClause(
                        name="no access-control check fired",
                        pattern=r"access[- ]control (?:check )?(?:passed|granted|enforced|fired)|permission (?:check )?(?:passed|granted)|authoriz(?:ation|ed) (?:check )?(?:passed|granted)",
                        absent=True,
                    ),
                ],
                typical_causes=[
                    "Privilege/security-state check missing on a decode path",
                    "Access-control logic bypassed for a subset of addresses",
                    "Secure/non-secure attribute not propagated to the checker",
                ],
                ownership="design",
                suggested_signals=["security state", "access-control enable", "protected region hit"],
                playbook_id="security.access-debug",
                confidence_modifiers={"rtl_bug": 0.13},
                references=[Reference(source=_SPEC, section="AccessControl", note="No access without a check.")],
            ),
            FailurePattern(
                id="security.secure-boot-unverified",
                name="Boot stage executed without verification",
                summary=(
                    "A boot stage executed while no signature/authentication check "
                    "was recorded for it, breaking the chain of trust: an accepted "
                    "execution plus an absent verification."
                ),
                required=[
                    EvidenceClause(
                        name="boot stage executed",
                        pattern=r"boot (?:stage|image|loader).*(?:launched|executed|proceeded|jumped)|next (?:stage|image).*(?:launched|executed)",
                        must_fail=True,
                    ),
                    EvidenceClause(
                        name="no signature verification",
                        pattern=r"signature (?:verified|valid|check passed)|image (?:authenticated|attested)|secure boot (?:verified|passed)",
                        absent=True,
                    ),
                ],
                typical_causes=[
                    "Verification step skipped or gated by a debug/override left enabled",
                    "Signature-check result not required before the jump to the stage",
                    "Measurement extended after, not before, execution",
                ],
                ownership="design",
                suggested_signals=["verify-done", "stage-launch enable", "override/debug straps"],
                playbook_id="security.boot-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="SecureBoot", note="Verify before execute.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="security.access-debug",
                name="Access-control bypass debug",
                steps=[
                    PlaybookStep(action="Confirm the accepted access and the security state at that cycle", signals=["security state", "protected region hit"]),
                    PlaybookStep(action="Check whether the access-control check was invoked at all", signals=["access-control enable"]),
                    PlaybookStep(action="Trace the decode path for a subset of addresses that skip the check"),
                    PlaybookStep(action="Verify the secure/non-secure attribute reaches the checker"),
                ],
            ),
            DebugPlaybook(
                id="security.boot-debug",
                name="Secure-boot verification debug",
                steps=[
                    PlaybookStep(action="Confirm which stage executed and whether a verify-done was recorded first", signals=["verify-done"]),
                    PlaybookStep(action="Check for a debug/override strap that bypasses verification", signals=["override/debug straps"]),
                    PlaybookStep(action="Confirm the jump to the stage is gated on the signature-check result", signals=["stage-launch enable"]),
                    PlaybookStep(action="Verify measurement/authentication happens before execution, not after"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for security verification.")],
    )
