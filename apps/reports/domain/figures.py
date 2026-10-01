"""Plain report arithmetic: profit, margins, shares, and filling every day or
period of a range, with zeros where nothing happened."""

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from datetime import date, timedelta
from decimal import Decimal

ZERO = Decimal("0")
RATIO_PLACES = Decimal("0.1")


@dataclass(frozen=True)
class DayFigures:
    """One local day (or a sum of days). Sales are gross; refunds are separate."""

    bills: int = 0
    items: Decimal = ZERO
    gross: Decimal = ZERO
    cash: Decimal = ZERO
    card: Decimal = ZERO
    wallet: Decimal = ZERO
    cost: Decimal = ZERO
    refund_count: int = 0
    refund_amount: Decimal = ZERO
    refund_cost_recovered: Decimal = ZERO
    stock_bought: Decimal = ZERO

    def __add__(self, other: DayFigures) -> DayFigures:
        return DayFigures(
            **{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)}
        )


def gross_profit(figures: DayFigures) -> Decimal:
    """Sales profit minus refunds, where a return that was not restocked is a
    full loss: only `refund_cost_recovered` comes back."""
    return figures.gross - figures.cost - (figures.refund_amount - figures.refund_cost_recovered)


def net(figures: DayFigures) -> Decimal:
    return figures.gross - figures.refund_amount - figures.stock_bought


def percent_change(current: Decimal, previous: Decimal) -> Decimal | None:
    """None when there is nothing to compare with."""
    if previous <= 0:
        return None
    return ((current - previous) / previous * 100).quantize(RATIO_PLACES)


def percent_of(part: Decimal, whole: Decimal) -> Decimal:
    if whole <= 0:
        return ZERO
    return (part / whole * 100).quantize(RATIO_PLACES)


def average(total: Decimal, count: int) -> Decimal:
    return (total / count).quantize(Decimal("0.01")) if count else ZERO


def days_in(first: date, last: date) -> list[date]:
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def week_start(day: date) -> date:
    """The Monday of `day`'s week."""
    return day - timedelta(days=day.weekday())


def month_start(day: date) -> date:
    return day.replace(day=1)


def group_days(
    by_day: dict[date, DayFigures],
    first: date,
    last: date,
    key: Callable[[date], date],
) -> list[tuple[date, date, DayFigures]]:
    """`(period start, period end, summed figures)` for every period in the
    range, in order; the first and last periods are cut to the range."""
    periods: dict[date, list[date]] = {}
    for day in days_in(first, last):
        periods.setdefault(key(day), []).append(day)
    return [
        (start, days[-1], sum((by_day.get(d, DayFigures()) for d in days), DayFigures()))
        for start, days in periods.items()
    ]


def with_stock_bought(figures: DayFigures, amount: Decimal) -> DayFigures:
    return replace(figures, stock_bought=amount)


@dataclass(frozen=True)
class ProductTotals:
    product_id: int
    name: str
    category_id: int | None
    category_name: str
    tint: str
    qty: Decimal
    revenue: Decimal
    cost: Decimal


@dataclass(frozen=True)
class CashierTotals:
    cashier_id: int
    name: str
    is_active: bool
    bills: int
    revenue: Decimal
    refund_count: int
    refund_amount: Decimal


@dataclass(frozen=True)
class LowStockItem:
    product_id: int
    name: str
    qty: Decimal
