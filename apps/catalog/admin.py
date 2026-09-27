from django.contrib import admin

from apps.catalog.models import Category, PriceHistory, Product
from apps.core.read_only_admin import ReadOnlyAdmin


@admin.register(Category)
class CategoryAdmin(ReadOnlyAdmin):
    list_display = ("name", "tint", "tenant_id", "sort_order")
    list_filter = ("tenant_id",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(ReadOnlyAdmin):
    list_display = ("name", "barcode", "category", "price", "cost", "tenant_id", "is_archived")
    list_filter = ("tenant_id", "is_archived", "unit")
    search_fields = ("name", "barcode")


@admin.register(PriceHistory)
class PriceHistoryAdmin(ReadOnlyAdmin):
    list_display = ("product", "old_price", "new_price", "changed_by", "changed_at")
    list_filter = ("tenant_id",)
