"""UART Knowledge Pack.

The asynchronous serial workhorse: start/stop/parity framing at an agreed
baud rate, with an RX FIFO buffering received bytes. The failures are a
framing error from a baud or stop-bit mismatch and an RX overrun that loses
data.
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

_SPEC = "UART (16550-class) interface conventions"


@register_pack
def uart_pack() -> KnowledgePack:
    return KnowledgePack(
        id="uart",
        name="UART",
        version="1.0.0",
        domain="protocol",
        summary="UART start/stop/parity framing and RX FIFO overrun.",
        concepts=[
            Concept(
                id="uart.framing",
                name="Asynchronous framing",
                summary=(
                    "A UART frame is a start bit, data bits, optional parity, and one "
                    "or more stop bits, sampled at an agreed baud rate. If the baud "
                    "rates differ or the stop bit is not high when expected, the "
                    "receiver flags a framing error."
                ),
                markers=[r"\buart\b", r"baud|start bit|stop bit|parity", r"framing"],
                references=[Reference(source=_SPEC, section="Framing", note="Start/stop/parity and baud.")],
            ),
            Concept(
                id="uart.fifo",
                name="RX FIFO and overrun",
                summary=(
                    "The receive FIFO buffers bytes until software reads them. If a "
                    "new byte arrives while the FIFO is full and the shift register "
                    "already holds an unread byte, the oldest data is lost: an "
                    "overrun."
                ),
                markers=[r"rx fifo|receive fifo", r"overrun", r"fifo (?:full|overflow)"],
                references=[Reference(source=_SPEC, section="FIFO", note="Overrun condition.")],
            ),
        ],
        signals=[
            ProtocolSignal(name="rxd", role="receive data line", channel="UART"),
            ProtocolSignal(name="fifo_level", role="RX FIFO occupancy", channel="UART"),
        ],
        patterns=[
            FailurePattern(
                id="uart.framing-error",
                name="Framing error",
                summary=(
                    "The receiver detected a framing error: the stop bit was not high "
                    "when expected, typically from a baud-rate mismatch or a corrupted "
                    "frame."
                ),
                required=[
                    EvidenceClause(
                        name="framing error flagged",
                        pattern=r"uart.*framing error|stop bit.*(?:not|missing|error)|framing error.*(?:baud|mismatch)",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="uart context", pattern=r"\buart\b|baud|stop bit|framing"),
                ],
                typical_causes=[
                    "Baud divisor programmed for the wrong reference clock",
                    "Oversampling point sampling the bit off-center",
                    "Number of stop bits configured differently on each end",
                ],
                ownership="design",
                suggested_signals=["rxd", "baud divisor", "sample point"],
                playbook_id="uart.framing-debug",
                confidence_modifiers={"rtl_bug": 0.10},
                references=[Reference(source=_SPEC, section="Framing", note="Stop-bit sampling.")],
            ),
            FailurePattern(
                id="uart.overrun",
                name="RX FIFO overrun",
                summary=(
                    "A received byte was lost because the RX FIFO was full and the "
                    "shift register still held an unread byte when the next arrived."
                ),
                required=[
                    EvidenceClause(
                        name="rx overrun",
                        pattern=r"uart.*overrun|rx (?:fifo )?overrun|receive.*overrun.*data lost",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Software/DMA not draining the FIFO fast enough at high baud",
                    "FIFO threshold interrupt raised too late",
                    "Flow control (RTS/CTS) not enabled or not honored",
                ],
                ownership="design",
                suggested_signals=["fifo_level", "drain rate", "flow control"],
                playbook_id="uart.overrun-debug",
                confidence_modifiers={"rtl_bug": 0.10},
                references=[Reference(source=_SPEC, section="FIFO", note="Overrun and flow control.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="uart.framing-debug",
                name="UART framing debug",
                steps=[
                    PlaybookStep(action="Verify the baud divisor against the actual reference clock", signals=["baud divisor"]),
                    PlaybookStep(action="Check the oversampling sample point is centered in the bit", signals=["sample point"]),
                    PlaybookStep(action="Confirm both ends agree on data bits, parity, and stop bits"),
                    PlaybookStep(action="Scope RXD for a bit-time skew across the frame", signals=["rxd"]),
                ],
            ),
            DebugPlaybook(
                id="uart.overrun-debug",
                name="UART overrun debug",
                steps=[
                    PlaybookStep(action="Measure the FIFO drain rate against the incoming byte rate", signals=["fifo_level", "drain rate"]),
                    PlaybookStep(action="Check the FIFO threshold interrupt timing"),
                    PlaybookStep(action="Confirm RTS/CTS flow control is enabled and honored", signals=["flow control"]),
                    PlaybookStep(action="Verify the overrun status bit sets and clears correctly"),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for UART.")],
    )
