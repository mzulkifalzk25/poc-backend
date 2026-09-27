from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.shifts.domain.errors import ShiftAlreadyOpenError, ShiftIdTakenError
from apps.shifts.models import Shift

_OPEN_CONSTRAINT = "uniq_shift_open_per_counter"


class ShiftRepository(Protocol):
    def get(self, tenant_id: int, shift_id: UUID) -> Shift | None: ...

    def lock(self, tenant_id: int, shift_id: UUID) -> Shift | None: ...

    def open_at_counter(self, tenant_id: int, counter_id: int) -> Shift | None: ...

    def cashiers_of(self, tenant_id: int, shift_ids: Iterable[UUID]) -> dict[UUID, int]: ...

    def add(self, shift: Shift) -> None: ...

    def save(self, shift: Shift, fields: list[str]) -> None: ...


class DjangoShiftRepository:
    def get(self, tenant_id: int, shift_id: UUID) -> Shift | None:
        return Shift.objects.for_tenant(tenant_id).filter(id=shift_id).first()

    def lock(self, tenant_id: int, shift_id: UUID) -> Shift | None:
        """Row lock until the end of the caller's transaction."""
        return Shift.objects.for_tenant(tenant_id).select_for_update().filter(id=shift_id).first()

    def open_at_counter(self, tenant_id: int, counter_id: int) -> Shift | None:
        return (
            Shift.objects.for_tenant(tenant_id)
            .filter(counter_id=counter_id, status=Shift.Status.OPEN)
            .first()
        )

    def cashiers_of(self, tenant_id: int, shift_ids: Iterable[UUID]) -> dict[UUID, int]:
        shifts = Shift.objects.for_tenant(tenant_id).filter(id__in=list(set(shift_ids)))
        return dict(shifts.values_list("id", "cashier_id"))

    def add(self, shift: Shift) -> None:
        """Insert only: a taken UUID or a second open shift is a domain error."""
        try:
            with transaction.atomic():
                shift.save(force_insert=True)
        except IntegrityError as error:
            if _OPEN_CONSTRAINT in str(error):
                raise ShiftAlreadyOpenError from None
            if "shifts_shift_pkey" in str(error):
                raise ShiftIdTakenError from None
            raise

    def save(self, shift: Shift, fields: list[str]) -> None:
        shift.save(update_fields=[*fields, "updated_at"])


shift_repository = DjangoShiftRepository()
