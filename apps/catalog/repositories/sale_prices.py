from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from apps.catalog.domain.price_history import PriceChange
from apps.catalog.models import PriceHistory, Product


class SalePriceRepository(Protocol):
    def products_by_id(self, tenant_id: int, ids: Iterable[int]) -> dict[int, Product]: ...

    def changes_after(
        self, tenant_id: int, ids: Iterable[int], since: datetime
    ) -> dict[int, list[PriceChange]]: ...


class DjangoSalePriceRepository:
    def products_by_id(self, tenant_id: int, ids: Iterable[int]) -> dict[int, Product]:
        """Archived products included: a sale that happened is never refused."""
        return Product.objects.for_tenant(tenant_id).in_bulk(list(set(ids)))

    def changes_after(
        self, tenant_id: int, ids: Iterable[int], since: datetime
    ) -> dict[int, list[PriceChange]]:
        """Only the changes after `since` decide the price in force from then on."""
        rows = PriceHistory.objects.for_tenant(tenant_id).filter(
            product_id__in=list(set(ids)), changed_at__gt=since
        )
        changes: dict[int, list[PriceChange]] = defaultdict(list)
        for product_id, changed_at, old_price in rows.values_list(
            "product_id", "changed_at", "old_price"
        ):
            changes[product_id].append(PriceChange(changed_at, old_price))
        return changes


sale_price_repository = DjangoSalePriceRepository()
