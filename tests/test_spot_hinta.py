"""Tests for kilowahti.sources.spot_hinta."""

from __future__ import annotations

import re
from datetime import timezone

import aiohttp
import pytest

from kilowahti.const import API_BASE_URL, API_ENDPOINT_TODAY, API_ENDPOINT_TOMORROW
from kilowahti.models import PriceResolution
from kilowahti.sources.spot_hinta import SpotHintaRateLimitError, SpotHintaSource

_TODAY_RE = re.compile(re.escape(f"{API_BASE_URL}{API_ENDPOINT_TODAY}"))
_TOMORROW_RE = re.compile(re.escape(f"{API_BASE_URL}{API_ENDPOINT_TOMORROW}"))


# ---------------------------------------------------------------------------
# fetch_today — success
# ---------------------------------------------------------------------------


async def test_fetch_today_returns_24_sorted_slots(mocked_aiohttp, spot_hinta_today_fi):
    mocked_aiohttp.get(_TODAY_RE, payload=spot_hinta_today_fi)
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        slots = await source.fetch_today(session, "FI", PriceResolution.HOUR)

    assert len(slots) == 24
    # Verify sorted ascending by dt_utc
    for i in range(len(slots) - 1):
        assert slots[i].dt_utc < slots[i + 1].dt_utc


async def test_fetch_today_timestamps_are_utc(mocked_aiohttp, spot_hinta_today_fi):
    mocked_aiohttp.get(_TODAY_RE, payload=spot_hinta_today_fi)
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        slots = await source.fetch_today(session, "FI", PriceResolution.HOUR)

    for slot in slots:
        assert slot.dt_utc.tzinfo == timezone.utc


async def test_fetch_today_price_converted_eur_to_snt(mocked_aiohttp, spot_hinta_today_fi):
    # Fixture has a slot at 2026-03-13T00:00:00+02:00 with PriceNoTax=0.03
    # That's 2026-03-12T22:00:00Z UTC. Converted: 0.03 * 100 = 3.0 c/kWh
    mocked_aiohttp.get(_TODAY_RE, payload=spot_hinta_today_fi)
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        slots = await source.fetch_today(session, "FI", PriceResolution.HOUR)

    first_slot = slots[0]  # earliest UTC slot
    assert abs(first_slot.price_no_tax - 3.0) < 1e-9


async def test_fetch_today_specific_price_conversion(mocked_aiohttp):
    # Single-item response with PriceNoTax=0.05 → 5.0 c/kWh
    payload = [{"DateTime": "2026-03-13T12:00:00+02:00", "PriceNoTax": 0.05, "Rank": 1}]
    mocked_aiohttp.get(_TODAY_RE, payload=payload)
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        slots = await source.fetch_today(session, "FI", PriceResolution.HOUR)

    assert len(slots) == 1
    assert abs(slots[0].price_no_tax - 5.0) < 1e-9


# ---------------------------------------------------------------------------
# fetch_today — query params
# ---------------------------------------------------------------------------


async def test_fetch_today_sends_correct_query_params(mocked_aiohttp, spot_hinta_today_fi):
    mocked_aiohttp.get(_TODAY_RE, payload=spot_hinta_today_fi)
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        await source.fetch_today(session, "FI", PriceResolution.HOUR)

    assert len(mocked_aiohttp.requests) == 1
    (method, called_url) = list(mocked_aiohttp.requests.keys())[0]
    assert method == "GET"
    assert called_url.host == "api.spot-hinta.fi"
    assert called_url.path == API_ENDPOINT_TODAY
    assert called_url.query.get("region") == "FI"
    assert called_url.query.get("priceResolution") == "60"


async def test_fetch_today_sends_min15_resolution(mocked_aiohttp):
    payload = [{"DateTime": "2026-03-13T12:00:00+02:00", "PriceNoTax": 0.05, "Rank": 1}]
    mocked_aiohttp.get(_TODAY_RE, payload=payload)
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        await source.fetch_today(session, "SE1", PriceResolution.MIN15)

    (_, called_url) = list(mocked_aiohttp.requests.keys())[0]
    assert called_url.query.get("region") == "SE1"
    assert called_url.query.get("priceResolution") == "15"


# ---------------------------------------------------------------------------
# fetch_tomorrow — 404
# ---------------------------------------------------------------------------


async def test_fetch_tomorrow_404_returns_none(mocked_aiohttp):
    mocked_aiohttp.get(_TOMORROW_RE, status=404)
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        result = await source.fetch_tomorrow(session, "FI", PriceResolution.HOUR)

    assert result is None


async def test_fetch_tomorrow_success_returns_slots(mocked_aiohttp, spot_hinta_today_fi):
    mocked_aiohttp.get(_TOMORROW_RE, payload=spot_hinta_today_fi)
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        slots = await source.fetch_tomorrow(session, "FI", PriceResolution.HOUR)

    assert slots is not None
    assert len(slots) == 24


# ---------------------------------------------------------------------------
# fetch_today — 429
# ---------------------------------------------------------------------------


async def test_fetch_today_429_raises_rate_limit_error(mocked_aiohttp):
    mocked_aiohttp.get(_TODAY_RE, status=429, headers={"Retry-After": "30"})
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        with pytest.raises(SpotHintaRateLimitError) as exc_info:
            await source.fetch_today(session, "FI", PriceResolution.HOUR)

    assert exc_info.value.retry_after == 30
    assert exc_info.value.status == 429


async def test_fetch_today_429_default_retry_after(mocked_aiohttp):
    # No Retry-After header → defaults to 60
    mocked_aiohttp.get(_TODAY_RE, status=429)
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        with pytest.raises(SpotHintaRateLimitError) as exc_info:
            await source.fetch_today(session, "FI", PriceResolution.HOUR)

    assert exc_info.value.retry_after == 60


# ---------------------------------------------------------------------------
# fetch_today — 500
# ---------------------------------------------------------------------------


async def test_fetch_today_500_raises_client_response_error(mocked_aiohttp):
    mocked_aiohttp.get(_TODAY_RE, status=500)
    source = SpotHintaSource()
    async with aiohttp.ClientSession() as session:
        with pytest.raises(aiohttp.ClientResponseError) as exc_info:
            await source.fetch_today(session, "FI", PriceResolution.HOUR)

    assert exc_info.value.status == 500
    assert not isinstance(exc_info.value, SpotHintaRateLimitError)
