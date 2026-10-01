import logging

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.accounts.models import User
from apps.accounts.use_cases.reset_owner_password import (
    NotAStoreLoginError,
    reset_owner_password,
    send_password_reset_email,
    set_owner_password,
)

logger = logging.getLogger(__name__)


class SetPasswordForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput(render_value=False))
    password_again = forms.CharField(widget=forms.PasswordInput(render_value=False))
    email_owner = forms.BooleanField(
        required=False, label="Also email the new password and login link to the owner"
    )

    def __init__(self, *args, user: User, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self) -> dict:
        data = super().clean()
        password = data.get("password")
        if password and password != data.get("password_again"):
            self.add_error("password_again", "The passwords do not match.")
        elif password:
            try:
                validate_password(password, self.user)
            except forms.ValidationError as error:
                self.add_error("password", error)
        return data


class DjangoAdminLoginForm(AdminAuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))
    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "invalid_login": "Enter the email and password of the Django admin account.",
    }


admin.site.login_form = DjangoAdminLoginForm
admin.site.site_header = "MartDesk maintenance"
admin.site.site_title = "MartDesk admin"
admin.site.index_template = "admin/martdesk_index.html"


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
    actions = ["reset_password_and_email"]
    change_form_template = "admin/accounts/user/change_form.html"

    def get_urls(self) -> list:
        custom = path(
            "<int:user_id>/set-password/",
            self.admin_site.admin_view(self.set_password_view),
            name="accounts_user_set_password",
        )
        return [custom, *super().get_urls()]

    def set_password_view(self, request, user_id: int):
        user = self.get_object(request, str(user_id))
        if user is None:
            return HttpResponseRedirect(reverse("admin:accounts_user_changelist"))
        form = SetPasswordForm(request.POST or None, user=user)
        if request.method == "POST" and form.is_valid():
            return self._apply_password(request, user, form)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Set password for {user.full_name}",
            "form": form,
            "target": user,
        }
        return TemplateResponse(request, "admin/accounts/user/set_password.html", context)

    def _apply_password(self, request, user: User, form: SetPasswordForm):
        password = form.cleaned_data["password"]
        try:
            set_owner_password(user, password)
        except NotAStoreLoginError:
            self.message_user(
                request,
                f"{user.full_name}: only owners and managers with an email can be changed.",
                messages.ERROR,
            )
        else:
            self.message_user(request, f"Password of {user.full_name} changed.")
            if form.cleaned_data["email_owner"]:
                self._email(request, user, password)
        return HttpResponseRedirect(reverse("admin:accounts_user_changelist"))

    def _email(self, request, user: User, password: str) -> None:
        try:
            send_password_reset_email(user, password)
        except Exception:
            logger.exception("Password email to %s failed", user.email)
            self.message_user(request, "The email could not be sent.", messages.WARNING)
        else:
            self.message_user(request, f"Emailed to {user.email}.")

    @admin.action(description="Reset password and email it to the selected owners and managers")
    def reset_password_and_email(self, request, queryset) -> None:
        for user in queryset:
            try:
                password = reset_owner_password(user)
            except NotAStoreLoginError:
                self.message_user(
                    request,
                    f"{user.full_name}: only owners and managers with an email can be reset.",
                    messages.ERROR,
                )
                continue
            try:
                send_password_reset_email(user, password)
            except Exception:
                logger.exception("Password reset email to %s failed", user.email)
                self.message_user(
                    request,
                    f"{user.full_name}: password reset but the email could not be sent. "
                    f"Give them this password yourself, shown only now: {password}",
                    messages.WARNING,
                )
            else:
                self.message_user(
                    request, f"{user.full_name}: new password emailed to {user.email}."
                )
