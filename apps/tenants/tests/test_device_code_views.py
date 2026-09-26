import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tenants.domain.activation_code import ALPHABET
from apps.tenants.models import Counter, Device, DeviceCode

from .helpers import authed_client, make_tenant

CODES_URL = "/api/v1/devices/codes"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def counter(tenant) -> Counter:
    return Counter.objects.create(tenant_id=tenant.id, name="Counter 3", code="003")


@pytest.mark.django_db
def test_owner_gets_a_formatted_code_that_expires_in_fifteen_minutes(tenant, counter):
    client, owner = authed_client(tenant)
    before = timezone.now()

    response = client.post(CODES_URL, {"counter_id": counter.id})

    assert response.status_code == 201
    code = response.json()["code"]
    assert len(code) == 9 and code[4] == "-"
    assert set(code.replace("-", "")) <= set(ALPHABET)
    row = DeviceCode.objects.get(counter=counter)
    assert row.created_by == owner.id
    assert 14 * 60 < (row.expires_at - before).total_seconds() <= 15 * 60 + 5


@pytest.mark.django_db
def test_only_the_hash_of_the_code_is_stored(tenant, counter):
    client, _ = authed_client(tenant)

    code = client.post(CODES_URL, {"counter_id": counter.id}).json()["code"]

    row = DeviceCode.objects.get(counter=counter)
    assert code.replace("-", "") not in row.code_hash
    assert code not in row.code_hash


@pytest.mark.django_db
def test_a_new_code_revokes_the_earlier_unused_code(tenant, counter):
    client, _ = authed_client(tenant)
    client.post(CODES_URL, {"counter_id": counter.id})

    client.post(CODES_URL, {"counter_id": counter.id})

    rows = DeviceCode.objects.filter(counter=counter).order_by("id")
    assert rows[0].revoked_at is not None
    assert rows[1].revoked_at is None


@pytest.mark.django_db
def test_no_code_while_the_counter_has_a_live_pc(tenant, counter):
    client, _ = authed_client(tenant)
    Device.objects.create(tenant_id=tenant.id, counter=counter, token_hash="a" * 64)

    response = client.post(CODES_URL, {"counter_id": counter.id})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "counter_active"


@pytest.mark.django_db
def test_a_revoked_pc_does_not_block_a_new_code(tenant, counter):
    client, _ = authed_client(tenant)
    Device.objects.create(
        tenant_id=tenant.id, counter=counter, token_hash="a" * 64, revoked_at=timezone.now()
    )

    response = client.post(CODES_URL, {"counter_id": counter.id})

    assert response.status_code == 201


@pytest.mark.django_db
def test_another_tenants_counter_is_not_found(counter):
    other_client, _ = authed_client(make_tenant("other-mart"))

    response = other_client.post(CODES_URL, {"counter_id": counter.id})

    assert response.status_code == 404
    assert not DeviceCode.objects.exists()


@pytest.mark.django_db
def test_counter_id_is_required(tenant):
    client, _ = authed_client(tenant)

    response = client.post(CODES_URL, {})

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["counter_id"]


@pytest.mark.django_db
def test_cashier_cannot_issue_codes(tenant, counter):
    client, _ = authed_client(tenant, role="cashier")

    response = client.post(CODES_URL, {"counter_id": counter.id})

    assert response.status_code == 403


def test_issuing_needs_a_signed_in_owner():
    response = APIClient().post(CODES_URL, {"counter_id": 1})

    assert response.status_code == 401


@pytest.mark.django_db
def test_owner_revokes_the_unused_code(tenant, counter):
    client, _ = authed_client(tenant)
    client.post(CODES_URL, {"counter_id": counter.id})

    response = client.delete(f"{CODES_URL}/{counter.id}")

    assert response.status_code == 204
    assert DeviceCode.objects.get(counter=counter).revoked_at is not None


@pytest.mark.django_db
def test_revoke_leaves_a_used_code_alone(tenant, counter):
    client, _ = authed_client(tenant)
    client.post(CODES_URL, {"counter_id": counter.id})
    DeviceCode.objects.filter(counter=counter).update(used_at=timezone.now())

    client.delete(f"{CODES_URL}/{counter.id}")

    assert DeviceCode.objects.get(counter=counter).revoked_at is None


@pytest.mark.django_db
def test_revoke_without_a_code_is_still_204(tenant, counter):
    client, _ = authed_client(tenant)

    response = client.delete(f"{CODES_URL}/{counter.id}")

    assert response.status_code == 204


@pytest.mark.django_db
def test_revoke_cannot_touch_another_tenants_counter(tenant, counter):
    client, _ = authed_client(tenant)
    client.post(CODES_URL, {"counter_id": counter.id})
    other_client, _ = authed_client(make_tenant("other-mart"))

    response = other_client.delete(f"{CODES_URL}/{counter.id}")

    assert response.status_code == 404
    assert DeviceCode.objects.get(counter=counter).revoked_at is None


@pytest.mark.django_db
def test_cashier_cannot_revoke_codes(tenant, counter):
    client, _ = authed_client(tenant, role="cashier")

    response = client.delete(f"{CODES_URL}/{counter.id}")

    assert response.status_code == 403
