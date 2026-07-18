"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def fixture_log():
    """Return a resolver for a named fixture log."""

    def _get(name: str) -> Path:
        path = FIXTURES / name
        assert path.is_file(), f"missing fixture {name}"
        return path

    return _get
