from django import forms
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm

from apps.accounts.models import User


class PlatformAdminLoginForm(AdminAuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))
    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "invalid_login": "Enter the email and password of a platform admin account.",
    }


admin.site.login_form = PlatformAdminLoginForm
admin.site.site_header = "MartDesk platform admin"
admin.site.site_title = "MartDesk admin"

_FIELDS = (
    "full_name",
    "role",
    "email",
    "username",
    "tenant_id",
    "is_active",
    "is_platform_admin",
    "last_login",
    "last_active_at",
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Store staff are managed in the app, so they are view-only here. A platform
    admin's name and active flag can change; its password comes from the
    `create_platform_admin` command. Password and PIN hashes are never shown."""

    list_display = ("full_name", "role", "email", "tenant_id", "is_active", "is_platform_admin")
    list_filter = ("is_platform_admin", "role", "is_active", "tenant_id")
    search_fields = ("full_name", "email", "username")
    fields = _FIELDS

    def get_readonly_fields(self, request, obj=None) -> tuple[str, ...]:
        editable = {"full_name", "is_active"} if obj and obj.is_platform_admin else set()
        return tuple(field for field in _FIELDS if field not in editable)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return obj is None or obj.is_platform_admin

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
