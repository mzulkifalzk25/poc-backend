from django.contrib import admin

from apps.reports.models import SalesDaily, SalesDailyCashier, SalesDailyProduct, SalesHourly


@admin.register(SalesHourly)
class SalesHourlyAdmin(admin.ModelAdmin):
    """Pre-summed by the rollup job; a manual edit is overwritten by its next pass."""

    list_display = ("tenant_id", "counter_id", "hour_start", "bills", "gross", "cash", "card")
    list_filter = ("tenant_id",)


@admin.register(SalesDaily)
class SalesDailyAdmin(admin.ModelAdmin):
    list_display = ("tenant_id", "local_date", "bills", "gross", "cash", "card", "refund_amount")
    list_filter = ("tenant_id",)


@admin.register(SalesDailyProduct)
class SalesDailyProductAdmin(admin.ModelAdmin):
    list_display = ("tenant_id", "local_date", "product_id", "qty", "revenue", "returns_qty")
    list_filter = ("tenant_id",)


@admin.register(SalesDailyCashier)
class SalesDailyCashierAdmin(admin.ModelAdmin):
    list_display = ("tenant_id", "local_date", "cashier_id", "bills", "revenue", "refund_amount")
    list_filter = ("tenant_id",)
