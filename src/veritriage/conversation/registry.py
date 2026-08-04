"""The question-handler plugin table.

One handler per :class:`Intent`. A handler reads a
:class:`ConversationContext` and the current :class:`NavigationContext`,
assembles an :class:`Answer` from artifacts that already exist, and optionally
returns an updated navigation context.

A handler owns no intelligence. It cannot compute a confidence, rank a
hypothesis, or decide anything: everything it says was decided upstream, and
everything it cites is minted through the context's reference builders.

``@register_handler`` is the plugin seam, identical in spirit to every other
registry in the platform.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, TypeVar

from veritriage.models import Answer, Intent, NavigationContext, Question

if TYPE_CHECKING:  # pragma: no cover - typing only
    from veritriage.conversation.context import ConversationContext

_H = TypeVar("_H", bound=type["QuestionHandler"])

_REGISTRY: dict[Intent, type["QuestionHandler"]] = {}


class QuestionHandler(ABC):
    """Answers one intent, from artifacts that already exist."""

    #: The intent this handler answers.
    intent: ClassVar[Intent]

    @abstractmethod
    def answer(
        self,
        question: Question,
        context: "ConversationContext",
        navigation: NavigationContext,
    ) -> tuple[Answer, NavigationContext]:
        """Assemble the answer and the navigation state it leaves behind."""
        raise NotImplementedError


def register_handler(handler_cls: _H) -> _H:
    """Class decorator adding a handler to the registry.

    Raises:
        ValueError: If another handler already answers the same intent.
    """
    existing = _REGISTRY.get(handler_cls.intent)
    if existing is not None and existing is not handler_cls:
        raise ValueError(
            f"Intent {handler_cls.intent.value!r} is already handled by {existing!r}"
        )
    _REGISTRY[handler_cls.intent] = handler_cls
    return handler_cls


def unregister_handler(intent: Intent) -> None:
    """Remove a handler (used by tests to clean up throwaway handlers)."""
    _REGISTRY.pop(intent, None)


def available_handlers() -> dict[Intent, type[QuestionHandler]]:
    """All registered handlers, keyed by intent."""
    return dict(_REGISTRY)


def get_handler(intent: Intent) -> QuestionHandler | None:
    """Instantiate the handler for an intent, or None when unhandled."""
    handler_cls = _REGISTRY.get(intent)
    return handler_cls() if handler_cls is not None else None
