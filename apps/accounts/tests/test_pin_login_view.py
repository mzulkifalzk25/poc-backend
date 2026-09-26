from datetime import timedelta

import pytest
from django.contrib.auth.hashers import make_password
from django.db import connections
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import PinDelay, User
from apps.audit.models import ActivityLog
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import activated_device, device_client, make_tenant

PIN_LOGIN_URL = "/api/v1/auth/pin-login"
REFRESH_URL = "/api/v1/auth/refresh"
pytestmark = pytest.mark.django_db(databases=["default", "audit"])


@pytest.fixture(autouse=True)
def _close_audit_connection():
    yield
    connections["audit"].close()


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
def client(device) -> APIClient:
    return device_client(device[1])


@pytest.fixture
def cashier(tenant) -> User:
    return _make_cashier(tenant.id)


def _make_cashier(tenant_id: int, name: str = "Zainab Khan", **extra) -> User:
    return User.objects.create(
        tenant_id=tenant_id, full_name=name, role="cashier", pin_hash=make_password("4821"), **extra
    )


def _login(client: APIClient, user_id: int, pin: str):
    return client.post(PIN_LOGIN_URL, {"user_id": user_id, "pin": pin}, format="json")


def _logged(tenant_id: int, action: str) -> list[ActivityLog]:
    return list(ActivityLog.objects.using("audit").filter(tenant_id=tenant_id, action=action))


def test_right_pin_signs_in_bound_to_this_pc(client, device, cashier):
    response = _login(client, cashier.id, "4821")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == cashier.id
    access = AccessToken(body["access"])
    refresh = RefreshToken(body["refresh"])
    assert access["device_id"] == device[0].id
    assert refresh["device_id"] == device[0].id
    refresh_days = (refresh["exp"] - refresh["iat"]) / 86400
    assert 29.9 < refresh_days <= 30
    assert (access["exp"] - access["iat"]) <= 15 * 60
    cashier.refresh_from_db()
    assert cashier.last_active_at is not None


def test_signed_in_cashier_token_works_on_normal_endpoints(client, cashier):
    access = _login(client, cashier.id, "4821").json()["access"]
    signed_in = APIClient()
    signed_in.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    assert signed_in.get("/api/v1/me").status_code == 200


def test_wrong_pin_is_401_and_logged_outside_the_transaction(tenant, client, cashier, device):
    response = _login(client, cashier.id, "0000")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_pin"
    entry = _logged(tenant.id, "pin_failure")[0]
    assert entry.user_id == cashier.id
    assert entry.device_id == device[0].id


def test_three_wrong_pins_are_free_then_a_30_second_delay(tenant, client, cashier):
    for _ in range(3):
        response = _login(client, cashier.id, "0000")
        assert response.status_code == 401
        assert "retry_after" not in response.json()

    fourth = _login(client, cashier.id, "0000")
    during = _login(client, cashier.id, "4821")

    assert fourth.status_code == 401
    assert fourth.json()["retry_after"] == 30
    assert during.status_code == 429
    assert during.json()["error"]["code"] == "pin_throttled"
    assert 0 < during.json()["retry_after"] <= 30
    assert during.headers["Retry-After"]
    assert _logged(tenant.id, "pin_throttled")


def test_next_delays_are_one_then_five_minutes(tenant, counter, client, cashier):
    retry_afters = []
    for _ in range(7):
        response = _login(client, cashier.id, "0000")
        retry_afters.append(response.json().get("retry_after"))
        PinDelay.objects.filter(user_id=cashier.id).update(next_allowed_at=None)

    assert retry_afters == [None, None, None, 30, 60, 300, 300]


def test_right_pin_after_the_delay_works_and_resets_the_count(client, cashier):
    for _ in range(4):
        _login(client, cashier.id, "0000")
    PinDelay.objects.update(next_allowed_at=timezone.now() - timedelta(seconds=1))

    response = _login(client, cashier.id, "4821")

    assert response.status_code == 200
    row = PinDelay.objects.get(user_id=cashier.id)
    assert row.fail_count == 0
    assert row.next_allowed_at is None


def test_delay_applies_to_this_counter_only(tenant, client, cashier):
    for _ in range(4):
        _login(client, cashier.id, "0000")
    other_counter = Counter.objects.create(tenant_id=tenant.id, name="Counter 1", code="001")
    other_client = device_client(activated_device(other_counter)[1])

    assert _login(client, cashier.id, "4821").status_code == 429
    assert _login(other_client, cashier.id, "4821").status_code == 200


def test_delay_applies_to_this_cashier_only(tenant, client, cashier):
    bilal = _make_cashier(tenant.id, "Bilal Raza")
    for _ in range(4):
        _login(client, cashier.id, "0000")

    assert _login(client, bilal.id, "4821").status_code == 200


def test_owner_account_never_uses_pin_sign_in(tenant, client):
    owner = User.objects.create(
        tenant_id=tenant.id,
        full_name="Sana",
        role="owner",
        username="sana",
        pin_hash=make_password("4821"),
    )

    for _ in range(5):
        assert _login(client, owner.id, "4821").status_code == 401
    assert not PinDelay.objects.filter(user_id=owner.id).exists()


def test_deactivated_cashier_cannot_sign_in(tenant, client):
    usman = _make_cashier(tenant.id, "Usman Tariq", is_active=False)

    assert _login(client, usman.id, "4821").status_code == 401


def test_another_tenants_cashier_cannot_sign_in_here(client):
    theirs = _make_cashier(make_tenant("other-mart").id)

    response = _login(client, theirs.id, "4821")

    assert response.status_code == 401
    assert not PinDelay.objects.exists()


def test_pin_login_needs_an_activated_pc(cashier):
    assert _login(APIClient(), cashier.id, "4821").status_code == 401


def test_a_deactivated_pc_gets_device_revoked(client, device, cashier):
    device[0].revoked_at = timezone.now()
    device[0].save()

    response = _login(client, cashier.id, "4821")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "device_revoked"


def test_missing_fields_are_400(client):
    response = client.post(PIN_LOGIN_URL, {}, format="json")

    assert response.status_code == 400
    assert set(response.json()["error"]["fields"]) == {"user_id", "pin"}


def test_counter_refresh_slides_30_days_and_keeps_the_pc(client, device, cashier):
    refresh = _login(client, cashier.id, "4821").json()["refresh"]

    response = APIClient().post(REFRESH_URL, {"refresh": refresh}, format="json")

    assert response.status_code == 200
    rotated = RefreshToken(response.json()["refresh"])
    assert rotated["device_id"] == device[0].id
    assert 29.9 < (rotated["exp"] - rotated["iat"]) / 86400 <= 30


def test_refresh_is_refused_once_the_pc_is_deactivated(client, device, cashier):
    refresh = _login(client, cashier.id, "4821").json()["refresh"]
    device[0].revoked_at = timezone.now()
    device[0].save()

    response = APIClient().post(REFRESH_URL, {"refresh": refresh}, format="json")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "device_revoked"
