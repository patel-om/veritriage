"""High Bandwidth Memory (HBM) Knowledge Pack.

Stacked DRAM with many independent channels and pseudo-channels. The
distinctive HBM failures are channel-routing errors (a transaction landing on
the wrong independent channel) and per-channel refresh colliding with access,
neither of which appears in a flat DRAM model.
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

_SPEC = "JEDEC High Bandwidth Memory (HBM) DRAM Standard"


@register_pack
def hbm_pack() -> KnowledgePack:
    return KnowledgePack(
        id="hbm",
        name="High Bandwidth Memory (HBM)",
        version="1.0.0",
        domain="memory",
        summary="HBM independent channels/pseudo-channels and per-channel refresh.",
        concepts=[
            Concept(
                id="hbm.channels",
                name="Independent channels and pseudo-channels",
                summary=(
                    "HBM presents many independent channels, each optionally split "
                    "into pseudo-channels sharing a command bus but with independent "
                    "banks. Address decode must route each transaction to exactly one "
                    "channel/pseudo-channel; a decode error corrupts an unrelated "
                    "channel's data."
                ),
                markers=[r"\bhbm\b", r"pseudo[- ]?channel|\bpc\b", r"channel (?:decode|routing|address)"],
                references=[Reference(source=_SPEC, section="Channels", note="Channel and pseudo-channel independence.")],
            ),
            Concept(
                id="hbm.refresh",
                name="Per-channel refresh",
                summary=(
                    "Each HBM channel refreshes independently. Refresh scheduling per "
                    "channel must not collide with in-flight accesses to that channel; "
                    "a collision either blocks the access or refreshes an open bank."
                ),
                markers=[r"hbm.*refresh|per[- ]channel refresh", r"refresh (?:collision|conflict)", r"channel refresh"],
                references=[Reference(source=_SPEC, section="Refresh", note="Per-channel refresh scheduling.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="channel_id", role="decoded target channel", channel="HBM"),
            ProtocolSignal(name="pc_id", role="decoded pseudo-channel", channel="HBM"),
        ],
        patterns=[
            FailurePattern(
                id="hbm.channel-crosstalk",
                name="Transaction routed to the wrong channel",
                summary=(
                    "Address decode sent a transaction to the wrong channel or "
                    "pseudo-channel, so an access landed on memory it was not "
                    "addressed to."
                ),
                required=[
                    EvidenceClause(
                        name="channel decode wrong",
                        pattern=r"hbm.*(?:wrong|cross).*channel|pseudo[- ]?channel.*(?:mismatch|crosstalk|wrong)|channel (?:routing|address).*wrong",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="hbm context", pattern=r"\bhbm\b|pseudo[- ]?channel|channel decode"),
                ],
                typical_causes=[
                    "Channel-select address bits mapped to the wrong field",
                    "Pseudo-channel bit ignored so both share a bank incorrectly",
                    "Interleave mode changes the decode without updating the router",
                ],
                ownership="design",
                suggested_signals=["channel_id", "pc_id", "address decode"],
                playbook_id="hbm.decode-debug",
                confidence_modifiers={"rtl_bug": 0.12},
                references=[Reference(source=_SPEC, section="Channels", note="Address-to-channel decode.")],
            ),
            FailurePattern(
                id="hbm.refresh-conflict",
                name="Per-channel refresh collided with access",
                summary=(
                    "A per-channel refresh was scheduled on top of an in-flight "
                    "access to the same channel, blocking the access or refreshing "
                    "an open bank."
                ),
                required=[
                    EvidenceClause(
                        name="refresh collided with access",
                        pattern=r"hbm.*refresh.*(?:conflict|collision)|refresh.*(?:collided|conflict).*(?:access|channel)|per[- ]channel refresh.*(?:block|collision)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Per-channel refresh arbiter unaware of that channel's open access",
                    "Refresh issued without first precharging open banks on the channel",
                    "Shared refresh timer across channels that should be independent",
                ],
                ownership="design",
                suggested_signals=["channel_id", "refresh scheduler", "bank state per channel"],
                playbook_id="hbm.refresh-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="Refresh", note="Refresh vs access per channel.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="hbm.decode-debug",
                name="HBM channel decode debug",
                steps=[
                    PlaybookStep(action="Compare the intended channel/pseudo-channel to the decoded one", signals=["channel_id", "pc_id"]),
                    PlaybookStep(action="Check the channel-select address bit mapping", signals=["address decode"]),
                    PlaybookStep(action="Confirm the pseudo-channel bit is honored in bank selection"),
                    PlaybookStep(action="Verify interleave-mode changes update the router"),
                ],
            ),
            DebugPlaybook(
                id="hbm.refresh-debug",
                name="HBM refresh debug",
                steps=[
                    PlaybookStep(action="Identify the refresh and the colliding access on the same channel", signals=["refresh scheduler"]),
                    PlaybookStep(action="Confirm the refresh arbiter sees that channel's open access"),
                    PlaybookStep(action="Check open banks are precharged before refresh", signals=["bank state per channel"]),
                    PlaybookStep(action="Verify each channel has an independent refresh timer"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for HBM.")],
    )
