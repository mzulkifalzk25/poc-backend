from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.core.domain.local_days import range_bounds
from apps.sales.domain.bill_search import bill_no_digits
from apps.sales.models import BillItem, Payment
from apps.sales.tests.factories import make_bill, make_product, make_return
from apps.tenants.tests.helpers import authed_client, make_tenant

BILLS = "/api/v1/bills"


@pytest.fixture
def owner_client(tenant):
    return authed_client(tenant)[0]


def _at(day: int, hour: int = 10) -> datetime:
    return datetime(2026, 9, day, hour, 0, tzinfo=UTC)


def _paid(bill, method="cash") -> None:
    Payment.objects.create(
        id=uuid4(), tenant_id=bill.tenant_id, bill=bill, method=method, amount=bill.total
    )


def test_bill_numbers_search_with_or_without_the_dash():
    assert bill_no_digits("002-000743") == bill_no_digits("002000743") == "002000743"
    assert bill_no_digits("002-0") == "0020"


def test_a_local_day_runs_from_local_midnight():
    start, end = range_bounds(
        datetime(2026, 9, 19).date(), datetime(2026, 9, 19).date(), "Asia/Karachi"
    )

    assert start == datetime(2026, 9, 18, 19, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 19, 19, 0, tzinfo=UTC)


@pytest.mark.django_db
def test_the_list_is_newest_first_with_a_summary_and_cursor(owner_client, counter, cashier):
    for n, hour in enumerate((8, 9, 10), start=1):
        make_bill(counter, cashier, f"00200000{n}", sold_at=_at(19, hour))

    first = owner_client.get(BILLS, {"limit": 2}).json()
    rest = owner_client.get(BILLS, {"limit": 2, "cursor": first["next_cursor"]}).json()

    assert first["summary"] == {"bills": 3, "total": "1860.00"}
    assert [b["bill_no"] for b in first["results"]] == ["002000003", "002000002"]
    assert [b["bill_no"] for b in rest["results"]] == ["002000001"]
    assert rest["next_cursor"] is None
    assert first["results"][0]["cashier"] == cashier.full_name


@pytest.mark.django_db
def test_filters_by_day_cashier_payment_status_and_number(owner_client, counter, cashier, tenant):
    today = make_bill(counter, cashier, "002000001", sold_at=_at(19))
    _paid(today, "cash")
    card = make_bill(counter, cashier, "002000002", sold_at=_at(19, 11), status="refunded")
    _paid(card, "card")
    make_bill(counter, cashier, "002000003", sold_at=_at(18))

    day = owner_client.get(BILLS, {"date": "2026-09-19"}).json()
    by_card = owner_client.get(BILLS, {"payment": "card"}).json()
    refunded = owner_client.get(BILLS, {"status": "refunded"}).json()
    searched = owner_client.get(BILLS, {"search": "002-000003"}).json()
    nobody = owner_client.get(BILLS, {"cashier": cashier.id + 1}).json()
    span = owner_client.get(BILLS, {"from": "2026-09-18", "to": "2026-09-19"}).json()

    assert day["summary"]["bills"] == 2
    assert [b["bill_no"] for b in by_card["results"]] == ["002000002"]
    assert [b["bill_no"] for b in refunded["results"]] == ["002000002"]
    assert [b["bill_no"] for b in searched["results"]] == ["002000003"]
    assert nobody["results"] == []
    assert span["summary"]["bills"] == 3


@pytest.mark.django_db
def test_another_stores_bills_are_never_listed(owner_client, tenant):
    from apps.tenants.models import Counter

    other = make_tenant("other-mart")
    counter = Counter.objects.create(tenant_id=other.id, name="C", code="001")
    from apps.shifts.tests.conftest import make_cashier

    make_bill(counter, make_cashier(other), "001000001")

    assert owner_client.get(BILLS).json()["summary"]["bills"] == 0


@pytest.mark.django_db
def test_detail_has_lines_payment_totals_and_returns(owner_client, counter, cashier, tenant):
    bill = make_bill(counter, cashier, "002000001", sold_at=_at(19))
    _paid(bill)
    product = make_product(tenant.id)
    BillItem.objects.create(
        tenant_id=tenant.id,
        bill=bill,
        line_no=1,
        product=product,
        name_snapshot="Cooking Oil 1L",
        barcode_snapshot=product.barcode,
        qty=Decimal("1"),
        unit_price=Decimal("620.00"),
        cost_snapshot=Decimal("540.00"),
        line_total=Decimal("620.00"),
        sold_at=bill.sold_at,
    )
    make_return(counter, cashier, original_bill=bill)

    body = owner_client.get(f"{BILLS}/{bill.id}").json()

    assert body["counter"]["code"] == "002"
    assert body["payment"]["method"] == "cash"
    assert body["items"][0]["name"] == "Cooking Oil 1L"
    assert body["totals"]["total"] == "620.00"
    assert len(body["returns"]) == 1


@pytest.mark.django_db
def test_a_missing_or_foreign_bill_is_404(owner_client):
    assert owner_client.get(f"{BILLS}/{uuid4()}").status_code == 404


@pytest.mark.django_db
def test_a_cashier_cannot_browse_bills(tenant):
    client, _ = authed_client(tenant, "cashier")

    assert client.get(BILLS).status_code == 403
