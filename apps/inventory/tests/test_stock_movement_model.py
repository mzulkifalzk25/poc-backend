from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.inventory.models import StockMovement


@pytest.fixture
def product() -> Product:
    category = Category.objects.create(tenant_id=1, name="Grocery", tint="green")
    return Product.objects.create(
        tenant_id=1,
        barcode="8961002300022",
        name="Cooking Oil 1L",
        name_lc="cooking oil 1l",
        category=category,
        unit="litre",
        price=Decimal("620.00"),
        cost=Decimal("540.00"),
    )


def _move(product: Product, type: str = "sale", ref_id: str = "bill-1", qty: str = "-2"):
    return StockMovement.objects.create(
        tenant_id=product.tenant_id,
        product=product,
        type=type,
        qty_delta=Decimal(qty),
        ref_type="bill",
        ref_id=ref_id,
        occurred_at=timezone.now(),
    )


@pytest.mark.django_db
def test_a_movement_keeps_a_signed_quantity(product):
    move = _move(product, qty="-2.500")

    assert StockMovement.objects.get(id=move.id).qty_delta == Decimal("-2.500")


@pytest.mark.django_db
@pytest.mark.parametrize("type", ["sale", "return"])
def test_a_sale_or_return_moves_a_product_once_per_record(product, type):
    _move(product, type=type)

    with pytest.raises(IntegrityError), transaction.atomic():
        _move(product, type=type)


@pytest.mark.django_db
def test_a_sale_and_a_return_of_the_same_ref_are_separate(product):
    _move(product, type="sale")

    assert _move(product, type="return", qty="1").type == "return"


@pytest.mark.django_db
def test_adjustments_may_repeat_a_ref(product):
    _move(product, type="adjust_add", qty="3")

    assert _move(product, type="adjust_add", qty="3").type == "adjust_add"


@pytest.mark.django_db
def test_other_records_move_the_same_product(product):
    _move(product, ref_id="bill-1")

    assert _move(product, ref_id="bill-2").ref_id == "bill-2"
