from decimal import Decimal

import pytest

from apps.audit.models import ActivityLog
from apps.inventory.models import StockLevel, StockMovement
from apps.tenants.tests.helpers import authed_client, make_tenant

STOCK = "/api/v1/stock"
ADJUST = "/api/v1/stock/adjust"
MOVES = "/api/v1/stock/movements"


def _qty(product) -> Decimal:
    return StockLevel.objects.get(product=product).qty


@pytest.mark.django_db
def test_the_stock_list_filters_and_summarises(owner_client, make_product):
    make_product("Rice", qty="40")
    make_product("Oil", qty="3")
    make_product("Sugar", qty="0")
    make_product("Milk", qty="-2")

    everything = owner_client.get(STOCK).json()
    low = owner_client.get(STOCK, {"status": "low"}).json()
    negative = owner_client.get(STOCK, {"status": "negative"}).json()

    assert everything["count"] == 4
    assert everything["summary"] == {
        "units_in_stock": "43.000",
        "stock_value": "3440.00",
        "low_count": 1,
        "out_count": 2,
    }
    assert [r["name"] for r in low["results"]] == ["Oil"]
    assert [r["name"] for r in negative["results"]] == ["Milk"]
    assert low["results"][0]["low_stock_alert"] == "5.000"


@pytest.mark.django_db
def test_other_stores_stock_is_not_listed(owner_client, make_product):
    other = make_tenant("other-mart")
    make_product("Theirs", tenant_id=other.id)

    assert owner_client.get(STOCK).json()["count"] == 0


@pytest.mark.django_db
def test_a_cashier_cannot_read_stock(tenant):
    client, _ = authed_client(tenant, "cashier")

    assert client.get(STOCK).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("mode", "qty", "after"),
    [("add", "60", "69.000"), ("remove", "4", "5.000"), ("set", "20", "20.000")],
)
def test_an_adjustment_changes_the_level_and_is_logged(
    owner_client, make_product, mode, qty, after
):
    product = make_product("Rice", qty="9")

    response = owner_client.post(
        ADJUST,
        {"product_id": product.id, "mode": mode, "qty": qty, "reason": "damaged", "note": "box"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json() == {"before": "9.000", "after": after}
    assert _qty(product) == Decimal(after)
    assert StockMovement.objects.filter(product=product, reason="damaged").count() == 1
    log = ActivityLog.objects.get(action="stock_adjusted")
    assert log.after == {"qty": after}


@pytest.mark.django_db
def test_remove_may_go_below_zero(owner_client, make_product):
    product = make_product("Rice", qty="2")

    owner_client.post(
        ADJUST,
        {"product_id": product.id, "mode": "remove", "qty": "5", "reason": "stolen_lost"},
        format="json",
    )

    assert _qty(product) == Decimal("-3")


@pytest.mark.django_db
def test_the_same_key_applies_once(owner_client, make_product):
    product = make_product("Rice", qty="9")
    body = {"product_id": product.id, "mode": "add", "qty": "1", "reason": "received"}

    first = owner_client.post(ADJUST, body, format="json", headers={"Idempotency-Key": "k1"})
    again = owner_client.post(ADJUST, body, format="json", headers={"Idempotency-Key": "k1"})

    assert first.json() == again.json() == {"before": "9.000", "after": "10.000"}
    assert _qty(product) == Decimal("10")


@pytest.mark.django_db
def test_a_reason_is_required_and_quantity_must_be_positive(owner_client, make_product):
    product = make_product("Rice")

    no_reason = owner_client.post(
        ADJUST, {"product_id": product.id, "mode": "add", "qty": "1"}, format="json"
    )
    zero = owner_client.post(
        ADJUST,
        {"product_id": product.id, "mode": "add", "qty": "0", "reason": "received"},
        format="json",
    )

    assert no_reason.status_code == zero.status_code == 400


@pytest.mark.django_db
def test_another_stores_product_is_not_found(owner_client, make_product):
    other = make_tenant("other-mart")
    theirs = make_product("Theirs", tenant_id=other.id)

    response = owner_client.post(
        ADJUST,
        {"product_id": theirs.id, "mode": "add", "qty": "1", "reason": "received"},
        format="json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_movements_list_newest_first_with_a_cursor_and_type_filter(owner_client, make_product):
    product = make_product("Rice", qty="0")
    for qty in ("1", "2", "3"):
        owner_client.post(
            ADJUST,
            {"product_id": product.id, "mode": "add", "qty": qty, "reason": "received"},
            format="json",
        )

    first = owner_client.get(MOVES, {"type": "adjust", "limit": 2}).json()
    rest = owner_client.get(
        MOVES, {"type": "adjust", "limit": 2, "cursor": first["next_cursor"]}
    ).json()

    assert [m["qty_delta"] for m in first["results"]] == ["3.000", "2.000"]
    assert [m["qty_delta"] for m in rest["results"]] == ["1.000"]
    assert rest["next_cursor"] is None
    assert first["results"][0]["user"] == "Owner"
    assert first["results"][0]["product"]["name"] == "Rice"
