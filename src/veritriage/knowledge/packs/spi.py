"""SPI / QSPI Knowledge Pack.

The Serial Peripheral Interface: clock polarity/phase modes (CPOL/CPHA),
chip-select framing, and the multi-lane QSPI variant. The failures are a
mode mismatch that samples the wrong clock edge and a chip-select timing
violation that truncates a transfer.
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

_SPEC = "SPI / QSPI de-facto interface conventions"


@register_pack
def spi_pack() -> KnowledgePack:
    return KnowledgePack(
        id="spi",
        name="SPI / QSPI",
        version="1.0.0",
        domain="protocol",
        summary="SPI CPOL/CPHA sampling modes and chip-select framing timing.",
        concepts=[
            Concept(
                id="spi.modes",
                name="CPOL/CPHA modes",
                summary=(
                    "SPI mode is set by CPOL (idle clock level) and CPHA (sampling "
                    "edge). Master and slave must agree on the mode; a mismatch makes "
                    "one side sample on the wrong edge and read shifted or wrong data."
                ),
                markers=[r"\bspi\b", r"\bcpol\b|\bcpha\b|spi mode", r"clock (?:polarity|phase)|sampling edge"],
                references=[Reference(source=_SPEC, section="Modes", note="CPOL/CPHA sampling conventions.")],
            ),
            Concept(
                id="spi.framing",
                name="Chip-select framing",
                summary=(
                    "Chip select (CS) frames a transfer: it must assert with setup "
                    "before the first clock and stay asserted, with hold, until the "
                    "last bit. Deasserting CS mid-transfer truncates the frame and "
                    "desynchronizes the slave's bit counter."
                ),
                markers=[r"chip[- ]select|\bcs\b|\bssn?\b", r"setup|hold", r"frame|transfer"],
                references=[Reference(source=_SPEC, section="Framing", note="Chip-select timing.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="sclk", role="serial clock", channel="SPI"),
            ProtocolSignal(name="cs_n", role="chip select", channel="SPI"),
        ],
        patterns=[
            FailurePattern(
                id="spi.mode-mismatch",
                name="CPOL/CPHA mode mismatch",
                summary=(
                    "Master and slave disagreed on CPOL/CPHA, so one side sampled on "
                    "the wrong clock edge and read shifted or incorrect data."
                ),
                required=[
                    EvidenceClause(
                        name="wrong sampling edge",
                        pattern=r"spi.*(?:cpol|cpha).*mismatch|clock (?:polarity|phase).*(?:mismatch|wrong)|sampled (?:wrong|incorrect) edge",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="spi context", pattern=r"\bspi\b|\bcpol\b|\bcpha\b|sclk"),
                ],
                typical_causes=[
                    "Slave mode strap or register set to the wrong CPOL/CPHA",
                    "Master samples on the launch edge instead of the capture edge",
                    "Clock inversion added in the path without adjusting the mode",
                ],
                ownership="design",
                suggested_signals=["sclk", "sampling edge", "mode config"],
                playbook_id="spi.mode-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="Modes", note="Both sides must agree on mode.")],
            ),
            FailurePattern(
                id="spi.cs-timing",
                name="Chip-select timing violation",
                summary=(
                    "Chip select violated its setup/hold or deasserted mid-transfer, "
                    "truncating the frame and desynchronizing the slave's bit counter."
                ),
                required=[
                    EvidenceClause(
                        name="cs timing violated",
                        pattern=r"chip[- ]select.*(?:timing|violat)|\bcs\b.*(?:setup|hold).*violat|cs deassert.*(?:early|mid)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "CS deasserted by the master before the final clock edge",
                    "CS setup time to first SCLK not met at higher clock rates",
                    "Automatic CS control counts the wrong number of bits",
                ],
                ownership="design",
                suggested_signals=["cs_n", "sclk", "bit counter"],
                playbook_id="spi.framing-debug",
                confidence_modifiers={"rtl_bug": 0.11},
                references=[Reference(source=_SPEC, section="Framing", note="CS setup/hold and frame length.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="spi.mode-debug",
                name="SPI mode debug",
                steps=[
                    PlaybookStep(action="Confirm master and slave CPOL/CPHA settings match", signals=["mode config"]),
                    PlaybookStep(action="Check which edge each side samples on", signals=["sampling edge"]),
                    PlaybookStep(action="Account for any clock inversion added in the path"),
                    PlaybookStep(action="Verify the first bit alignment against the mode"),
                ],
            ),
            DebugPlaybook(
                id="spi.framing-debug",
                name="SPI framing debug",
                steps=[
                    PlaybookStep(action="Measure CS assert-to-first-clock setup and last-clock-to-deassert hold", signals=["cs_n", "sclk"]),
                    PlaybookStep(action="Confirm CS stays asserted for the whole frame", signals=["cs_n"]),
                    PlaybookStep(action="Check the automatic CS bit count against the transfer length", signals=["bit counter"]),
                    PlaybookStep(action="Verify the slave resynchronizes on the next CS assertion"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for SPI/QSPI.")],
    )
