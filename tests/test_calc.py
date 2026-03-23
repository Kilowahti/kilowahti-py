"""Tests for kilowahti.calc."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kilowahti.calc import (
    cheapest_window,
    compute_score,
    control_factor,
    control_factor_bipolar,
    normalize_transfer_rank,
    price_quartile,
    rank_to_bucket,
    spot_effective,
    total_price_rank,
    transfer_rank_info,
)
from kilowahti.models import PriceSlot, TransferGroup, TransferTier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slot(hour: int, price: float, rank: int = 1) -> PriceSlot:
    dt = datetime(2026, 3, 13, hour, 0, 0, tzinfo=timezone.utc)
    return PriceSlot(dt_utc=dt, price_no_tax=price, rank=rank)


def _as_local(dt: datetime) -> datetime:
    """Identity: treat UTC as local (for deterministic tests)."""
    return dt


def _make_day_night_group() -> TransferGroup:
    """Two-tier group: day price 2.5 (hours 7–22), night price 1.5 (0–7 and 22–24)."""
    day = TransferTier(
        label="day",
        price=2.5,
        months=list(range(1, 13)),
        weekdays=list(range(7)),
        hour_start=7,
        hour_end=22,
        priority=1,
    )
    night_late = TransferTier(
        label="night_late",
        price=1.5,
        months=list(range(1, 13)),
        weekdays=list(range(7)),
        hour_start=22,
        hour_end=24,
        priority=2,
    )
    night_early = TransferTier(
        label="night_early",
        price=1.5,
        months=list(range(1, 13)),
        weekdays=list(range(7)),
        hour_start=0,
        hour_end=7,
        priority=3,
    )
    return TransferGroup(
        id="g1", label="Day/Night", active=True, tiers=[day, night_late, night_early]
    )


def _make_single_tier_group() -> TransferGroup:
    """Single flat-rate tier covering all hours."""
    flat = TransferTier(
        label="flat",
        price=3.0,
        months=list(range(1, 13)),
        weekdays=list(range(7)),
        hour_start=0,
        hour_end=24,
        priority=1,
    )
    return TransferGroup(id="g2", label="Flat", active=True, tiers=[flat])


# ---------------------------------------------------------------------------
# spot_effective
# ---------------------------------------------------------------------------


def test_spot_effective_numerical():
    slot = _slot(hour=12, price=10.0)
    result = spot_effective(slot, vat_rate=0.255, commission=0.35)
    assert abs(result - 12.9) < 1e-9


def test_spot_effective_zero_commission():
    slot = _slot(hour=12, price=10.0)
    result = spot_effective(slot, vat_rate=0.255, commission=0.0)
    assert abs(result - 12.55) < 1e-9


def test_spot_effective_zero_vat():
    slot = _slot(hour=12, price=10.0)
    result = spot_effective(slot, vat_rate=0.0, commission=0.5)
    assert abs(result - 10.5) < 1e-9


# ---------------------------------------------------------------------------
# control_factor
# ---------------------------------------------------------------------------


def test_control_factor_rank1_is_one():
    assert control_factor(
        rank=1, slots_per_day=24, function="linear", scaling=1.0
    ) == pytest.approx(1.0)


def test_control_factor_rank_max_is_zero():
    assert control_factor(
        rank=24, slots_per_day=24, function="linear", scaling=1.0
    ) == pytest.approx(0.0)


def test_control_factor_single_slot():
    assert control_factor(rank=1, slots_per_day=1, function="linear", scaling=1.0) == 0.5


def test_control_factor_linear_midpoint():
    # rank=13, slots_per_day=24: t = 12/23 ≈ 0.5217, cf = 1 - 0.5217 ≈ 0.4783
    cf = control_factor(rank=13, slots_per_day=24, function="linear", scaling=1.0)
    expected = 1.0 - 12 / 23
    assert cf == pytest.approx(expected)


def test_control_factor_sinusoidal_rank1():
    cf = control_factor(rank=1, slots_per_day=24, function="sinusoidal", scaling=1.0)
    assert cf == pytest.approx(1.0)


def test_control_factor_sinusoidal_rank_max():
    cf = control_factor(rank=24, slots_per_day=24, function="sinusoidal", scaling=1.0)
    assert cf == pytest.approx(0.0, abs=1e-9)


def test_control_factor_sinusoidal_midpoint():
    # t = 0.5 → cos(π*0.5) = cos(π/2) = 0 → cf = 0.5
    cf = control_factor(rank=13, slots_per_day=25, function="sinusoidal", scaling=1.0)
    # rank=13, slots_per_day=25: t = 12/24 = 0.5
    assert cf == pytest.approx(0.5)


def test_control_factor_scaling_reduces_mid_values():
    cf1 = control_factor(rank=12, slots_per_day=24, function="linear", scaling=1.0)
    cf2 = control_factor(rank=12, slots_per_day=24, function="linear", scaling=2.0)
    assert cf2 < cf1  # Higher scaling compresses toward 0 for mid-high ranks


def test_control_factor_clamped_at_zero_and_one():
    assert 0.0 <= control_factor(rank=1, slots_per_day=24, function="linear", scaling=5.0) <= 1.0
    assert 0.0 <= control_factor(rank=24, slots_per_day=24, function="linear", scaling=5.0) <= 1.0


# ---------------------------------------------------------------------------
# control_factor_bipolar
# ---------------------------------------------------------------------------


def test_control_factor_bipolar_from_one():
    assert control_factor_bipolar(1.0) == pytest.approx(1.0)


def test_control_factor_bipolar_from_zero():
    assert control_factor_bipolar(0.0) == pytest.approx(-1.0)


def test_control_factor_bipolar_from_half():
    assert control_factor_bipolar(0.5) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# rank_to_bucket
# ---------------------------------------------------------------------------


def test_rank_to_bucket_24_slots():
    # Q = 6
    assert rank_to_bucket(1, 24) == "q1"
    assert rank_to_bucket(6, 24) == "q1"
    assert rank_to_bucket(7, 24) == "q2"
    assert rank_to_bucket(12, 24) == "q2"
    assert rank_to_bucket(13, 24) == "q3"
    assert rank_to_bucket(18, 24) == "q3"
    assert rank_to_bucket(19, 24) == "q4"
    assert rank_to_bucket(24, 24) == "q4"


def test_rank_to_bucket_96_slots():
    # Q = 24
    assert rank_to_bucket(1, 96) == "q1"
    assert rank_to_bucket(24, 96) == "q1"
    assert rank_to_bucket(25, 96) == "q2"
    assert rank_to_bucket(48, 96) == "q2"
    assert rank_to_bucket(49, 96) == "q3"
    assert rank_to_bucket(72, 96) == "q3"
    assert rank_to_bucket(73, 96) == "q4"
    assert rank_to_bucket(96, 96) == "q4"


# ---------------------------------------------------------------------------
# price_quartile
# ---------------------------------------------------------------------------


def test_price_quartile_returns_int():
    assert price_quartile(1, 24) == 1
    assert price_quartile(6, 24) == 1
    assert price_quartile(7, 24) == 2
    assert price_quartile(19, 24) == 4


# ---------------------------------------------------------------------------
# normalize_transfer_rank
# ---------------------------------------------------------------------------


def test_normalize_transfer_rank_single_tier():
    assert normalize_transfer_rank(1, 1) == pytest.approx(0.0)


def test_normalize_transfer_rank_cheapest():
    assert normalize_transfer_rank(1, 5) == pytest.approx(0.0)


def test_normalize_transfer_rank_most_expensive():
    assert normalize_transfer_rank(5, 5) == pytest.approx(1.0)


def test_normalize_transfer_rank_midpoint():
    assert normalize_transfer_rank(3, 5) == pytest.approx(0.5)


def test_normalize_transfer_rank_two_tiers():
    assert normalize_transfer_rank(1, 2) == pytest.approx(0.0)
    assert normalize_transfer_rank(2, 2) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# transfer_rank_info
# ---------------------------------------------------------------------------


def test_transfer_rank_info_no_group():
    assert transfer_rank_info(None, datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc)) is None


def test_transfer_rank_info_single_tier():
    group = _make_single_tier_group()
    now = datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc)
    result = transfer_rank_info(group, now)
    assert result == (1, 1)


def test_transfer_rank_info_two_tiers_day():
    group = _make_day_night_group()
    # Hour 10 = day tier (price 2.5) — ranks 2nd among {1.5, 2.5}
    now = datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc)
    result = transfer_rank_info(group, now)
    assert result == (2, 2)


def test_transfer_rank_info_two_tiers_night():
    group = _make_day_night_group()
    # Hour 3 = night tier (price 1.5) — ranks 1st among {1.5, 2.5}
    now = datetime(2026, 3, 13, 3, 0, tzinfo=timezone.utc)
    result = transfer_rank_info(group, now)
    assert result == (1, 2)


# ---------------------------------------------------------------------------
# compute_score
# ---------------------------------------------------------------------------


def test_compute_score_empty():
    assert compute_score({}) == pytest.approx(0.0)


def test_compute_score_all_q1():
    # raw = 100, default: (100-30)/53.3*100 = 131.3 → clamped to 100
    assert compute_score({"q1": 1.0}) == pytest.approx(100.0)


def test_compute_score_all_q4():
    # raw = 0, default: (0-30)/53.3*100 = -56.3 → clamped to 0
    assert compute_score({"q4": 1.0}) == pytest.approx(0.0)


def test_compute_score_raw_formula_differs_from_default():
    # Mixed usage where raw and default yield different results
    bucket_data = {"q1": 0.2, "q2": 0.2, "q3": 0.3, "q4": 0.3}
    raw_score = compute_score(bucket_data, formula="raw")
    default_score = compute_score(bucket_data, formula="default")
    # raw ≈ 43.33, default ≈ 25.0
    assert raw_score != pytest.approx(default_score)
    assert raw_score > default_score


def test_compute_score_raw_no_clamp():
    # All q1: raw=100, which raw formula does not amplify past 100
    assert compute_score({"q1": 1.0}, formula="raw") == pytest.approx(100.0)


def test_compute_score_all_q2():
    # raw = (0 + 2*1.0 + 0) / (1.0*3) * 100 = 2/3*100 ≈ 66.67
    # default: (66.67-30)/53.3*100 ≈ 68.7
    raw_score = compute_score({"q2": 1.0}, formula="raw")
    assert raw_score == pytest.approx(200 / 3, rel=1e-4)


# ---------------------------------------------------------------------------
# cheapest_window
# ---------------------------------------------------------------------------


def _make_slots_with_prices(prices: list[float]) -> list[PriceSlot]:
    return [
        PriceSlot(
            dt_utc=datetime(2026, 3, 13, i, 0, 0, tzinfo=timezone.utc),
            price_no_tax=p,
            rank=i + 1,
        )
        for i, p in enumerate(prices)
    ]


def test_cheapest_window_basic():
    # prices: [5.0, 3.0, 2.0, 4.0, 6.0], window=2
    # windows: [5+3=8, 3+2=5, 2+4=6, 4+6=10] → best at index 1 with avg 2.5
    slots = _make_slots_with_prices([5.0, 3.0, 2.0, 4.0, 6.0])
    result = cheapest_window(slots, slots_needed=2, price_fn=lambda s: s.price_no_tax)
    assert result is not None
    window, avg = result
    assert len(window) == 2
    assert window[0].price_no_tax == 3.0
    assert window[1].price_no_tax == 2.0
    assert avg == pytest.approx(2.5)


def test_cheapest_window_single_slot():
    slots = _make_slots_with_prices([7.0, 3.0, 5.0])
    result = cheapest_window(slots, slots_needed=1, price_fn=lambda s: s.price_no_tax)
    assert result is not None
    window, avg = result
    assert len(window) == 1
    assert window[0].price_no_tax == 3.0
    assert avg == pytest.approx(3.0)


def test_cheapest_window_full_range():
    slots = _make_slots_with_prices([4.0, 2.0, 6.0])
    result = cheapest_window(slots, slots_needed=3, price_fn=lambda s: s.price_no_tax)
    assert result is not None
    window, avg = result
    assert len(window) == 3
    assert avg == pytest.approx(4.0)


def test_cheapest_window_too_many_slots_needed():
    slots = _make_slots_with_prices([1.0, 2.0, 3.0])
    assert cheapest_window(slots, slots_needed=4, price_fn=lambda s: s.price_no_tax) is None


def test_cheapest_window_empty_slots():
    assert cheapest_window([], slots_needed=1, price_fn=lambda s: s.price_no_tax) is None


def test_cheapest_window_respects_price_fn():
    # price_fn can apply any transformation; effective = p*1.255+0.35
    # Relative ordering same; window selection unchanged
    slots = _make_slots_with_prices([5.0, 3.0, 2.0, 4.0])
    result = cheapest_window(
        slots, slots_needed=2, price_fn=lambda s: spot_effective(s, 0.255, 0.35)
    )
    assert result is not None
    window, _ = result
    assert window[0].price_no_tax == 3.0
    assert window[1].price_no_tax == 2.0


# ---------------------------------------------------------------------------
# total_price_rank
# ---------------------------------------------------------------------------


def test_total_price_rank_cheapest_is_one():
    slots = _make_slots_with_prices([5.0, 3.0, 7.0])
    current = slots[1]  # price 3.0 — cheapest
    result = total_price_rank(
        current, slots, vat_rate=0.0, commission=0.0, group=None, as_local_fn=_as_local
    )
    assert result == 1


def test_total_price_rank_competition_ranking():
    # Two slots with price 3.0 (tied), one with 7.0
    slots = _make_slots_with_prices([3.0, 3.0, 7.0])
    # Both tied slots should get rank 1
    assert (
        total_price_rank(
            slots[0], slots, vat_rate=0.0, commission=0.0, group=None, as_local_fn=_as_local
        )
        == 1
    )
    assert (
        total_price_rank(
            slots[1], slots, vat_rate=0.0, commission=0.0, group=None, as_local_fn=_as_local
        )
        == 1
    )
    # Expensive slot: 2 cheaper slots → rank 3
    assert (
        total_price_rank(
            slots[2], slots, vat_rate=0.0, commission=0.0, group=None, as_local_fn=_as_local
        )
        == 3
    )


def test_total_price_rank_not_in_today_returns_none():
    slots = _make_slots_with_prices([5.0, 3.0])
    # Create a slot with a different timestamp
    outsider = PriceSlot(
        dt_utc=datetime(2026, 3, 14, 0, 0, 0, tzinfo=timezone.utc),
        price_no_tax=1.0,
        rank=1,
    )
    result = total_price_rank(
        outsider, slots, vat_rate=0.0, commission=0.0, group=None, as_local_fn=_as_local
    )
    assert result is None


def test_total_price_rank_empty_today_returns_none():
    slot = _slot(hour=10, price=5.0)
    result = total_price_rank(
        slot, [], vat_rate=0.0, commission=0.0, group=None, as_local_fn=_as_local
    )
    assert result is None


def test_total_price_rank_most_expensive():
    slots = _make_slots_with_prices([5.0, 3.0, 7.0])
    current = slots[2]  # price 7.0 — most expensive
    result = total_price_rank(
        current, slots, vat_rate=0.0, commission=0.0, group=None, as_local_fn=_as_local
    )
    assert result == 3
