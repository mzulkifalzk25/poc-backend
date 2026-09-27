from collections import Counter

from apps.catalog.domain.category_rules import TINTS
from apps.catalog.domain.product_rules import UNITS, stock_status
from scripts.seed.barcodes import is_valid_ean13
from scripts.seed.sample_data import CASHIERS, CATEGORIES, COUNTERS, PRODUCTS


def test_ten_products_with_unique_valid_896_barcodes():
    barcodes = [product.barcode for product in PRODUCTS]

    assert len(PRODUCTS) == 10
    assert len(set(barcodes)) == 10
    assert all(code.startswith("896") and is_valid_ean13(code) for code in barcodes)


def test_costs_are_80_to_90_percent_of_price():
    for product in PRODUCTS:
        assert product.price * 80 / 100 <= product.cost <= product.price * 90 / 100, product.name


def test_two_products_are_low_and_one_is_out_of_stock():
    statuses = Counter(
        stock_status(product.stock, product.low_stock_alert, is_archived=False)
        for product in PRODUCTS
    )

    assert statuses == {"in_stock": 7, "low": 2, "out": 1}


def test_products_use_known_units_and_categories():
    names = {category.name for category in CATEGORIES}

    assert all(product.unit in UNITS for product in PRODUCTS)
    assert all(product.category in names for product in PRODUCTS)


def test_seven_categories_each_with_its_own_design_tint():
    assert [category.name for category in CATEGORIES] == [
        "Grocery",
        "Dairy & eggs",
        "Beverages",
        "Snacks",
        "Personal care",
        "Household",
        "Bakery",
    ]
    assert sorted(category.tint for category in CATEGORIES) == sorted(TINTS)


def test_counters_and_cashiers_match_the_sample_store():
    assert [(c.code, c.activated) for c in COUNTERS] == [
        ("001", True),
        ("002", True),
        ("003", False),
    ]
    assert [(c.full_name, c.counter_code, c.is_active) for c in CASHIERS] == [
        ("Zainab Khan", "002", True),
        ("Bilal Raza", "001", True),
        ("Hina Malik", "003", True),
        ("Usman Tariq", None, False),
    ]
