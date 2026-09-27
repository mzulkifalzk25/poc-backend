from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.shifts.domain.errors import ShiftIdTakenError
from apps.shifts.models import Shift
from apps.shifts.repositories.shifts import ShiftRepository, shift_repository


@dataclass(frozen=True)
class ShiftOpening:
    tenant_id: int
    counter_id: int
    device_id: int
    cashier_id: int
    shift_id: UUID
    opened_at: datetime
    opening_cash: Decimal


@dataclass(frozen=True)
class OpenedShift:
    shift: Shift
    created: bool


def open_shift(opening: ShiftOpening, shifts: ShiftRepository = shift_repository) -> OpenedShift:
    """Idempotent on the client UUID: a retry returns the stored shift."""
    existing = _same_counter_shift(opening, shifts)
    if existing is not None:
        return OpenedShift(existing, created=False)
    shift = _new_shift(opening)
    try:
        with transaction.atomic():
            shifts.add(shift)
            _log_opened(shift, opening.device_id)
    except ShiftIdTakenError:
        existing = _same_counter_shift(opening, shifts)
        if existing is None:
            raise
        return OpenedShift(existing, created=False)
    return OpenedShift(shift, created=True)


def current_shift(
    tenant_id: int, counter_id: int, shifts: ShiftRepository = shift_repository
) -> Shift | None:
    return shifts.open_at_counter(tenant_id, counter_id)


def _same_counter_shift(opening: ShiftOpening, shifts: ShiftRepository) -> Shift | None:
    existing = shifts.get(opening.tenant_id, opening.shift_id)
    if existing is not None and existing.counter_id != opening.counter_id:
        raise ShiftIdTakenError
    return existing


def _new_shift(opening: ShiftOpening) -> Shift:
    return Shift(
        id=opening.shift_id,
        tenant_id=opening.tenant_id,
        counter_id=opening.counter_id,
        cashier_id=opening.cashier_id,
        opened_at=opening.opened_at,
        opening_cash=opening.opening_cash,
    )


def _log_opened(shift: Shift, device_id: int) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=shift.tenant_id,
            user_id=shift.cashier_id,
            action="shift_opened",
            entity_type="shift",
            entity_id=str(shift.id),
            device_id=device_id,
            detail={"counter_id": shift.counter_id, "opening_cash": str(shift.opening_cash)},
            occurred_at=shift.opened_at,
        )
    )
