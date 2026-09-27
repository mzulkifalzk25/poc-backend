"""The server's mirror of held bills: best effort, never logged (a held-bill
delete is logged only through the audit event upload)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.sales.domain.errors import HeldBillIdTakenError
from apps.sales.models import HeldBill
from apps.sales.repositories.held_bills import HeldBillRepository, held_bill_repository
from apps.shifts.repositories.shifts import ShiftRepository, shift_repository

CREATED, UPDATED, UNCHANGED, REJECTED = "created", "updated", "unchanged", "rejected"


@dataclass(frozen=True)
class HeldUpload:
    id: UUID
    title: str
    payload: dict
    total: Decimal
    status: str
    updated_at: datetime


@dataclass(frozen=True)
class HeldScope:
    tenant_id: int
    counter_id: int
    cashier_id: int


def sync_held_bills(
    scope: HeldScope,
    uploads: list[HeldUpload],
    held: HeldBillRepository = held_bill_repository,
    shifts: ShiftRepository = shift_repository,
) -> dict[UUID, str]:
    """Upsert by id; the newest `updated_at` from the counter wins."""
    shift = shifts.open_at_counter(scope.tenant_id, scope.counter_id)
    shift_id = shift.id if shift else None
    with transaction.atomic():
        return {upload.id: _sync_one(scope, shift_id, upload, held) for upload in uploads}


def _sync_one(
    scope: HeldScope, shift_id: UUID | None, upload: HeldUpload, held: HeldBillRepository
) -> str:
    row = held.get(scope.tenant_id, upload.id)
    if row is None:
        try:
            held.add(_new_row(scope, shift_id, upload))
        except HeldBillIdTakenError:
            return REJECTED
        return CREATED
    if row.counter_id != scope.counter_id:
        return REJECTED
    if upload.updated_at <= row.client_updated_at:
        return UNCHANGED
    _apply(row, upload)
    held.save(row)
    return UPDATED


def _new_row(scope: HeldScope, shift_id: UUID | None, upload: HeldUpload) -> HeldBill:
    row = HeldBill(
        id=upload.id,
        tenant_id=scope.tenant_id,
        counter_id=scope.counter_id,
        cashier_id=scope.cashier_id,
        shift_id=shift_id,
    )
    _apply(row, upload)
    return row


def _apply(row: HeldBill, upload: HeldUpload) -> None:
    row.title = upload.title
    row.payload = upload.payload
    row.total = upload.total
    row.status = upload.status
    row.client_updated_at = upload.updated_at
