"""I2C / I3C Knowledge Pack.

The two-wire bus family: classic I2C (start/stop, addressing, ACK, clock
stretching) and I3C (dynamic addressing, common command codes, in-band
interrupts). The failures are a device that never acknowledges and an I3C
in-band interrupt lost to arbitration.
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

_SPEC = "MIPI I3C / NXP I2C-bus Specification"


@register_pack
def i2c_i3c_pack() -> KnowledgePack:
    return KnowledgePack(
        id="i2c-i3c",
        name="I2C / I3C",
        version="1.0.0",
        domain="protocol",
        summary="I2C addressing/ACK and I3C dynamic addressing/IBI arbitration.",
        concepts=[
            Concept(
                id="i2c.addressing",
                name="I2C addressing and ACK",
                summary=(
                    "An I2C master issues START, an address byte with R/W, and expects "
                    "the addressed device to pull SDA low for ACK. A missing ACK "
                    "(NACK) on the address means no device responded, or the device "
                    "held clock stretching too long."
                ),
                markers=[r"\bi2c\b", r"\back\b|\bnack\b|acknowledge", r"start condition|stop condition|clock stretch"],
                references=[Reference(source=_SPEC, section="I2C", note="Addressing and acknowledge.")],
            ),
            Concept(
                id="i3c.dynamic",
                name="I3C dynamic addressing and IBI",
                summary=(
                    "I3C assigns dynamic addresses (via ENTDAA), issues common command "
                    "codes (CCC), and lets targets raise in-band interrupts (IBI) by "
                    "winning arbitration on the bus. An IBI that loses arbitration and "
                    "is not retried is a lost interrupt."
                ),
                markers=[r"\bi3c\b", r"\bibi\b|in[- ]band interrupt", r"\bccc\b|entdaa|dynamic address"],
                references=[Reference(source=_SPEC, section="I3C", note="Dynamic addressing, CCC, and IBI.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="sda_ack", role="acknowledge on SDA", channel="I2C"),
            ProtocolSignal(name="ibi_win", role="IBI won arbitration", channel="I3C"),
        ],
        patterns=[
            FailurePattern(
                id="i2c.missing-ack",
                name="No ACK from addressed device",
                summary=(
                    "The addressed device did not acknowledge: SDA was not pulled low "
                    "for ACK after the address byte, so the transfer cannot proceed."
                ),
                required=[
                    EvidenceClause(
                        name="address not acknowledged",
                        pattern=r"i2c.*(?:no|missing) ack|nack.*(?:address|device|byte)|acknowledge.*not (?:driven|received)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="i2c context", pattern=r"\bi2c\b|\bsda\b|\bscl\b|acknowledge"),
                ],
                typical_causes=[
                    "Address decode in the device does not match the transmitted address",
                    "Clock stretching released too late, past the master's timeout",
                    "SDA drive strength/timing misses the ACK sampling window",
                ],
                ownership="design",
                suggested_signals=["sda_ack", "device address decode", "clock stretch"],
                playbook_id="i2c.ack-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="I2C", note="Acknowledge on the ninth clock.")],
            ),
            FailurePattern(
                id="i3c.ibi-lost",
                name="I3C in-band interrupt lost",
                summary=(
                    "A target raised an IBI but lost bus arbitration and the request "
                    "was not retried, so the in-band interrupt was dropped and never "
                    "serviced."
                ),
                required=[
                    EvidenceClause(
                        name="ibi lost to arbitration",
                        pattern=r"i3c.*ibi.*(?:lost|dropped|not)|in[- ]band interrupt.*(?:lost|dropped)|ibi.*arbitration.*(?:lost|fail)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "IBI not re-arbitrated after losing to a higher-address target",
                    "IBI request cleared on arbitration loss instead of held",
                    "Address-based IBI priority resolved backwards",
                ],
                ownership="design",
                suggested_signals=["ibi_win", "arbitration state", "IBI request hold"],
                playbook_id="i3c.ibi-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="I3C", note="IBI arbitration and retry.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="i2c.ack-debug",
                name="I2C acknowledge debug",
                steps=[
                    PlaybookStep(action="Confirm the transmitted address matches the device's decode", signals=["device address decode"]),
                    PlaybookStep(action="Check clock stretching release timing against the master timeout", signals=["clock stretch"]),
                    PlaybookStep(action="Verify SDA is driven low within the ACK sampling window", signals=["sda_ack"]),
                    PlaybookStep(action="Rule out bus contention from a second master"),
                ],
            ),
            DebugPlaybook(
                id="i3c.ibi-debug",
                name="I3C IBI debug",
                steps=[
                    PlaybookStep(action="Trace the IBI arbitration and identify the winning target", signals=["arbitration state"]),
                    PlaybookStep(action="Confirm a losing IBI is held and retried, not cleared", signals=["IBI request hold"]),
                    PlaybookStep(action="Check the address-based priority resolution direction"),
                    PlaybookStep(action="Verify the controller accepts the IBI once it wins", signals=["ibi_win"]),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for I2C/I3C.")],
    )
