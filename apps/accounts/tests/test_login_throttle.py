import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tenants.models import Tenant

LOGIN_URL = "/api/v1/auth/login"


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_repeated_wrong_attempts_are_rate_limited_not_locked_out(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    owner = User(tenant_id=tenant.id, full_name="Sana Ahmed", role="owner", username="sana")
    owner.set_password("correct horse battery staple")
    owner.save()

    for _ in range(10):
        response = client.post(LOGIN_URL, {"login": "sana", "password": "wrong"})
        assert response.status_code == 401

    throttled = client.post(LOGIN_URL, {"login": "sana", "password": "wrong"})
    assert throttled.status_code == 429
    body = throttled.json()
    assert body["error"]["code"] == "login_throttled"
    assert body["retry_after"] > 0
    assert "Retry-After" in throttled.headers

    # The account itself is never locked: a different IP is unaffected...
    other_ip_client = APIClient(REMOTE_ADDR="10.0.0.9")
    still_available = other_ip_client.post(LOGIN_URL, {"login": "sana", "password": "wrong"})
    assert still_available.status_code == 401

    # ...and the correct password still works once the throttle window is
    # cleared, proving this is a delay, not an account lock.
    cache.clear()
    success = client.post(LOGIN_URL, {"login": "sana", "password": "correct horse battery staple"})
    assert success.status_code == 200


@pytest.mark.django_db
def test_different_logins_from_the_same_ip_are_throttled_independently(client):
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")
    for name, username in (("Sana Ahmed", "sana"), ("Other Owner", "other")):
        user = User(tenant_id=tenant.id, full_name=name, role="owner", username=username)
        user.set_password("correct horse battery staple")
        user.save()

    for _ in range(10):
        client.post(LOGIN_URL, {"login": "sana", "password": "wrong"})

    response = client.post(LOGIN_URL, {"login": "other", "password": "wrong"})
    assert response.status_code == 401
