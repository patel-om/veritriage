"""File I/O helpers."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


def write_json(model: BaseModel, path: Path) -> Path:
    """Serialize a Pydantic model to pretty-printed JSON at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    return path
