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


class StockMovement(TenantModel):
    """Append-only history of stock changes. The partial unique indexes make a
    retried sale or return write its movement once per product."""

    class Type(models.TextChoices):
        SALE = "sale"
        RETURN = "return"
        RECEIVE = "receive"
        ADJUST_ADD = "adjust_add"
        ADJUST_REMOVE = "adjust_remove"
        COUNT_CORRECTION = "count_correction"

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="stock_movements", db_index=False
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    qty_delta = models.DecimalField(max_digits=12, decimal_places=3)
    ref_type = models.CharField(max_length=20, blank=True, default="")
    ref_id = models.CharField(max_length=64, blank=True, default="")
    reason = models.CharField(max_length=20, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    user_id = models.BigIntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(
                fields=["tenant_id", "product", "-occurred_at"], name="stock_move_product_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "ref_type", "ref_id", "product"],
                condition=models.Q(type="sale"),
                name="uniq_stock_move_sale_ref",
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "ref_type", "ref_id", "product"],
                condition=models.Q(type="return"),
                name="uniq_stock_move_return_ref",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.qty_delta} of {self.product_id}"
