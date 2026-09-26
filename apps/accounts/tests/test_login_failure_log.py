import pytest
from django.core.cache import cache
from django.db import connections
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import ActivityLog
from apps.tenants.tests.helpers import make_tenant

LOGIN_URL = "/api/v1/auth/login"
pytestmark = pytest.mark.django_db(databases=["default", "audit"])


@pytest.fixture(autouse=True)
def _reset():
    cache.clear()
    yield
    cache.clear()
    connections["audit"].close()


@pytest.fixture
def owner():
    user = User(tenant_id=make_tenant().id, full_name="Sana Ahmed", role="owner", username="sana")
    user.set_password("correct horse battery staple")
    user.save()
    return user


def _entries(action: str) -> list[ActivityLog]:
    return list(ActivityLog.objects.using("audit").filter(action=action))


def test_wrong_password_is_logged_against_the_account(owner):
    APIClient().post(LOGIN_URL, {"login": "SANA", "password": "wrong"})

    entry = _entries("login_failure")[0]
    assert entry.tenant_id == owner.tenant_id
    assert entry.user_id == owner.id
    assert entry.ip == "127.0.0.1"


def test_unknown_login_has_no_tenant_and_is_not_logged(owner):
    response = APIClient().post(LOGIN_URL, {"login": "nobody", "password": "wrong"})

    assert response.status_code == 401
    assert not _entries("login_failure")


def test_successful_login_is_not_a_failure(owner):
    APIClient().post(LOGIN_URL, {"login": "sana", "password": "correct horse battery staple"})

    assert not _entries("login_failure")


def test_throttled_login_is_logged(owner):
    client = APIClient()
    for _ in range(10):
        client.post(LOGIN_URL, {"login": "sana", "password": "wrong"})

    response = client.post(LOGIN_URL, {"login": "sana", "password": "wrong"})

    assert response.status_code == 429
    assert _entries("login_throttled")[0].user_id == owner.id
    assert len(_entries("login_failure")) == 10
