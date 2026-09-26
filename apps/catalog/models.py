from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import TenantModel


class Category(TenantModel):
    name = models.CharField(max_length=100)
    tint = models.CharField(max_length=20)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "tenant_id", Lower("name"), name="uniq_category_tenant_name_lower"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Product(TenantModel):
    """`name_lc` is the lower-cased name for search. Deleting archives."""

    barcode = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    name_lc = models.CharField(max_length=255)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products", db_index=False
    )
    unit = models.CharField(max_length=10)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    cost = models.DecimalField(max_digits=12, decimal_places=2)
    low_stock_alert = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.BigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "barcode"],
                condition=models.Q(is_archived=False),
                name="uniq_product_live_barcode",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "updated_at", "id"], name="product_sync_idx"),
            models.Index(fields=["tenant_id", "category"], name="product_category_idx"),
            GinIndex(fields=["name_lc"], opclasses=["gin_trgm_ops"], name="product_name_trgm_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class PriceHistory(TenantModel):
    """Also finds the price in force at a past time (returns)."""

    SOURCES = [("edit", "Edit"), ("import", "Import")]

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="price_history", db_index=False
    )
    old_price = models.DecimalField(max_digits=12, decimal_places=2)
    new_price = models.DecimalField(max_digits=12, decimal_places=2)
    changed_by = models.BigIntegerField(null=True, blank=True)
    source = models.CharField(max_length=10, choices=SOURCES, default="edit")
    changed_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(
                fields=["tenant_id", "product", "-changed_at"], name="price_history_product_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id}: {self.old_price} -> {self.new_price}"
