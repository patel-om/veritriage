"""Generative AI (M17): providers render, never reason.

LLMs exist here to communicate deterministic intelligence, never to produce it.
A provider receives a frozen :class:`Prompt` built from cited platform objects
and returns text. It cannot see a raw artifact, cannot reach platform state,
cannot create a citation, and cannot change a conclusion. Remove every provider
and the platform loses prose and nothing else.

One vendor registry serves the whole platform. The M12 ``ReasoningProvider``
seam stays frozen and becomes a consumer of this one through
:mod:`veritriage.ai.adapters`, so registering a vendor once gives both agent
narration and every renderer.

Grounding is enforced rather than requested: the prompt declares its citation
set, and any citation outside it is stripped from the response with the
omission recorded.

Importing this package registers the four built-in providers, none of which
calls an external API.
"""

from veritriage.ai import grounding, providers  # noqa: F401  (registers the built-ins)
from veritriage.ai.adapters import AGENT_NARRATION, LlmReasoningProvider
from veritriage.ai.prompt import (
    BUILT_IN_TEMPLATES,
    PromptBuilder,
    PromptContext,
    PromptTemplate,
)
from veritriage.ai.provider import BaseProvider, LLMProvider
from veritriage.ai.registry import (
    DEFAULT_PROVIDER,
    available_llm_providers,
    get_llm_provider,
    register_llm_provider,
    unregister_llm_provider,
)
from veritriage.ai.renderers import (
    available_renderers,
    render_answer,
    render_explanation,
    render_report,
)
from veritriage.ai.service import AIService, default_service

__all__ = [
    "AGENT_NARRATION",
    "AIService",
    "BUILT_IN_TEMPLATES",
    "BaseProvider",
    "DEFAULT_PROVIDER",
    "LLMProvider",
    "LlmReasoningProvider",
    "PromptBuilder",
    "PromptContext",
    "PromptTemplate",
    "available_llm_providers",
    "available_renderers",
    "default_service",
    "get_llm_provider",
    "grounding",
    "register_llm_provider",
    "render_answer",
    "render_explanation",
    "render_report",
    "unregister_llm_provider",
]
