from datetime import datetime
from decimal import Decimal

from rest_framework import serializers

from apps.shifts.models import Shift


def present_shift(shift: Shift) -> dict:
    return {
        "id": str(shift.id),
        "counter_id": shift.counter_id,
        "cashier_id": shift.cashier_id,
        "status": shift.status,
        "opened_at": _time(shift.opened_at),
        "opening_cash": _money(shift.opening_cash),
        "closed_at": _time(shift.closed_at),
        "counted_cash": _money(shift.counted_cash),
        "expected_cash": _money(shift.expected_cash),
        "difference": _money(shift.difference),
    }


def _time(value: datetime | None) -> str | None:
    return serializers.DateTimeField().to_representation(value) if value else None


def _money(value: Decimal | None) -> str | None:
    return None if value is None else f"{Decimal(value):.2f}"


def present_close(shift: Shift) -> dict:
    return {
        "expected_cash": _money(shift.expected_cash),
        "difference": _money(shift.difference),
        "server_summary": shift.summary["server"],
        "mismatch": shift.summary["mismatch"],
    }
