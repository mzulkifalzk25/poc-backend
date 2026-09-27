from django.contrib import admin

from apps.core.read_only_admin import ReadOnlyAdmin
from apps.tenants.models import Counter, Device, Tenant, TenantSettings


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """The platform-level record: name, plan, status and time zone can change here."""

    list_display = ("name", "slug", "plan", "status", "timezone", "created_at")
    list_filter = ("status", "plan")
    search_fields = ("name", "slug")
    readonly_fields = ("slug", "created_at", "updated_at")

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(TenantSettings)
class TenantSettingsAdmin(ReadOnlyAdmin):
    list_display = ("tenant", "store_name", "tax_rate", "receipt_paper_mm")


@admin.register(Counter)
class CounterAdmin(ReadOnlyAdmin):
    list_display = ("name", "code", "tenant_id", "is_active", "last_bill_seq")
    list_filter = ("tenant_id", "is_active")


@admin.register(Device)
class DeviceAdmin(ReadOnlyAdmin):
    list_display = ("counter", "tenant_id", "app_version", "last_seen_at", "revoked_at")
    list_filter = ("tenant_id",)
    exclude = ("token_hash",)
