from uuid import uuid4

import pytest

from apps.sales.tests.factories import make_product
from apps.sales.tests.payloads import BATCH_URL, batch, bill, line

OPEN_URL = "/api/v1/shifts/open"
RETURNS_URL = "/api/v1/returns/batch"


def _open(pc, counter, cashier) -> str:
    shift_id = str(uuid4())
    body = {
        "id": shift_id,
        "counter_id": counter.id,
        "opened_at": "2026-09-27T04:00:00Z",
        "opening_cash": "5000.00",
        "cashier_id": cashier.id,
    }
    assert pc.post(OPEN_URL, body, format="json").status_code == 201
    return shift_id


def _sale(cashier_id, product, shift_id, seq, method="cash", qty="1.000") -> dict:
    body = bill(cashier_id, [line(product, qty)], seq=seq, shift_id=shift_id)
    body["payment"] = {**body["payment"], "method": method}
    return body


def _close(pc, shift_id, cashier, counted, local) -> dict:
    body = {
        "closed_at": "2026-09-27T16:00:00Z",
        "counted_cash": counted,
        "local_summary": local,
        "unsynced_count": 0,
        "cashier_id": cashier.id,
    }
    return pc.post(f"/api/v1/shifts/{shift_id}/close", body, format="json").json()


@pytest.mark.django_db
def test_expected_cash_counts_the_shifts_cash_sales_only(pc, tenant, counter, cashier):
    oil = make_product(tenant.id, price="50.00")
    shift_id = _open(pc, counter, cashier)
    sales = [
        _sale(cashier.id, oil, shift_id, 1, qty="5.000"),
        _sale(cashier.id, oil, shift_id, 2, method="card", qty="2.000"),
        _sale(cashier.id, oil, shift_id, 3, method="wallet"),
        _sale(cashier.id, oil, str(uuid4()), 4, qty="9.000"),
    ]
    pc.post(BATCH_URL, batch(counter.id, *sales), format="json")

    result = _close(pc, shift_id, cashier, "5250.00", {"bills": 3, "cash": "250.00"})

    assert (result["expected_cash"], result["difference"], result["mismatch"]) == (
        "5250.00",
        "0.00",
        False,
    )
    summary = result["server_summary"]
    assert (summary["bills"], summary["total_sales"]) == (3, "400.00")
    assert (summary["cash"], summary["card"], summary["wallet"]) == ("250.00", "100.00", "50.00")
    assert (summary["refund_count"], summary["cash_refunds"]) == (0, "0.00")


@pytest.mark.django_db
def test_sales_the_server_has_not_seen_are_a_mismatch(pc, tenant, counter, cashier):
    oil = make_product(tenant.id, price="50.00")
    shift_id = _open(pc, counter, cashier)
    pc.post(BATCH_URL, batch(counter.id, _sale(cashier.id, oil, shift_id, 1)), format="json")

    result = _close(pc, shift_id, cashier, "5100.00", {"bills": 2, "cash": "100.00"})

    assert (result["expected_cash"], result["difference"], result["mismatch"]) == (
        "5050.00",
        "50.00",
        True,
    )


def _refund(product, shift_id, method: str, amount: str, qty: str = "1.000") -> dict:
    return {
        "id": str(uuid4()),
        "shift_id": shift_id,
        "lines": [{"product_id": product.id, "qty": qty}],
        "reason": "changed_mind",
        "restock": True,
        "refund": {"method": method, "amount": amount},
        "returned_at": "2026-09-27T07:52:10Z",
    }


@pytest.mark.django_db
def test_only_the_shifts_cash_refunds_come_out_of_expected_cash(pc, tenant, counter, cashier):
    oil = make_product(tenant.id, price="50.00")
    shift_id = _open(pc, counter, cashier)
    pc.post(BATCH_URL, batch(counter.id, _sale(cashier.id, oil, shift_id, 1, qty="5.000")),
            format="json")  # fmt: skip
    refunds = [
        {**_refund(oil, shift_id, "cash", "100.00", "2.000"), "cashier_id": cashier.id},
        {**_refund(oil, shift_id, "card", "50.00"), "cashier_id": cashier.id},
        {**_refund(oil, str(uuid4()), "cash", "50.00"), "cashier_id": cashier.id},
    ]
    pc.post(RETURNS_URL, {"returns": refunds}, format="json")

    result = _close(pc, shift_id, cashier, "5150.00", {"bills": 1, "cash": "250.00"})

    assert (result["expected_cash"], result["difference"], result["mismatch"]) == (
        "5150.00",
        "0.00",
        False,
    )
    summary = result["server_summary"]
    assert (summary["refund_count"], summary["refund_amount"], summary["cash_refunds"]) == (
        2,
        "150.00",
        "100.00",
    )
