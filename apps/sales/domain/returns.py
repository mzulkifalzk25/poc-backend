"""Return refunds. A product on the found bill is refunded at the price paid,
anything else at today's price. Anomalies are flagged, never refused."""

from dataclasses import dataclass, replace
from decimal import Decimal

from apps.core.domain.money import Money

from .flags import CLOCK_SKEW, PRICE_MISMATCH
from .lines import SaleLine
from .totals import TaxRule, bill_totals

OVER_RETURN = "over_return"
ITEM_NOT_ON_BILL = "item_not_on_bill"
BILL_NOT_FOUND = "bill_not_found"
_ORDER = (OVER_RETURN, ITEM_NOT_ON_BILL, BILL_NOT_FOUND, PRICE_MISMATCH, CLOCK_SKEW)

PAID = "paid"
CURRENT = "current"

BILL_PAID = "paid"
BILL_PARTIALLY_REFUNDED = "partially_refunded"
BILL_REFUNDED = "refunded"


@dataclass(frozen=True)
class ReturnedQty:
    product_id: int
    qty: Decimal


@dataclass(frozen=True)
class BillLine:
    bill_item_id: int
    product_id: int
    qty: Decimal
    unit_price: Decimal
    cost_snapshot: Decimal
    returned: Decimal


@dataclass(frozen=True)
class FoundBill:
    """A bill as earlier returns left it: what they took back and paid out."""

    total: Money
    refunded: Money
    lines: dict[int, BillLine]

    def is_cleared(self) -> bool:
        return all(line.returned >= line.qty for line in self.lines.values())


@dataclass(frozen=True)
class TodayPrice:
    price: Decimal
    cost: Decimal


@dataclass(frozen=True)
class RefundLine:
    product_id: int
    qty: Decimal
    bill_item_id: int | None
    price_source: str
    unit_price: Decimal
    refund_amount: Money
    tax_refund: Money
    cost_snapshot: Decimal


@dataclass(frozen=True)
class Refund:
    lines: list[RefundLine]
    total: Money
    flags: set[str]


def merge_returned(lines: list[ReturnedQty]) -> list[ReturnedQty]:
    """One row per product, in the order each product first appears."""
    merged: dict[int, Decimal] = {}
    for line in lines:
        merged[line.product_id] = merged.get(line.product_id, Decimal("0")) + line.qty
    return [ReturnedQty(product_id, qty) for product_id, qty in merged.items()]


def price_return(
    lines: list[ReturnedQty],
    bill: FoundBill | None,
    bill_no_given: bool,
    today: dict[int, TodayPrice],
    tax: TaxRule,
) -> Refund:
    on_bill = bill.lines if bill else {}
    priced = [
        _paid_line(line, on_bill[line.product_id], tax)
        if line.product_id in on_bill
        else _current_line(line, today[line.product_id], tax)
        for line in lines
    ]
    return Refund(priced, _total(priced, bill, tax), _bill_flags(lines, bill, bill_no_given))


def after_return(bill: FoundBill, lines: list[ReturnedQty], paid: Money) -> FoundBill:
    """The bill as the next return sees it."""
    taken = {line.product_id: line.qty for line in lines}
    updated = {
        product_id: replace(line, returned=line.returned + taken.get(product_id, Decimal("0")))
        for product_id, line in bill.lines.items()
    }
    return FoundBill(bill.total, bill.refunded + paid, updated)


def bill_status(bill: FoundBill) -> str:
    if bill.is_cleared():
        return BILL_REFUNDED
    if any(line.returned > 0 for line in bill.lines.values()):
        return BILL_PARTIALLY_REFUNDED
    return BILL_PAID


def ordered_return_flags(raised: set[str]) -> list[str]:
    return [flag for flag in _ORDER if flag in raised]


def is_paid_from_drawer(method: str) -> bool:
    """Only cash leaves the drawer; card and wallet refunds are recorded only."""
    return method == "cash"


def _paid_line(line: ReturnedQty, paid: BillLine, tax: TaxRule) -> RefundLine:
    amount = Money(line.qty * paid.unit_price)
    return RefundLine(
        line.product_id,
        line.qty,
        paid.bill_item_id,
        PAID,
        paid.unit_price,
        amount,
        _tax_refund(amount, tax),
        paid.cost_snapshot,
    )


def _current_line(line: ReturnedQty, today: TodayPrice, tax: TaxRule) -> RefundLine:
    amount = Money(line.qty * today.price)
    return RefundLine(
        line.product_id,
        line.qty,
        None,
        CURRENT,
        today.price,
        amount,
        _tax_refund(amount, tax),
        today.cost,
    )


def _tax_refund(amount: Money, tax: TaxRule) -> Money:
    """Tax is refunded on top only when prices exclude it."""
    if tax.rate <= 0 or tax.prices_include_tax:
        return Money.zero()
    return Money(amount.amount * tax.rate / 100)


def _total(lines: list[RefundLine], bill: FoundBill | None, tax: TaxRule) -> Money:
    """Whole-rupee rounding as on a bill. The return that clears a bill pays
    what is left of it, so the refunds add up to the bill total."""
    paid = [line for line in lines if line.price_source == PAID]
    if bill is None or not paid or bill.is_cleared():
        return _rounded(lines, tax)
    after = after_return(bill, [ReturnedQty(line.product_id, line.qty) for line in paid], Money(0))
    if not after.is_cleared():
        return _rounded(lines, tax)
    left = max(bill.total - bill.refunded, Money.zero())
    return left + _rounded([line for line in lines if line.price_source == CURRENT], tax)


def _rounded(lines: list[RefundLine], tax: TaxRule) -> Money:
    if not lines:
        return Money.zero()
    sale_lines = [SaleLine(0, line.product_id, "", "", line.qty, line.unit_price) for line in lines]
    return bill_totals(sale_lines, tax).total


def _bill_flags(lines: list[ReturnedQty], bill: FoundBill | None, bill_no_given: bool) -> set[str]:
    if bill is None:
        return {BILL_NOT_FOUND} if bill_no_given else set()
    flags = set()
    for line in lines:
        paid = bill.lines.get(line.product_id)
        if paid is None:
            flags.add(ITEM_NOT_ON_BILL)
        elif paid.returned + line.qty > paid.qty:
            flags.add(OVER_RETURN)
    return flags
