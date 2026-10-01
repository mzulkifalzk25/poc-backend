from decimal import Decimal
from typing import Protocol

from django.db.models import Count, Q, QuerySet, Sum
from django.db.models.functions import Coalesce

from apps.sales.domain.bill_cursor import BillCursor
from apps.sales.models import Bill, Return


class BillBrowseRepository(Protocol):
    def filtered(self, tenant_id: int, filters: dict) -> QuerySet[Bill]: ...

    def summary(self, bills: QuerySet[Bill]) -> tuple[int, Decimal]: ...

    def page(self, bills: QuerySet[Bill], cursor: BillCursor | None, limit: int) -> list[Bill]: ...

    def detail(self, tenant_id: int, bill_id) -> Bill | None: ...

    def returns_of(self, bill: Bill) -> list[Return]: ...


class DjangoBillBrowseRepository:
    def filtered(self, tenant_id: int, filters: dict):
        bills = Bill.objects.for_tenant(tenant_id)
        if filters.get("since"):
            bills = bills.filter(sold_at__gte=filters["since"])
        if filters.get("until"):
            bills = bills.filter(sold_at__lt=filters["until"])
        if filters.get("cashier"):
            bills = bills.filter(cashier_id=filters["cashier"])
        if filters.get("status"):
            bills = bills.filter(status=filters["status"])
        if filters.get("payment"):
            bills = bills.filter(payments__method=filters["payment"])
        if filters.get("bill_no"):
            bills = bills.filter(bill_no__startswith=filters["bill_no"])
        return bills

    def summary(self, bills) -> tuple[int, Decimal]:
        totals = bills.aggregate(bills=Count("id"), total=Coalesce(Sum("total"), Decimal("0")))
        return totals["bills"], totals["total"]

    def page(self, bills, cursor: BillCursor | None, limit: int) -> list[Bill]:
        if cursor:
            bills = bills.filter(
                Q(sold_at__lt=cursor.sold_at) | Q(sold_at=cursor.sold_at, id__gt=cursor.id)
            )
        rows = bills.select_related("cashier").prefetch_related("payments")
        return list(rows.order_by("-sold_at", "id")[:limit])

    def detail(self, tenant_id: int, bill_id) -> Bill | None:
        return (
            Bill.objects.for_tenant(tenant_id)
            .select_related("cashier", "counter")
            .prefetch_related("items", "payments")
            .filter(id=bill_id)
            .first()
        )

    def returns_of(self, bill: Bill) -> list[Return]:
        rows = Return.objects.for_tenant(bill.tenant_id).filter(original_bill=bill)
        return list(rows.prefetch_related("items").order_by("returned_at"))


bill_browse_repository = DjangoBillBrowseRepository()
