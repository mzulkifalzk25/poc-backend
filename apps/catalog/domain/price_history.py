from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class PriceChange:
    changed_at: datetime
    old_price: Decimal


def price_in_force(current: Decimal, changes: Sequence[PriceChange], at: datetime) -> Decimal:
    """The price before the first change after `at`, else today's price."""
    later = [change for change in changes if change.changed_at > at]
    if not later:
        return current
    return min(later, key=lambda change: change.changed_at).old_price
