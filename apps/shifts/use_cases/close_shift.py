from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.core.domain.money import Money
from apps.shifts.domain.drawer import check_drawer
from apps.shifts.domain.errors import ShiftNotFoundError
from apps.shifts.models import Shift
from apps.shifts.repositories.shift_sales import ShiftSalesRepository, shift_sales_repository
from apps.shifts.repositories.shifts import ShiftRepository, shift_repository

_CLOSE_FIELDS = [
    "status",
    "closed_at",
    "counted_cash",
    "expected_cash",
    "difference",
    "unsynced_at_close",
    "summary",
]


@dataclass(frozen=True)
class ShiftClosing:
    tenant_id: int
    counter_id: int
    device_id: int
    cashier_id: int
    shift_id: UUID
    closed_at: datetime
    counted_cash: Decimal
    local_summary: dict
    unsynced_count: int


def close_shift(
    closing: ShiftClosing,
    shifts: ShiftRepository = shift_repository,
    sales: ShiftSalesRepository = shift_sales_repository,
) -> Shift:
    """Closing again returns the stored result and logs nothing."""
    with transaction.atomic():
        shift = shifts.lock(closing.tenant_id, closing.shift_id)
        if shift is None or shift.counter_id != closing.counter_id:
            raise ShiftNotFoundError
        if shift.status == Shift.Status.CLOSED:
            return shift
        _apply_close(shift, closing, sales)
        shifts.save(shift, _CLOSE_FIELDS)
        _log_closed(shift, closing)
    return shift


def _apply_close(shift: Shift, closing: ShiftClosing, sales: ShiftSalesRepository) -> None:
    check = check_drawer(
        Money(shift.opening_cash),
        Money(closing.counted_cash),
        sales.sales_of(shift.tenant_id, shift.id),
        closing.local_summary,
        closing.unsynced_count,
    )
    shift.status = Shift.Status.CLOSED
    shift.closed_at = closing.closed_at
    shift.counted_cash = closing.counted_cash
    shift.expected_cash = check.expected_cash.amount
    shift.difference = check.difference.amount
    shift.unsynced_at_close = closing.unsynced_count
    shift.summary = {
        "server": check.summary,
        "local": closing.local_summary,
        "mismatch": check.mismatch,
    }


def _log_closed(shift: Shift, closing: ShiftClosing) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=shift.tenant_id,
            user_id=closing.cashier_id,
            action="shift_closed",
            entity_type="shift",
            entity_id=str(shift.id),
            device_id=closing.device_id,
            detail={
                "counter_id": shift.counter_id,
                "counted_cash": str(shift.counted_cash),
                "expected_cash": str(shift.expected_cash),
                "difference": str(shift.difference),
                "unsynced_count": closing.unsynced_count,
                "mismatch": shift.summary["mismatch"],
            },
            occurred_at=shift.closed_at,
        )
    )
