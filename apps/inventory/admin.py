from django.contrib import admin

from apps.inventory.models import StockLevel, StockMovement


@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = ("product", "qty", "tenant_id", "updated_at")
    list_filter = ("tenant_id",)
    search_fields = ("product__name", "product__barcode")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "type", "qty_delta", "reason", "tenant_id", "occurred_at")
    list_filter = ("tenant_id", "type")
