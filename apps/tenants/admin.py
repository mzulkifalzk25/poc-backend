from django.contrib import admin

from apps.tenants.models import Counter, Device, DeviceCode, Tenant, TenantSettings


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "plan", "status", "timezone", "created_at")
    list_filter = ("status", "plan")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TenantSettings)
class TenantSettingsAdmin(admin.ModelAdmin):
    list_display = ("tenant", "store_name", "tax_rate", "receipt_paper_mm")


@admin.register(Counter)
class CounterAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "tenant_id", "is_active", "last_bill_seq")
    list_filter = ("tenant_id", "is_active")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    """`token_hash` is excluded: it is the raw credential the counter presents
    on every request, not a business field, so it is not shown or editable."""

    list_display = ("counter", "tenant_id", "app_version", "last_seen_at", "revoked_at")
    list_filter = ("tenant_id",)
    exclude = ("token_hash",)


@admin.register(DeviceCode)
class DeviceCodeAdmin(admin.ModelAdmin):
    """`code_hash` is excluded for the same reason as `Device.token_hash`."""

    list_display = ("counter", "tenant_id", "expires_at", "used_at", "revoked_at", "created_by")
    list_filter = ("tenant_id",)
    exclude = ("code_hash",)
