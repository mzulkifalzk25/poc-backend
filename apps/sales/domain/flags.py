"""Anomalies on an uploaded bill. The bill is always accepted; flags mark it."""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal

PRICE_MISMATCH = "price_mismatch"
CLOCK_SKEW = "clock_skew"
TOTAL_MISMATCH = "total_mismatch"
BILL_NO_CONFLICT = "bill_no_conflict"
NEGATIVE_STOCK = "negative_stock"
_ORDER = (PRICE_MISMATCH, CLOCK_SKEW, TOTAL_MISMATCH, BILL_NO_CONFLICT, NEGATIVE_STOCK)

CLOCK_SKEW_LIMIT = timedelta(minutes=5)


def ordered_flags(raised: set[str]) -> list[str]:
    return [flag for flag in _ORDER if flag in raised]


def is_clock_skewed(sold_at: datetime, received_at: datetime) -> bool:
    """A sale the server receives more than 5 minutes before it happened."""
    return sold_at - received_at > CLOCK_SKEW_LIMIT


def is_bill_no_conflict(bill_no: str, counter_code: str, taken: bool) -> bool:
    return taken or bill_no[:3] != counter_code


def negative_stock_bills(
    levels: Mapping[int, Decimal], bills: Sequence[Mapping[int, Decimal]]
) -> list[bool]:
    """Walks the bills in order from the current levels; a bill is flagged when
    it takes any of its products below zero."""
    running = dict(levels)
    flagged = []
    for quantities in bills:
        for product_id, qty in quantities.items():
            running[product_id] = running.get(product_id, Decimal("0")) - qty
        flagged.append(any(running[product_id] < 0 for product_id in quantities))
    return flagged
