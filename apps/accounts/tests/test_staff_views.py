from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import ActivityLog
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import authed_client, make_tenant

USERS_URL = "/api/v1/users"


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
def counter(tenant) -> Counter:
    return Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")


def _cashier(client, name="Zainab Khan", password="pw-482134", **extra):
    extra.setdefault("email", f"{uuid4().hex[:8]}@example.com")
    return client.post(USERS_URL, {"full_name": name, "password": password, **extra}, format="json")


@pytest.mark.django_db
def test_owner_creates_a_cashier_with_a_hashed_password(owner_client, counter):
    response = _cashier(
        owner_client, "  Zainab   Khan ", email="zainab@example.com", default_counter_id=counter.id
    )

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Zainab Khan"
    assert body["initials"] == "ZK"
    assert body["role"] == "cashier"
    assert body["email"] == "zainab@example.com"
    assert body["default_counter_id"] == counter.id
    assert "password" not in body
    user = User.objects.get(id=body["id"])
    assert user.check_password("pw-482134")


@pytest.mark.django_db
def test_creating_staff_is_logged_without_secrets(tenant, owner):
    client, owner_user = owner

    user_id = _cashier(client).json()["id"]

    entry = ActivityLog.objects.for_tenant(tenant.id).get(action="staff_created")
    assert entry.user_id == owner_user.id
    assert entry.entity_id == str(user_id)
    assert "pw-482134" not in str(entry.after)


@pytest.mark.django_db
@pytest.mark.parametrize("typed", ["Zainab Khan", "zainab khan", "  ZAINAB   KHAN "])
def test_duplicate_cashier_name_is_409_name_exists(owner_client, typed):
    _cashier(owner_client)

    response = _cashier(owner_client, typed)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "name_exists"
    assert error["fields"]["full_name"]


@pytest.mark.django_db
def test_a_deactivated_cashiers_name_stays_taken(tenant, owner_client):
    User.objects.create(
        tenant_id=tenant.id, full_name="Usman Tariq", role="cashier", is_active=False
    )

    assert _cashier(owner_client, "Usman Tariq").status_code == 409


@pytest.mark.django_db
def test_same_cashier_name_in_another_tenant_is_fine(owner_client):
    other_client, _ = authed_client(make_tenant("other-mart"))
    _cashier(owner_client)

    assert _cashier(other_client).status_code == 201


@pytest.mark.django_db
def test_cashier_without_a_password_is_rejected(owner_client):
    response = owner_client.post(
        USERS_URL, {"full_name": "Hina Malik", "email": "hina@example.com"}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["password"]


@pytest.mark.django_db
def test_cashier_needs_an_email_or_username(owner_client):
    response = owner_client.post(
        USERS_URL, {"full_name": "Hina Malik", "password": "pw-482134"}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["role"]


@pytest.mark.django_db
def test_default_counter_must_belong_to_the_tenant(owner_client):
    other = Counter.objects.create(tenant_id=make_tenant("other-mart").id, name="C", code="001")

    response = _cashier(owner_client, email="zainab@example.com", default_counter_id=other.id)

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["default_counter_id"]


@pytest.mark.django_db
def test_owner_creates_a_manager_with_a_password(owner_client):
    response = owner_client.post(
        USERS_URL,
        {"full_name": "Ali Manager", "role": "manager", "username": "ali", "password": "pw-123456"},
        format="json",
    )

    assert response.status_code == 201
    user = User.objects.get(id=response.json()["id"])
    assert user.check_password("pw-123456")


@pytest.mark.django_db
def test_duplicate_username_is_409(owner_client):
    body = {"full_name": "A", "role": "manager", "username": "ali", "password": "pw-123456"}
    owner_client.post(USERS_URL, body, format="json")

    response = owner_client.post(USERS_URL, {**body, "username": "ALI"}, format="json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "username_exists"


@pytest.mark.django_db
def test_list_is_paged_and_filtered(tenant, owner_client, counter):
    _cashier(owner_client, "Zainab Khan", email="zainab@example.com", default_counter_id=counter.id)
    _cashier(owner_client, "Bilal Raza", email="bilal@example.com")
    usman = _cashier(owner_client, "Usman Tariq", email="usman@example.com").json()
    owner_client.patch(f"{USERS_URL}/{usman['id']}", {"is_active": False}, format="json")

    everyone = owner_client.get(USERS_URL).json()
    cashiers = owner_client.get(USERS_URL, {"role": "cashier", "status": "active"}).json()
    at_counter = owner_client.get(USERS_URL, {"counter": counter.id}).json()

    assert everyone["count"] == 4
    assert [row["full_name"] for row in cashiers["results"]] == ["Bilal Raza", "Zainab Khan"]
    assert [row["full_name"] for row in at_counter["results"]] == ["Zainab Khan"]


@pytest.mark.django_db
def test_bad_filter_is_400(owner_client):
    assert owner_client.get(USERS_URL, {"status": "gone"}).status_code == 400


@pytest.mark.django_db
def test_list_never_shows_another_tenants_staff(owner_client):
    other_client, _ = authed_client(make_tenant("other-mart"))
    _cashier(other_client, "Other Cashier")

    names = [row["full_name"] for row in owner_client.get(USERS_URL).json()["results"]]

    assert "Other Cashier" not in names


@pytest.mark.django_db
def test_rename_follows_the_unique_name_rule(tenant, owner_client):
    _cashier(owner_client, "Zainab Khan")
    bilal = _cashier(owner_client, "Bilal Raza").json()

    clash = owner_client.patch(f"{USERS_URL}/{bilal['id']}", {"full_name": "ZAINAB KHAN"})
    fine = owner_client.patch(f"{USERS_URL}/{bilal['id']}", {"full_name": " Bilal  Raza K "})

    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "name_exists"
    assert fine.status_code == 200
    assert fine.json()["full_name"] == "Bilal Raza K"
    assert ActivityLog.objects.for_tenant(tenant.id).filter(action="staff_updated").count() == 1


@pytest.mark.django_db
def test_owner_deactivates_a_cashier(owner_client):
    zainab = _cashier(owner_client).json()

    response = owner_client.patch(f"{USERS_URL}/{zainab['id']}", {"is_active": False})

    assert response.status_code == 200
    assert response.json()["is_active"] is False


@pytest.mark.django_db
def test_owner_cannot_deactivate_themselves(owner):
    client, owner_user = owner

    response = client.patch(f"{USERS_URL}/{owner_user.id}", {"is_active": False})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "cannot_deactivate_self"


@pytest.mark.django_db
def test_another_tenants_user_is_not_found(owner_client):
    other_client, _ = authed_client(make_tenant("other-mart"))
    theirs = _cashier(other_client).json()

    response = owner_client.patch(f"{USERS_URL}/{theirs['id']}", {"full_name": "Taken Over"})

    assert response.status_code == 404
    assert User.objects.get(id=theirs["id"]).full_name == "Zainab Khan"


@pytest.mark.django_db
def test_cashier_cannot_manage_staff(tenant):
    client, _ = authed_client(tenant, role="cashier")

    assert client.get(USERS_URL).status_code == 403
    assert _cashier(client).status_code == 403


def test_staff_needs_a_signed_in_owner():
    assert APIClient().get(USERS_URL).status_code == 401
