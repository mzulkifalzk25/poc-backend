import pytest

from apps.accounts.models import User
from apps.audit.models import ActivityLog
from apps.tenants.tests.helpers import authed_client, make_tenant

USERS_URL = "/api/v1/users"


def _reset_url(user_id: int) -> str:
    return f"{USERS_URL}/{user_id}/reset-password"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner(tenant):
    return authed_client(tenant)


@pytest.fixture
def owner_client(owner):
    return owner[0]


@pytest.fixture
def cashier(tenant) -> User:
    user = User(tenant_id=tenant.id, full_name="Zainab Khan", role="cashier", email="z@example.com")
    user.set_password("old-password")
    user.save()
    return user


@pytest.mark.django_db
def test_owner_resets_a_staff_password(tenant, owner, cashier):
    client, owner_user = owner

    response = client.post(_reset_url(cashier.id))

    assert response.status_code == 200
    new_password = response.json()["password"]
    assert new_password != "old-password"
    cashier.refresh_from_db()
    assert cashier.check_password(new_password)
    assert not cashier.check_password("old-password")
    entry = ActivityLog.objects.for_tenant(tenant.id).get(action="password_reset")
    assert entry.user_id == owner_user.id
    assert entry.entity_id == str(cashier.id)
    assert new_password not in str(entry.after)


@pytest.mark.django_db
def test_reset_signs_the_cashier_in_with_the_new_password(owner_client, cashier):
    new_password = owner_client.post(_reset_url(cashier.id)).json()["password"]

    assert User.objects.get(id=cashier.id).check_password(new_password)


@pytest.mark.django_db
def test_another_tenants_user_is_not_found(owner_client):
    other_client, _ = authed_client(make_tenant("other-mart"))
    theirs = other_client.post(
        USERS_URL,
        {"full_name": "Their Cashier", "password": "x", "email": "t@example.com"},
        format="json",
    ).json()

    assert owner_client.post(_reset_url(theirs["id"])).status_code == 404


@pytest.mark.django_db
def test_cashier_cannot_reset_passwords(tenant, cashier):
    client, _ = authed_client(tenant, role="cashier")

    assert client.post(_reset_url(cashier.id)).status_code == 403
