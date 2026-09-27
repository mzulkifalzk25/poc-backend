from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.models import User
from apps.sales.domain.flags import BILL_NO_CONFLICT
from apps.sales.models import Bill, BillItem, Payment
from apps.tenants.models import Counter

from .factories import make_bill, make_product


@pytest.fixture
def counter() -> Counter:
    return Counter.objects.create(tenant_id=1, name="Counter 2", code="002")


@pytest.fixture
def cashier() -> User:
    return User.objects.create(tenant_id=1, full_name="Zainab Khan", role="cashier", pin_hash="x")


def _item(bill: Bill, product, line_no: int = 1) -> BillItem:
    return BillItem.objects.create(
        tenant_id=bill.tenant_id,
        bill=bill,
        line_no=line_no,
        product=product,
        name_snapshot=product.name,
        barcode_snapshot=product.barcode,
        qty=Decimal("2"),
        unit_price=product.price,
        cost_snapshot=product.cost,
        line_total=product.price * 2,
        sold_at=bill.sold_at,
    )


@pytest.mark.django_db
def test_a_bill_starts_paid_without_flags_and_not_rolled_up(counter, cashier):
    bill = Bill.objects.get(id=make_bill(counter, cashier).id)

    assert (bill.status, bill.flags, bill.rolled_up_at) == ("paid", [], None)
    assert bill.discount_amount is None


@pytest.mark.django_db
def test_a_bill_number_is_unique_per_tenant(counter, cashier):
    make_bill(counter, cashier)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_bill(counter, cashier)


@pytest.mark.django_db
def test_a_conflicting_bill_number_is_kept_when_flagged(counter, cashier):
    make_bill(counter, cashier)

    flagged = make_bill(counter, cashier, flags=[BILL_NO_CONFLICT])

    assert Bill.objects.filter(bill_no="002000001").count() == 2
    assert flagged.flags == [BILL_NO_CONFLICT]


@pytest.mark.django_db
def test_other_tenants_reuse_bill_numbers(counter, cashier):
    other_counter = Counter.objects.create(tenant_id=2, name="Counter 2", code="002")
    other_cashier = User.objects.create(tenant_id=2, full_name="A B", role="cashier", pin_hash="x")
    make_bill(counter, cashier)

    assert make_bill(other_counter, other_cashier).bill_no == "002000001"


@pytest.mark.django_db
def test_a_bill_has_one_row_per_product(counter, cashier):
    bill = make_bill(counter, cashier)
    product = make_product(1)
    _item(bill, product)

    with pytest.raises(IntegrityError), transaction.atomic():
        _item(bill, product, line_no=2)
    assert _item(bill, make_product(1, barcode="8961002300039"), line_no=2).line_no == 2


@pytest.mark.django_db
def test_a_payment_belongs_to_a_bill_with_the_client_id(counter, cashier):
    bill = make_bill(counter, cashier)
    payment_id = uuid4()
    Payment.objects.create(
        id=payment_id,
        tenant_id=1,
        bill=bill,
        method="cash",
        amount=Decimal("620.00"),
        tendered=Decimal("1000.00"),
        change_given=Decimal("380.00"),
    )

    assert list(bill.payments.values_list("id", flat=True)) == [payment_id]
    assert Payment.objects.get(id=payment_id).reference == ""


@pytest.mark.django_db
def test_bills_protect_their_counter_and_cashier(counter, cashier):
    make_bill(counter, cashier)

    with pytest.raises(ProtectedError):
        counter.delete()
    with pytest.raises(ProtectedError):
        cashier.delete()
