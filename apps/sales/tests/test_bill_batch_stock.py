from datetime import datetime
from decimal import Decimal

import pytest

from apps.inventory.models import StockLevel, StockMovement

from .factories import make_product
from .payloads import BATCH_URL, batch, bill, line


def _post(client, counter, *bills):
    return client.post(BATCH_URL, batch(counter.id, *bills), format="json")


def _qty(product) -> Decimal:
    return StockLevel.objects.get(product=product).qty


@pytest.mark.django_db
def test_a_sale_takes_its_quantity_off_stock_with_a_movement(pc, counter, cashier, oil):
    before = StockLevel.objects.get(product=oil).updated_at
    body = bill(cashier.id, [line(oil, "5.000")])

    _post(pc, counter, body)

    level = StockLevel.objects.get(product=oil)
    assert level.qty == Decimal("95")
    assert level.updated_at > before
    move = StockMovement.objects.get(product=oil)
    assert (move.type, move.qty_delta, move.ref_type, move.ref_id) == (
        "sale",
        Decimal("-5"),
        "bill",
        body["id"],
    )
    assert (move.user_id, move.occurred_at) == (cashier.id, datetime.fromisoformat(body["sold_at"]))


@pytest.mark.django_db
def test_a_retried_batch_never_takes_stock_twice(pc, counter, cashier, oil):
    body = bill(cashier.id, [line(oil, "5.000")])
    _post(pc, counter, body)

    _post(pc, counter, body)

    assert _qty(oil) == Decimal("95")
    assert StockMovement.objects.count() == 1


@pytest.mark.django_db
def test_bills_in_one_batch_are_summed_per_product(pc, counter, cashier, oil, rice):
    first = bill(cashier.id, [line(oil, "2.000"), line(rice, line_no=2)], seq=1)
    second = bill(cashier.id, [line(oil, "3.000")], seq=2)

    _post(pc, counter, first, second)

    assert (_qty(oil), _qty(rice)) == (Decimal("95"), Decimal("99"))
    assert StockMovement.objects.filter(product=oil).count() == 2


@pytest.mark.django_db
def test_an_out_of_stock_sale_is_accepted_flagged_and_goes_negative(pc, tenant, counter, cashier):
    bread = make_product(tenant.id, "8961002300046", price="120.00", stock="0")

    result = _post(pc, counter, bill(cashier.id, [line(bread, "2.000")])).json()["results"][0]

    assert (result["status"], result["flags"]) == ("created", ["negative_stock"])
    assert _qty(bread) == Decimal("-2")


@pytest.mark.django_db
def test_only_the_bill_that_crosses_zero_is_flagged(pc, tenant, counter, cashier):
    eggs = make_product(tenant.id, "8961002300053", price="360.00", stock="3")
    bills = [bill(cashier.id, [line(eggs, "2.000")], seq=n) for n in (1, 2)]

    results = _post(pc, counter, *bills).json()["results"]

    assert [r["flags"] for r in results] == [[], ["negative_stock"]]
    assert _qty(eggs) == Decimal("-1")


@pytest.mark.django_db
def test_a_product_without_a_stock_row_gets_one(pc, tenant, counter, cashier):
    tea = make_product(tenant.id, "8961002300060", price="450.00", stock=None)

    result = _post(pc, counter, bill(cashier.id, [line(tea)])).json()["results"][0]

    assert result["flags"] == ["negative_stock"]
    assert _qty(tea) == Decimal("-1")


@pytest.mark.django_db
def test_rejected_bills_leave_stock_alone(pc, counter, cashier, oil):
    bad = bill(cashier.id, [line(oil, "5.000"), {**line(oil), "product_id": 999999}])

    _post(pc, counter, bad)

    assert _qty(oil) == Decimal("100")
    assert not StockMovement.objects.exists()


@pytest.mark.django_db
def test_counters_see_the_new_stock_through_sync(pc, counter, cashier, oil):
    since = pc.get("/api/v1/stock/sync/").json()["next_since"]

    _post(pc, counter, bill(cashier.id, [line(oil, "5.000")]))

    levels = pc.get("/api/v1/stock/sync/", {"since": since}).json()["levels"]
    assert {"product_id": oil.id, "qty": "95.000"} in levels
