from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from django.db import IntegrityError, connection, transaction
from django.db.models import Sum

from apps.core.domain.money import Money
from apps.sales.domain.errors import ReturnIdTakenError
from apps.sales.domain.flags import BILL_NO_CONFLICT
from apps.sales.domain.returns import BillLine, FoundBill
from apps.sales.models import Bill, BillItem, Return, ReturnItem

# First key of the two-key advisory lock taken per counter for a return batch.
_RETURN_BATCH_LOCK = 7303


@dataclass(frozen=True)
class LockedBill:
    id: UUID
    bill_no: str
    found: FoundBill


class ReturnRepository(Protocol):
    def try_lock_counter(self, counter_id: int) -> bool: ...

    def stored_flags(self, tenant_id: int, ids: Iterable[UUID]) -> dict[UUID, list[str]]: ...

    def lock_bills(self, tenant_id: int, bill_nos: Iterable[str]) -> dict[str, LockedBill]: ...

    def add(self, ret: Return, items: list[ReturnItem]) -> None: ...

    def set_bill_status(self, tenant_id: int, bill_id: UUID, status: str) -> None: ...


class DjangoReturnRepository:
    def try_lock_counter(self, counter_id: int) -> bool:
        """Held until the caller's transaction ends; one batch per counter."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_xact_lock(%s, %s)",
                [_RETURN_BATCH_LOCK, counter_id % 2**31],
            )
            return cursor.fetchone()[0]

    def stored_flags(self, tenant_id: int, ids: Iterable[UUID]) -> dict[UUID, list[str]]:
        returns = Return.objects.for_tenant(tenant_id).filter(id__in=list(ids))
        return dict(returns.values_list("id", "flags"))

    def lock_bills(self, tenant_id: int, bill_nos: Iterable[str]) -> dict[str, LockedBill]:
        """Row locks in bill-id order, then what earlier returns took back.
        A number held by several bills resolves to the one that owns it."""
        ids = sorted(_owner_ids(tenant_id, set(bill_nos)))
        bills = list(
            Bill.objects.for_tenant(tenant_id).filter(id__in=ids).select_for_update().order_by("id")
        )
        returned = _returned_qty(tenant_id, ids)
        refunded = _refunded(tenant_id, ids)
        lines: dict[UUID, dict[int, BillLine]] = {bill.id: {} for bill in bills}
        for item in BillItem.objects.for_tenant(tenant_id).filter(bill_id__in=ids):
            lines[item.bill_id][item.product_id] = BillLine(
                item.id,
                item.product_id,
                item.qty,
                item.unit_price,
                item.cost_snapshot,
                returned.get(item.id, Decimal("0")),
            )
        return {
            bill.bill_no: LockedBill(
                bill.id,
                bill.bill_no,
                FoundBill(Money(bill.total), refunded.get(bill.id, Money.zero()), lines[bill.id]),
            )
            for bill in bills
        }

    def add(self, ret: Return, items: list[ReturnItem]) -> None:
        """One savepoint per return: a failure leaves the rest of the batch intact."""
        try:
            with transaction.atomic():
                ret.save(force_insert=True)
                ReturnItem.objects.bulk_create(items)
        except IntegrityError as error:
            if "sales_return_pkey" in str(error):
                raise ReturnIdTakenError from None
            raise

    def set_bill_status(self, tenant_id: int, bill_id: UUID, status: str) -> None:
        Bill.objects.for_tenant(tenant_id).filter(id=bill_id).update(status=status)


def _owner_ids(tenant_id: int, bill_nos: set[str]) -> list[UUID]:
    rows = (
        Bill.objects.for_tenant(tenant_id)
        .filter(bill_no__in=bill_nos)
        .order_by("-received_at")
        .values_list("id", "bill_no", "flags")
    )
    owners: dict[str, UUID] = {}
    for bill_id, bill_no, flags in rows:
        if bill_no not in owners or BILL_NO_CONFLICT not in flags:
            owners[bill_no] = bill_id
    return list(owners.values())


def _returned_qty(tenant_id: int, bill_ids: list[UUID]) -> dict[int, Decimal]:
    rows = (
        ReturnItem.objects.for_tenant(tenant_id)
        .filter(bill_item__bill_id__in=bill_ids)
        .values_list("bill_item_id")
        .annotate(qty=Sum("qty"))
    )
    return dict(rows)


def _refunded(tenant_id: int, bill_ids: list[UUID]) -> dict[UUID, Money]:
    rows = (
        Return.objects.for_tenant(tenant_id)
        .filter(original_bill_id__in=bill_ids)
        .values_list("original_bill_id")
        .annotate(total=Sum("refund_total"))
    )
    return {bill_id: Money(total) for bill_id, total in rows}


return_repository = DjangoReturnRepository()
