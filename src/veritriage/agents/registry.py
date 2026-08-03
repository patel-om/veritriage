"""The agent plugin table.

Registry-shaped extension, identical in spirit to the parser, pack, adapter,
provider, step, profile, tool, and annotation-target registries already in the
platform: a new specialist is one decorated class, referenced by nothing and
changing nothing. ``test_new_agent_needs_only_registration`` proves it.
"""

from __future__ import annotations

from typing import TypeVar

from veritriage.agents.base import Agent

_A = TypeVar("_A", bound=type[Agent])

_REGISTRY: dict[str, type[Agent]] = {}


def register_agent(agent_cls: _A) -> _A:
    """Class decorator adding an agent to the registry.

    Raises:
        ValueError: If another agent already registered the same ID.
    """
    existing = _REGISTRY.get(agent_cls.agent_id)
    if existing is not None and existing is not agent_cls:
        raise ValueError(
            f"Agent ID {agent_cls.agent_id!r} is already registered by {existing!r}"
        )
    _REGISTRY[agent_cls.agent_id] = agent_cls
    return agent_cls


def unregister_agent(agent_id: str) -> None:
    """Remove an agent (used by tests to clean up throwaway agents)."""
    _REGISTRY.pop(agent_id, None)


def available_agents() -> dict[str, type[Agent]]:
    """All registered agents, keyed by ID."""
    return dict(_REGISTRY)


def get_agent(agent_id: str) -> Agent:
    """Instantiate a registered agent.

    Raises:
        KeyError: If no agent with that ID is registered.
    """
    try:
        return _REGISTRY[agent_id]()
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown agent {agent_id!r}. Registered: {known}") from None


def default_agents() -> list[Agent]:
    """One instance of every registered agent, in deterministic ID order."""
    return [_REGISTRY[agent_id]() for agent_id in sorted(_REGISTRY)]
