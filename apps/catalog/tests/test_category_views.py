import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Category
from apps.tenants.tests.helpers import authed_client, make_tenant

CATEGORIES_URL = "/api/v1/categories"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner_client(tenant):
    return authed_client(tenant)[0]


def _create(client, name="Grocery", tint="green"):
    return client.post(CATEGORIES_URL, {"name": name, "tint": tint}, format="json")


@pytest.mark.django_db
def test_owner_creates_a_category(tenant, owner_client):
    response = _create(owner_client, "  Dairy   &  eggs ", "blue")

    assert response.status_code == 201
    body = response.json()
    assert body == {"id": body["id"], "name": "Dairy & eggs", "tint": "blue", "product_count": 0}
    assert Category.objects.get(id=body["id"]).tenant_id == tenant.id


@pytest.mark.django_db
def test_list_keeps_the_order_categories_were_added(owner_client):
    for name in ("Grocery", "Dairy & eggs", "Beverages"):
        _create(owner_client, name)

    names = [row["name"] for row in owner_client.get(CATEGORIES_URL).json()]

    assert names == ["Grocery", "Dairy & eggs", "Beverages"]


@pytest.mark.django_db
@pytest.mark.parametrize("typed", ["Grocery", "grocery", "  GROCERY "])
def test_duplicate_name_is_409_name_exists(owner_client, typed):
    _create(owner_client)

    response = _create(owner_client, typed, "blue")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "name_exists"
    assert error["fields"]["name"]


@pytest.mark.django_db
def test_same_name_in_another_tenant_is_fine(owner_client):
    _create(owner_client)
    other_client, _ = authed_client(make_tenant("other-mart"))

    assert _create(other_client).status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "tint", "field"), [("", "green", "name"), ("Snacks", "red", "tint")]
)
def test_name_and_a_design_tint_are_required(owner_client, name, tint, field):
    response = _create(owner_client, name, tint)

    assert response.status_code == 400
    assert response.json()["error"]["fields"][field]


@pytest.mark.django_db
def test_owner_renames_and_retints(owner_client):
    category = _create(owner_client, "Snaks", "pink").json()

    response = owner_client.patch(
        f"{CATEGORIES_URL}/{category['id']}", {"name": "Snacks", "tint": "orange"}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Snacks"
    assert response.json()["tint"] == "orange"


@pytest.mark.django_db
def test_rename_to_an_existing_name_is_409(owner_client):
    _create(owner_client, "Grocery")
    bakery = _create(owner_client, "Bakery", "yellow").json()

    response = owner_client.patch(f"{CATEGORIES_URL}/{bakery['id']}", {"name": "grocery"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "name_exists"


@pytest.mark.django_db
def test_rename_keeping_the_same_name_in_new_case_is_fine(owner_client):
    grocery = _create(owner_client, "grocery").json()

    response = owner_client.patch(f"{CATEGORIES_URL}/{grocery['id']}", {"name": "Grocery"})

    assert response.status_code == 200


@pytest.mark.django_db
def test_another_tenants_categories_are_invisible(owner_client):
    other_client, _ = authed_client(make_tenant("other-mart"))
    theirs = _create(other_client, "Their Category").json()

    listed = owner_client.get(CATEGORIES_URL).json()
    patched = owner_client.patch(f"{CATEGORIES_URL}/{theirs['id']}", {"name": "Mine now"})

    assert listed == []
    assert patched.status_code == 404
    assert Category.objects.get(id=theirs["id"]).name == "Their Category"


@pytest.mark.django_db
def test_cashier_can_read_but_not_change_categories(tenant, owner_client):
    grocery = _create(owner_client).json()
    cashier_client, _ = authed_client(tenant, role="cashier")

    assert cashier_client.get(CATEGORIES_URL).status_code == 200
    assert _create(cashier_client, "Snacks", "pink").status_code == 403
    assert (
        cashier_client.patch(f"{CATEGORIES_URL}/{grocery['id']}", {"name": "X"}).status_code == 403
    )


def test_categories_need_a_signed_in_user():
    assert APIClient().get(CATEGORIES_URL).status_code == 401
