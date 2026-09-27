from django.contrib import admin

from apps.sales.models import Bill, BillItem, HeldBill, Payment, Return, ReturnItem


class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 0
    exclude = ("tenant_id",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    exclude = ("tenant_id",)


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ("bill_no", "counter", "cashier", "total", "status", "flags", "sold_at")
    list_filter = ("tenant_id", "status")
    search_fields = ("bill_no",)
    inlines = (BillItemInline, PaymentInline)


@admin.register(BillItem)
class BillItemAdmin(admin.ModelAdmin):
    list_display = ("bill", "line_no", "product", "qty", "unit_price", "line_total")
    list_filter = ("tenant_id",)
    search_fields = ("name_snapshot", "barcode_snapshot")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("bill", "method", "amount", "tendered", "change_given")
    list_filter = ("tenant_id", "method")


@admin.register(HeldBill)
class HeldBillAdmin(admin.ModelAdmin):
    list_display = ("title", "counter", "cashier", "status", "client_updated_at")
    list_filter = ("tenant_id", "status")


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    exclude = ("tenant_id",)


@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_bill_no",
        "counter",
        "cashier",
        "refund_method",
        "refund_total",
        "flags",
        "returned_at",
    )
    list_filter = ("tenant_id", "refund_method", "reason")
    search_fields = ("original_bill_no",)
    inlines = (ReturnItemInline,)


@admin.register(ReturnItem)
class ReturnItemAdmin(admin.ModelAdmin):
    list_display = (
        "return_record",
        "product",
        "qty",
        "price_source",
        "unit_price",
        "refund_amount",
    )
    list_filter = ("tenant_id",)
