from decimal import Decimal

from apps.core.domain.money import Money


def test_quantizes_to_two_decimal_places():
    assert Money("10.005").as_string() == "10.01"
    assert Money("10").as_string() == "10.00"


def test_addition_and_subtraction():
    total = Money("250.50") + Money("19.50")
    assert total.as_string() == "270.00"
    assert (total - Money("20.00")).as_string() == "250.00"


def test_multiplication_by_quantity():
    line_total = Money("50.00") * Decimal("5.000")
    assert line_total.as_string() == "250.00"


def test_equality_and_ordering():
    assert Money("10.00") == Money("10.00")
    assert Money("9.99") < Money("10.00")
    assert Money("9.99") <= Money("9.99")


def test_round_to_whole_rupee_rounds_half_up():
    assert Money("250.50").round_to_whole_rupee().as_string() == "251.00"
    assert Money("250.49").round_to_whole_rupee().as_string() == "250.00"
    assert Money("250.00").round_to_whole_rupee().as_string() == "250.00"


def test_rounding_adjustment_is_the_difference():
    money = Money("250.50")
    assert money.rounding_adjustment().as_string() == "0.50"
    assert Money("250.00").rounding_adjustment().as_string() == "0.00"


def test_zero_is_a_valid_starting_point():
    assert Money.zero().as_string() == "0.00"
    assert (Money.zero() + Money("5.00")).as_string() == "5.00"
