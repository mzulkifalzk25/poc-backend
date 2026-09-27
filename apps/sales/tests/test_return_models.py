from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.models import User
from apps.sales.models import ReturnItem
from apps.tenants.models import Counter

from .factories import make_bill, make_product, make_return


@pytest.fixture
def counter() -> Counter:
    return Counter.objects.create(tenant_id=1, name="Counter 2", code="002")


@pytest.fixture
def cashier() -> User:
    return User.objects.create(tenant_id=1, full_name="Zainab Khan", role="cashier", pin_hash="x")


def _item(ret, product, **extra) -> ReturnItem:
    return ReturnItem.objects.create(
        tenant_id=ret.tenant_id,
        return_record=ret,
        product=product,
        qty=Decimal("1"),
        price_source="current",
        unit_price=product.price,
        refund_amount=product.price,
        tax_refund=Decimal("0.00"),
        cost_snapshot=product.cost,
        **extra,
    )


@pytest.mark.django_db
def test_a_return_starts_without_flags_bill_or_rollup(counter, cashier):
    ret = make_return(counter, cashier)
    ret.refresh_from_db()

    assert (ret.flags, ret.original_bill_id, ret.original_bill_no, ret.rolled_up_at) == (
        [],
        None,
        None,
        None,
    )


@pytest.mark.django_db
def test_a_return_holds_one_row_per_product(counter, cashier):
    ret = make_return(counter, cashier)
    oil = make_product(1)
    _item(ret, oil)

    with pytest.raises(IntegrityError), transaction.atomic():
        _item(ret, oil)


@pytest.mark.django_db
def test_a_returned_bill_cannot_be_deleted(counter, cashier):
    bill = make_bill(counter, cashier)
    make_return(counter, cashier, original_bill=bill, original_bill_no="002-000001")

    with pytest.raises(ProtectedError):
        bill.delete()
