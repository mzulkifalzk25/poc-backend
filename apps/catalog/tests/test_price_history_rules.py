from datetime import UTC, datetime, timedelta
from decimal import Decimal

from apps.catalog.domain.price_history import PriceChange, price_in_force

NOON = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def test_the_price_in_force_is_the_old_price_of_the_next_change():
    changes = [
        PriceChange(NOON + timedelta(hours=2), Decimal("60.00")),
        PriceChange(NOON + timedelta(hours=1), Decimal("50.00")),
    ]

    assert price_in_force(Decimal("70.00"), changes, NOON) == Decimal("50.00")
    assert price_in_force(Decimal("70.00"), changes, NOON + timedelta(minutes=90)) == Decimal(
        "60.00"
    )
    assert price_in_force(Decimal("70.00"), changes, NOON + timedelta(hours=3)) == Decimal("70.00")
    assert price_in_force(Decimal("70.00"), [], NOON) == Decimal("70.00")
