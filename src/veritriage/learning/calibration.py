"""Confidence calibration: bounded, explainable, and off by default.

The one place learning touches ranking. A specialist that history repeatedly
confirms gains influence; one history repeatedly disproves loses it. Neither
can run away, because three guards apply:

1. **A floor on evidence.** Below ``MIN_OBSERVATIONS`` leading runs, an agent is
   left at 1.0. A specialist is never re-weighted on anecdote.
2. **A clamp on effect.** The multiplier is confined to
   ``[MIN_MULTIPLIER, MAX_MULTIPLIER]``, a deliberately narrow band. No amount
   of history can silence a specialist or crown one.
3. **A default of nothing.** An empty calibration map produces byte-identical
   output to v1.8.0, so calibration is opt-in through the presence of learning,
   not an ambient behavior change.

Calibration is applied by the Coordinator at merge time, never by an agent. An
agent still computes the same position from the same evidence; only its
influence on the merged finding moves. That is what preserves agent purity.
"""

from __future__ import annotations

from typing import Iterable

from veritriage.models import AgentReliability

#: Leading runs required before an agent is calibrated at all.
MIN_OBSERVATIONS = 3

#: The accuracy at which an agent is neither rewarded nor penalized.
NEUTRAL_ACCURACY = 0.5

#: How hard accuracy moves the multiplier before clamping.
SLOPE = 0.5

#: The band the multiplier is confined to.
MIN_MULTIPLIER = 0.80
MAX_MULTIPLIER = 1.20


def calibration_multiplier(accuracy: float | None, times_led: int) -> float:
    """Map an agent's historical accuracy to a bounded influence multiplier.

    Returns exactly 1.0 (no effect) when there is not enough evidence to judge.
    """
    if accuracy is None or times_led < MIN_OBSERVATIONS:
        return 1.0
    raw = 1.0 + (accuracy - NEUTRAL_ACCURACY) * SLOPE
    return round(max(MIN_MULTIPLIER, min(MAX_MULTIPLIER, raw)), 4)


def calibration_map(reliabilities: Iterable[AgentReliability]) -> dict[str, float]:
    """Agent ID -> multiplier, omitting agents that would have no effect.

    Omitting 1.0 entries keeps the map honest: what appears in it is exactly
    what changes an outcome, so an empty map provably changes nothing.
    """
    calibration: dict[str, float] = {}
    for reliability in reliabilities:
        multiplier = reliability.calibration_multiplier
        if multiplier != 1.0:
            calibration[reliability.agent_id] = multiplier
    return dict(sorted(calibration.items()))


def explain(agent_id: str, multiplier: float, reliability: AgentReliability | None) -> str:
    """A printable reason for one calibration adjustment.

    Every calibrated confidence must be readable line by line, like every other
    confidence in the platform.
    """
    direction = "raised" if multiplier > 1.0 else "lowered"
    if reliability is None:
        return f"Historical calibration {direction} the {agent_id} specialist's influence."
    return (
        f"Historical calibration {direction} the {agent_id} specialist's influence to "
        f"{multiplier:.2f}x: it led {reliability.times_led} prior investigation(s) and "
        f"matched the confirmed outcome {reliability.times_correct} time(s)."
    )
