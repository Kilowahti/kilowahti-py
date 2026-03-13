"""Shared fixtures for kilowahti tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aioresponses import aioresponses

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def mocked_aiohttp():
    """Yield an aioresponses mock context."""
    with aioresponses() as m:
        yield m


@pytest.fixture
def spot_hinta_today_fi() -> list[dict]:
    """Load the FI today fixture."""
    return json.loads((FIXTURES_DIR / "spot_hinta_today_fi.json").read_text())
