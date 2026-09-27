"""Bill totals, computed the way the counter does: tax on the subtotal (inside
the prices or added on top), then the total rounded to a whole rupee."""

from dataclasses import dataclass
from decimal import Decimal

from apps.core.domain.money import Money

from .lines import SaleLine

TOTAL_TOLERANCE = Decimal("1.00")


@dataclass(frozen=True)
class TaxRule:
    rate: Decimal
    prices_include_tax: bool


@dataclass(frozen=True)
class BillTotals:
    item_count: Decimal
    subtotal: Money
    tax: Money
    rounding: Money
    total: Money


def line_total(line: SaleLine) -> Money:
    return Money(line.qty * line.unit_price)


def bill_totals(lines: list[SaleLine], rule: TaxRule) -> BillTotals:
    subtotal = sum((line_total(line) for line in lines), Money.zero())
    tax = _tax(subtotal, rule)
    gross = subtotal if rule.prices_include_tax else subtotal + tax
    total = gross.round_to_whole_rupee()
    return BillTotals(
        item_count=sum((line.qty for line in lines), Decimal("0")),
        subtotal=subtotal,
        tax=tax,
        rounding=total - gross,
        total=total,
    )


def total_differs(sent: Money, computed: Money) -> bool:
    """Beyond Rs 1 either way."""
    return abs(sent.amount - computed.amount) > TOTAL_TOLERANCE


def _tax(subtotal: Money, rule: TaxRule) -> Money:
    if rule.rate <= 0:
        return Money.zero()
    divisor = 100 + rule.rate if rule.prices_include_tax else Decimal("100")
    return Money(subtotal.amount * rule.rate / divisor)
