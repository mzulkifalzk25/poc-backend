from django.db import models

from apps.catalog.models import Product
from apps.core.models import TenantModel


class StockLevel(TenantModel):
    """One row per product. `qty` may go negative: never clamped, no CHECK."""

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="stock_levels", db_index=False
    )
    qty = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "product"], name="uniq_stock_level_product"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "updated_at", "id"], name="stock_level_sync_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id}: {self.qty}"
