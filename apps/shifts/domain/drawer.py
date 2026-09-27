"""Shift close figures. Expected cash = opening + cash sales (amounts, not
tendered) - cash refunds paid from the drawer. Card and wallet never touch it."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from apps.core.domain.money import Money


@dataclass(frozen=True)
class ShiftSales:
    """What the server has received for one shift."""

    bills: int
    total_sales: Money
    cash: Money
    card: Money
    wallet: Money
    refund_count: int
    refund_amount: Money
    cash_refunds: Money

    @classmethod
    def none(cls) -> ShiftSales:
        zero = Money.zero()
        return cls(0, zero, zero, zero, zero, 0, zero, zero)


@dataclass(frozen=True)
class DrawerCheck:
    expected_cash: Money
    difference: Money
    summary: dict[str, str | int]
    mismatch: bool


def check_drawer(
    opening: Money, counted: Money, sales: ShiftSales, local_summary: dict, unsynced_count: int
) -> DrawerCheck:
    expected = opening + sales.cash - sales.cash_refunds
    difference = counted - expected
    return DrawerCheck(
        expected_cash=expected,
        difference=difference,
        summary=_summary(sales, expected, difference),
        mismatch=unsynced_count > 0 or not _agrees(local_summary, sales),
    )


def _summary(sales: ShiftSales, expected: Money, difference: Money) -> dict[str, str | int]:
    """The keys the counter sends as its own `local_summary`."""
    return {
        "bills": sales.bills,
        "total_sales": sales.total_sales.as_string(),
        "cash": sales.cash.as_string(),
        "card": sales.card.as_string(),
        "wallet": sales.wallet.as_string(),
        "refund_count": sales.refund_count,
        "refund_amount": sales.refund_amount.as_string(),
        "cash_refunds": sales.cash_refunds.as_string(),
        "expected_cash": expected.as_string(),
        "difference": difference.as_string(),
    }


def _agrees(local_summary: dict, sales: ShiftSales) -> bool:
    """The counter's bill count and cash sales match the server's. A missing
    or unreadable figure counts as a disagreement."""
    try:
        bills = local_summary["bills"]
        cash = Money(Decimal(str(local_summary["cash"])))
    except (KeyError, TypeError, InvalidOperation):
        return False
    return not isinstance(bills, bool) and bills == sales.bills and cash == sales.cash
