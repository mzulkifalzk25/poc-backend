"""What a counter sends in `POST /returns/batch`, and what it gets back."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from apps.sales.domain.returns import ReturnedQty


@dataclass(frozen=True)
class ReturnUpload:
    id: UUID
    shift_id: UUID
    lines: list[ReturnedQty]
    reason: str
    restock: bool
    refund_method: str
    refund_amount: Decimal
    original_bill_no: str | None
    returned_at: datetime
    cashier_id: int | None = None


@dataclass(frozen=True)
class ReturnBatch:
    """`cashier_id` is the signed-in cashier; None for a PC token."""

    tenant_id: int
    counter_id: int
    device_id: int
    cashier_id: int | None
    received_at: datetime
    returns: list[ReturnUpload]


@dataclass(frozen=True)
class ReturnResult:
    id: str | None
    status: str
    flags: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
