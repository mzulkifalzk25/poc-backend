from django.contrib import admin

from apps.core.read_only_admin import ReadOnlyAdmin
from apps.shifts.models import Shift


@admin.register(Shift)
class ShiftAdmin(ReadOnlyAdmin):
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
