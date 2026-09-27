from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.core.domain.money import Money
from apps.sales.domain.bill_number import (
    counter_code_of,
    is_valid_bill_no,
    normalize_bill_no,
    sequence_of,
)
from apps.sales.domain.flags import (
    is_bill_no_conflict,
    is_clock_skewed,
    negative_stock_bills,
    ordered_flags,
)
from apps.sales.domain.lines import SaleLine, merge_lines
from apps.sales.domain.totals import TaxRule, bill_totals, total_differs

NO_TAX = TaxRule(Decimal("0"), prices_include_tax=False)
NOON = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def _line(product_id: int, qty: str, price: str, line_no: int = 1) -> SaleLine:
    return SaleLine(
        line_no, product_id, f"896{product_id}", f"Item {product_id}", Decimal(qty), Decimal(price)
    )


def test_repeated_products_are_merged_into_the_first_row():
    lines = [_line(1, "2", "50.00", 1), _line(2, "1", "10.00", 2), _line(1, "3", "55.00", 3)]

    merged = merge_lines(lines)

    assert [(line.product_id, line.qty, line.unit_price, line.line_no) for line in merged] == [
        (1, Decimal("5"), Decimal("50.00"), 1),
        (2, Decimal("1"), Decimal("10.00"), 2),
    ]


def test_totals_without_tax_round_to_a_whole_rupee():
    totals = bill_totals([_line(1, "3", "33.35"), _line(2, "1", "0.20")], NO_TAX)

    assert (totals.item_count, totals.subtotal, totals.tax) == (
        Decimal("4"),
        Money("100.25"),
        Money("0"),
    )
    assert (totals.rounding, totals.total) == (Money("-0.25"), Money("100.00"))


def test_half_a_rupee_rounds_up():
    totals = bill_totals([_line(1, "1", "100.50")], NO_TAX)

    assert (totals.total, totals.rounding) == (Money("101.00"), Money("0.50"))


def test_tax_added_on_top_of_the_prices():
    totals = bill_totals(
        [_line(1, "5", "50.00")], TaxRule(Decimal("17.00"), prices_include_tax=False)
    )

    assert (totals.subtotal, totals.tax, totals.total) == (
        Money("250.00"),
        Money("42.50"),
        Money("293.00"),
    )
    assert totals.rounding == Money("0.50")


def test_tax_inside_the_prices_does_not_change_the_total():
    totals = bill_totals(
        [_line(1, "1", "1170.00")], TaxRule(Decimal("17.00"), prices_include_tax=True)
    )

    assert (totals.tax, totals.total, totals.rounding) == (
        Money("170.00"),
        Money("1170.00"),
        Money("0"),
    )


def test_included_tax_is_rounded_to_the_paisa():
    totals = bill_totals(
        [_line(1, "1", "100.00")], TaxRule(Decimal("17.00"), prices_include_tax=True)
    )

    assert totals.tax == Money("14.53")


@pytest.mark.parametrize(
    ("sent", "differs"), [("100.00", False), ("101.00", False), ("98.99", True), ("101.01", True)]
)
def test_a_total_differs_only_beyond_one_rupee(sent, differs):
    assert total_differs(Money(sent), Money("100.00")) is differs


def test_bill_numbers_are_nine_digits():
    assert is_valid_bill_no("002000743")
    assert not any(
        is_valid_bill_no(text)
        for text in ["002-000743", "00200074", "0020007430", "00200074a", "٠٠٢٠٠٠٧٤٣"]
    )
    assert (counter_code_of("002000743"), sequence_of("002000743")) == ("002", 743)
    assert normalize_bill_no(" 002-000743 ") == "002000743"


def test_clock_skew_is_a_sale_more_than_five_minutes_in_the_future():
    assert not is_clock_skewed(NOON + timedelta(minutes=5), NOON)
    assert is_clock_skewed(NOON + timedelta(minutes=5, seconds=1), NOON)
    assert not is_clock_skewed(NOON - timedelta(days=3), NOON)


@pytest.mark.parametrize(
    ("bill_no", "taken", "conflict"),
    [("002000743", False, False), ("002000743", True, True), ("001000743", False, True)],
)
def test_a_bill_number_conflicts_when_taken_or_from_another_counter(bill_no, taken, conflict):
    assert is_bill_no_conflict(bill_no, "002", taken) is conflict


def test_negative_stock_flags_the_bill_that_goes_below_zero():
    levels = {1: Decimal("3"), 2: Decimal("10")}
    bills = [
        {1: Decimal("2")},
        {2: Decimal("1")},
        {1: Decimal("2"), 2: Decimal("1")},
        {3: Decimal("1")},
    ]

    assert negative_stock_bills(levels, bills) == [False, False, True, True]


def test_flags_come_in_a_fixed_order():
    raised = {
        "negative_stock",
        "price_mismatch",
        "bill_no_conflict",
        "clock_skew",
        "total_mismatch",
    }

    assert ordered_flags(raised) == [
        "price_mismatch",
        "clock_skew",
        "total_mismatch",
        "bill_no_conflict",
        "negative_stock",
    ]
    assert ordered_flags(set()) == []
