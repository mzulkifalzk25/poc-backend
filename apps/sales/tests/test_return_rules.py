from decimal import Decimal

from apps.core.domain.money import Money
from apps.sales.domain.returns import (
    BILL_NOT_FOUND,
    ITEM_NOT_ON_BILL,
    OVER_RETURN,
    BillLine,
    FoundBill,
    ReturnedQty,
    TodayPrice,
    after_return,
    bill_status,
    is_paid_from_drawer,
    merge_returned,
    ordered_return_flags,
    price_return,
)
from apps.sales.domain.totals import TaxRule

NO_TAX = TaxRule(Decimal("0"), prices_include_tax=True)
OIL, RICE, SOAP = 1, 2, 3
TODAY = {
    OIL: TodayPrice(Decimal("55.00"), Decimal("45.00")),
    RICE: TodayPrice(Decimal("1700.00"), Decimal("1500.00")),
    SOAP: TodayPrice(Decimal("120.00"), Decimal("90.00")),
}


def _qty(product_id: int, qty: str) -> ReturnedQty:
    return ReturnedQty(product_id, Decimal(qty))


def _bill(total: str = "1750.00", refunded: str = "0.00", **returned: str) -> FoundBill:
    """Oil 2 x 50.00 and rice 1 x 1650.00, as sold."""
    return FoundBill(
        Money(total),
        Money(refunded),
        {
            OIL: BillLine(11, OIL, Decimal("2"), Decimal("50.00"), Decimal("40.00"),
                          Decimal(returned.get("oil", "0"))),
            RICE: BillLine(12, RICE, Decimal("1"), Decimal("1650.00"), Decimal("1400.00"),
                           Decimal(returned.get("rice", "0"))),
        },
    )  # fmt: skip


def test_lines_for_one_product_are_merged():
    merged = merge_returned([_qty(OIL, "1"), _qty(RICE, "1"), _qty(OIL, "2")])

    assert merged == [_qty(OIL, "3"), _qty(RICE, "1")]


def test_without_a_bill_every_line_is_refunded_at_todays_price():
    refund = price_return([_qty(OIL, "2")], None, False, TODAY, NO_TAX)

    [line] = refund.lines
    assert (line.price_source, line.unit_price, line.bill_item_id) == (
        "current",
        Decimal("55.00"),
        None,
    )
    assert (line.refund_amount, line.cost_snapshot) == (Money("110.00"), Decimal("45.00"))
    assert (refund.total, refund.flags) == (Money("110.00"), set())


def test_a_bill_number_the_server_does_not_know_is_flagged_and_priced_today():
    refund = price_return([_qty(OIL, "1")], None, True, TODAY, NO_TAX)

    assert refund.flags == {BILL_NOT_FOUND}
    assert refund.total == Money("55.00")


def test_a_line_on_the_found_bill_is_refunded_at_the_price_paid():
    refund = price_return([_qty(OIL, "1")], _bill(), True, TODAY, NO_TAX)

    [line] = refund.lines
    assert (line.price_source, line.unit_price, line.bill_item_id, line.cost_snapshot) == (
        "paid",
        Decimal("50.00"),
        11,
        Decimal("40.00"),
    )
    assert (refund.total, refund.flags) == (Money("50.00"), set())


def test_a_product_not_on_the_bill_is_priced_today_and_flagged():
    refund = price_return([_qty(OIL, "1"), _qty(SOAP, "1")], _bill(), True, TODAY, NO_TAX)

    assert [line.price_source for line in refund.lines] == ["paid", "current"]
    assert refund.flags == {ITEM_NOT_ON_BILL}
    assert refund.total == Money("170.00")


def test_returning_more_than_was_bought_is_flagged_over_return():
    refund = price_return([_qty(OIL, "2")], _bill(oil="1"), True, TODAY, NO_TAX)

    assert refund.flags == {OVER_RETURN}
    assert refund.total == Money("100.00")


def test_tax_is_refunded_on_top_when_prices_exclude_it():
    tax = TaxRule(Decimal("17.00"), prices_include_tax=False)

    refund = price_return([_qty(OIL, "1")], None, False, TODAY, tax)

    [line] = refund.lines
    assert (line.refund_amount, line.tax_refund) == (Money("55.00"), Money("9.35"))
    assert refund.total == Money("64.00")


def test_no_tax_is_added_when_prices_include_it():
    tax = TaxRule(Decimal("17.00"), prices_include_tax=True)

    refund = price_return([_qty(OIL, "1")], None, False, TODAY, tax)

    assert refund.lines[0].tax_refund == Money.zero()
    assert refund.total == Money("55.00")


def test_the_return_that_clears_a_bill_pays_what_is_left_of_it():
    bill = _bill(total="1753.00", refunded="50.00", oil="1")

    refund = price_return([_qty(OIL, "1"), _qty(RICE, "1")], bill, True, TODAY, NO_TAX)

    assert refund.total == Money("1703.00")


def test_a_clearing_return_adds_todays_price_for_items_not_on_the_bill():
    bill = _bill(total="1753.00", refunded="50.00", oil="1")

    refund = price_return(
        [_qty(OIL, "1"), _qty(RICE, "1"), _qty(SOAP, "1")], bill, True, TODAY, NO_TAX
    )

    assert refund.total == Money("1823.00")


def test_what_is_left_of_a_bill_never_goes_below_zero():
    bill = _bill(total="1750.00", refunded="1800.00", oil="1", rice="1")

    refund = price_return([_qty(OIL, "1")], bill, True, TODAY, NO_TAX)

    assert refund.total == Money("0.00")


def test_a_return_after_the_bill_is_cleared_is_priced_line_by_line():
    bill = _bill(refunded="1750.00", oil="2", rice="1")

    refund = price_return([_qty(OIL, "1")], bill, True, TODAY, NO_TAX)

    assert refund.flags == {OVER_RETURN}
    assert refund.total == Money("50.00")


def test_after_a_return_the_bill_counts_what_was_taken_and_paid():
    after = after_return(_bill(), [_qty(OIL, "1"), _qty(SOAP, "1")], Money("50.00"))

    assert after.lines[OIL].returned == Decimal("1")
    assert after.lines[RICE].returned == Decimal("0")
    assert after.refunded == Money("50.00")


def test_bill_status_follows_what_was_returned():
    assert bill_status(_bill()) == "paid"
    assert bill_status(_bill(oil="1")) == "partially_refunded"
    assert bill_status(_bill(oil="2", rice="1")) == "refunded"


def test_flags_follow_the_contract_order():
    raised = {"clock_skew", "price_mismatch", BILL_NOT_FOUND, OVER_RETURN, ITEM_NOT_ON_BILL}

    assert ordered_return_flags(raised) == [
        "over_return",
        "item_not_on_bill",
        "bill_not_found",
        "price_mismatch",
        "clock_skew",
    ]


def test_only_cash_refunds_come_from_the_drawer():
    assert is_paid_from_drawer("cash")
    assert not is_paid_from_drawer("card")
    assert not is_paid_from_drawer("wallet")
