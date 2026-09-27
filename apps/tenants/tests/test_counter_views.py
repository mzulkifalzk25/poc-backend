import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.audit.models import ActivityLog
from apps.tenants.models import Counter, Tenant

COUNTERS_URL = "/api/v1/counters"


def _authed_client(tenant: Tenant, role: str = "owner") -> tuple[APIClient, User]:
    kwargs = {"username": f"user-{tenant.id}-{role}"} if role != "cashier" else {}
    user = User(tenant_id=tenant.id, full_name="Test User", role=role, **kwargs)
    if role != "cashier":
        user.set_password("password123")
    user.save()
    access = str(RefreshToken.for_user(user).access_token)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client, user


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")


@pytest.mark.django_db
def test_owner_can_create_a_counter(tenant):
    owner_client, owner = _authed_client(tenant)

    response = owner_client.post(COUNTERS_URL, {"name": "Counter 1", "code": "001"})

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "001"
    assert body["next_bill_no"] == "001000001"

    entry = ActivityLog.objects.for_tenant(tenant.id).get(action="counter_created")
    assert entry.user_id == owner.id


@pytest.mark.django_db
def test_duplicate_code_in_same_tenant_is_rejected(tenant):
    owner_client, _owner = _authed_client(tenant)
    owner_client.post(COUNTERS_URL, {"name": "Counter 1", "code": "001"})

    response = owner_client.post(COUNTERS_URL, {"name": "Counter 1 Again", "code": "001"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "code_exists"


@pytest.mark.django_db
def test_same_code_is_allowed_in_a_different_tenant():
    tenant_a = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    tenant_b = Tenant.objects.create(name="Other Mart", slug="other-mart")
    client_a, _ = _authed_client(tenant_a)
    client_b, _ = _authed_client(tenant_b)
    client_a.post(COUNTERS_URL, {"name": "Counter 1", "code": "001"})

    response = client_b.post(COUNTERS_URL, {"name": "Counter 1", "code": "001"})

    assert response.status_code == 201


@pytest.mark.django_db
def test_invalid_code_format_is_rejected(tenant):
    owner_client, _owner = _authed_client(tenant)

    response = owner_client.post(COUNTERS_URL, {"name": "Counter 1", "code": "12"})

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["code"]


@pytest.mark.django_db
def test_owner_only_lists_counters_for_their_own_tenant():
    tenant_a = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    tenant_b = Tenant.objects.create(name="Other Mart", slug="other-mart")
    client_a, _ = _authed_client(tenant_a)
    client_b, _ = _authed_client(tenant_b)
    client_a.post(COUNTERS_URL, {"name": "Counter A", "code": "001"})
    client_b.post(COUNTERS_URL, {"name": "Counter B", "code": "002"})

    response = client_a.get(COUNTERS_URL)

    names = [row["name"] for row in response.json()]
    assert names == ["Counter A"]


@pytest.mark.django_db
def test_owner_can_rename_a_counter(tenant):
    owner_client, owner = _authed_client(tenant)
    created = owner_client.post(COUNTERS_URL, {"name": "Counter 1", "code": "001"}).json()

    response = owner_client.patch(f"{COUNTERS_URL}/{created['id']}", {"name": "Front Counter"})

    assert response.status_code == 200
    assert response.json()["name"] == "Front Counter"
    entry = ActivityLog.objects.for_tenant(tenant.id).get(action="counter_updated")
    assert entry.user_id == owner.id


@pytest.mark.django_db
def test_code_can_change_before_the_first_bill(tenant):
    owner_client, _owner = _authed_client(tenant)
    created = owner_client.post(COUNTERS_URL, {"name": "Counter 1", "code": "001"}).json()

    response = owner_client.patch(f"{COUNTERS_URL}/{created['id']}", {"code": "002"})

    assert response.status_code == 200
    assert response.json()["code"] == "002"


@pytest.mark.django_db
def test_code_is_locked_once_the_counter_has_billed(tenant):
    owner_client, _owner = _authed_client(tenant)
    created = owner_client.post(COUNTERS_URL, {"name": "Counter 1", "code": "001"}).json()
    Counter.objects.filter(id=created["id"]).update(last_bill_seq=1)

    response = owner_client.patch(f"{COUNTERS_URL}/{created['id']}", {"code": "002"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "counter_code_locked"


@pytest.mark.django_db
def test_changing_code_to_one_already_in_use_is_rejected(tenant):
    owner_client, _owner = _authed_client(tenant)
    owner_client.post(COUNTERS_URL, {"name": "Counter 1", "code": "001"})
    counter_2 = owner_client.post(COUNTERS_URL, {"name": "Counter 2", "code": "002"}).json()

    response = owner_client.patch(f"{COUNTERS_URL}/{counter_2['id']}", {"code": "001"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "code_exists"


@pytest.mark.django_db
def test_cashier_is_forbidden(tenant):
    cashier_client, _cashier = _authed_client(tenant, role="cashier")

    response = cashier_client.get(COUNTERS_URL)

    assert response.status_code == 403


def test_unauthenticated_is_rejected():
    response = APIClient().get(COUNTERS_URL)

    assert response.status_code == 401
