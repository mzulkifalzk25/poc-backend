from datetime import date
from decimal import Decimal

import pytest

from apps.audit.models import ActivityLog
from apps.catalog.models import Product
from apps.inventory.models import StockLevel
from apps.reports.models import PurchasesDaily
from apps.tenants.tests.helpers import authed_client, make_tenant

SUPPLIERS = "/api/v1/suppliers"
RECEIPTS = "/api/v1/stock/receipts"


def _supplier(client) -> int:
    return client.post(SUPPLIERS, {"name": "Metro Traders", "phone": "0300"}).json()["id"]


def _draft(client, supplier_id, lines, day="2026-09-19") -> dict:
    body = {
        "supplier_id": supplier_id,
        "invoice_no": "INV-1",
        "delivery_date": day,
        "lines": lines,
    }
    return client.post(RECEIPTS, body, format="json").json()


@pytest.mark.django_db
def test_suppliers_are_created_and_listed_with_unique_names(owner_client):
    _supplier(owner_client)

    again = owner_client.post(SUPPLIERS, {"name": "Metro Traders"})

    assert again.status_code == 409
    assert [s["name"] for s in owner_client.get(SUPPLIERS).json()] == ["Metro Traders"]


@pytest.mark.django_db
def test_a_draft_changes_nothing_until_confirmed(owner_client, make_product):
    product = make_product("Rice", qty="10", cost="80.00")

    draft = _draft(
        owner_client,
        _supplier(owner_client),
        [{"product_id": product.id, "qty": "20", "unit_cost": "90.00"}],
    )

    assert draft["status"] == "draft"
    assert draft["total_cost"] == "1800.00"
    assert StockLevel.objects.get(product=product).qty == Decimal("10")
    assert Product.objects.get(id=product.id).cost == Decimal("80.00")


@pytest.mark.django_db
def test_confirming_adds_stock_sets_cost_and_counts_money_out(owner_client, make_product):
    rice = make_product("Rice", qty="10", cost="80.00")
    oil = make_product("Oil", qty="0", cost="100.00")
    draft = _draft(
        owner_client,
        _supplier(owner_client),
        [
            {"product_id": rice.id, "qty": "20", "unit_cost": "90.00"},
            {"product_id": oil.id, "qty": "5", "unit_cost": "100.00"},
        ],
    )

    response = owner_client.post(f"{RECEIPTS}/{draft['id']}/confirm")

    body = response.json()
    assert response.status_code == 200 and body["status"] == "confirmed"
    assert [i["name"] for i in body["cost_increase_items"]] == ["Rice"]
    assert StockLevel.objects.get(product=rice).qty == Decimal("30")
    assert StockLevel.objects.get(product=oil).qty == Decimal("5")
    assert Product.objects.get(id=rice.id).cost == Decimal("90.00")
    assert PurchasesDaily.objects.get(local_date=date(2026, 9, 19)).amount == Decimal("2300.00")
    assert ActivityLog.objects.filter(action="stock_received").count() == 1


@pytest.mark.django_db
def test_confirming_twice_adds_nothing_more(owner_client, make_product):
    product = make_product("Rice", qty="10")
    draft = _draft(
        owner_client,
        _supplier(owner_client),
        [{"product_id": product.id, "qty": "20", "unit_cost": "90.00"}],
    )

    owner_client.post(f"{RECEIPTS}/{draft['id']}/confirm")
    again = owner_client.post(f"{RECEIPTS}/{draft['id']}/confirm")

    assert again.status_code == 200
    assert StockLevel.objects.get(product=product).qty == Decimal("30")
    assert PurchasesDaily.objects.get().amount == Decimal("1800.00")


@pytest.mark.django_db
def test_two_deliveries_on_one_day_add_up(owner_client, make_product):
    product = make_product("Rice")
    supplier = _supplier(owner_client)
    for _ in range(2):
        draft = _draft(
            owner_client, supplier, [{"product_id": product.id, "qty": "1", "unit_cost": "50"}]
        )
        owner_client.post(f"{RECEIPTS}/{draft['id']}/confirm")

    assert PurchasesDaily.objects.get().amount == Decimal("100.00")


@pytest.mark.django_db
def test_a_receipt_needs_a_known_supplier_and_products(owner_client, make_product):
    product = make_product("Rice")
    line = [{"product_id": product.id, "qty": "1", "unit_cost": "5"}]
    body = {"supplier_id": 999, "delivery_date": "2026-09-19", "lines": line}

    unknown_supplier = owner_client.post(RECEIPTS, body, format="json")
    unknown_product = owner_client.post(
        RECEIPTS,
        {**body, "supplier_id": _supplier(owner_client), "lines": [{**line[0], "product_id": 999}]},
        format="json",
    )
    no_lines = owner_client.post(RECEIPTS, {**body, "lines": []}, format="json")

    assert unknown_supplier.status_code == unknown_product.status_code == 400
    assert no_lines.status_code == 400


@pytest.mark.django_db
def test_history_and_detail_are_this_stores_only(owner_client, make_product, tenant):
    product = make_product("Rice")
    draft = _draft(
        owner_client,
        _supplier(owner_client),
        [{"product_id": product.id, "qty": "1", "unit_cost": "5"}],
    )
    stranger, _ = authed_client(make_tenant("other"))

    assert owner_client.get(RECEIPTS).json()["count"] == 1
    assert owner_client.get(f"{RECEIPTS}/{draft['id']}").json()["lines"][0]["name"] == "Rice"
    assert stranger.get(f"{RECEIPTS}/{draft['id']}").status_code == 404
    assert stranger.post(f"{RECEIPTS}/{draft['id']}/confirm").status_code == 404
