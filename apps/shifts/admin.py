from django.contrib import admin

from apps.shifts.models import Shift


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = (
        "counter",
        "cashier",
        "status",
        "opened_at",
        "closed_at",
        "expected_cash",
        "difference",
    )
    list_filter = ("tenant_id", "status")
