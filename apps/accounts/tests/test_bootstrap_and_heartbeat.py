import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.api.tokens import issue_counter_tokens
from apps.accounts.models import User
from apps.tenants.models import Counter, Device, TenantSettings
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

BOOTSTRAP_URL = "/api/v1/pos/bootstrap"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def counter(tenant) -> Counter:
    return Counter.objects.create(
        tenant_id=tenant.id, name="Counter 2", code="002", last_bill_seq=742
    )


@pytest.fixture
def device(counter):
    return activated_device(counter)


@pytest.fixture
def client(device):
    return device_client(device[1])


@pytest.fixture
def cashier(tenant) -> User:
    return User.objects.create(
        tenant_id=tenant.id, full_name="Zainab Khan", role="cashier", pin_hash="x"
    )


def _cashier_client(cashier: User, device: Device) -> APIClient:
    client = APIClient()
    access = issue_counter_tokens(cashier, device.id).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _heartbeat_url(counter: Counter) -> str:
    return f"/api/v1/counters/{counter.id}/heartbeat"


@pytest.mark.django_db
def test_bootstrap_gives_the_counter_settings_sequence_and_roster(tenant, client, cashier):
    TenantSettings.objects.create(tenant=tenant, tax_rate="17.00", prices_include_tax=True)
    User.objects.create(
        tenant_id=make_tenant("other-mart").id, full_name="Other", role="cashier", pin_hash="x"
    )

    response = client.get(BOOTSTRAP_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["counter"]["code"] == "002"
    assert body["last_bill_seq"] == 742
    assert body["settings"]["tax_rate"] == "17.00"
    assert body["settings"]["prices_include_tax"] is True
    assert body["settings"]["block_when_out_of_stock"] is False
    assert body["settings"]["receipt_paper_mm"] == 80
    assert body["roster"] == [{"id": cashier.id, "full_name": "Zainab Khan", "initials": "ZK"}]
    assert body["server_time"]


@pytest.mark.django_db
def test_signed_in_cashier_gets_the_same_bootstrap(counter, device, cashier):
    response = _cashier_client(cashier, device[0]).get(BOOTSTRAP_URL)

    assert response.status_code == 200
    assert response.json()["counter"]["id"] == counter.id


@pytest.mark.django_db
def test_bootstrap_refuses_non_counters(tenant, device):
    owner_client, _ = authed_client(tenant)

    assert APIClient().get(BOOTSTRAP_URL).status_code == 401
    assert owner_client.get(BOOTSTRAP_URL).status_code == 403


@pytest.mark.django_db
def test_bootstrap_refuses_a_deactivated_pc(client, device):
    Device.objects.filter(id=device[0].id).update(revoked_at=timezone.now())

    response = client.get(BOOTSTRAP_URL)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "device_revoked"


@pytest.mark.django_db
def test_heartbeat_records_last_seen_backlog_and_version(tenant, counter, client, device):
    response = client.post(
        _heartbeat_url(counter), {"unsynced_count": 7, "app_version": "1.3.0"}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["server_time"]
    row = Device.objects.get(id=device[0].id)
    assert row.unsynced_count == 7
    assert row.app_version == "1.3.0"
    assert row.last_seen_at is not None
    owner_client, _ = authed_client(tenant)
    counters = owner_client.get("/api/v1/counters").json()
    assert counters[0]["unsynced_count"] == 7


@pytest.mark.django_db
def test_heartbeat_marks_the_cashier_active_without_a_people_resync(counter, client, cashier):
    before = cashier.updated_at

    client.post(
        _heartbeat_url(counter), {"unsynced_count": 0, "cashier_id": cashier.id}, format="json"
    )

    cashier.refresh_from_db()
    assert cashier.last_active_at is not None
    assert cashier.updated_at == before


@pytest.mark.django_db
def test_signed_in_cashier_heartbeat_uses_the_token_cashier(counter, device, cashier):
    client = _cashier_client(cashier, device[0])

    response = client.post(_heartbeat_url(counter), {"unsynced_count": 0}, format="json")

    assert response.status_code == 200
    cashier.refresh_from_db()
    assert cashier.last_active_at is not None


@pytest.mark.django_db
def test_heartbeat_for_another_counter_is_404(tenant, client):
    other = Counter.objects.create(tenant_id=tenant.id, name="Counter 1", code="001")

    response = client.post(_heartbeat_url(other), {"unsynced_count": 0}, format="json")

    assert response.status_code == 404


@pytest.mark.django_db
def test_heartbeat_rejects_another_tenants_cashier(counter, client):
    theirs = User.objects.create(
        tenant_id=make_tenant("other-mart").id, full_name="Z", role="cashier", pin_hash="x"
    )

    response = client.post(
        _heartbeat_url(counter), {"unsynced_count": 0, "cashier_id": theirs.id}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["cashier_id"]
    theirs.refresh_from_db()
    assert theirs.last_active_at is None


@pytest.mark.django_db
def test_heartbeat_validates_the_backlog(counter, client):
    response = client.post(_heartbeat_url(counter), {"unsynced_count": -1}, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["unsynced_count"]
