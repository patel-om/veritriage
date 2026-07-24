"""Compute Express Link (CXL) Knowledge Pack.

CXL layers three protocols on a PCIe PHY: CXL.io (config/enumeration, PCIe
semantics), CXL.cache (device caching of host memory), and CXL.mem (host
access to device-attached memory). The bring-up failure is Flex Bus mode
negotiation; the runtime failure is a CXL.mem request that never completes.
"""

from __future__ import annotations

from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    PlaybookStep,
    ProtocolSignal,
    Reference,
)
from veritriage.knowledge.registry import register_pack

_SPEC = "Compute Express Link (CXL) Specification"


@register_pack
def cxl_pack() -> KnowledgePack:
    return KnowledgePack(
        id="cxl",
        name="Compute Express Link (CXL)",
        version="1.0.0",
        domain="protocol",
        summary="CXL Flex Bus negotiation and CXL.mem/.cache transaction completion.",
        concepts=[
            Concept(
                id="cxl.flexbus",
                name="Flex Bus mode negotiation",
                summary=(
                    "A Flex Bus port trains as PCIe and, during alternate-protocol "
                    "negotiation, may switch to CXL, agreeing which of CXL.io/.cache/"
                    ".mem are enabled. If negotiation fails or the modes disagree, "
                    "the link either falls back to PCIe or never brings up CXL."
                ),
                markers=[r"flex ?bus", r"alternate protocol|mode negotiation", r"\bcxl\b.*(?:training|negotiat)"],
                references=[Reference(source=_SPEC, section="6.1", note="Flex Bus and alternate protocol negotiation.")],
            ),
            Concept(
                id="cxl.mem",
                name="CXL.mem and CXL.cache transactions",
                summary=(
                    "CXL.mem carries host-to-device memory requests (M2S) answered by "
                    "device responses (S2M); CXL.cache lets a device cache host memory "
                    "with coherent snoops. Each M2S request requires an S2M response; a "
                    "missing completion stalls the host memory access."
                ),
                markers=[r"cxl\.mem|cxl\.cache", r"\bm2s\b|\bs2m\b", r"(?:mem|cache) (?:request|completion|response)"],
                references=[Reference(source=_SPEC, section="3.3", note="CXL.mem M2S/S2M transaction flow.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="flexbus_mode", role="negotiated Flex Bus mode", channel="link"),
            ProtocolSignal(name="m2s_req", role="host-to-device request", channel="CXL.mem"),
            ProtocolSignal(name="s2m_rsp", role="device-to-host response", channel="CXL.mem"),
        ],
        patterns=[
            FailurePattern(
                id="cxl.link-training-failed",
                name="CXL alternate-protocol negotiation failed",
                summary=(
                    "Flex Bus negotiation did not bring up CXL: alternate-protocol "
                    "negotiation failed or the agreed modes were inconsistent, so the "
                    "port stayed in PCIe or never trained CXL."
                ),
                required=[
                    EvidenceClause(
                        name="cxl negotiation failed",
                        pattern=r"cxl.*(?:link training|negotiation).*(?:fail|stuck)|alternate protocol.*(?:fail|not negotiated)|flex ?bus.*(?:training|mode).*(?:fail|mismatch)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="cxl context", pattern=r"\bcxl\b|flex ?bus|alternate protocol"),
                ],
                typical_causes=[
                    "Alternate-protocol advertisement dropped or malformed in the modified TS1/TS2",
                    "Enabled-mode bits disagree between the two ports",
                    "Fallback to PCIe triggered by a spurious negotiation timeout",
                ],
                ownership="design",
                suggested_signals=["flexbus_mode", "alternate protocol status", "link state"],
                playbook_id="cxl.negotiation-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="6.1", note="Alternate protocol negotiation.")],
            ),
            FailurePattern(
                id="cxl.mem-completion-missing",
                name="CXL.mem request without completion",
                summary=(
                    "An M2S memory request on CXL.mem never received its S2M "
                    "response, so the host memory access is outstanding forever."
                ),
                required=[
                    EvidenceClause(
                        name="s2m response never returned",
                        pattern=r"cxl\.mem.*(?:no|missing) (?:completion|response)|m2s.*s2m.*never|mem request.*(?:no completion|never returned|never completed)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Device memory scheduler drops the request under a full queue",
                    "S2M response routed to the wrong tag/requester",
                    "Poison or error response never generated for a failed access",
                ],
                ownership="design",
                suggested_signals=["m2s_req", "s2m_rsp", "device memory scheduler"],
                playbook_id="cxl.mem-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="3.3", note="Every M2S request needs an S2M response.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="cxl.negotiation-debug",
                name="CXL negotiation debug",
                steps=[
                    PlaybookStep(action="Capture the modified TS1/TS2 alternate-protocol advertisement on both ports"),
                    PlaybookStep(action="Compare the enabled-mode bits agreed by each side", signals=["flexbus_mode"]),
                    PlaybookStep(action="Check for a negotiation timeout that forced PCIe fallback", signals=["link state"]),
                    PlaybookStep(action="Confirm the PHY reached the required speed before negotiation"),
                ],
            ),
            DebugPlaybook(
                id="cxl.mem-debug",
                name="CXL.mem completion debug",
                steps=[
                    PlaybookStep(action="Find the outstanding M2S request and its tag", signals=["m2s_req"]),
                    PlaybookStep(action="Trace the device memory scheduler for a drop under backpressure", signals=["device memory scheduler"]),
                    PlaybookStep(action="Confirm the S2M response is routed to the correct requester/tag", signals=["s2m_rsp"]),
                    PlaybookStep(action="Verify error/poison responses are generated for failed accesses"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for CXL.")],
    )
