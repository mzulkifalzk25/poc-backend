from decimal import Decimal
from typing import Protocol

from apps.catalog.models import Product
from apps.core.domain.cursor import Cursor
from apps.core.repositories.keyset import rows_after
from apps.inventory.models import StockLevel


class StockLevelRepository(Protocol):
    def add(self, product: Product, qty: Decimal) -> StockLevel: ...

    def changed_after(self, tenant_id: int, since: Cursor | None) -> list[StockLevel]: ...


class DjangoStockLevelRepository:
    def add(self, product: Product, qty: Decimal) -> StockLevel:
        return StockLevel.objects.create(tenant_id=product.tenant_id, product=product, qty=qty)

    def changed_after(self, tenant_id: int, since: Cursor | None) -> list[StockLevel]:
        """Every change since the cursor, in `(updated_at, id)` order; not paged."""
        return list(rows_after(StockLevel.objects.for_tenant(tenant_id), since))


stock_level_repository = DjangoStockLevelRepository()
