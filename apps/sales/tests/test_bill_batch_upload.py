from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import PriceHistory
from apps.sales.models import Bill, BillItem, Payment
from apps.tenants.models import TenantSettings

from .conftest import cashier_client, make_cashier
from .payloads import BATCH_URL, batch, bill, line


def _post(client, counter, *bills):
    return client.post(BATCH_URL, batch(counter.id, *bills), format="json")


@pytest.mark.django_db
def test_a_new_bill_is_stored_as_sent(pc, counter, device, cashier, oil):
    body = bill(cashier.id, [line(oil, "5.000")])

    response = _post(pc, counter, body)

    assert response.status_code == 200
    assert response.json()["server_time"]
    assert response.json()["results"] == [
        {"id": body["id"], "status": "created", "bill_no": "002000743", "flags": [], "errors": []}
    ]
    stored = Bill.objects.get(id=body["id"])
    assert (stored.counter_id, stored.cashier_id, str(stored.shift_id)) == (
        counter.id,
        cashier.id,
        body["shift_id"],
    )
    assert (stored.total, stored.item_count, stored.device_id) == (
        Decimal("250.00"),
        Decimal("5"),
        device[0].id,
    )
    assert stored.received_at is not None and stored.rolled_up_at is None
    item = BillItem.objects.get(bill_id=body["id"])
    assert (item.qty, item.line_total, item.cost_snapshot) == (
        Decimal("5"),
        Decimal("250.00"),
        oil.cost,
    )
    assert (item.name_snapshot, item.barcode_snapshot) == (oil.name, oil.barcode)
    payment = Payment.objects.get(bill_id=body["id"])
    assert (payment.method, payment.amount, payment.tendered) == (
        "cash",
        Decimal("250.00"),
        Decimal("350.00"),
    )


@pytest.mark.django_db
def test_the_same_batch_twice_creates_each_bill_once(pc, counter, cashier, oil, rice):
    bills = [bill(cashier.id, [line(oil)], seq=1), bill(cashier.id, [line(rice)], seq=2)]
    _post(pc, counter, *bills)

    again = _post(pc, counter, *bills)

    assert [result["status"] for result in again.json()["results"]] == ["duplicate", "duplicate"]
    assert Bill.objects.count() == 2
    assert BillItem.objects.count() == 2
    assert Payment.objects.count() == 2


@pytest.mark.django_db
def test_a_bill_repeated_inside_one_batch_is_a_duplicate(pc, counter, cashier, oil):
    body = bill(cashier.id, [line(oil)])

    response = _post(pc, counter, body, body)

    assert [r["status"] for r in response.json()["results"]] == ["created", "duplicate"]
    assert Bill.objects.count() == 1


@pytest.mark.django_db
def test_a_duplicate_reports_the_stored_flags(pc, counter, cashier, oil):
    body = bill(cashier.id, [line(oil, price="45.00")])
    first = _post(pc, counter, body).json()["results"][0]

    again = _post(pc, counter, body).json()["results"][0]

    assert first["flags"] == again["flags"] == ["price_mismatch"]


@pytest.mark.django_db
def test_repeated_product_lines_are_merged(pc, counter, cashier, oil, rice):
    lines = [line(oil, "2.000", line_no=1), line(rice, line_no=2), line(oil, "3.000", line_no=3)]

    _post(pc, counter, bill(cashier.id, lines))

    oil_row = BillItem.objects.get(product=oil)
    assert (oil_row.qty, oil_row.line_no, oil_row.line_total) == (
        Decimal("5"),
        1,
        Decimal("250.00"),
    )
    assert BillItem.objects.count() == 2


@pytest.mark.django_db
def test_one_bad_bill_never_blocks_the_rest(pc, counter, cashier, oil):
    good = bill(cashier.id, [line(oil)], seq=1)
    bad = bill(cashier.id, [{**line(oil), "product_id": 999999}], seq=2)

    results = _post(pc, counter, good, bad).json()["results"]

    assert [r["status"] for r in results] == ["created", "rejected"]
    assert results[1]["errors"] == ["items.0.product_id: Unknown product."]
    assert str(Bill.objects.get().id) == good["id"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"bill_no": "002-000743"}, "bill_no: A bill number is 9 digits."),
        ({"items": []}, "items"),
        ({"payment": {"id": "x", "method": "cheque", "amount": "1.00"}}, "payment.method"),
        ({"sold_at": "noon"}, "sold_at"),
        ({"id": "not-a-uuid"}, "id"),
    ],
)
def test_malformed_bills_are_rejected_with_their_errors(pc, counter, cashier, oil, change, error):
    body = {**bill(cashier.id, [line(oil)]), **change}

    result = _post(pc, counter, body).json()["results"][0]

    assert result["status"] == "rejected"
    assert any(text.startswith(error) for text in result["errors"])
    assert result["bill_no"] == body["bill_no"]
    assert not Bill.objects.exists()


@pytest.mark.django_db
def test_a_non_positive_quantity_is_rejected(pc, counter, cashier, oil):
    result = _post(pc, counter, bill(cashier.id, [line(oil, "0.000")])).json()["results"][0]

    assert result["status"] == "rejected"
    assert result["errors"][0].startswith("items.0.qty:")


@pytest.mark.django_db
def test_archived_products_and_deactivated_cashiers_still_upload(pc, tenant, counter, oil):
    gone = make_cashier(tenant, "Usman Tariq", is_active=False)
    oil.is_archived = True
    oil.save()

    result = _post(pc, counter, bill(gone.id, [line(oil)])).json()["results"][0]

    assert result["status"] == "created"


@pytest.mark.django_db
def test_a_total_off_by_more_than_a_rupee_is_kept_and_flagged(pc, counter, cashier, oil):
    body = bill(cashier.id, [line(oil, "5.000")])
    body["totals"] = {**body["totals"], "total": "248.00"}
    close = bill(cashier.id, [line(oil, "5.000")], seq=744)
    close["totals"] = {**close["totals"], "total": "251.00"}

    results = _post(pc, counter, body, close).json()["results"]

    assert results[0]["flags"] == ["total_mismatch"]
    assert results[1]["flags"] == []
    assert Bill.objects.get(id=body["id"]).total == Decimal("248.00")


@pytest.mark.django_db
def test_tax_settings_are_used_to_recompute(pc, tenant, counter, cashier, oil):
    TenantSettings.objects.create(tenant=tenant, tax_rate="17.00", prices_include_tax=False)
    body = bill(cashier.id, [line(oil, "5.000")])
    body["totals"] = {**body["totals"], "tax": "42.50", "rounding": "0.50", "total": "293.00"}
    plain = bill(cashier.id, [line(oil, "5.000")], seq=744)

    results = _post(pc, counter, body, plain).json()["results"]

    assert [r["flags"] for r in results] == [[], ["total_mismatch"]]


@pytest.mark.django_db
def test_a_price_other_than_the_one_in_force_is_flagged(pc, counter, cashier, oil):
    PriceHistory.objects.create(
        tenant_id=oil.tenant_id,
        product=oil,
        old_price=Decimal("45.00"),
        new_price=Decimal("50.00"),
        changed_at=timezone.now(),
    )
    old_price = bill(cashier.id, [line(oil, price="45.00")], seq=1)
    new_price = bill(cashier.id, [line(oil, price="50.00")], seq=2)
    odd_price = bill(cashier.id, [line(oil, price="47.00")], seq=3)

    results = _post(pc, counter, old_price, new_price, odd_price).json()["results"]

    assert [r["flags"] for r in results] == [[], ["price_mismatch"], ["price_mismatch"]]


@pytest.mark.django_db
def test_a_sale_from_the_future_is_flagged_clock_skew(pc, counter, cashier, oil):
    later = (timezone.now() + timedelta(minutes=30)).isoformat()

    result = _post(pc, counter, bill(cashier.id, [line(oil)], sold_at=later)).json()["results"][0]

    assert (result["status"], result["flags"]) == ("created", ["clock_skew"])


@pytest.mark.django_db
def test_a_taken_bill_number_is_accepted_and_flagged(pc, counter, cashier, oil):
    first = bill(cashier.id, [line(oil)], seq=743)
    second = bill(cashier.id, [line(oil)], seq=743)
    _post(pc, counter, first)

    result = _post(pc, counter, second).json()["results"][0]

    assert (result["status"], result["flags"]) == ("created", ["bill_no_conflict"])
    assert Bill.objects.filter(bill_no="002000743").count() == 2
    assert Bill.objects.get(id=first["id"]).flags == []


@pytest.mark.django_db
def test_the_same_number_twice_in_one_batch_flags_the_second(pc, counter, cashier, oil):
    results = _post(
        pc, counter, bill(cashier.id, [line(oil)]), bill(cashier.id, [line(oil)])
    ).json()["results"]

    assert [r["flags"] for r in results] == [[], ["bill_no_conflict"]]


@pytest.mark.django_db
def test_another_counters_prefix_is_accepted_and_flagged(pc, counter, cashier, oil):
    result = _post(pc, counter, bill(cashier.id, [line(oil)], code="001")).json()["results"][0]

    assert (result["status"], result["flags"]) == ("created", ["bill_no_conflict"])
    counter.refresh_from_db()
    assert counter.last_bill_seq == 0


@pytest.mark.django_db
def test_the_counter_sequence_only_goes_up(pc, counter, cashier, oil):
    _post(pc, counter, bill(cashier.id, [line(oil)], seq=743), bill(cashier.id, [line(oil)], seq=9))
    counter.refresh_from_db()
    assert counter.last_bill_seq == 743

    _post(pc, counter, bill(cashier.id, [line(oil)], seq=12))

    counter.refresh_from_db()
    assert counter.last_bill_seq == 743


@pytest.mark.django_db
def test_a_signed_in_cashier_uploads_too(device, counter, cashier, oil):
    response = _post(cashier_client(cashier, device[0]), counter, bill(cashier.id, [line(oil)]))

    assert response.json()["results"][0]["status"] == "created"


@pytest.mark.django_db
@pytest.mark.parametrize("count", [0, 101])
def test_a_batch_holds_one_to_a_hundred_bills(pc, counter, cashier, oil, count):
    bills = [bill(cashier.id, [line(oil)], seq=n + 1) for n in range(count)]

    response = _post(pc, counter, *bills)

    assert response.status_code == 400
    assert "bills" in response.json()["error"]["fields"]


@pytest.mark.django_db
def test_the_counter_comes_from_the_pc(pc, counter, cashier, oil):
    body = batch(counter.id + 1000, bill(cashier.id, [line(oil)]))

    response = pc.post(BATCH_URL, body, format="json")

    assert response.status_code == 400
    assert not Bill.objects.exists()
