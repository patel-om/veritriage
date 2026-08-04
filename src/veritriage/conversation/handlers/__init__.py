"""The built-in question handlers.

Importing this package registers a handler for every intent. Each reaches the
engine through ``@register_handler`` alone, so an eleventh intent is one class
and nothing more, which ``test_new_intent_needs_only_registration`` proves.
"""

from veritriage.conversation.handlers.evidence import FilterHandler, ShowEvidenceHandler
from veritriage.conversation.handlers.explain import (
    ExplainHandler,
    WhyHandler,
    WhyNotHandler,
)
from veritriage.conversation.handlers.navigate import (
    HelpHandler,
    NavigateHandler,
    SummarizeHandler,
)
from veritriage.conversation.handlers.trace import CompareHandler, TraceHandler

__all__ = [
    "CompareHandler",
    "ExplainHandler",
    "FilterHandler",
    "HelpHandler",
    "NavigateHandler",
    "ShowEvidenceHandler",
    "SummarizeHandler",
    "TraceHandler",
    "WhyHandler",
    "WhyNotHandler",
]
