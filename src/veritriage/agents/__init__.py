"""The Agent Framework (M12): specialized reasoning above deterministic reasoning.

An agent is a specialized reasoning component with one responsibility: form an
evidence-backed position about one verification domain. The Coordinator invokes
the registered agents, merges their positions into ranked findings, detects
where they agree and where they conflict, and cross-checks the result against
the deterministic reasoning engine.

The law, pinned by tests: **agents form a second opinion, never a replacement
verdict.** The Evidence Graph stays immutable, the Knowledge Engine stays
authoritative, and the Reasoning Engine remains the deterministic source of
truth. This layer sits above them and never writes back.

Importing this package registers the eight built-in agents.
"""

from veritriage.agents import builtin  # noqa: F401  (registers the built-in agents)
from veritriage.agents.base import Agent
from veritriage.agents.context import AgentContext, build_agent_context
from veritriage.agents.coordinator import AgentCoordinator
from veritriage.agents.providers import (
    DeterministicProvider,
    NullProvider,
    ProviderRequest,
    ProviderResponse,
    ReasoningProvider,
    available_providers,
    get_provider,
    register_provider,
    unregister_provider,
)
from veritriage.agents.registry import (
    available_agents,
    default_agents,
    get_agent,
    register_agent,
    unregister_agent,
)

__all__ = [
    "Agent",
    "AgentContext",
    "AgentCoordinator",
    "DeterministicProvider",
    "NullProvider",
    "ProviderRequest",
    "ProviderResponse",
    "ReasoningProvider",
    "available_agents",
    "available_providers",
    "build_agent_context",
    "default_agents",
    "get_agent",
    "get_provider",
    "register_agent",
    "register_provider",
    "unregister_agent",
    "unregister_provider",
]
