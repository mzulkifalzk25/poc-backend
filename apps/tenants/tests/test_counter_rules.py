import pytest

from apps.tenants.domain.counter_rules import (
    CounterCodeLockedError,
    ensure_code_can_change,
    format_bill_no,
    is_valid_counter_code,
    next_bill_no,
)


def test_valid_three_digit_codes():
    assert is_valid_counter_code("001")
    assert is_valid_counter_code("999")


def test_invalid_codes_are_rejected():
    assert not is_valid_counter_code("12")
    assert not is_valid_counter_code("1234")
    assert not is_valid_counter_code("abc")
    assert not is_valid_counter_code("")


def test_code_can_change_before_the_first_bill():
    ensure_code_can_change(current_code="001", new_code="002", last_bill_seq=0)


def test_code_is_locked_after_the_first_bill():
    with pytest.raises(CounterCodeLockedError):
        ensure_code_can_change(current_code="001", new_code="002", last_bill_seq=1)


def test_keeping_the_same_code_is_always_allowed():
    ensure_code_can_change(current_code="001", new_code="001", last_bill_seq=743)


def test_next_bill_no_is_one_past_the_last_sequence():
    assert next_bill_no(0) == 1
    assert next_bill_no(742) == 743


def test_format_bill_no_matches_the_contract_shape():
    assert format_bill_no("002", 743) == "002000743"
