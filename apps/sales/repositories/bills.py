from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from django.db import IntegrityError, connection, transaction

from apps.sales.domain.errors import BillIdTakenError
from apps.sales.domain.flags import BILL_NO_CONFLICT
from apps.sales.models import Bill, BillItem, Payment

# First key of the two-key advisory lock taken per counter for a bill batch.
_BILL_BATCH_LOCK = 7301
_ID_CONSTRAINTS = ("sales_bill_pkey", "sales_payment_pkey")


class BillRepository(Protocol):
    def try_lock_counter(self, counter_id: int) -> bool: ...

    def stored_flags(self, tenant_id: int, ids: Iterable[UUID]) -> dict[UUID, list[str]]: ...

    def taken_bill_nos(self, tenant_id: int, bill_nos: Iterable[str]) -> set[str]: ...

    def add(self, bill: Bill, items: list[BillItem], payment: Payment) -> None: ...

    def by_bill_no(self, tenant_id: int, bill_no: str) -> Bill | None: ...

    def items_of(self, bill: Bill) -> list[BillItem]: ...


class DjangoBillRepository:
    def try_lock_counter(self, counter_id: int) -> bool:
        """Held until the caller's transaction ends; one batch per counter."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_xact_lock(%s, %s)", [_BILL_BATCH_LOCK, counter_id % 2**31]
            )
            return cursor.fetchone()[0]

    def stored_flags(self, tenant_id: int, ids: Iterable[UUID]) -> dict[UUID, list[str]]:
        bills = Bill.objects.for_tenant(tenant_id).filter(id__in=list(ids))
        return dict(bills.values_list("id", "flags"))

    def taken_bill_nos(self, tenant_id: int, bill_nos: Iterable[str]) -> set[str]:
        bills = Bill.objects.for_tenant(tenant_id).filter(bill_no__in=list(set(bill_nos)))
        return set(bills.values_list("bill_no", flat=True))

    def add(self, bill: Bill, items: list[BillItem], payment: Payment) -> None:
        """One savepoint per bill: a failure leaves the rest of the batch intact."""
        try:
            with transaction.atomic():
                bill.save(force_insert=True)
                BillItem.objects.bulk_create(items)
                payment.save(force_insert=True)
        except IntegrityError as error:
            if any(name in str(error) for name in _ID_CONSTRAINTS):
                raise BillIdTakenError from None
            raise

    def by_bill_no(self, tenant_id: int, bill_no: str) -> Bill | None:
        """The bill that owns the number; a flagged copy only when there is none."""
        bills = Bill.objects.for_tenant(tenant_id).filter(bill_no=bill_no)
        owner = bills.exclude(flags__contains=[BILL_NO_CONFLICT]).first()
        return owner or bills.order_by("-received_at").first()

    def items_of(self, bill: Bill) -> list[BillItem]:
        return list(
            BillItem.objects.for_tenant(bill.tenant_id).filter(bill=bill).order_by("line_no")
        )


bill_repository = DjangoBillRepository()
