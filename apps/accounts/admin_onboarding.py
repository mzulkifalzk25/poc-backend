import logging

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.password_validation import validate_password
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.text import slugify

from apps.accounts.domain.role_rules import MANAGER, OWNER
from apps.accounts.repositories.users import user_repository
from apps.accounts.use_cases.onboard_tenant import (
    NewTenant,
    OnboardedTenant,
    TenantSlugTakenError,
    onboard_tenant,
)
from apps.accounts.use_cases.send_owner_welcome import send_owner_welcome

logger = logging.getLogger(__name__)


class OnboardTenantForm(forms.Form):
    store_name = forms.CharField(max_length=255, label="Mart name")
    store_phone = forms.CharField(max_length=32, required=False, label="Mart phone")
    store_address = forms.CharField(max_length=255, required=False, label="Mart address")
    owner_first_name = forms.CharField(max_length=100, label="Owner first name")
    owner_last_name = forms.CharField(max_length=100, label="Owner last name")
    owner_email = forms.EmailField(label="Owner email")
    owner_phone = forms.CharField(max_length=32, required=False, label="Owner phone")
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave empty to generate one. It is emailed to the owner with the login link.",
    )

    def clean_store_name(self) -> str:
        name = self.cleaned_data["store_name"].strip()
        if not slugify(name):
            raise forms.ValidationError("Use letters or numbers in the mart name.")
        return name

    def clean_owner_email(self) -> str:
        email = self.cleaned_data["owner_email"].strip()
        if user_repository.login_candidates(email, [OWNER, MANAGER]):
            raise forms.ValidationError("An owner or manager already signs in with this email.")
        return email

    def clean_password(self) -> str:
        password = self.cleaned_data["password"]
        if password:
            validate_password(password)
        return password

    def to_new_tenant(self) -> NewTenant:
        data = self.cleaned_data
        return NewTenant(
            tenant_name=data["store_name"],
            tenant_slug=slugify(data["store_name"]),
            owner_first_name=data["owner_first_name"],
            owner_last_name=data["owner_last_name"],
            owner_email=data["owner_email"],
            tenant_phone=data["store_phone"],
            tenant_address=data["store_address"],
            owner_phone=data["owner_phone"],
            password=data["password"] or None,
        )


def onboard_tenant_view(request: HttpRequest, site: admin.AdminSite) -> HttpResponse:
    form = OnboardTenantForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            onboarded = onboard_tenant(form.to_new_tenant())
        except TenantSlugTakenError:
            form.add_error("store_name", "A mart with this name already exists.")
        else:
            _report(request, onboarded)
            return HttpResponseRedirect(reverse("admin:tenants_tenant_changelist"))
    context = {**site.each_context(request), "title": "Add mart and owner", "form": form}
    return TemplateResponse(request, "admin/onboard_tenant.html", context)


def _report(request: HttpRequest, onboarded: OnboardedTenant) -> None:
    name, email = onboarded.tenant.name, onboarded.owner.email
    try:
        send_owner_welcome(onboarded)
    except Exception:
        logger.exception("Welcome email to %s failed", email)
        messages.warning(
            request,
            f"{name} and its owner were created, but the email to {email} could not be sent. "
            f"Give the owner this password yourself, it is shown only now: {onboarded.password}",
        )
        return
    messages.success(request, f"{name} created. Login details were emailed to {email}.")
