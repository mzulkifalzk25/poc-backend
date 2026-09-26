from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.api.tokens import issue_counter_tokens
from apps.accounts.models import PinDelay, User
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

ROSTER_URL = "/api/v1/pos/roster"
SYNC_URL = "/api/v1/pos/people/sync/"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def counter(tenant) -> Counter:
    return Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")


@pytest.fixture
def device(counter):
    return activated_device(counter)


@pytest.fixture
def client(device):
    return device_client(device[1])


def _cashier(tenant_id: int, name: str, **extra) -> User:
    return User.objects.create(
        tenant_id=tenant_id,
        full_name=name,
        role="cashier",
        pin_hash="x",
        pin_verifier=f"pbkdf2_sha256$1000$salt${name}",
        **extra,
    )


@pytest.fixture
def staff(tenant):
    other_counter = Counter.objects.create(tenant_id=tenant.id, name="Counter 1", code="001")
    return {
        "zainab": _cashier(tenant.id, "Zainab Khan"),
        "bilal": _cashier(tenant.id, "Bilal Raza", default_counter_id=other_counter.id),
        "usman": _cashier(tenant.id, "Usman Tariq", is_active=False),
        "owner": User.objects.create(
            tenant_id=tenant.id, full_name="Sana Ahmed", role="owner", username="sana"
        ),
        "foreign": _cashier(make_tenant("other-mart").id, "Other Cashier"),
    }


@pytest.mark.django_db
def test_roster_lists_every_active_cashier_of_the_tenant(client, staff):
    response = client.get(ROSTER_URL)

    assert response.status_code == 200
    assert response.json() == [
        {"id": staff["bilal"].id, "full_name": "Bilal Raza", "initials": "BR"},
        {"id": staff["zainab"].id, "full_name": "Zainab Khan", "initials": "ZK"},
    ]


@pytest.mark.django_db
def test_roster_needs_an_activated_pc(tenant, staff):
    owner_client, _ = authed_client(tenant)

    assert APIClient().get(ROSTER_URL).status_code == 401
    assert owner_client.get(ROSTER_URL).status_code in (401, 403)


@pytest.mark.django_db
def test_roster_refuses_a_deactivated_pc(client, device):
    device[0].revoked_at = timezone.now()
    device[0].save()

    response = client.get(ROSTER_URL)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "device_revoked"


@pytest.mark.django_db
def test_full_sync_sends_active_cashiers_with_verifiers(client, staff):
    response = client.get(SYNC_URL)

    assert response.status_code == 200
    body = response.json()
    by_name = {row["full_name"]: row for row in body["roster"]}
    assert set(by_name) == {"Zainab Khan", "Bilal Raza"}
    assert by_name["Zainab Khan"]["pin_verifier"] == "pbkdf2_sha256$1000$salt$Zainab Khan"
    assert by_name["Zainab Khan"]["active"] is True
    assert by_name["Zainab Khan"]["unlocked_at"] is None
    assert body["next_since"]


@pytest.mark.django_db
def test_since_zero_is_a_full_sync(client, staff):
    assert len(client.get(SYNC_URL, {"since": "0"}).json()["roster"]) == 2


@pytest.mark.django_db
def test_delta_sends_changes_including_deactivation(client, staff):
    User.objects.update(updated_at=timezone.now() - timedelta(minutes=5))
    next_since = client.get(SYNC_URL).json()["next_since"]
    bilal = staff["bilal"]
    bilal.is_active = False
    bilal.save()

    rows = client.get(SYNC_URL, {"since": next_since}).json()["roster"]

    assert [row["full_name"] for row in rows] == ["Bilal Raza"]
    assert rows[0]["active"] is False
    assert rows[0]["pin_verifier"] is None


@pytest.mark.django_db
def test_unlocked_at_is_for_this_counter(tenant, counter, client, staff):
    unlocked = timezone.now()
    PinDelay.objects.create(
        tenant_id=tenant.id,
        counter_id=counter.id,
        user_id=staff["zainab"].id,
        unlocked_at=unlocked,
    )
    PinDelay.objects.create(
        tenant_id=tenant.id,
        counter_id=counter.id + 1000,
        user_id=staff["bilal"].id,
        unlocked_at=unlocked,
    )

    by_name = {row["full_name"]: row for row in client.get(SYNC_URL).json()["roster"]}

    assert by_name["Zainab Khan"]["unlocked_at"] is not None
    assert by_name["Bilal Raza"]["unlocked_at"] is None


@pytest.mark.django_db
def test_signed_in_cashier_can_sync_for_their_pc(device, staff):
    access = issue_counter_tokens(staff["zainab"], device[0].id).access_token
    cashier = APIClient()
    cashier.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = cashier.get(SYNC_URL)

    assert response.status_code == 200
    assert len(response.json()["roster"]) == 2


@pytest.mark.django_db
def test_owner_token_is_not_a_counter(tenant, staff):
    owner_client, _ = authed_client(tenant)

    assert owner_client.get(SYNC_URL).status_code == 403


@pytest.mark.django_db
def test_bad_since_is_400(client):
    response = client.get(SYNC_URL, {"since": "yesterday"})

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["since"]
