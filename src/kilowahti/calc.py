"""Pure price calculation functions for the kilowahti library."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime, timezone

from kilowahti.const import CONTROL_FACTOR_SINUSOIDAL, SCORE_FORMULA_RAW
from kilowahti.models import FixedPeriod, PriceSlot, TransferGroup


def spot_effective(slot: PriceSlot, vat_rate: float, commission: float) -> float:
    """Apply VAT to raw spot price, then add commission (gross).

    API always returns prices excl. VAT; commission is gross (VAT included).
    """
    return slot.price_no_tax * (1 + vat_rate) + commission


def effective_prices(slots: list[PriceSlot], vat_rate: float, commission: float) -> list[float]:
    """Return effective prices for a list of slots."""
    return [spot_effective(s, vat_rate, commission) for s in slots]


def slots_in_range(all_slots: list[PriceSlot], start: datetime, end: datetime) -> list[PriceSlot]:
    """Return slots whose start time falls within [start, end)."""
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    return [s for s in all_slots if start_utc <= s.dt_utc < end_utc]


def transfer_price_for_slot(
    slot: PriceSlot,
    group: TransferGroup | None,
    as_local_fn: Callable[[datetime], datetime],
) -> float | None:
    """Return transfer price for a slot, or None if no group configured."""
    if group is None:
        return None
    slot_local = as_local_fn(slot.dt_utc)
    return group.price_at(slot_local.month, slot_local.weekday(), slot_local.hour)


def transfer_rank_info(
    group: TransferGroup | None,
    now_local: datetime,
) -> tuple[int, int] | None:
    """Return (rank, tier_count) for the current transfer price among today's unique tiers.

    rank 1 = cheapest. Returns None if no group or no matching tier.
    """
    if group is None:
        return None
    current = group.price_at(now_local.month, now_local.weekday(), now_local.hour)
    if current is None:
        return None
    prices: set[float] = set()
    for hour in range(24):
        p = group.price_at(now_local.month, now_local.weekday(), hour)
        if p is not None:
            prices.add(p)
    if not prices:
        return None
    sorted_prices = sorted(prices)
    return sorted_prices.index(current) + 1, len(sorted_prices)


def total_price(effective: float, transfer: float | None) -> float:
    """Combine effective energy price and transfer price."""
    return effective + (transfer or 0.0)


def total_price_rank(
    current: PriceSlot,
    today_slots: list[PriceSlot],
    vat_rate: float,
    commission: float,
    group: TransferGroup | None,
    as_local_fn: Callable[[datetime], datetime],
) -> int | None:
    """Rank of the current slot's total price among today's slots.

    1 = cheapest. Competition ranking: tied slots share the lowest rank.
    Returns None if today_slots is empty or current is not among them.
    """
    if not today_slots:
        return None

    def _total(s: PriceSlot) -> float:
        return round(
            spot_effective(s, vat_rate, commission)
            + (transfer_price_for_slot(s, group, as_local_fn) or 0.0),
            5,
        )

    totals = {s.dt_utc: _total(s) for s in today_slots}
    current_total = totals.get(current.dt_utc)
    if current_total is None:
        return None
    return sum(1 for p in totals.values() if p < current_total) + 1


def control_factor(rank: int, slots_per_day: int, function: str, scaling: float) -> float:
    """Compute normalized control factor (0–1) from rank.

    0 = cheapest slot, 1 = most expensive.
    The control factor is the inverse: 1.0 = cheapest, 0.0 = most expensive.
    """
    if slots_per_day <= 1:
        return 0.5

    t = (rank - 1) / (slots_per_day - 1)  # 0 = cheapest, 1 = most expensive

    if function == CONTROL_FACTOR_SINUSOIDAL:
        cf = (1.0 + math.cos(math.pi * t)) / 2.0
    else:  # linear
        cf = 1.0 - t

    cf = cf**scaling
    return max(0.0, min(1.0, cf))


def control_factor_bipolar(cf: float) -> float:
    """Convert control factor (0–1) to bipolar (-1 to +1)."""
    return 2.0 * cf - 1.0


def rank_to_bucket(rank: int, slots_per_day: int) -> str:
    """Map a slot rank to a quartile bucket: 'q1'..'q4'."""
    q = slots_per_day // 4
    if rank <= q:
        return "q1"
    if rank <= 2 * q:
        return "q2"
    if rank <= 3 * q:
        return "q3"
    return "q4"


def price_quartile(rank: int, slots_per_day: int) -> int:
    """Return quartile (1–4) for a given rank."""
    return int(rank_to_bucket(rank, slots_per_day)[1])


def normalize_transfer_rank(rank: int, total: int) -> float:
    """Normalize transfer rank to [0.0, 1.0].

    0.0 = cheapest, 1.0 = most expensive.
    When total == 1, always returns 0.0.
    """
    if total <= 1:
        return 0.0
    return (rank - 1) / (total - 1)


def compute_score(bucket_data: dict[str, float], formula: str = "default") -> float:
    """Compute optimization score (0–100) from quartile bucket data."""
    q1 = bucket_data.get("q1", 0.0)
    q2 = bucket_data.get("q2", 0.0)
    q3 = bucket_data.get("q3", 0.0)
    total = q1 + q2 + bucket_data.get("q4", 0.0) + q3
    if total <= 0:
        return 0.0
    raw = (q1 * 3 + q2 * 2 + q3) / (total * 3) * 100
    if formula == SCORE_FORMULA_RAW:
        return max(0.0, min(100.0, raw))
    return max(0.0, min(100.0, (raw - 30.0) / 53.3 * 100))


def cheapest_window(
    slots: list[PriceSlot],
    slots_needed: int,
    price_fn: Callable[[PriceSlot], float],
) -> tuple[list[PriceSlot], float] | None:
    """Find the consecutive window of slots_needed slots with the lowest average price.

    price_fn is called once per slot to determine its price for comparison.
    Returns (window_slots, avg_price) or None if slots_needed > len(slots).
    """
    if not slots or slots_needed > len(slots):
        return None

    prices = [price_fn(s) for s in slots]
    best_start_idx = 0
    best_total = sum(prices[:slots_needed])
    current_total = best_total

    for i in range(1, len(slots) - slots_needed + 1):
        current_total -= prices[i - 1]
        current_total += prices[i + slots_needed - 1]
        if current_total < best_total:
            best_total = current_total
            best_start_idx = i

    best_window = slots[best_start_idx : best_start_idx + slots_needed]
    avg_price = best_total / slots_needed
    return best_window, avg_price


def fixed_period_for_date(periods: list[FixedPeriod], d: date) -> FixedPeriod | None:
    """Return the first FixedPeriod active on date d, or None."""
    for p in periods:
        if p.is_active_on(d):
            return p
    return None
