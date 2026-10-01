from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from apps.inventory.models import StockReceipt
from apps.reports.models import (
    PurchasesDaily,
    SalesDaily,
    SalesDailyCashier,
    SalesDailyProduct,
    SalesHourly,
)
from apps.sales.tests.factories import make_product
from apps.shifts.tests.conftest import make_cashier
from apps.tenants.tests.helpers import authed_client, make_tenant

D = Decimal
SEPT_19 = date(2026, 9, 19)


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner_client(tenant):
    return authed_client(tenant)[0]


def sales_day(tenant, day: date, **figures) -> None:
    SalesDaily.objects.create(tenant_id=tenant.id, local_date=day, **figures)


@pytest.mark.django_db
def test_money_returns_every_day_with_zeros_and_the_net(owner_client, tenant):
    sales_day(
        tenant,
        SEPT_19,
        bills=2,
        gross=D("1000"),
        cash=D("600"),
        card=D("400"),
        cost=D("800"),
        refund_count=1,
        refund_amount=D("100"),
        refund_cost_recovered=D("80"),
    )
    PurchasesDaily.objects.create(
        tenant_id=tenant.id, local_date=date(2026, 9, 18), amount=D("300")
    )

    body = owner_client.get(
        "/api/v1/reports/money", {"from": "2026-09-17", "to": "2026-09-19", "group": "day"}
    ).json()

    assert [p["period"] for p in body["periods"]] == ["2026-09-17", "2026-09-18", "2026-09-19"]
    quiet, bought, busy = body["periods"]
    assert quiet["sales_total"] == "0.00" and quiet["net"] == "0.00"
    assert bought["stock_bought"] == "300.00" and bought["net"] == "-300.00"
    assert busy["net"] == "900.00" and busy["gross_profit"] == "180.00"
    assert body["totals"]["net"] == "600.00"
    assert body["totals"]["sales_card"] == "400.00"


@pytest.mark.django_db
def test_money_by_month_and_range_limits(owner_client, tenant):
    sales_day(tenant, date(2026, 8, 31), gross=D("10"))
    sales_day(tenant, date(2026, 9, 1), gross=D("20"))

    months = owner_client.get(
        "/api/v1/reports/money", {"from": "2026-08-01", "to": "2026-09-19", "group": "month"}
    ).json()
    too_long = owner_client.get(
        "/api/v1/reports/money", {"from": "2026-01-01", "to": "2026-09-19", "group": "day"}
    )

    assert [(p["period"], p["sales_total"]) for p in months["periods"]] == [
        ("2026-08", "10.00"),
        ("2026-09", "20.00"),
    ]
    assert too_long.status_code == 400
    backwards = owner_client.get(
        "/api/v1/reports/money", {"from": "2026-09-19", "to": "2026-09-01"}
    )
    assert backwards.status_code == 400


@pytest.mark.django_db
def test_money_counts_confirmed_deliveries(owner_client, tenant):
    from apps.inventory.models import Supplier

    supplier = Supplier.objects.create(tenant_id=tenant.id, name="S")
    for status in ("confirmed", "draft"):
        StockReceipt.objects.create(
            tenant_id=tenant.id, supplier=supplier, delivery_date=SEPT_19, status=status
        )

    body = owner_client.get(
        "/api/v1/reports/money", {"from": "2026-09-19", "to": "2026-09-19"}
    ).json()

    assert body["totals"]["deliveries"] == 1


@pytest.mark.django_db
def test_summary_kpis_and_week_buckets(owner_client, tenant):
    sales_day(tenant, date(2026, 9, 13), bills=1, gross=D("100"), cost=D("60"))
    sales_day(tenant, date(2026, 9, 14), bills=3, gross=D("300"), cost=D("200"))

    body = owner_client.get(
        "/api/v1/reports/summary", {"from": "2026-09-13", "to": "2026-09-14", "group": "week"}
    ).json()

    assert body["kpis"] == {
        "revenue": "400.00",
        "gross_profit": "140.00",
        "bills": 4,
        "average_bill": "100.00",
        "refund_count": 0,
    }
    assert [(p["period"], p["revenue"]) for p in body["periods"]] == [
        ("2026-09-07", "100.00"),
        ("2026-09-14", "300.00"),
    ]


@pytest.mark.django_db
def test_summary_by_hour_reads_the_hourly_table(owner_client, tenant):
    SalesHourly.objects.create(
        tenant_id=tenant.id,
        counter_id=1,
        hour_start=datetime(2026, 9, 19, 7, 0, tzinfo=UTC),
        bills=2,
        gross=D("500"),
    )

    body = owner_client.get(
        "/api/v1/reports/summary", {"from": "2026-09-19", "to": "2026-09-19", "group": "hour"}
    ).json()

    assert body["kpis"]["revenue"] == "500.00" and len(body["periods"]) == 1
    assert body["periods"][0]["period"].startswith("2026-09-19T07:00")


@pytest.mark.django_db
def test_categories_cashiers_top_products_and_refunds_by_cashier(owner_client, tenant):
    rice = make_product(tenant.id, barcode="8961000000011", name="Rice", price="100")
    zainab = make_cashier(tenant)
    SalesDailyProduct.objects.create(
        tenant_id=tenant.id,
        local_date=SEPT_19,
        product_id=rice.id,
        qty=D("5"),
        revenue=D("500"),
        cost=D("400"),
    )
    SalesDailyCashier.objects.create(
        tenant_id=tenant.id,
        local_date=SEPT_19,
        cashier_id=zainab.id,
        bills=4,
        revenue=D("500"),
        refund_count=2,
        refund_amount=D("70"),
    )
    zainab.is_active = False
    zainab.save()
    window = {"from": "2026-09-19", "to": "2026-09-19"}

    categories = owner_client.get("/api/v1/reports/categories", window).json()
    top = owner_client.get("/api/v1/reports/top-products", window).json()
    cashiers = owner_client.get("/api/v1/reports/cashiers", window).json()
    refunds = owner_client.get("/api/v1/reports/refunds-by-cashier", window).json()

    assert categories == [
        {
            "name": "Grocery",
            "tint": "green",
            "revenue": "500.00",
            "profit": "100.00",
            "margin": "20.0",
        }
    ]
    assert top == [{"product_id": rice.id, "name": "Rice", "units": "5.000", "revenue": "500.00"}]
    assert cashiers["results"][0]["bills"] == 4 and cashiers["total_cashiers"] == 1
    assert refunds[0]["refunds_count"] == 2 and refunds[0]["is_active"] is False


@pytest.mark.django_db
def test_dashboard_today_series_top_and_low_stock(owner_client, tenant):
    rice = make_product(
        tenant.id, barcode="8961000000011", name="Rice", stock="3", low_stock_alert=D("5")
    )
    sales_day(
        tenant,
        SEPT_19,
        bills=10,
        items=D("30"),
        gross=D("1060"),
        refund_count=1,
        refund_amount=D("60"),
    )
    sales_day(tenant, date(2026, 9, 18), bills=8, items=D("20"), gross=D("1000"))
    SalesDailyProduct.objects.create(
        tenant_id=tenant.id,
        local_date=SEPT_19,
        product_id=rice.id,
        qty=D("30"),
        revenue=D("1060"),
        cost=D("800"),
    )

    body = owner_client.get("/api/v1/reports/dashboard", {"date": "2026-09-19"}).json()

    assert body["today"]["sales"] == "1060.00" and body["today"]["bills"] == 10
    assert body["today"]["sales_change"] == "6.0"
    assert body["today"]["refunds"] == {"count": 1, "amount": "60.00"}
    assert len(body["series_7"]) == 7 and len(body["series_30"]) == 30
    assert body["series_7"][-1] == {"date": "2026-09-19", "sales": "1060.00"}
    assert body["top_products"][0]["name"] == "Rice"
    assert body["categories"][0]["share"] == "100.0"
    assert body["low_stock_count"] == 1 and body["low_stock"][0]["name"] == "Rice"


@pytest.mark.django_db
def test_dashboard_with_no_sales_is_all_zeros(owner_client):
    body = owner_client.get("/api/v1/reports/dashboard").json()

    assert body["today"]["sales"] == "0.00" and body["today"]["sales_change"] is None
    assert body["top_products"] == [] and body["low_stock"] == []


@pytest.mark.django_db
def test_export_is_a_csv_of_the_report(owner_client, tenant):
    sales_day(tenant, SEPT_19, bills=1, gross=D("100"), cost=D("60"))

    response = owner_client.get(
        "/api/v1/reports/export", {"report": "money", "from": "2026-09-19", "to": "2026-09-19"}
    )

    lines = response.content.decode().splitlines()
    assert response["Content-Type"] == "text/csv"
    assert lines[0].startswith("period,sales_total")
    assert lines[1].startswith("2026-09-19,100.00")


@pytest.mark.django_db
def test_other_stores_figures_never_show_and_cashiers_are_refused(owner_client, tenant):
    other = make_tenant("other-mart")
    sales_day(other, SEPT_19, gross=D("999"))
    cashier, _ = authed_client(tenant, "cashier")

    body = owner_client.get(
        "/api/v1/reports/summary", {"from": "2026-09-19", "to": "2026-09-19"}
    ).json()

    assert body["kpis"]["revenue"] == "0.00"
    assert cashier.get("/api/v1/reports/dashboard").status_code == 403
