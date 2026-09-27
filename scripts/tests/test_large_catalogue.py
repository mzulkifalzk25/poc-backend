from collections import Counter

import pytest
from django.utils import timezone

from apps.catalog.domain.product_rules import UNITS, stock_status
from apps.catalog.models import Product
from apps.inventory.models import StockLevel
from apps.tenants.models import Counter as CounterRow
from apps.tenants.models import Device
from scripts.seed.barcodes import is_valid_ean13
from scripts.seed.demo_tenant import seed_demo_tenant
from scripts.seed.large_catalogue import large_counters, large_products
from scripts.seed.sample_data import CATEGORIES, PRODUCTS


@pytest.fixture(scope="module")
def products():
    return large_products()


def test_has_18462_products_starting_with_the_small_set(products):
    assert len(products) == 18_462
    assert products[: len(PRODUCTS)] == PRODUCTS


def test_barcodes_are_unique_valid_896_ean13(products):
    barcodes = [product.barcode for product in products]

    assert len(set(barcodes)) == len(barcodes)
    assert all(code.startswith("896") and is_valid_ean13(code) for code in barcodes)


def test_names_are_unique(products):
    assert len({product.name for product in products}) == len(products)


def test_every_category_gets_an_even_share(products):
    shares = Counter(product.category for product in products)

    assert set(shares) == {category.name for category in CATEGORIES}
    assert max(shares.values()) - min(shares.values()) <= 2


def test_prices_and_costs_follow_the_small_set_rules(products):
    for product in products:
        assert product.unit in UNITS
        assert product.price >= 20
        assert product.price * 80 / 100 <= product.cost <= product.price * 90 / 100
        assert product.cost == product.cost.to_integral_value()


def test_some_products_are_low_and_some_out_of_stock(products):
    statuses = Counter(
        stock_status(product.stock, product.low_stock_alert, is_archived=False)
        for product in products
    )

    assert set(statuses) == {"in_stock", "low", "out"}
    assert 0 < statuses["out"] < statuses["low"] < statuses["in_stock"]


def test_the_same_catalogue_on_every_run(products):
    assert large_products() == products


def test_forty_counters_with_only_003_left_to_activate():
    counters = large_counters()

    assert [counter.code for counter in counters] == [f"{n:03d}" for n in range(1, 41)]
    assert [counter.code for counter in counters if not counter.activated] == ["003"]


@pytest.mark.django_db
def test_seeds_the_large_set_into_the_database(products):
    result = seed_demo_tenant(timezone.now(), large_counters(), products)

    tenant_id = result.tenant.id
    assert Product.objects.for_tenant(tenant_id).count() == 18_462
    assert StockLevel.objects.for_tenant(tenant_id).count() == 18_462
    assert CounterRow.objects.for_tenant(tenant_id).count() == 40
    assert Device.objects.for_tenant(tenant_id).count() == 39
    assert len(result.device_tokens) == 39
    assert list(result.activation_codes) == ["003"]
