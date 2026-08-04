"""The event bus: ordered, synchronous, replayable, and observable.

Deterministic by construction, and every one of those properties is a
deliberate refusal:

* **Synchronous.** ``publish`` runs subscribers inline and returns. No threads,
  no async, no queues, no hidden callbacks. A platform whose reactions happen
  on another thread cannot be reasoned about or tested.
* **Ordered.** Every event carries a monotonic sequence assigned here, and
  subscribers run in registration order.
* **Replayable.** ``replay`` re-runs the recorded log through the current
  subscribers. Because rule evaluation is a pure function of an event and its
  payload, a replay reaches identical decisions.
* **Bounded.** The log has a cap so a long-lived workspace cannot grow without
  limit, and what was dropped is reported rather than hidden.

A subscriber that raises is isolated and recorded. One broken listener must
never cost a publish, for the same reason one broken agent must never cost an
investigation.
"""

from __future__ import annotations

from typing import Any, Callable

from veritriage.models import Event, EventKind, make_event_id

#: How many events one bus retains. Beyond this the oldest are dropped, and
#: the count of what was dropped is reported in the status.
DEFAULT_CAPACITY = 500

Subscriber = Callable[[Event], None]


class EventBus:
    """Publish, subscribe, filter, and replay. Nothing hidden."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._capacity = max(1, capacity)
        self._log: list[Event] = []
        self._subscribers: list[tuple[EventKind | None, str, Subscriber]] = []
        self._sequence = 0
        self._dropped = 0
        self._failures: list[str] = []

    # --- Publishing ---------------------------------------------------------

    def publish(
        self,
        kind: EventKind,
        payload: dict[str, Any] | None = None,
        subject: str | None = None,
        source: str = "workspace",
    ) -> Event:
        """Record an event and deliver it to every matching subscriber."""
        payload = dict(payload or {})
        event = Event(
            event_id=make_event_id(kind, payload, self._sequence),
            kind=kind,
            sequence=self._sequence,
            source=source,
            subject=subject,
            payload=payload,
        )
        self._sequence += 1
        self._record(event)
        self._deliver(event)
        return event

    def _record(self, event: Event) -> None:
        self._log.append(event)
        while len(self._log) > self._capacity:
            self._log.pop(0)
            self._dropped += 1

    def _deliver(self, event: Event) -> None:
        for wanted, name, subscriber in self._subscribers:
            if wanted is not None and wanted is not event.kind:
                continue
            try:
                subscriber(event)
            except Exception as exc:  # one broken listener must not cost a publish
                self._failures.append(
                    f"subscriber {name!r} failed on {event.event_id}: "
                    f"{type(exc).__name__}: {exc}"
                )

    # --- Subscribing --------------------------------------------------------

    def subscribe(
        self, subscriber: Subscriber, kind: EventKind | None = None, name: str = ""
    ) -> None:
        """Register a listener, optionally for one event kind only.

        Subscribers run in registration order, which is what makes delivery
        deterministic rather than merely eventual.
        """
        self._subscribers.append((kind, name or getattr(subscriber, "__name__", "anonymous"), subscriber))

    def unsubscribe(self, name: str) -> None:
        self._subscribers = [s for s in self._subscribers if s[1] != name]

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    # --- Reading ------------------------------------------------------------

    def events(
        self,
        kind: EventKind | None = None,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """The recorded log, filtered, in sequence order."""
        found = [
            e
            for e in self._log
            if (kind is None or e.kind is kind) and (since is None or e.sequence >= since)
        ]
        return found[-limit:] if limit else found

    def last(self, kind: EventKind | None = None) -> Event | None:
        found = self.events(kind)
        return found[-1] if found else None

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def failures(self) -> list[str]:
        """Subscriber failures, recorded rather than raised."""
        return list(self._failures)

    def replay(self, kind: EventKind | None = None, since: int | None = None) -> int:
        """Re-deliver recorded events to the current subscribers.

        Returns how many were replayed. Nothing is re-recorded and no sequence
        is reassigned: replay observes history, it does not rewrite it.
        """
        replayed = self.events(kind, since)
        for event in replayed:
            self._deliver(event)
        return len(replayed)

    def clear(self) -> None:
        """Forget the recorded log. Subscribers and sequence are untouched."""
        self._log.clear()
        self._failures.clear()
