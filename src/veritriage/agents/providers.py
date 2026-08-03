"""The boundary between Deterministic and Generative Intelligence.

Every agent's conclusion is deterministic. A :class:`ReasoningProvider` may
*narrate* a conclusion that already exists; it may never create, alter, or veto
one. Three rules make that safe, and all three are structural:

1. A provider receives a :class:`ProviderRequest` built from an already final
   :class:`AgentResult`. It runs after the conclusion exists, and it never sees
   a raw artifact.
2. The Coordinator applies only ``narrative`` and ``provider`` from a response.
   Nothing else in a response is read, so a provider that returns rewritten
   hypotheses or inflated confidences changes nothing
   (``test_provider_cannot_alter_conclusions``).
3. The default is :class:`NullProvider`. The platform is complete and fully
   useful with zero generative intelligence configured.

This module ships the protocol and two deterministic implementations, and no
API-calling provider: no vendor SDK, no model name, no network call appears
anywhere in ``agents/``. A future ``AnthropicProvider``, ``OpenAIProvider``,
``GeminiProvider``, ``LocalProvider``, or ``McpAiProvider`` is one class
implementing ``elaborate`` plus one ``register_provider`` call, with no change
to the Coordinator, to any agent, or to any contract.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, Field

from veritriage.models import AgentHypothesis, AgentObservation, AgentResult


class ProviderRequest(BaseModel):
    """The bounded payload a provider may reason over.

    Deliberately the agent's own normalized output plus its citations: the same
    posture as the platform's original AI boundary, now per agent.
    """

    agent_id: str
    domain: str
    observations: list[AgentObservation] = Field(default_factory=list)
    hypotheses: list[AgentHypothesis] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    knowledge_ids: list[str] = Field(default_factory=list)


class ProviderResponse(BaseModel):
    """What a provider is allowed to contribute: prose, and nothing else."""

    narrative: str


@runtime_checkable
class ReasoningProvider(Protocol):
    """The seam every future AI integration implements.

    One method, one bounded input, one narrative output. Implementations are
    free to call a hosted model, a local model, or nothing at all.
    """

    name: str

    def elaborate(self, request: ProviderRequest) -> ProviderResponse | None:
        """Return prose describing the agent's position, or None to decline."""
        ...


class NullProvider:
    """The default: no generative intelligence at all."""

    name = "null"

    def elaborate(self, request: ProviderRequest) -> ProviderResponse | None:
        return None


class DeterministicProvider:
    """A narrative composed from the agent's own output. No I/O, no model.

    Exists to prove the seam end to end without a network call, and to give
    deployments that forbid external AI a useful narrative anyway.
    """

    name = "deterministic"

    def elaborate(self, request: ProviderRequest) -> ProviderResponse | None:
        if not request.hypotheses:
            return None
        leading = request.hypotheses[0]
        parts = [
            f"The {request.domain} specialist leads with "
            f"{leading.category.display_name} at confidence "
            f"{leading.confidence:.2f}: {leading.statement}"
        ]
        if request.observations:
            shown = "; ".join(o.statement for o in request.observations[:3])
            parts.append(f"Supporting observations: {shown}")
        if len(request.hypotheses) > 1:
            alternatives = ", ".join(
                f"{h.category.display_name} ({h.confidence:.2f})"
                for h in request.hypotheses[1:]
            )
            parts.append(f"It also considered: {alternatives}")
        if request.limitations:
            parts.append(f"Stated limits: {'; '.join(request.limitations[:2])}")
        parts.append(
            f"Every claim above traces to {len(request.evidence_ids)} cited evidence "
            f"node(s)."
        )
        return ProviderResponse(narrative=" ".join(parts))


_P = TypeVar("_P", bound=type)

_PROVIDERS: dict[str, type] = {}


def register_provider(provider_cls: _P) -> _P:
    """Class decorator adding a reasoning provider to the registry.

    Raises:
        ValueError: If another provider already registered the same name.
    """
    existing = _PROVIDERS.get(provider_cls.name)
    if existing is not None and existing is not provider_cls:
        raise ValueError(
            f"Provider name {provider_cls.name!r} is already registered by {existing!r}"
        )
    _PROVIDERS[provider_cls.name] = provider_cls
    return provider_cls


def unregister_provider(name: str) -> None:
    """Remove a provider (used by tests to clean up throwaway providers)."""
    _PROVIDERS.pop(name, None)


def available_providers() -> dict[str, type]:
    """All registered providers, keyed by name."""
    return dict(_PROVIDERS)


def get_provider(name: str) -> ReasoningProvider:
    """Instantiate a registered provider.

    Raises:
        KeyError: If no provider with that name is registered.
    """
    try:
        return _PROVIDERS[name]()
    except KeyError:
        known = ", ".join(sorted(_PROVIDERS)) or "<none>"
        raise KeyError(f"Unknown reasoning provider {name!r}. Registered: {known}") from None


def build_request(result: AgentResult) -> ProviderRequest:
    """Project a final agent result into the bounded provider payload.

    Every model is deep-copied. A provider therefore holds no reference to
    anything the result owns, so it cannot reach back and mutate a hypothesis,
    a confidence, or a citation through the payload it was handed. Rule 2 of
    this module's contract is enforced here, not merely asserted
    (``test_provider_cannot_alter_conclusions`` pins it with a provider that
    deliberately tries).
    """
    return ProviderRequest(
        agent_id=result.agent_id,
        domain=result.domain.value,
        observations=[o.model_copy(deep=True) for o in result.observations],
        hypotheses=[h.model_copy(deep=True) for h in result.hypotheses],
        limitations=list(result.limitations),
        evidence_ids=list(result.evidence_ids),
        knowledge_ids=list(result.knowledge_ids),
    )


register_provider(NullProvider)
register_provider(DeterministicProvider)
