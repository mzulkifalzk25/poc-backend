from decimal import Decimal
from typing import Protocol

from apps.catalog.models import Product
from apps.inventory.models import StockLevel


class StockLevelRepository(Protocol):
    def add(self, product: Product, qty: Decimal) -> StockLevel: ...


class DjangoStockLevelRepository:
    def add(self, product: Product, qty: Decimal) -> StockLevel:
        return StockLevel.objects.create(tenant_id=product.tenant_id, product=product, qty=qty)


stock_level_repository = DjangoStockLevelRepository()
