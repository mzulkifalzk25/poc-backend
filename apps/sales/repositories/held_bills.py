from typing import Protocol
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.sales.domain.errors import HeldBillIdTakenError
from apps.sales.models import HeldBill


class HeldBillRepository(Protocol):
    def get(self, tenant_id: int, held_id: UUID) -> HeldBill | None: ...

    def add(self, held: HeldBill) -> None: ...

    def save(self, held: HeldBill) -> None: ...


class DjangoHeldBillRepository:
    def get(self, tenant_id: int, held_id: UUID) -> HeldBill | None:
        return HeldBill.objects.for_tenant(tenant_id).filter(id=held_id).first()

    def add(self, held: HeldBill) -> None:
        try:
            with transaction.atomic():
                held.save(force_insert=True)
        except IntegrityError as error:
            if "sales_heldbill_pkey" in str(error):
                raise HeldBillIdTakenError from None
            raise

    def save(self, held: HeldBill) -> None:
        held.save()


held_bill_repository = DjangoHeldBillRepository()
