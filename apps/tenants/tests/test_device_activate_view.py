from datetime import timedelta

import pytest
from django.core.cache import cache
from django.db import connections
from rest_framework.test import APIClient

from apps.audit.models import ActivityLog
from apps.tenants.domain.device_token import hash_device_token
from apps.tenants.models import Counter, Device, DeviceCode

from .helpers import authed_client, make_tenant

ACTIVATE_URL = "/api/v1/devices/activate"
BOTH_DATABASES = pytest.mark.django_db(databases=["default", "audit"])


@pytest.fixture(autouse=True)
def _reset_throttle_and_audit_connection():
    cache.clear()
    yield
    cache.clear()
    connections["audit"].close()


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def counter(tenant) -> Counter:
    return Counter.objects.create(tenant_id=tenant.id, name="Counter 3", code="003")


@pytest.fixture
def code(tenant, counter) -> str:
    client, _ = authed_client(tenant)
    return client.post("/api/v1/devices/codes", {"counter_id": counter.id}).json()["code"]


def _activate(code: str, client: APIClient | None = None):
    client = client or APIClient()
    return client.post(ACTIVATE_URL, {"code": code, "app_version": "1.0.0"})


def _failures(tenant_id: int, reason: str):
    rows = ActivityLog.objects.using("audit").filter(
        tenant_id=tenant_id, action="activation_failed"
    )
    return [row for row in rows if row.detail == {"reason": reason}]


@pytest.mark.django_db
def test_activation_returns_a_device_token_and_the_counter(tenant, counter, code):
    response = _activate(code)

    assert response.status_code == 200
    body = response.json()
    assert body["counter"] == {"id": counter.id, "name": "Counter 3", "code": "003"}
    device = Device.objects.get(counter=counter)
    assert device.token_hash == hash_device_token(body["device_token"])
    assert device.tenant_id == tenant.id
    assert device.app_version == "1.0.0"
    assert DeviceCode.objects.get(counter=counter).used_at is not None


@pytest.mark.django_db
def test_activation_is_logged_with_the_device(tenant, counter, code):
    _activate(code)

    entry = ActivityLog.objects.for_tenant(tenant.id).get(action="counter_activated")
    assert entry.entity_id == str(counter.id)
    assert entry.device_id == Device.objects.get(counter=counter).id


@pytest.mark.django_db
@pytest.mark.parametrize("typed", [str.lower, lambda c: c.replace("-", ""), lambda c: f" {c} "])
def test_case_hyphen_and_spaces_are_ignored(counter, code, typed):
    response = _activate(typed(code))

    assert response.status_code == 200


@pytest.mark.django_db
def test_an_owner_token_on_the_request_is_ignored(code):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

    response = _activate(code, client)

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("typed", ["K7M4-Q92R", "K7M4", "K7M0-Q92R"])
def test_unknown_or_malformed_code_is_invalid(typed):
    response = _activate(typed)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "code_invalid"


@pytest.mark.django_db
def test_code_is_required():
    response = APIClient().post(ACTIVATE_URL, {"app_version": "1.0.0"})

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["code"]


@BOTH_DATABASES
def test_expired_code_is_410_and_logged(tenant, counter, code):
    row = DeviceCode.objects.get(counter=counter)
    DeviceCode.objects.filter(id=row.id).update(expires_at=row.expires_at - timedelta(minutes=16))

    response = _activate(code)

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "code_expired"
    assert not Device.objects.exists()
    assert _failures(tenant.id, "code_expired")


@BOTH_DATABASES
def test_used_code_is_409_and_logged(tenant, code):
    _activate(code)
    Device.objects.update(revoked_at=DeviceCode.objects.get().used_at)

    response = _activate(code)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "code_used"
    assert _failures(tenant.id, "code_used")


@BOTH_DATABASES
def test_revoked_code_is_invalid(tenant, counter, code):
    client, _ = authed_client(tenant)
    client.delete(f"/api/v1/devices/codes/{counter.id}")

    response = _activate(code)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "code_invalid"
    assert _failures(tenant.id, "code_invalid")


@BOTH_DATABASES
def test_counter_that_gained_a_live_pc_is_409_counter_active(tenant, counter, code):
    Device.objects.create(tenant_id=tenant.id, counter=counter, token_hash="a" * 64)

    response = _activate(code)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "counter_active"
    assert DeviceCode.objects.get(counter=counter).used_at is None
    assert _failures(tenant.id, "counter_active")


@pytest.mark.django_db
def test_activation_is_rate_limited_per_ip_after_ten_attempts():
    for _ in range(10):
        assert _activate("K7M4-Q92R").status_code == 400

    throttled = _activate("K7M4-Q92R")

    assert throttled.status_code == 429
    body = throttled.json()
    assert body["error"]["code"] == "activation_throttled"
    assert 0 < body["retry_after"] <= 15 * 60
    assert _activate("K7M4-Q92R", APIClient(REMOTE_ADDR="10.0.0.9")).status_code == 400
