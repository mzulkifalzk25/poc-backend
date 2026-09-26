from decimal import Decimal

import pytest

from apps.catalog.domain.product_rules import (
    UNITS,
    name_key,
    normalize_barcode,
    normalize_product_name,
    stock_status,
)


def test_units_are_the_four_design_units():
    assert UNITS == ("pcs", "kg", "litre", "pack")


def test_names_are_trimmed_and_the_search_key_is_lower_case():
    assert normalize_product_name("  Cooking   Oil 1L ") == "Cooking Oil 1L"
    assert name_key("  Cooking   Oil 1L ") == "cooking oil 1l"


@pytest.mark.parametrize(
    ("raw", "expected"), [(" 8961002300022 ", "8961002300022"), ("ABC-123", "ABC-123")]
)
def test_barcodes_keep_their_value_without_outer_spaces(raw, expected):
    assert normalize_barcode(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "896 100", "x" * 65])
def test_empty_spaced_or_too_long_barcodes_are_invalid(raw):
    assert normalize_barcode(raw) is None


@pytest.mark.parametrize(
    ("qty", "alert", "archived", "expected"),
    [
        ("5", "10", True, "archived"),
        ("-2", "10", False, "negative"),
        ("0", "10", False, "out"),
        ("10", "10", False, "low"),
        ("3.5", "10", False, "low"),
        ("11", "10", False, "in_stock"),
        ("1", "0", False, "in_stock"),
    ],
)
def test_stock_status(qty, alert, archived, expected):
    assert stock_status(Decimal(qty), Decimal(alert), archived) == expected
