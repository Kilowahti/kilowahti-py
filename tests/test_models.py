"""Tests for kilowahti.models."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from kilowahti.models import (
    FixedPeriod,
    PriceResolution,
    PriceSlot,
    TransferGroup,
    TransferTier,
)

# ---------------------------------------------------------------------------
# PriceResolution
# ---------------------------------------------------------------------------


def test_resolution_slots_per_day_hour():
    assert PriceResolution.HOUR.slots_per_day == 24


def test_resolution_slots_per_day_min15():
    assert PriceResolution.MIN15.slots_per_day == 96


# ---------------------------------------------------------------------------
# PriceSlot round-trip
# ---------------------------------------------------------------------------


def test_price_slot_round_trip_utc():
    dt = datetime(2026, 3, 13, 12, 0, 0, tzinfo=timezone.utc)
    slot = PriceSlot(dt_utc=dt, price_no_tax=5.5, rank=3)
    restored = PriceSlot.from_dict(slot.to_dict())
    assert restored.dt_utc == dt
    assert restored.dt_utc.tzinfo == timezone.utc
    assert restored.price_no_tax == 5.5
    assert restored.rank == 3


def test_price_slot_round_trip_preserves_utc_when_offset_given():
    # datetime with +02:00 offset should be stored as UTC
    dt_with_offset = datetime.fromisoformat("2026-03-13T14:00:00+02:00")
    dt_utc = datetime(2026, 3, 13, 12, 0, 0, tzinfo=timezone.utc)
    slot = PriceSlot(dt_utc=dt_with_offset.astimezone(timezone.utc), price_no_tax=3.0, rank=1)
    restored = PriceSlot.from_dict(slot.to_dict())
    assert restored.dt_utc == dt_utc
    assert restored.dt_utc.tzinfo == timezone.utc


def test_price_slot_from_dict_naive_assumes_utc():
    data = {"dt_utc": "2026-03-13T12:00:00", "price_no_tax": 4.0, "rank": 2}
    slot = PriceSlot.from_dict(data)
    assert slot.dt_utc.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# TransferTier.matches
# ---------------------------------------------------------------------------


def _make_tier(hour_start: int, hour_end: int, price: float = 5.0) -> TransferTier:
    return TransferTier(
        label="test",
        price=price,
        months=list(range(1, 13)),
        weekdays=list(range(7)),
        hour_start=hour_start,
        hour_end=hour_end,
        priority=1,
    )


def test_transfer_tier_matches_inclusive_start():
    tier = _make_tier(hour_start=7, hour_end=22)
    assert tier.matches(month=3, weekday=0, hour=7) is True


def test_transfer_tier_matches_exclusive_end():
    tier = _make_tier(hour_start=7, hour_end=22)
    assert tier.matches(month=3, weekday=0, hour=22) is False


def test_transfer_tier_matches_inside_range():
    tier = _make_tier(hour_start=7, hour_end=22)
    assert tier.matches(month=3, weekday=0, hour=15) is True


def test_transfer_tier_matches_just_before_end():
    tier = _make_tier(hour_start=7, hour_end=22)
    assert tier.matches(month=3, weekday=0, hour=21) is True


def test_transfer_tier_no_match_wrong_month():
    tier = TransferTier(
        label="winter",
        price=5.0,
        months=[11, 12, 1, 2],
        weekdays=list(range(7)),
        hour_start=0,
        hour_end=24,
        priority=1,
    )
    assert tier.matches(month=6, weekday=0, hour=12) is False
    assert tier.matches(month=12, weekday=0, hour=12) is True


def test_transfer_tier_matches_hour_end_24():
    tier = _make_tier(hour_start=22, hour_end=24)
    assert tier.matches(month=3, weekday=0, hour=22) is True
    assert tier.matches(month=3, weekday=0, hour=23) is True


# ---------------------------------------------------------------------------
# TransferGroup.price_at
# ---------------------------------------------------------------------------


def _make_group() -> TransferGroup:
    day = TransferTier(
        label="day",
        price=3.5,
        months=list(range(1, 13)),
        weekdays=list(range(7)),
        hour_start=7,
        hour_end=22,
        priority=1,
    )
    night = TransferTier(
        label="night",
        price=1.5,
        months=list(range(1, 13)),
        weekdays=list(range(7)),
        hour_start=22,
        hour_end=24,
        priority=2,
    )
    night2 = TransferTier(
        label="night_early",
        price=1.5,
        months=list(range(1, 13)),
        weekdays=list(range(7)),
        hour_start=0,
        hour_end=7,
        priority=3,
    )
    return TransferGroup(id="g1", label="Test", active=True, tiers=[day, night, night2])


def test_transfer_group_price_at_returns_first_match_by_priority():
    group = _make_group()
    assert group.price_at(month=3, weekday=0, hour=10) == 3.5
    assert group.price_at(month=3, weekday=0, hour=23) == 1.5
    assert group.price_at(month=3, weekday=0, hour=3) == 1.5


def test_transfer_group_price_at_returns_none_when_no_match():
    # Group with a tier that covers only some months
    tier = TransferTier(
        label="winter",
        price=2.0,
        months=[12, 1],
        weekdays=list(range(7)),
        hour_start=0,
        hour_end=24,
        priority=1,
    )
    group = TransferGroup(id="g2", label="Partial", active=True, tiers=[tier])
    assert group.price_at(month=6, weekday=0, hour=12) is None


# ---------------------------------------------------------------------------
# FixedPeriod.is_active_on
# ---------------------------------------------------------------------------


@pytest.fixture
def period() -> FixedPeriod:
    return FixedPeriod(
        id="fp1",
        label="Winter rate",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        price=8.5,
    )


def test_fixed_period_active_on_start_boundary(period):
    assert period.is_active_on(date(2026, 1, 1)) is True


def test_fixed_period_active_on_end_boundary(period):
    assert period.is_active_on(date(2026, 3, 31)) is True


def test_fixed_period_active_on_inside(period):
    assert period.is_active_on(date(2026, 2, 15)) is True


def test_fixed_period_not_active_before_start(period):
    assert period.is_active_on(date(2025, 12, 31)) is False


def test_fixed_period_not_active_after_end(period):
    assert period.is_active_on(date(2026, 4, 1)) is False


def test_fixed_period_round_trip(period):
    restored = FixedPeriod.from_dict(period.to_dict())
    assert restored.id == period.id
    assert restored.start_date == period.start_date
    assert restored.end_date == period.end_date
    assert restored.price == period.price
