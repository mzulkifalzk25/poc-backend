import pytest
from django.contrib import admin
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.use_cases.django_admin import save_django_admin
from apps.sales.tests.factories import make_return
from apps.tenants.models import Counter, Tenant

EMAIL = "admin@example.com"
PASSWORD = "Blue-Kettle-Morning-42"


@pytest.fixture(autouse=True)
def _admin_email(settings):
    settings.DJANGO_ADMIN_EMAIL = EMAIL


@pytest.fixture
def django_admin(db) -> User:
    save_django_admin(EMAIL, PASSWORD)
    return User.objects.get(is_django_admin=True)


@pytest.fixture
def signed_in(django_admin) -> Client:
    client = Client()
    client.post(reverse("admin:login"), {"username": EMAIL, "password": PASSWORD})
    return client


def test_the_django_admin_signs_in_with_email_and_password(django_admin):
    client = Client()

    response = client.post(reverse("admin:login"), {"username": EMAIL, "password": PASSWORD})

    assert response.status_code == 302
    assert client.get(reverse("admin:index")).status_code == 200


@pytest.mark.django_db
def test_a_store_owner_with_the_right_password_is_refused():
    owner = User(tenant_id=1, full_name="Sana Ahmed", role="owner", email="sana@example.com")
    owner.set_password(PASSWORD)
    owner.save()
    client = Client()

    response = client.post(
        reverse("admin:login"), {"username": "sana@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert "Django admin account" in response.content.decode()
    assert client.get(reverse("admin:index")).status_code == 302


def test_every_registered_model_lists_for_the_django_admin(signed_in):
    for model in admin.site._registry:
        meta = model._meta
        url = reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")
        assert signed_in.get(url).status_code == 200, url


def test_the_activity_log_cannot_be_added_to(signed_in):
    assert signed_in.get(reverse("admin:audit_activitylog_add")).status_code == 403


def test_store_staff_are_fully_editable(signed_in):
    owner = User.objects.create(tenant_id=1, full_name="Sana Ahmed", role="owner")
    url = reverse("admin:accounts_user_change", args=[owner.id])

    response = signed_in.post(url, {"full_name": "Changed", "role": "owner", "tenant_id": 1})

    assert response.status_code == 302
    owner.refresh_from_db()
    assert owner.full_name == "Changed"


def test_returns_have_full_crud(signed_in):
    counter = Counter.objects.create(tenant_id=1, name="Counter 2", code="002")
    cashier = User.objects.create(tenant_id=1, full_name="Zainab Khan", role="cashier")
    ret = make_return(counter, cashier)

    assert signed_in.get(reverse("admin:sales_return_add")).status_code == 200
    assert signed_in.get(reverse("admin:sales_return_change", args=[ret.id])).status_code == 200
    assert signed_in.post(reverse("admin:sales_return_delete", args=[ret.id]), {"post": "yes"})[
        "Location"
    ] == reverse("admin:sales_return_changelist")


def test_every_other_model_can_be_added(signed_in):
    from apps.audit.models import ActivityLog

    for model in admin.site._registry:
        meta = model._meta
        # ActivityLog stays append-only; token_blacklist is a third-party app
        # whose own admin already refuses manual adds, not ours to change.
        # Tenant's add opens the onboarding page (mart and owner together).
        if model in (ActivityLog, Tenant) or meta.app_label == "token_blacklist":
            continue
        url = reverse(f"admin:{meta.app_label}_{meta.model_name}_add")
        assert signed_in.get(url).status_code == 200, url


def test_the_django_admin_changes_their_own_password(signed_in):
    new = "Green-Lantern-River-77"

    response = signed_in.post(
        reverse("admin:password_change"),
        {"old_password": PASSWORD, "new_password1": new, "new_password2": new},
    )

    assert response.status_code == 302
    assert User.objects.get(is_django_admin=True).check_password(new)
    again = Client()
    again.post(reverse("admin:login"), {"username": EMAIL, "password": new})
    assert again.get(reverse("admin:index")).status_code == 200
