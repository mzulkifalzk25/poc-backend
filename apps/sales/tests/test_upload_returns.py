from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.audit.models import ActivityLog
from apps.inventory.models import StockLevel, StockMovement
from apps.sales.domain.errors import BatchBusyError
from apps.sales.domain.returns import ReturnedQty
from apps.sales.models import Bill, Return, ReturnItem
from apps.sales.use_cases.return_upload import ReturnBatch, ReturnUpload
from apps.sales.use_cases.upload_returns import ReturnRepositories, upload_returns
from apps.shifts.models import Shift

from .conftest import make_cashier
from .factories import make_product
from .payloads import BATCH_URL, batch, bill, line

NOW = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


def _return(*lines: tuple, **fields) -> ReturnUpload:
    body = {
        "id": uuid4(),
        "shift_id": uuid4(),
        "lines": [ReturnedQty(product.id, Decimal(qty)) for product, qty in lines],
        "reason": "changed_mind",
        "restock": True,
        "refund_method": "cash",
        "refund_amount": Decimal("0.00"),
        "original_bill_no": None,
        "returned_at": NOW - timedelta(minutes=1),
    }
    return ReturnUpload(**{**body, **fields})


def _upload(counter, device, cashier, *returns: ReturnUpload):
    cashier_id = cashier.id if cashier else None
    return upload_returns(
        ReturnBatch(counter.tenant_id, counter.id, device[0].id, cashier_id, NOW, list(returns))
    )


@pytest.fixture
def sold(pc, counter, cashier, oil, rice) -> Bill:
    """Bill 002000743: 2 x oil at 50.00 and 1 x rice at 1650.00, total 1750."""
    body = bill(cashier.id, [line(oil, "2.000"), line(rice, "1.000", line_no=2)])
    pc.post(BATCH_URL, batch(counter.id, body), format="json")
    return Bill.objects.get(id=body["id"])


@pytest.mark.django_db
def test_a_return_without_a_bill_is_stored_at_todays_price(counter, device, cashier, oil):
    upload = _return((oil, "2"), refund_amount=Decimal("100.00"))

    [result] = _upload(counter, device, cashier, upload)

    assert (result.status, result.flags, result.errors) == ("created", [], [])
    stored = Return.objects.get(id=upload.id)
    assert (stored.cashier_id, stored.counter_id, stored.refund_total) == (
        cashier.id,
        counter.id,
        Decimal("100.00"),
    )
    assert (stored.paid_from_drawer, stored.original_bill_id, stored.rolled_up_at) == (
        True,
        None,
        None,
    )
    item = ReturnItem.objects.get(return_record=stored)
    assert (item.price_source, item.unit_price, item.refund_amount, item.cost_snapshot) == (
        "current",
        Decimal("50.00"),
        Decimal("100.00"),
        oil.cost,
    )


@pytest.mark.django_db
def test_a_restocked_return_adds_stock_once(counter, device, cashier, oil):
    upload = _return((oil, "2"), refund_amount=Decimal("100.00"))

    _upload(counter, device, cashier, upload)
    again = _upload(counter, device, cashier, upload)

    assert again[0].status == "duplicate"
    assert Return.objects.count() == 1
    assert StockLevel.objects.get(product=oil).qty == Decimal("102")
    movement = StockMovement.objects.get(product=oil)
    assert (movement.type, movement.qty_delta, movement.ref_type, movement.ref_id) == (
        "return",
        Decimal("2"),
        "return",
        str(upload.id),
    )


@pytest.mark.django_db
def test_a_return_not_restocked_leaves_stock_alone(counter, device, cashier, oil):
    upload = _return((oil, "1"), restock=False, reason="expired_damaged", refund_method="card")

    _upload(counter, device, cashier, upload)

    assert StockLevel.objects.get(product=oil).qty == Decimal("100")
    assert not StockMovement.objects.exists()
    assert Return.objects.get(id=upload.id).paid_from_drawer is False


@pytest.mark.django_db
def test_lines_for_one_product_become_one_item(counter, device, cashier, oil):
    upload = _return((oil, "1"), (oil, "2"), refund_amount=Decimal("150.00"))

    [result] = _upload(counter, device, cashier, upload)

    assert result.flags == []
    assert ReturnItem.objects.get().qty == Decimal("3")
    assert StockLevel.objects.get(product=oil).qty == Decimal("103")


@pytest.mark.django_db
def test_a_found_bill_refunds_the_price_paid_and_links_the_item(
    counter, device, cashier, oil, sold
):
    oil.price = Decimal("55.00")
    oil.save()
    upload = _return((oil, "1"), refund_amount=Decimal("50.00"), original_bill_no="002-000743")

    [result] = _upload(counter, device, cashier, upload)

    assert result.flags == []
    stored = Return.objects.get(id=upload.id)
    assert (stored.original_bill_id, stored.original_bill_no) == (sold.id, "002-000743")
    item = ReturnItem.objects.get(return_record=stored)
    assert (item.price_source, item.unit_price, item.bill_item_id) == (
        "paid",
        Decimal("50.00"),
        sold.items.get(product=oil).id,
    )
    sold.refresh_from_db()
    assert sold.status == "partially_refunded"


@pytest.mark.django_db
def test_returning_everything_marks_the_bill_refunded(counter, device, cashier, oil, rice, sold):
    first = _return((oil, "1"), refund_amount=Decimal("50.00"), original_bill_no="002000743")
    last = _return(
        (oil, "1"), (rice, "1"), refund_amount=Decimal("1700.00"), original_bill_no="002000743"
    )

    results = _upload(counter, device, cashier, first, last)

    assert [result.flags for result in results] == [[], []]
    sold.refresh_from_db()
    assert sold.status == "refunded"


@pytest.mark.django_db
def test_returning_more_than_was_bought_is_flagged_across_batches(
    counter, device, cashier, oil, sold
):
    _upload(counter, device, cashier, _return((oil, "2"), refund_amount=Decimal("100.00"),
                                              original_bill_no="002000743"))  # fmt: skip

    [result] = _upload(
        counter,
        device,
        cashier,
        _return((oil, "1"), refund_amount=Decimal("50.00"), original_bill_no="002000743"),
    )

    assert result.status == "created"
    assert result.flags == ["over_return"]


@pytest.mark.django_db
def test_bill_anomalies_are_flagged_not_refused(counter, device, cashier, oil, rice, sold):
    unknown = _return((oil, "1"), refund_amount=Decimal("50.00"), original_bill_no="002999999")
    other = make_product(counter.tenant_id, "8961002300046", price="120.00", name="Soap")
    extra = _return((other, "1"), refund_amount=Decimal("120.00"), original_bill_no="002000743")
    typo = _return((oil, "1"), refund_amount=Decimal("50.00"), original_bill_no="12-34")

    results = _upload(counter, device, cashier, unknown, extra, typo)

    assert [(r.status, r.flags) for r in results] == [
        ("created", ["bill_not_found"]),
        ("created", ["item_not_on_bill"]),
        ("created", ["bill_not_found"]),
    ]
    assert Return.objects.get(id=typo.id).original_bill_no == "12-34"
    sold.refresh_from_db()
    assert sold.status == "paid"


@pytest.mark.django_db
def test_a_refund_off_by_more_than_one_rupee_is_stored_as_sent(counter, device, cashier, oil):
    upload = _return((oil, "1"), refund_amount=Decimal("60.00"))
    early = _return(
        (oil, "1"), refund_amount=Decimal("50.00"), returned_at=NOW + timedelta(hours=1)
    )

    results = _upload(counter, device, cashier, upload, early)

    assert [result.flags for result in results] == [["price_mismatch"], ["clock_skew"]]
    assert Return.objects.get(id=upload.id).refund_total == Decimal("60.00")


@pytest.mark.django_db
def test_a_pc_token_takes_the_cashier_of_the_shift(tenant, counter, device, cashier, oil):
    shift = Shift.objects.create(
        id=uuid4(),
        tenant_id=tenant.id,
        counter=counter,
        cashier=cashier,
        opened_at=NOW,
        opening_cash=Decimal("0"),
    )
    upload = _return((oil, "1"), refund_amount=Decimal("50.00"), shift_id=shift.id)

    [result] = _upload(counter, device, None, upload)

    assert result.status == "created"
    assert Return.objects.get(id=upload.id).cashier_id == cashier.id


@pytest.mark.django_db
def test_a_pc_token_may_name_the_cashier(tenant, counter, device, cashier, oil):
    hina = make_cashier(tenant, "Hina Malik", is_active=False)
    upload = _return((oil, "1"), refund_amount=Decimal("50.00"), cashier_id=hina.id)

    [result] = _upload(counter, device, None, upload)

    assert result.status == "created"
    assert Return.objects.get(id=upload.id).cashier_id == hina.id


@pytest.mark.django_db
def test_unknown_cashier_or_product_is_rejected(counter, device, oil):
    unknown_shift = _return((oil, "1"))
    foreign = _return((oil, "1"), cashier_id=999_999)

    results = _upload(counter, device, None, unknown_shift, foreign)

    assert [(r.status, r.errors) for r in results] == [
        ("rejected", ["cashier_id: Unknown cashier."]),
        ("rejected", ["cashier_id: Unknown cashier."]),
    ]
    assert not Return.objects.exists()


@pytest.mark.django_db
def test_a_product_of_another_store_is_rejected(counter, device, cashier, oil):
    theirs = make_product(counter.tenant_id + 1, "8961002300053")

    [result] = _upload(counter, device, cashier, _return((oil, "1"), (theirs, "1")))

    assert (result.status, result.errors) == ("rejected", ["lines.1.product_id: Unknown product."])


@pytest.mark.django_db
def test_a_return_is_logged_with_cashier_items_amount_and_reason(counter, device, cashier, oil):
    upload = _return((oil, "2"), refund_amount=Decimal("100.00"), original_bill_no="002999999")

    _upload(counter, device, cashier, upload)

    entry = ActivityLog.objects.get(action="return_processed")
    assert (entry.user_id, entry.entity_type, entry.entity_id) == (
        cashier.id,
        "return",
        str(upload.id),
    )
    assert entry.detail["items"] == [{"product_id": oil.id, "name": oil.name, "qty": "2.000"}]
    assert (entry.detail["amount"], entry.detail["reason"], entry.detail["flags"]) == (
        "100.00",
        "changed_mind",
        ["bill_not_found"],
    )


class LockedReturns:
    def try_lock_counter(self, counter_id: int) -> bool:
        return False


@pytest.mark.django_db
def test_a_busy_counter_writes_nothing():
    batch = ReturnBatch(1, 2, 3, None, NOW, returns=[])

    with pytest.raises(BatchBusyError):
        upload_returns(batch, ReturnRepositories(returns=LockedReturns()))
