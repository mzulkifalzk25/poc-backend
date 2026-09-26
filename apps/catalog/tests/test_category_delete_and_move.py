from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.tenants.tests.helpers import authed_client, make_tenant

CATEGORIES_URL = "/api/v1/categories"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner_client(tenant):
    return authed_client(tenant)[0]


def _category(tenant_id, name, tint="green") -> Category:
    return Category.objects.create(tenant_id=tenant_id, name=name, tint=tint)


def _product(category, barcode, archived=False) -> Product:
    return Product.objects.create(
        tenant_id=category.tenant_id,
        barcode=barcode,
        name=barcode,
        name_lc=barcode,
        category=category,
        unit="pcs",
        price=Decimal("10.00"),
        cost=Decimal("8.00"),
        is_archived=archived,
    )


@pytest.mark.django_db
def test_product_count_counts_live_products_only(tenant, owner_client):
    grocery = _category(tenant.id, "Grocery")
    _product(grocery, "1")
    _product(grocery, "2")
    _product(grocery, "3", archived=True)

    rows = owner_client.get(CATEGORIES_URL).json()

    assert rows[0]["product_count"] == 2


@pytest.mark.django_db
def test_an_empty_category_is_deleted(tenant, owner_client):
    snacks = _category(tenant.id, "Snacks", "pink")

    response = owner_client.delete(f"{CATEGORIES_URL}/{snacks.id}")

    assert response.status_code == 204
    assert not Category.objects.filter(id=snacks.id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("archived", [False, True])
def test_a_category_with_products_is_409_even_if_they_are_archived(tenant, owner_client, archived):
    grocery = _category(tenant.id, "Grocery")
    _product(grocery, "1", archived=archived)

    response = owner_client.delete(f"{CATEGORIES_URL}/{grocery.id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "category_has_products"
    assert Category.objects.filter(id=grocery.id).exists()


@pytest.mark.django_db
def test_move_products_then_delete(tenant, owner_client):
    old = _category(tenant.id, "Snaks", "pink")
    new = _category(tenant.id, "Snacks", "pink")
    live = _product(old, "1")
    archived = _product(old, "2", archived=True)
    Product.objects.update(updated_at=timezone.now() - timedelta(days=1))

    moved = owner_client.post(
        f"{CATEGORIES_URL}/{old.id}/move-products", {"to_category_id": new.id}, format="json"
    )
    deleted = owner_client.delete(f"{CATEGORIES_URL}/{old.id}")

    assert moved.status_code == 200
    assert moved.json() == {"moved": 2}
    assert deleted.status_code == 204
    for product in (live, archived):
        product.refresh_from_db()
        assert product.category_id == new.id
        assert product.updated_at > timezone.now() - timedelta(minutes=1)


@pytest.mark.django_db
def test_move_to_itself_or_to_another_tenants_category_is_refused(tenant, owner_client):
    grocery = _category(tenant.id, "Grocery")
    _product(grocery, "1")
    theirs = _category(make_tenant("other-mart").id, "Theirs")

    for target in (grocery.id, theirs.id, 999999):
        response = owner_client.post(
            f"{CATEGORIES_URL}/{grocery.id}/move-products",
            {"to_category_id": target},
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["error"]["fields"]["to_category_id"]
    assert Product.objects.get(barcode="1").category_id == grocery.id


@pytest.mark.django_db
def test_another_tenants_category_cannot_be_deleted_or_emptied(tenant):
    theirs = _category(make_tenant("other-mart").id, "Theirs")
    client, _ = authed_client(tenant)

    assert client.delete(f"{CATEGORIES_URL}/{theirs.id}").status_code == 404
    assert (
        client.post(
            f"{CATEGORIES_URL}/{theirs.id}/move-products", {"to_category_id": 1}, format="json"
        ).status_code
        == 404
    )
    assert Category.objects.filter(id=theirs.id).exists()


@pytest.mark.django_db
def test_cashier_cannot_delete_or_move(tenant):
    grocery = _category(tenant.id, "Grocery")
    client, _ = authed_client(tenant, role="cashier")

    assert client.delete(f"{CATEGORIES_URL}/{grocery.id}").status_code == 403
    assert (
        client.post(
            f"{CATEGORIES_URL}/{grocery.id}/move-products", {"to_category_id": 1}, format="json"
        ).status_code
        == 403
    )
