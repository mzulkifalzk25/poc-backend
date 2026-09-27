from django import forms
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm

from apps.accounts.models import User


class DjangoAdminLoginForm(AdminAuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))
    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "invalid_login": "Enter the email and password of the Django admin account.",
    }


admin.site.login_form = DjangoAdminLoginForm
admin.site.site_header = "MartDesk maintenance"
admin.site.site_title = "MartDesk admin"


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Full CRUD for every account (store owners, managers, cashiers and the
    Django admin itself). `password` is excluded: it is a hash, not a business
    field, and editing it directly here would not go through Django's hasher,
    so a new password is set with `manage.py create_store_owner`,
    `create_django_admin` or the store's own reset-password screen."""

    list_display = ("full_name", "role", "email", "tenant_id", "is_active", "is_django_admin")
    list_filter = ("is_django_admin", "role", "is_active", "tenant_id")
    search_fields = ("full_name", "email", "username")
    exclude = ("password",)
