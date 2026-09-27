import pytest

from apps.core.domain.money import Money
from apps.shifts.domain.drawer import ShiftSales, check_drawer

LOCAL_MATCH = {"bills": 3, "cash": "266480.00"}


def _sales(**changes) -> ShiftSales:
    figures = {
        "bills": 3,
        "total_sales": Money("300000.00"),
        "cash": Money("266480.00"),
        "card": Money("20000.00"),
        "wallet": Money("13520.00"),
        "refund_count": 3,
        "refund_amount": Money("4000.00"),
        "cash_refunds": Money("2910.00"),
    }
    return ShiftSales(**{**figures, **changes})


def test_expected_cash_is_opening_plus_cash_sales_minus_cash_refunds():
    check = check_drawer(Money("5000"), Money("268570"), _sales(), LOCAL_MATCH, 0)

    assert check.expected_cash == Money("268570.00")
    assert check.difference == Money.zero()


def test_card_and_wallet_never_touch_the_drawer():
    busy = _sales(card=Money("99999"), wallet=Money("5555"))

    assert check_drawer(Money("5000"), Money("0"), busy, {}, 0).expected_cash == Money("268570")


@pytest.mark.parametrize(("counted", "difference"), [("268600", "30.00"), ("268500", "-70.00")])
def test_difference_is_counted_minus_expected(counted, difference):
    check = check_drawer(Money("5000"), Money(counted), _sales(), LOCAL_MATCH, 0)

    assert check.difference == Money(difference)


def test_nothing_sold_expects_the_opening_cash():
    check = check_drawer(
        Money("5000"), Money("5000"), ShiftSales.none(), {"bills": 0, "cash": 0}, 0
    )

    assert check.expected_cash == Money("5000")
    assert check.mismatch is False


def test_summary_uses_the_counters_keys_as_strings():
    summary = check_drawer(Money("5000"), Money("268570"), _sales(), LOCAL_MATCH, 0).summary

    assert summary == {
        "bills": 3,
        "total_sales": "300000.00",
        "cash": "266480.00",
        "card": "20000.00",
        "wallet": "13520.00",
        "refund_count": 3,
        "refund_amount": "4000.00",
        "cash_refunds": "2910.00",
        "expected_cash": "268570.00",
        "difference": "0.00",
    }


def test_matching_counts_are_no_mismatch():
    assert check_drawer(Money("5000"), Money("1"), _sales(), LOCAL_MATCH, 0).mismatch is False


@pytest.mark.parametrize(
    "local",
    [
        {"bills": 2, "cash": "266480.00"},
        {"bills": 3, "cash": "266479.00"},
        {"cash": "266480.00"},
        {"bills": 3},
        {"bills": 3, "cash": "lots"},
        {"bills": True, "cash": "266480.00"},
        {},
    ],
)
def test_a_different_or_unreadable_local_summary_is_a_mismatch(local):
    assert check_drawer(Money("5000"), Money("1"), _sales(), local, 0).mismatch is True


def test_unsynced_sales_at_close_are_a_mismatch():
    assert check_drawer(Money("5000"), Money("1"), _sales(), LOCAL_MATCH, 4).mismatch is True
