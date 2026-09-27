"""Turns uploaded bills into deltas for the report tables.

Bills are bucketed by `sold_at` in the tenant's time zone, so a late upload
still lands in the hour and day of the sale."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

CENT = Decimal("0.01")
ZERO = Decimal("0")


@dataclass(frozen=True)
class SoldLine:
    product_id: int
    qty: Decimal
    line_total: Decimal
    cost_snapshot: Decimal

    @property
    def cost(self) -> Decimal:
        return (self.qty * self.cost_snapshot).quantize(CENT)


@dataclass(frozen=True)
class SoldBill:
    id: UUID
    tenant_id: int
    counter_id: int
    cashier_id: int
    sold_at: datetime
    item_count: Decimal
    tax: Decimal
    total: Decimal
    payments: tuple[tuple[str, Decimal], ...]
    lines: tuple[SoldLine, ...]


@dataclass
class SalesDelta:
    bills: int = 0
    items: Decimal = ZERO
    gross: Decimal = ZERO
    tax: Decimal = ZERO
    cash: Decimal = ZERO
    card: Decimal = ZERO
    wallet: Decimal = ZERO
    cost: Decimal = ZERO

    def add(self, bill: SoldBill) -> None:
        self.bills += 1
        self.items += bill.item_count
        self.gross += bill.total
        self.tax += bill.tax
        self.cost += sum((line.cost for line in bill.lines), ZERO)
        for method, amount in bill.payments:
            setattr(self, method, getattr(self, method) + amount)


@dataclass
class ProductDelta:
    qty: Decimal = ZERO
    revenue: Decimal = ZERO
    cost: Decimal = ZERO


@dataclass
class CashierDelta:
    bills: int = 0
    revenue: Decimal = ZERO


@dataclass
class RollupDeltas:
    hourly: dict[tuple[int, int, datetime], SalesDelta] = field(default_factory=dict)
    daily: dict[tuple[int, date], SalesDelta] = field(default_factory=dict)
    products: dict[tuple[int, date, int], ProductDelta] = field(default_factory=dict)
    cashiers: dict[tuple[int, date, int], CashierDelta] = field(default_factory=dict)


def local_hour(moment: datetime, timezone_name: str) -> datetime:
    """The start of the hour, in the tenant's time zone, that `moment` falls in."""
    local = moment.astimezone(ZoneInfo(timezone_name))
    return local.replace(minute=0, second=0, microsecond=0)


def sum_bills(bills: Iterable[SoldBill], timezones: dict[int, str]) -> RollupDeltas:
    deltas = RollupDeltas()
    for bill in bills:
        hour = local_hour(bill.sold_at, timezones[bill.tenant_id])
        day = hour.date()
        deltas.hourly.setdefault((bill.tenant_id, bill.counter_id, hour), SalesDelta()).add(bill)
        deltas.daily.setdefault((bill.tenant_id, day), SalesDelta()).add(bill)
        cashier = deltas.cashiers.setdefault((bill.tenant_id, day, bill.cashier_id), CashierDelta())
        cashier.bills += 1
        cashier.revenue += bill.total
        for line in bill.lines:
            product = deltas.products.setdefault(
                (bill.tenant_id, day, line.product_id), ProductDelta()
            )
            product.qty += line.qty
            product.revenue += line.line_total
            product.cost += line.cost
    return deltas
