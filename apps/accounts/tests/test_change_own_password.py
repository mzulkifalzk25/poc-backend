import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import ActivityLog
from apps.tenants.models import Tenant

URL = "/api/v1/me/change-password"
OLD = "correct horse battery staple"
NEW = "Green-Lantern-River-77"


def _signed_in(role: str, login: str) -> tuple[APIClient, User]:
    tenant = Tenant.objects.create(name="Mart", slug=f"mart-{login}")
    user = User(tenant_id=tenant.id, full_name="Sana Ahmed", role=role, username=login)
    user.set_password(OLD)
    user.save()
    client = APIClient()
    if role == "cashier":
        client.force_authenticate(user)
    else:
        tokens = client.post("/api/v1/auth/login", {"login": login, "password": OLD}).json()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client, user


@pytest.mark.django_db
def test_an_owner_changes_their_own_password_and_signs_in_with_it():
    client, user = _signed_in("owner", "sana")

    response = client.post(URL, {"current_password": OLD, "new_password": NEW})

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password(NEW)
    again = APIClient().post("/api/v1/auth/login", {"login": "sana", "password": NEW})
    assert again.status_code == 200
    assert ActivityLog.objects.filter(action="password_changed", user_id=user.id).exists()


@pytest.mark.django_db
def test_a_wrong_current_password_changes_nothing():
    client, user = _signed_in("owner", "sana")

    response = client.post(URL, {"current_password": "nope", "new_password": NEW})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_current_password"
    user.refresh_from_db()
    assert user.check_password(OLD)


@pytest.mark.django_db
def test_a_weak_new_password_is_refused():
    client, user = _signed_in("owner", "sana")

    response = client.post(URL, {"current_password": OLD, "new_password": "123"})

    assert response.status_code == 400
    assert "new_password" in response.json()["error"]["fields"]
    user.refresh_from_db()
    assert user.check_password(OLD)


@pytest.mark.django_db
def test_a_cashier_cannot_use_it():
    client, _user = _signed_in("cashier", "bilal")

    response = client.post(URL, {"current_password": OLD, "new_password": NEW})

    assert response.status_code == 403


@pytest.mark.django_db
def test_it_needs_a_signed_in_user():
    response = APIClient().post(URL, {"current_password": OLD, "new_password": NEW})

    assert response.status_code == 401
