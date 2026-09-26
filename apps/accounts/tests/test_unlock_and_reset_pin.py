from datetime import timedelta

import pytest
from django.contrib.auth.hashers import check_password, make_password
from django.db import connections
from django.utils import timezone

from apps.accounts.domain.pin import is_valid_pin, verifier_matches
from apps.accounts.models import PinDelay, User
from apps.audit.models import ActivityLog
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

USERS_URL = "/api/v1/users"
pytestmark = pytest.mark.django_db(databases=["default", "audit"])


@pytest.fixture(autouse=True)
def _close_audit_connection():
    yield
    connections["audit"].close()


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def counters(tenant) -> list[Counter]:
    return [
        Counter.objects.create(tenant_id=tenant.id, name=f"Counter {n}", code=f"00{n}")
        for n in (1, 2, 3)
    ]


@pytest.fixture
def owner_client(tenant):
    return authed_client(tenant)[0]


@pytest.fixture
def cashier(tenant) -> User:
    return User.objects.create(
        tenant_id=tenant.id, full_name="Zainab Khan", role="cashier", pin_hash=make_password("4821")
    )


def _delay(cashier: User, counter: Counter) -> PinDelay:
    return PinDelay.objects.create(
        tenant_id=cashier.tenant_id,
        counter_id=counter.id,
        user_id=cashier.id,
        fail_count=6,
        next_allowed_at=timezone.now() + timedelta(minutes=5),
    )


def _pin_login(client, user_id: int, pin: str):
    return client.post("/api/v1/auth/pin-login", {"user_id": user_id, "pin": pin}, format="json")


def test_unlock_clears_the_delay_on_every_counter(tenant, owner_client, counters, cashier):
    _delay(cashier, counters[0])
    before = User.objects.get(id=cashier.id).updated_at

    response = owner_client.post(f"{USERS_URL}/{cashier.id}/unlock")

    assert response.status_code == 204
    rows = PinDelay.objects.filter(user_id=cashier.id).order_by("counter_id")
    assert [row.counter_id for row in rows] == [counter.id for counter in counters]
    assert all(row.fail_count == 0 and row.next_allowed_at is None for row in rows)
    assert all(row.unlocked_at is not None for row in rows)
    assert User.objects.get(id=cashier.id).updated_at > before
    assert ActivityLog.objects.for_tenant(tenant.id).filter(action="pin_unlock").count() == 1


def test_unlocked_cashier_can_sign_in_at_once(owner_client, counters, cashier):
    _delay(cashier, counters[0])
    client = device_client(activated_device(counters[0])[1])
    assert _pin_login(client, cashier.id, "4821").status_code == 429

    owner_client.post(f"{USERS_URL}/{cashier.id}/unlock")

    assert _pin_login(client, cashier.id, "4821").status_code == 200


def test_unlock_reaches_the_counter_through_people_sync(owner_client, counters, cashier):
    client = device_client(activated_device(counters[1])[1])

    owner_client.post(f"{USERS_URL}/{cashier.id}/unlock")

    rows = client.get("/api/v1/pos/people/sync/").json()["roster"]
    assert rows[0]["unlocked_at"] is not None


def test_reset_pin_returns_a_new_pin_once_and_clears_delays(
    tenant, owner_client, counters, cashier
):
    _delay(cashier, counters[0])

    response = owner_client.post(f"{USERS_URL}/{cashier.id}/reset-pin")

    assert response.status_code == 200
    pin = response.json()["pin"]
    assert is_valid_pin(pin)
    cashier.refresh_from_db()
    assert check_password(pin, cashier.pin_hash)
    assert verifier_matches(pin, cashier.pin_verifier)
    assert PinDelay.objects.get(user_id=cashier.id, counter_id=counters[0].id).fail_count == 0
    entry = ActivityLog.objects.for_tenant(tenant.id).get(action="pin_reset")
    assert pin not in str(entry.after) and pin not in str(entry.detail)


@pytest.mark.parametrize("action", ["unlock", "reset-pin"])
def test_only_cashiers_have_a_pin(tenant, owner_client, action):
    manager = User.objects.create(
        tenant_id=tenant.id, full_name="Ali", role="manager", username="ali"
    )

    response = owner_client.post(f"{USERS_URL}/{manager.id}/{action}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_a_cashier"


@pytest.mark.parametrize("action", ["unlock", "reset-pin"])
def test_another_tenants_cashier_is_not_found(owner_client, action):
    theirs = User.objects.create(
        tenant_id=make_tenant("other-mart").id, full_name="Z", role="cashier", pin_hash="x"
    )

    response = owner_client.post(f"{USERS_URL}/{theirs.id}/{action}")

    assert response.status_code == 404
    assert User.objects.get(id=theirs.id).pin_hash == "x"


@pytest.mark.parametrize("action", ["unlock", "reset-pin"])
def test_cashiers_cannot_unlock_or_reset(tenant, cashier, action):
    client, _ = authed_client(tenant, role="cashier")

    assert client.post(f"{USERS_URL}/{cashier.id}/{action}").status_code == 403
