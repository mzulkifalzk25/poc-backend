from django.contrib import admin

from apps.catalog.models import Category, PriceHistory, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "tint", "tenant_id", "sort_order")
    list_filter = ("tenant_id",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "barcode", "category", "price", "cost", "tenant_id", "is_archived")
    list_filter = ("tenant_id", "is_archived", "unit")
    search_fields = ("name", "barcode")


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("product", "old_price", "new_price", "changed_by", "changed_at")
    list_filter = ("tenant_id",)
