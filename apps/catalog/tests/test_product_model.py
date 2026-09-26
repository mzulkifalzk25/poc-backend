from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.catalog.models import Category, Product
from apps.inventory.models import StockLevel


@pytest.fixture
def category() -> Category:
    return Category.objects.create(tenant_id=1, name="Grocery", tint="green")


def _product(category, barcode="8961002300022", tenant_id=1, **extra) -> Product:
    return Product.objects.create(
        tenant_id=tenant_id,
        barcode=barcode,
        name="Cooking Oil 1L",
        name_lc="cooking oil 1l",
        category=category,
        unit="litre",
        price=Decimal("620.00"),
        cost=Decimal("540.00"),
        **extra,
    )


@pytest.mark.django_db
def test_live_barcode_is_unique_per_tenant(category):
    _product(category)

    with pytest.raises(IntegrityError), transaction.atomic():
        _product(category)


@pytest.mark.django_db
def test_an_archived_product_frees_its_barcode(category):
    _product(category, is_archived=True)

    _product(category)

    assert Product.objects.filter(barcode="8961002300022").count() == 2


@pytest.mark.django_db
def test_same_barcode_in_another_tenant_is_fine(category):
    other = Category.objects.create(tenant_id=2, name="Grocery", tint="green")
    _product(category)

    _product(other, tenant_id=2)


@pytest.mark.django_db
def test_stock_level_is_one_per_product_and_may_go_negative(category):
    product = _product(category)
    level = StockLevel.objects.create(tenant_id=1, product=product, qty=Decimal("-3.500"))

    with pytest.raises(IntegrityError), transaction.atomic():
        StockLevel.objects.create(tenant_id=1, product=product)
    level.refresh_from_db()
    assert level.qty == Decimal("-3.500")


@pytest.mark.django_db
def test_a_category_with_products_cannot_be_deleted_at_database_level(category):
    _product(category)

    with pytest.raises(ProtectedError), transaction.atomic():
        category.delete()
