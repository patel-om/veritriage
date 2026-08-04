"""The Conversation Engine (M16): the intelligence becomes navigable.

Not a chatbot, not an LLM wrapper, and not a second reasoning path. A
structured, stateful, composable interaction layer over artifacts that already
exist.

The law, pinned by tests: **conversation navigates; it never concludes.**
Every answer is assembled from artifacts that already exist, every statement
carries references that resolve to a real artifact, and asking any number of
questions leaves the report byte-identical. This package owns no intelligence.

Questions are structured objects. A deterministic parser maps a declared,
finite vocabulary of phrasings onto intents and says so honestly when a phrase
falls outside it. A language model may later translate prose into `Question`
objects and render `Answer` objects back into prose, but it never owns either.

Importing this package registers a handler for every intent.
"""

from veritriage.conversation import handlers  # noqa: F401  (registers the built-ins)
from veritriage.conversation.context import ConversationContext
from veritriage.conversation.engine import ConversationEngine, start_conversation
from veritriage.conversation.parse import parse, vocabulary
from veritriage.conversation.registry import (
    QuestionHandler,
    available_handlers,
    get_handler,
    register_handler,
    unregister_handler,
)

__all__ = [
    "ConversationContext",
    "ConversationEngine",
    "QuestionHandler",
    "available_handlers",
    "get_handler",
    "parse",
    "register_handler",
    "start_conversation",
    "unregister_handler",
    "vocabulary",
]
