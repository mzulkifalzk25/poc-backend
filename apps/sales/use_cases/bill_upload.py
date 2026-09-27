"""What a counter sends in `POST /bills/batch`, and what it gets back."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from apps.sales.domain.lines import SaleLine

CREATED = "created"
DUPLICATE = "duplicate"
REJECTED = "rejected"


@dataclass(frozen=True)
class PaymentUpload:
    id: UUID
    method: str
    amount: Decimal
    tendered: Decimal | None
    change_given: Decimal | None
    reference: str


@dataclass(frozen=True)
class SentTotals:
    item_count: Decimal
    subtotal: Decimal
    tax: Decimal
    rounding: Decimal
    total: Decimal


@dataclass(frozen=True)
class BillUpload:
    id: UUID
    bill_no: str
    shift_id: UUID
    cashier_id: int
    sold_at: datetime
    lines: list[SaleLine]
    payment: PaymentUpload
    totals: SentTotals


@dataclass(frozen=True)
class BillBatch:
    tenant_id: int
    counter_id: int
    device_id: int
    received_at: datetime
    bills: list[BillUpload]


@dataclass(frozen=True)
class BillResult:
    id: str | None
    status: str
    bill_no: str | None
    flags: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def rejected(bill_id: str | None, bill_no: str | None, errors: list[str]) -> BillResult:
    return BillResult(bill_id, REJECTED, bill_no, [], errors)
