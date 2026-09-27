import pytest
from django.contrib import admin
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.use_cases.platform_admin import save_platform_admin

EMAIL = "admin@example.com"
PASSWORD = "Blue-Kettle-Morning-42"


@pytest.fixture
def platform_admin(db) -> User:
    save_platform_admin(EMAIL, PASSWORD)
    return User.objects.get(is_platform_admin=True)


@pytest.fixture
def signed_in(platform_admin) -> Client:
    client = Client()
    client.post(reverse("admin:login"), {"username": EMAIL, "password": PASSWORD})
    return client


def test_the_platform_admin_signs_in_with_email_and_password(platform_admin):
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
    assert "platform admin account" in response.content.decode()
    assert client.get(reverse("admin:index")).status_code == 302


def test_every_registered_model_lists_for_the_platform_admin(signed_in):
    for model in admin.site._registry:
        meta = model._meta
        url = reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")
        assert signed_in.get(url).status_code == 200, url


def test_the_activity_log_cannot_be_added_to(signed_in):
    assert signed_in.get(reverse("admin:audit_activitylog_add")).status_code == 403


def test_store_staff_are_view_only(signed_in):
    owner = User.objects.create(tenant_id=1, full_name="Sana Ahmed", role="owner")
    url = reverse("admin:accounts_user_change", args=[owner.id])

    response = signed_in.post(url, {"full_name": "Changed", "is_active": ""})

    assert response.status_code == 403
    owner.refresh_from_db()
    assert owner.full_name == "Sana Ahmed" and owner.is_active
