from django.contrib import admin

from apps.core.read_only_admin import ReadOnlyAdmin
from apps.sales.models import Bill, BillItem, HeldBill, Payment, Return, ReturnItem


class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 0
    can_delete = False
    exclude = ("tenant_id",)

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


class PaymentInline(BillItemInline):
    model = Payment


class ReturnItemInline(BillItemInline):
    model = ReturnItem


@admin.register(Bill)
class BillAdmin(ReadOnlyAdmin):
    list_display = ("bill_no", "counter", "cashier", "total", "status", "flags", "sold_at")
    list_filter = ("tenant_id", "status")
    search_fields = ("bill_no",)
    inlines = (BillItemInline, PaymentInline)


@admin.register(HeldBill)
class HeldBillAdmin(ReadOnlyAdmin):
    list_display = ("title", "counter", "cashier", "status", "client_updated_at")
    list_filter = ("tenant_id", "status")


@admin.register(Return)
class ReturnAdmin(ReadOnlyAdmin):
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
