from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.audit.models import ActivityLog
from apps.catalog.models import Category, Product
from apps.inventory.models import StockLevel
from apps.tenants.tests.helpers import authed_client, make_tenant

PRODUCTS_URL = "/api/v1/products"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner(tenant):
    return authed_client(tenant)


@pytest.fixture
def grocery(tenant) -> Category:
    return Category.objects.create(tenant_id=tenant.id, name="Grocery", tint="green")


def _body(category, **extra) -> dict:
    return {
        "barcode": "8961002300022",
        "name": "  Cooking   Oil 1L ",
        "category_id": category.id,
        "unit": "litre",
        "price": "620.00",
        "cost": "540.00",
        **extra,
    }


def _post(client, body):
    return client.post(PRODUCTS_URL, body, format="json")


@pytest.mark.django_db
def test_owner_creates_a_product_with_opening_stock(tenant, owner, grocery):
    client, owner_user = owner

    response = _post(client, _body(grocery, stock="24", low_stock_alert="5"))

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Cooking Oil 1L"
    assert body["category"] == {"id": grocery.id, "name": "Grocery", "tint": "green"}
    assert body["price"] == "620.00" and body["cost"] == "540.00"
    assert body["stock"] == "24.000" and body["low_stock_alert"] == "5.000"
    assert body["status"] == "in_stock" and body["is_archived"] is False
    product = Product.objects.get(id=body["id"])
    assert product.name_lc == "cooking oil 1l"
    assert StockLevel.objects.get(product=product).qty == Decimal("24.000")
    entry = ActivityLog.objects.for_tenant(tenant.id).get(action="product_created")
    assert entry.user_id == owner_user.id and entry.after["stock"] == "24.000"


@pytest.mark.django_db
def test_without_opening_stock_the_level_is_zero_and_status_out(owner, grocery):
    body = _post(owner[0], _body(grocery)).json()

    assert body["stock"] == "0.000"
    assert body["status"] == "out"
    assert StockLevel.objects.get(product_id=body["id"]).qty == 0


@pytest.mark.django_db
def test_duplicate_live_barcode_is_409_barcode_exists(owner, grocery):
    _post(owner[0], _body(grocery))

    response = _post(owner[0], _body(grocery, name="Other"))

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "barcode_exists"
    assert error["fields"]["barcode"]
    assert Product.objects.count() == 1 and StockLevel.objects.count() == 1


@pytest.mark.django_db
def test_an_archived_products_barcode_can_be_reused(owner, grocery):
    first = _post(owner[0], _body(grocery)).json()
    Product.objects.filter(id=first["id"]).update(is_archived=True)

    assert _post(owner[0], _body(grocery)).status_code == 201


@pytest.mark.django_db
def test_same_barcode_in_another_tenant_is_fine(owner, grocery):
    other = make_tenant("other-mart")
    other_client, _ = authed_client(other)
    theirs = Category.objects.create(tenant_id=other.id, name="Grocery", tint="green")
    _post(owner[0], _body(grocery))

    assert _post(other_client, _body(theirs)).status_code == 201


@pytest.mark.django_db
def test_category_must_belong_to_the_tenant(owner):
    theirs = Category.objects.create(tenant_id=make_tenant("other-mart").id, name="G", tint="green")

    response = _post(owner[0], _body(theirs))

    assert response.status_code == 400
    assert response.json()["error"]["fields"]["category_id"]
    assert not Product.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("barcode", "896 100"),
        ("barcode", ""),
        ("name", "   "),
        ("unit", "box"),
        ("price", "-1.00"),
        ("price", "1.005"),
        ("cost", "abc"),
        ("stock", "-2"),
        ("low_stock_alert", "-1"),
    ],
)
def test_invalid_fields_are_400_with_a_field_error(owner, grocery, field, value):
    response = _post(owner[0], _body(grocery, **{field: value}))

    assert response.status_code == 400
    assert response.json()["error"]["fields"][field]


@pytest.mark.django_db
def test_cashier_cannot_create_products(tenant, grocery):
    client, _ = authed_client(tenant, role="cashier")

    assert _post(client, _body(grocery)).status_code == 403


def test_creating_products_needs_sign_in():
    assert APIClient().post(PRODUCTS_URL, {}, format="json").status_code == 401
