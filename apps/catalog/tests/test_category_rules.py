import pytest

from apps.catalog.domain.category_rules import (
    TINTS,
    is_valid_tint,
    next_sort_order,
    normalize_category_name,
)


def test_the_seven_design_tints_are_valid():
    assert TINTS == ("green", "blue", "orange", "pink", "purple", "teal", "yellow")
    assert all(is_valid_tint(tint) for tint in TINTS)


@pytest.mark.parametrize("tint", ["", "red", "Green", "#E3F3EA"])
def test_other_values_are_not_tints(tint):
    assert not is_valid_tint(tint)


def test_names_are_trimmed_and_inner_spaces_collapsed():
    assert normalize_category_name("  Dairy   &  eggs ") == "Dairy & eggs"


def test_new_categories_go_last():
    assert next_sort_order(None) == 1
    assert next_sort_order(7) == 8
