from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product
from apps.inventory.models import StockLevel
from apps.tenants.tests.helpers import authed_client, make_tenant

PRODUCTS_URL = "/api/v1/products"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner_client(tenant):
    return authed_client(tenant)[0]


@pytest.fixture
def catalogue(tenant):
    grocery = Category.objects.create(tenant_id=tenant.id, name="Grocery", tint="green")
    dairy = Category.objects.create(tenant_id=tenant.id, name="Dairy & eggs", tint="blue")
    rows = [
        ("8961000000011", "Basmati Rice 5kg", grocery, "40", "5", False),
        ("8961000000028", "Cooking Oil 1L", grocery, "3", "5", False),
        ("8961000000035", "Sugar 1kg", grocery, "0", "5", False),
        ("8961000000042", "Fresh Milk 1L", dairy, "-2", "5", False),
        ("8961000000059", "Old Rice", grocery, "10", "0", True),
    ]
    for barcode, name, category, qty, alert, archived in rows:
        product = Product.objects.create(
            tenant_id=tenant.id,
            barcode=barcode,
            name=name,
            name_lc=name.lower(),
            category=category,
            unit="pcs",
            price=Decimal("100.00"),
            cost=Decimal("80.00"),
            low_stock_alert=Decimal(alert),
            is_archived=archived,
        )
        StockLevel.objects.create(tenant_id=tenant.id, product=product, qty=Decimal(qty))
    return {"grocery": grocery, "dairy": dairy}


def _names(client, **params) -> list[str]:
    response = client.get(PRODUCTS_URL, params)
    assert response.status_code == 200
    return [row["name"] for row in response.json()["results"]]


@pytest.mark.django_db
def test_list_is_paged_sorted_and_live_only(owner_client, catalogue):
    body = owner_client.get(PRODUCTS_URL, {"page_size": 2}).json()

    assert body["count"] == 4
    assert [row["name"] for row in body["results"]] == ["Basmati Rice 5kg", "Cooking Oil 1L"]
    row = body["results"][0]
    assert set(row) == {
        "id",
        "barcode",
        "name",
        "category",
        "unit",
        "price",
        "cost",
        "stock",
        "status",
    }
    assert row["category"]["tint"] == "green" and row["stock"] == "40.000"


@pytest.mark.django_db
def test_search_matches_name_anywhere_or_barcode_prefix(owner_client, catalogue):
    assert _names(owner_client, search="RICE") == ["Basmati Rice 5kg"]
    assert _names(owner_client, search="89610000000") == [
        "Basmati Rice 5kg",
        "Cooking Oil 1L",
        "Fresh Milk 1L",
        "Sugar 1kg",
    ]
    assert _names(owner_client, search="8961000000042") == ["Fresh Milk 1L"]


@pytest.mark.django_db
def test_category_and_stock_filters(owner_client, catalogue):
    assert _names(owner_client, category=catalogue["dairy"].id) == ["Fresh Milk 1L"]
    assert _names(owner_client, stock="low") == ["Cooking Oil 1L"]
    assert _names(owner_client, stock="out") == ["Fresh Milk 1L", "Sugar 1kg"]


@pytest.mark.django_db
def test_status_per_row(owner_client, catalogue):
    rows = {row["name"]: row["status"] for row in owner_client.get(PRODUCTS_URL).json()["results"]}

    assert rows == {
        "Basmati Rice 5kg": "in_stock",
        "Cooking Oil 1L": "low",
        "Sugar 1kg": "out",
        "Fresh Milk 1L": "negative",
    }


@pytest.mark.django_db
def test_archived_products_show_only_when_asked(owner_client, catalogue):
    body = owner_client.get(PRODUCTS_URL, {"archived": "true"}).json()

    assert [row["name"] for row in body["results"]] == ["Old Rice"]
    assert body["results"][0]["status"] == "archived"


@pytest.mark.django_db
def test_bad_filters_are_400(owner_client):
    assert owner_client.get(PRODUCTS_URL, {"stock": "negative"}).status_code == 400
    assert owner_client.get(PRODUCTS_URL, {"category": "x"}).status_code == 400


@pytest.mark.django_db
def test_cashier_list_hides_cost(tenant, catalogue):
    cashier, _ = authed_client(tenant, role="cashier")

    rows = cashier.get(PRODUCTS_URL).json()["results"]

    assert rows and all("cost" not in row for row in rows)


@pytest.mark.django_db
def test_list_never_shows_another_tenants_products(catalogue):
    other_client, _ = authed_client(make_tenant("other-mart"))

    assert other_client.get(PRODUCTS_URL).json() == {"count": 0, "results": []}


@pytest.mark.django_db
def test_manager_and_anonymous_cannot_list(tenant):
    manager, _ = authed_client(tenant, role="manager")

    assert manager.get(PRODUCTS_URL).status_code == 403
    assert APIClient().get(PRODUCTS_URL).status_code == 401


@pytest.mark.django_db
def test_price_history_newest_first_with_who(tenant, catalogue):
    client, owner_user = authed_client(tenant)
    product = Product.objects.get(name="Cooking Oil 1L")
    for price in ("110.00", "120.00"):
        client.patch(f"{PRODUCTS_URL}/{product.id}", {"price": price}, format="json")

    response = client.get(f"{PRODUCTS_URL}/{product.id}/price-history")

    assert response.status_code == 200
    rows = response.json()
    assert [(row["old"], row["new"]) for row in rows] == [
        ("110.00", "120.00"),
        ("100.00", "110.00"),
    ]
    assert rows[0]["who"] == owner_user.full_name and rows[0]["when"].endswith("Z")


@pytest.mark.django_db
def test_price_history_is_owner_only_and_tenant_scoped(tenant, catalogue):
    product = Product.objects.get(name="Cooking Oil 1L")
    cashier, _ = authed_client(tenant, role="cashier")
    other_client, _ = authed_client(make_tenant("other-mart"))

    assert cashier.get(f"{PRODUCTS_URL}/{product.id}/price-history").status_code == 403
    assert other_client.get(f"{PRODUCTS_URL}/{product.id}/price-history").status_code == 404
