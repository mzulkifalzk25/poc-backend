import pytest
from django.core.cache import cache
from django.db import connections
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import ActivityLog
from apps.tenants.models import Counter, Tenant
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

LOGIN_URL = "/api/v1/auth/cashier-login"
pytestmark = pytest.mark.django_db(databases=["default", "audit"])


@pytest.fixture(autouse=True)
def _reset():
    cache.clear()
    yield
    cache.clear()
    connections["audit"].close()


def _make_cashier(
    tenant: Tenant, email: str = "zainab@example.com", password: str = "pw-482134"
) -> User:
    user = User(tenant_id=tenant.id, full_name="Zainab Khan", role="cashier", email=email)
    user.set_password(password)
    user.save()
    return user


@pytest.fixture
def tenant() -> Tenant:
    return make_tenant()


@pytest.fixture
def counter(tenant) -> Counter:
    return Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")


@pytest.fixture
def device(counter):
    return activated_device(counter)


@pytest.fixture
def pc(device) -> APIClient:
    return device_client(device[1])


def test_a_cashier_signs_in_with_email_and_password(tenant, counter, pc):
    _make_cashier(tenant)

    response = pc.post(LOGIN_URL, {"login": "zainab@example.com", "password": "pw-482134"})

    assert response.status_code == 200
    body = response.json()
    assert body["access"] and body["refresh"]
    assert body["user"] == {
        "id": User.objects.get(email="zainab@example.com").id,
        "full_name": "Zainab Khan",
        "role": "cashier",
        "email": "zainab@example.com",
        "username": None,
    }


def test_login_is_case_insensitive(tenant, pc):
    _make_cashier(tenant)

    response = pc.post(LOGIN_URL, {"login": "ZAINAB@example.com", "password": "pw-482134"})

    assert response.status_code == 200


def test_wrong_password_is_invalid_credentials(tenant, pc):
    _make_cashier(tenant)

    response = pc.post(LOGIN_URL, {"login": "zainab@example.com", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_an_owner_account_cannot_sign_in_here(tenant, pc):
    owner = User(tenant_id=tenant.id, full_name="Sana Ahmed", role="owner", username="sana")
    owner.set_password("pw-482134")
    owner.save()

    response = pc.post(LOGIN_URL, {"login": "sana", "password": "pw-482134"})

    assert response.status_code == 401


def test_a_deactivated_cashier_cannot_sign_in(tenant, pc):
    cashier = _make_cashier(tenant)
    cashier.is_active = False
    cashier.save()

    response = pc.post(LOGIN_URL, {"login": "zainab@example.com", "password": "pw-482134"})

    assert response.status_code == 401


def test_the_token_is_bound_to_the_device(tenant, counter, device, pc):
    _make_cashier(tenant)
    access = pc.post(LOGIN_URL, {"login": "zainab@example.com", "password": "pw-482134"}).json()[
        "access"
    ]
    till = APIClient()
    till.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    assert till.get("/api/v1/counters").status_code == 403  # a cashier, not an owner
    assert till.get("/api/v1/bills/lookup?bill_no=001000001").status_code == 404  # counter-bound


def test_a_request_without_a_device_token_is_refused(tenant):
    _make_cashier(tenant)

    response = APIClient().post(LOGIN_URL, {"login": "zainab@example.com", "password": "pw-482134"})

    assert response.status_code == 401


def test_an_owner_token_cannot_call_the_cashier_login_endpoint(tenant, pc):
    owner_client, _ = authed_client(tenant)

    response = owner_client.post(LOGIN_URL, {"login": "x", "password": "y"})

    assert response.status_code == 401


def test_another_tenants_cashier_gets_a_token_this_counter_refuses(tenant, pc):
    """Login matches by email across every tenant, same limitation as the
    owner's `/auth/login` (no tenant context exists yet at that point); the
    device-bound counter context then refuses the mismatched tenant."""
    other = make_tenant("other-mart")
    _make_cashier(other)

    login = pc.post(LOGIN_URL, {"login": "zainab@example.com", "password": "pw-482134"})
    assert login.status_code == 200
    till = APIClient()
    till.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")

    assert till.get("/api/v1/bills/lookup?bill_no=001000001").status_code == 401


def test_wrong_password_is_logged_against_the_account(tenant, pc):
    cashier = _make_cashier(tenant)

    pc.post(LOGIN_URL, {"login": "ZAINAB@example.com", "password": "wrong"})

    entry = ActivityLog.objects.using("audit").get(action="login_failure")
    assert (entry.tenant_id, entry.user_id) == (tenant.id, cashier.id)


def test_repeated_wrong_attempts_are_throttled_not_locked_out(tenant, pc):
    _make_cashier(tenant)

    for _ in range(10):
        assert (
            pc.post(LOGIN_URL, {"login": "zainab@example.com", "password": "wrong"}).status_code
            == 401
        )

    throttled = pc.post(LOGIN_URL, {"login": "zainab@example.com", "password": "wrong"})

    assert throttled.status_code == 429
    assert throttled.json()["error"]["code"] == "login_throttled"
    assert throttled["Retry-After"]
    assert ActivityLog.objects.using("audit").filter(action="login_throttled").count() == 1
