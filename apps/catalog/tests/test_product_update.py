from decimal import Decimal

import pytest

from apps.audit.models import ActivityLog
from apps.catalog.models import Category, PriceHistory, Product
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
def grocery(tenant):
    return Category.objects.create(tenant_id=tenant.id, name="Grocery", tint="green")


@pytest.fixture
def oil(owner, grocery) -> dict:
    body = {
        "barcode": "8961002300022",
        "name": "Cooking Oil 1L",
        "category_id": grocery.id,
        "unit": "litre",
        "price": "620.00",
        "cost": "540.00",
        "stock": "12",
    }
    return owner[0].post(PRODUCTS_URL, body, format="json").json()


def _patch(client, product_id, body):
    return client.patch(f"{PRODUCTS_URL}/{product_id}", body, format="json")


@pytest.mark.django_db
def test_owner_reads_a_product_with_its_stock(owner, oil):
    response = owner[0].get(f"{PRODUCTS_URL}/{oil['id']}")

    assert response.status_code == 200
    assert response.json()["stock"] == "12.000"
    assert response.json()["cost"] == "540.00"


@pytest.mark.django_db
def test_price_change_writes_price_history_and_activity(tenant, owner, oil):
    client, owner_user = owner

    response = _patch(client, oil["id"], {"price": "650.00"})

    assert response.status_code == 200
    assert response.json()["price"] == "650.00"
    history = PriceHistory.objects.get(product_id=oil["id"])
    assert (history.old_price, history.new_price) == (Decimal("620.00"), Decimal("650.00"))
    assert history.changed_by == owner_user.id and history.source == "edit"
    entry = ActivityLog.objects.for_tenant(tenant.id).get(action="price_changed")
    assert entry.before == {"price": "620.00"} and entry.after == {"price": "650.00"}


@pytest.mark.django_db
def test_other_edits_write_no_price_history(tenant, owner, oil, grocery):
    dairy = Category.objects.create(tenant_id=tenant.id, name="Dairy & eggs", tint="blue")

    response = _patch(
        owner[0],
        oil["id"],
        {"name": " Canola  Oil 1L ", "price": "620.00", "category_id": dairy.id},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Canola Oil 1L"
    assert response.json()["category"]["id"] == dairy.id
    assert Product.objects.get(id=oil["id"]).name_lc == "canola oil 1l"
    assert not PriceHistory.objects.exists()
    assert not ActivityLog.objects.for_tenant(tenant.id).filter(action="price_changed").exists()


@pytest.mark.django_db
def test_stock_is_not_edited_here(owner, oil):
    _patch(owner[0], oil["id"], {"stock": "99"})

    assert StockLevel.objects.get(product_id=oil["id"]).qty == Decimal("12.000")


@pytest.mark.django_db
def test_changing_to_a_live_barcode_is_409(owner, oil, grocery):
    other = (
        owner[0]
        .post(
            PRODUCTS_URL,
            {
                "barcode": "8961002300039",
                "name": "Tea",
                "category_id": grocery.id,
                "unit": "pack",
                "price": "540.00",
                "cost": "470.00",
            },
            format="json",
        )
        .json()
    )

    response = _patch(owner[0], other["id"], {"barcode": "8961002300022"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "barcode_exists"
    assert Product.objects.get(id=other["id"]).barcode == "8961002300039"


@pytest.mark.django_db
def test_invalid_price_is_400(owner, oil):
    assert _patch(owner[0], oil["id"], {"price": "-5"}).status_code == 400


@pytest.mark.django_db
def test_another_tenants_product_is_not_found(oil):
    other_client, _ = authed_client(make_tenant("other-mart"))

    assert other_client.get(f"{PRODUCTS_URL}/{oil['id']}").status_code == 404
    assert _patch(other_client, oil["id"], {"price": "1.00"}).status_code == 404
    assert Product.objects.get(id=oil["id"]).price == Decimal("620.00")


@pytest.mark.django_db
def test_cashier_cannot_read_detail_or_edit(tenant, oil):
    client, _ = authed_client(tenant, role="cashier")

    assert client.get(f"{PRODUCTS_URL}/{oil['id']}").status_code == 403
    assert _patch(client, oil["id"], {"price": "1.00"}).status_code == 403
