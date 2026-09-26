from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.api.tokens import issue_counter_tokens
from apps.accounts.models import User
from apps.catalog.models import Category, Product
from apps.inventory.models import StockLevel
from apps.tenants.models import Counter, Device
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

PRODUCT_SYNC = "/api/v1/products/sync/"
STOCK_SYNC = "/api/v1/stock/sync/"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def device(tenant):
    counter = Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")
    return activated_device(counter)


@pytest.fixture
def client(device):
    return device_client(device[1])


@pytest.fixture
def grocery(tenant):
    return Category.objects.create(tenant_id=tenant.id, name="Grocery", tint="green", sort_order=1)


def _product(category, barcode, qty="5", **extra) -> Product:
    product = Product.objects.create(
        tenant_id=category.tenant_id,
        barcode=barcode,
        name=f"Item {barcode}",
        name_lc=f"item {barcode}",
        category=category,
        unit="pcs",
        price=Decimal("10.00"),
        cost=Decimal("8.00"),
        **extra,
    )
    StockLevel.objects.create(tenant_id=category.tenant_id, product=product, qty=Decimal(qty))
    return product


def _age_everything(minutes=5):
    old = timezone.now() - timedelta(minutes=minutes)
    Product.objects.update(updated_at=old)
    StockLevel.objects.update(updated_at=old)


def _sync(client, url, **params):
    response = client.get(url, params)
    assert response.status_code == 200, response.json()
    return response.json()


@pytest.mark.django_db
def test_full_sync_sends_products_with_archived_and_categories_without_cost(client, grocery):
    _product(grocery, "1")
    _product(grocery, "2", is_archived=True)

    body = _sync(client, PRODUCT_SYNC, since="0")

    assert [p["barcode"] for p in body["products"]] == ["1", "2"]
    assert body["products"][1]["is_archived"] is True
    assert all("cost" not in p for p in body["products"])
    assert body["categories"] == [
        {"id": grocery.id, "name": "Grocery", "tint": "green", "sort_order": 1}
    ]
    assert body["has_more"] is False and body["next_since"]


@pytest.mark.django_db
def test_pages_through_rows_that_share_one_timestamp_without_repeats(client, grocery):
    for n in range(5):
        _product(grocery, str(n))
    Product.objects.update(updated_at=timezone.now() - timedelta(minutes=5))

    seen, since, pages = [], "0", 0
    while True:
        body = _sync(client, PRODUCT_SYNC, since=since, page_size=2)
        seen += [p["barcode"] for p in body["products"]]
        since, pages = body["next_since"], pages + 1
        if not body["has_more"]:
            break

    assert pages == 3
    assert seen == ["0", "1", "2", "3", "4"]


@pytest.mark.django_db
def test_delta_sends_only_what_changed(client, grocery):
    _product(grocery, "1")
    changed = _product(grocery, "2")
    _age_everything()
    since = _sync(client, PRODUCT_SYNC)["next_since"]
    changed.price = Decimal("12.00")
    changed.save()

    body = _sync(client, PRODUCT_SYNC, since=since)

    assert [(p["barcode"], p["price"]) for p in body["products"]] == [("2", "12.00")]


@pytest.mark.django_db
def test_recent_rows_are_sent_again_inside_the_overlap(client, grocery):
    _product(grocery, "1")

    first = _sync(client, PRODUCT_SYNC)
    again = _sync(client, PRODUCT_SYNC, since=first["next_since"])

    assert [p["barcode"] for p in again["products"]] == ["1"]


@pytest.mark.django_db
def test_archiving_reaches_the_counter(tenant, client, grocery):
    product = _product(grocery, "1")
    _age_everything()
    since = _sync(client, PRODUCT_SYNC)["next_since"]
    owner, _ = authed_client(tenant)
    owner.post(f"/api/v1/products/{product.id}/archive")

    body = _sync(client, PRODUCT_SYNC, since=since)

    assert body["products"][0]["is_archived"] is True


@pytest.mark.django_db
def test_sync_never_sends_another_tenants_rows(client, grocery):
    theirs = Category.objects.create(tenant_id=make_tenant("other-mart").id, name="X", tint="blue")
    _product(theirs, "999")

    body = _sync(client, PRODUCT_SYNC)

    assert body["products"] == [] and body["categories"] == [
        {"id": grocery.id, "name": "Grocery", "tint": "green", "sort_order": 1}
    ]
    assert _sync(client, STOCK_SYNC)["levels"] == []


@pytest.mark.django_db
@pytest.mark.parametrize("url", [PRODUCT_SYNC, STOCK_SYNC])
def test_signed_in_cashier_on_the_pc_can_sync(tenant, device, grocery, url):
    _product(grocery, "1")
    cashier = User.objects.create(tenant_id=tenant.id, full_name="Zainab Khan", role="cashier")
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {issue_counter_tokens(cashier, device[0].id).access_token}"
    )

    assert client.get(url).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("url", [PRODUCT_SYNC, STOCK_SYNC])
def test_sync_refuses_owners_strangers_and_revoked_pcs(tenant, client, device, url):
    owner, _ = authed_client(tenant)
    assert owner.get(url).status_code == 403
    assert APIClient().get(url).status_code == 401
    Device.objects.filter(id=device[0].id).update(revoked_at=timezone.now())
    response = client.get(url)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "device_revoked"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("params", "field"), [({"since": "garbage"}, "since"), ({"page_size": 2001}, "page_size")]
)
def test_bad_sync_parameters_are_400(client, params, field):
    response = client.get(PRODUCT_SYNC, params)

    assert response.status_code == 400
    assert response.json()["error"]["fields"][field]


@pytest.mark.django_db
def test_stock_sync_full_then_delta(client, grocery):
    first = _product(grocery, "1", qty="5")
    second = _product(grocery, "2", qty="-1.5")
    _age_everything()

    full = _sync(client, STOCK_SYNC, since="0")
    level = StockLevel.objects.get(product=first)
    level.qty = Decimal("4.000")
    level.save()
    delta = _sync(client, STOCK_SYNC, since=full["next_since"])

    assert full["levels"] == [
        {"product_id": first.id, "qty": "5.000"},
        {"product_id": second.id, "qty": "-1.500"},
    ]
    assert delta["levels"] == [{"product_id": first.id, "qty": "4.000"}]
