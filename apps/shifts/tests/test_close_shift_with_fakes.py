from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.core.domain.money import Money
from apps.shifts.domain.drawer import ShiftSales
from apps.shifts.domain.errors import ShiftNotFoundError
from apps.shifts.models import Shift
from apps.shifts.use_cases.close_shift import ShiftClosing, close_shift

CLOSED_AT = datetime(2026, 9, 27, 16, 0, tzinfo=UTC)


class FakeShifts:
    def __init__(self, shift: Shift) -> None:
        self.shift = shift
        self.saved: list[list[str]] = []

    def lock(self, tenant_id, shift_id):
        return self.shift if self.shift.id == shift_id else None

    def save(self, shift, fields):
        self.saved.append(fields)


class FakeSales:
    def sales_of(self, tenant_id, shift_id):
        return replace(ShiftSales.none(), cash=Money("700"))


def _shift(status: str = "open") -> Shift:
    return Shift(
        id=uuid4(),
        tenant_id=1,
        counter_id=2,
        cashier_id=3,
        opened_at=CLOSED_AT,
        opening_cash=Decimal("5000.00"),
        status=status,
    )


def _closing(shift: Shift, counter_id: int = 2) -> ShiftClosing:
    return ShiftClosing(
        tenant_id=1,
        counter_id=counter_id,
        device_id=9,
        cashier_id=3,
        shift_id=shift.id,
        closed_at=CLOSED_AT,
        counted_cash=Decimal("5700.00"),
        local_summary={"bills": 0, "cash": "700.00"},
        unsynced_count=0,
    )


@pytest.mark.django_db
def test_close_uses_the_servers_sales_for_the_expected_cash():
    shift = _shift()
    shifts = FakeShifts(shift)

    close_shift(_closing(shift), shifts=shifts, sales=FakeSales())

    assert shift.status == "closed"
    assert shift.expected_cash == Decimal("5700.00")
    assert shift.difference == Decimal("0.00")
    assert shift.summary["mismatch"] is False
    assert shift.summary["local"] == {"bills": 0, "cash": "700.00"}
    assert len(shifts.saved) == 1


@pytest.mark.django_db
def test_a_closed_shift_is_returned_as_stored():
    shift = _shift(status="closed")
    shifts = FakeShifts(shift)

    assert close_shift(_closing(shift), shifts=shifts, sales=FakeSales()) is shift
    assert shifts.saved == []


@pytest.mark.django_db
def test_another_counters_shift_is_not_found():
    shift = _shift()

    with pytest.raises(ShiftNotFoundError):
        close_shift(_closing(shift, counter_id=7), shifts=FakeShifts(shift), sales=FakeSales())
