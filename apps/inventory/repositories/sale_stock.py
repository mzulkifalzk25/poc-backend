from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from django.db.models import F

from apps.inventory.models import StockLevel, StockMovement


class SaleStockRepository(Protocol):
    def lock_levels(self, tenant_id: int, product_ids: Iterable[int]) -> dict[int, Decimal]: ...

    def record(
        self,
        tenant_id: int,
        movements: list[StockMovement],
        deltas: Mapping[int, Decimal],
        now: datetime,
    ) -> None: ...


class DjangoSaleStockRepository:
    def lock_levels(self, tenant_id: int, product_ids: Iterable[int]) -> dict[int, Decimal]:
        """Row locks in product-id order (every writer uses the same order, so
        two batches never deadlock). A product without a row gets one at 0."""
        ids = sorted(set(product_ids))
        StockLevel.objects.bulk_create(
            [StockLevel(tenant_id=tenant_id, product_id=product_id) for product_id in ids],
            ignore_conflicts=True,
        )
        levels = (
            StockLevel.objects.for_tenant(tenant_id)
            .filter(product_id__in=ids)
            .select_for_update()
            .order_by("product_id")
        )
        return {product_id: qty for product_id, qty in levels.values_list("product_id", "qty")}

    def record(
        self,
        tenant_id: int,
        movements: list[StockMovement],
        deltas: Mapping[int, Decimal],
        now: datetime,
    ) -> None:
        """Movements skip a (record, product) pair already written; then one
        summed update per product, in product-id order. `updated_at` is set
        explicitly so the change reaches counters through stock sync."""
        StockMovement.objects.bulk_create(movements, ignore_conflicts=True)
        levels = StockLevel.objects.for_tenant(tenant_id)
        for product_id in sorted(deltas):
            levels.filter(product_id=product_id).update(
                qty=F("qty") + deltas[product_id], updated_at=now
            )


sale_stock_repository = DjangoSaleStockRepository()
