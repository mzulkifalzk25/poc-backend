import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.audit.models import ActivityLog
from apps.tenants.models import Tenant

SETTINGS_URL = "/api/v1/tenant/settings"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _authed_client(tenant: Tenant, role: str = "owner") -> tuple[APIClient, User]:
    kwargs = {"username": f"user-{tenant.id}"} if role != "cashier" else {"pin_hash": "x"}
    user = User(tenant_id=tenant.id, full_name="Test User", role=role, **kwargs)
    if role != "cashier":
        user.set_password("password123")
    user.save()
    access = str(RefreshToken.for_user(user).access_token)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client, user


@pytest.mark.django_db
def test_owner_can_read_settings_with_pkr_default(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    owner_client, _owner = _authed_client(tenant)

    response = owner_client.get(SETTINGS_URL)

    assert response.status_code == 200
    assert response.json()["currency"] == "PKR"


@pytest.mark.django_db
def test_owner_can_update_settings_and_it_is_logged(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    owner_client, owner = _authed_client(tenant)

    response = owner_client.patch(SETTINGS_URL, {"tax_rate": "5.00", "store_name": "FB Mart"})

    assert response.status_code == 200
    body = response.json()
    assert body["tax_rate"] == "5.00"
    assert body["store_name"] == "FB Mart"

    entry = ActivityLog.objects.for_tenant(tenant.id).get(action="settings_changed")
    assert entry.user_id == owner.id
    assert entry.after["tax_rate"] == "5.00"


@pytest.mark.django_db
def test_currency_cannot_be_changed(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    owner_client, _owner = _authed_client(tenant)

    response = owner_client.patch(SETTINGS_URL, {"currency": "USD"})

    assert response.status_code == 200
    assert response.json()["currency"] == "PKR"


@pytest.mark.django_db
def test_cashier_is_forbidden(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    cashier_client, _cashier = _authed_client(tenant, role="cashier")

    response = cashier_client.get(SETTINGS_URL)

    assert response.status_code == 403


@pytest.mark.django_db
def test_unauthenticated_is_rejected(client):
    response = client.get(SETTINGS_URL)

    assert response.status_code == 401


@pytest.mark.django_db
def test_each_tenant_only_sees_its_own_settings():
    tenant_a = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    tenant_b = Tenant.objects.create(name="Other Mart", slug="other-mart")
    client_a, _owner_a = _authed_client(tenant_a)
    client_b, _owner_b = _authed_client(tenant_b)

    client_a.patch(SETTINGS_URL, {"store_name": "Tenant A Store"})
    client_b.patch(SETTINGS_URL, {"store_name": "Tenant B Store"})

    response_a = client_a.get(SETTINGS_URL)
    response_b = client_b.get(SETTINGS_URL)

    assert response_a.json()["store_name"] == "Tenant A Store"
    assert response_b.json()["store_name"] == "Tenant B Store"


@pytest.mark.django_db
@pytest.mark.parametrize("rate", ["-1.00", "100.01", "150.00"])
def test_tax_rate_outside_zero_to_one_hundred_percent_is_rejected(rate):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    owner_client, _owner = _authed_client(tenant)

    response = owner_client.patch(SETTINGS_URL, {"tax_rate": rate})

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["tax_rate"]
    assert owner_client.get(SETTINGS_URL).json()["tax_rate"] == "0.00"


@pytest.mark.django_db
@pytest.mark.parametrize("rate", ["0.00", "17.00", "100.00"])
def test_tax_rate_edges_are_accepted(rate):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    owner_client, _owner = _authed_client(tenant)

    response = owner_client.patch(SETTINGS_URL, {"tax_rate": rate})

    assert response.status_code == 200
    assert response.json()["tax_rate"] == rate
