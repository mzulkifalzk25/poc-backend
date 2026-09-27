from django.contrib import admin

from apps.core.read_only_admin import ReadOnlyAdmin
from apps.inventory.models import StockLevel, StockMovement


@admin.register(StockLevel)
class StockLevelAdmin(ReadOnlyAdmin):
    list_display = ("product", "qty", "tenant_id", "updated_at")
    list_filter = ("tenant_id",)
    search_fields = ("product__name", "product__barcode")


@admin.register(StockMovement)
class StockMovementAdmin(ReadOnlyAdmin):
    list_display = ("product", "type", "qty_delta", "reason", "tenant_id", "occurred_at")
    list_filter = ("tenant_id", "type")
