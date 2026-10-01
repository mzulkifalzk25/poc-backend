from decimal import Decimal
from typing import Protocol

from django.db.models import DecimalField, ExpressionWrapper, F, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.catalog.repositories.products import product_repository
from apps.core.domain.cursor import Cursor
from apps.inventory.models import StockLevel, StockMovement


class StockAdminRepository(Protocol):
    def stock_rows(self, tenant_id: int, filters: dict) -> QuerySet[Product]: ...

    def summary(self, tenant_id: int) -> dict: ...

    def movements(
        self, tenant_id: int, filters: dict, cursor: Cursor | None, limit: int
    ) -> list[StockMovement]: ...

    def user_names(self, tenant_id: int, ids: set[int]) -> dict[int, str]: ...

    def replayed_adjustment(
        self, tenant_id: int, product_id: int, key: str
    ) -> StockMovement | None: ...

    def level(self, tenant_id: int, product_id: int) -> Decimal: ...

    def product(self, tenant_id: int, product_id: int) -> Product | None: ...


class DjangoStockAdminRepository:
    def stock_rows(self, tenant_id: int, filters: dict) -> QuerySet[Product]:
        status = filters.get("status", "all")
        rows = product_repository.list_rows(
            tenant_id, {"search": filters.get("search", ""), "stock": _stock_filter(status)}
        )
        return rows.filter(stock_qty__lt=0) if status == "negative" else rows

    def summary(self, tenant_id: int) -> dict:
        live = product_repository.list_rows(tenant_id, {})
        value = ExpressionWrapper(F("stock_qty") * F("cost"), output_field=DecimalField())
        positive = Q(stock_qty__gt=0)
        totals = live.aggregate(
            units=Coalesce(Sum("stock_qty", filter=positive), Value(Decimal("0"))),
            value=Coalesce(Sum(value, filter=positive), Value(Decimal("0"))),
        )
        low = product_repository.list_rows(tenant_id, {"stock": "low"}).count()
        out = product_repository.list_rows(tenant_id, {"stock": "out"}).count()
        return {**totals, "low": low, "out": out}

    def movements(
        self,
        tenant_id: int,
        filters: dict,
        cursor: Cursor | None,
        limit: int,
    ) -> list[StockMovement]:
        rows = StockMovement.objects.for_tenant(tenant_id).select_related("product")
        if filters.get("product"):
            rows = rows.filter(product_id=filters["product"])
        if filters.get("types"):
            rows = rows.filter(type__in=filters["types"])
        if filters.get("from_"):
            rows = rows.filter(occurred_at__gte=filters["from_"])
        if filters.get("to"):
            rows = rows.filter(occurred_at__lt=filters["to"])
        if cursor:
            rows = rows.filter(
                Q(occurred_at__lt=cursor.occurred_at)
                | Q(occurred_at=cursor.occurred_at, id__lt=cursor.id)
            )
        return list(rows.order_by("-occurred_at", "-id")[:limit])

    def user_names(self, tenant_id: int, ids: set[int]) -> dict[int, str]:
        return dict(
            User.objects.for_tenant(tenant_id).filter(id__in=ids).values_list("id", "full_name")
        )

    def replayed_adjustment(
        self, tenant_id: int, product_id: int, key: str
    ) -> StockMovement | None:
        return (
            StockMovement.objects.for_tenant(tenant_id)
            .filter(ref_type="adjust", ref_id=key, product_id=product_id)
            .first()
        )

    def product(self, tenant_id: int, product_id: int) -> Product | None:
        return Product.objects.for_tenant(tenant_id).filter(id=product_id).first()

    def level(self, tenant_id: int, product_id: int) -> Decimal:
        row = StockLevel.objects.for_tenant(tenant_id).filter(product_id=product_id).first()
        return row.qty if row else Decimal("0")


def _stock_filter(status: str) -> str:
    return status if status in ("low", "out") else "all"


stock_admin_repository = DjangoStockAdminRepository()
