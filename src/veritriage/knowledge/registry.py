"""Knowledge Pack plugin registry.

A pack registers by decorating a zero-argument factory with
``@register_pack``. Nothing else changes anywhere: the Knowledge Graph,
the matcher, the reasoning integration, and the report all discover packs
through this table, so adding a domain (TileLink, CHI, PCIe, RISC-V
privilege, a company-internal protocol) is one new module.
"""

from __future__ import annotations

from typing import Callable

from veritriage.knowledge.model import KnowledgePack

PackFactory = Callable[[], KnowledgePack]

_PACKS: dict[str, PackFactory] = {}


def register_pack(factory: PackFactory) -> PackFactory:
    """Decorator: register a Knowledge Pack factory under its pack id."""
    pack = factory()
    if pack.id in _PACKS:
        raise ValueError(f"Knowledge pack id already registered: {pack.id}")
    _PACKS[pack.id] = factory
    return factory


def unregister_pack(pack_id: str) -> None:
    """Remove a pack (used by tests to clean up)."""
    _PACKS.pop(pack_id, None)


def available_packs() -> dict[str, PackFactory]:
    """Registered pack factories keyed by pack id."""
    _ensure_builtin_packs()
    return dict(_PACKS)


def load_packs(ids: list[str] | None = None) -> list[KnowledgePack]:
    """Instantiate packs (all registered ones by default), in sorted-id order."""
    _ensure_builtin_packs()
    wanted = sorted(_PACKS) if ids is None else ids
    return [_PACKS[i]() for i in wanted]


def _ensure_builtin_packs() -> None:
    """Import the built-in pack modules so their decorators run."""
    from veritriage.knowledge import packs  # noqa: F401  (import for side effect)
