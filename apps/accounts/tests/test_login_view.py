import pytest
from django.db import connections
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tenants.models import Tenant

LOGIN_URL = "/api/v1/auth/login"


def _make_owner(tenant_id: int, username: str, password: str) -> User:
    user = User(tenant_id=tenant_id, full_name="Sana Ahmed", role="owner", username=username)
    user.set_password(password)
    user.save()
    return user


@pytest.fixture(autouse=True)
def _close_audit_connection():
    yield
    connections["audit"].close()


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db(databases=["default", "audit"])
def test_owner_can_log_in_with_username_and_password(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    _make_owner(tenant.id, "sana", "correct horse battery staple")

    response = client.post(LOGIN_URL, {"login": "sana", "password": "correct horse battery staple"})

    assert response.status_code == 200
    body = response.json()
    assert body["access"] and body["refresh"]
    assert body["user"]["role"] == "owner"
    assert body["tenant"]["slug"] == "fresh-basket-mart"
    assert body["landing"] == "admin"


@pytest.mark.django_db(databases=["default", "audit"])
def test_login_is_case_insensitive(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    _make_owner(tenant.id, "sana", "correct horse battery staple")

    response = client.post(LOGIN_URL, {"login": "SANA", "password": "correct horse battery staple"})

    assert response.status_code == 200


@pytest.mark.django_db(databases=["default", "audit"])
def test_wrong_password_returns_invalid_credentials(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    _make_owner(tenant.id, "sana", "correct horse battery staple")

    response = client.post(LOGIN_URL, {"login": "sana", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.django_db(databases=["default", "audit"])
def test_unknown_login_returns_invalid_credentials(client):
    response = client.post(LOGIN_URL, {"login": "nobody", "password": "whatever"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.django_db(databases=["default", "audit"])
def test_cashier_gets_the_same_invalid_credentials_error(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    User.objects.create(tenant_id=tenant.id, full_name="Zainab Khan", role="cashier", username=None)

    response = client.post(LOGIN_URL, {"login": "Zainab Khan", "password": "whatever"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.django_db(databases=["default", "audit"])
def test_deactivated_owner_cannot_log_in(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    owner = _make_owner(tenant.id, "sana", "correct horse battery staple")
    owner.is_active = False
    owner.save()

    response = client.post(LOGIN_URL, {"login": "sana", "password": "correct horse battery staple"})

    assert response.status_code == 401


@pytest.mark.django_db(databases=["default", "audit"])
def test_login_resolves_the_correct_tenant_when_usernames_differ(client):
    tenant_a = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    tenant_b = Tenant.objects.create(name="Other Mart", slug="other-mart")
    _make_owner(tenant_a.id, "owner-a", "password-a-123")
    _make_owner(tenant_b.id, "owner-b", "password-b-123")

    response = client.post(LOGIN_URL, {"login": "owner-b", "password": "password-b-123"})

    assert response.status_code == 200
    assert response.json()["tenant"]["slug"] == "other-mart"


@pytest.mark.django_db(databases=["default", "audit"])
def test_the_django_admin_cannot_log_in_to_the_store_app(client):
    admin = User(tenant_id=1, full_name="Django admin", role="owner", email="admin@example.com")
    admin.is_django_admin = True
    admin.set_password("correct horse battery staple")
    admin.save()

    response = client.post(
        LOGIN_URL, {"login": "admin@example.com", "password": "correct horse battery staple"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
