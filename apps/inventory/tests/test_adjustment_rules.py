from decimal import Decimal

from apps.inventory.domain.adjustment import adjustment_delta, movement_type
from apps.inventory.domain.receipt import (
    ReceiptLineFigures,
    costs_more,
    line_total,
    receipt_total,
)


def test_add_and_remove_change_by_the_quantity():
    assert adjustment_delta("add", Decimal("5"), Decimal("9")) == Decimal("5")
    assert adjustment_delta("remove", Decimal("5"), Decimal("9")) == Decimal("-5")


def test_set_changes_by_whatever_reaches_the_count():
    assert adjustment_delta("set", Decimal("69"), Decimal("9")) == Decimal("60")
    assert adjustment_delta("set", Decimal("0"), Decimal("9")) == Decimal("-9")


def test_each_mode_has_its_movement_type():
    assert [movement_type(m) for m in ("add", "remove", "set")] == [
        "adjust_add",
        "adjust_remove",
        "count_correction",
    ]


def test_receipt_totals_round_to_paisa():
    lines = [
        ReceiptLineFigures(Decimal("2.5"), Decimal("10.33"), Decimal("0")),
        ReceiptLineFigures(Decimal("1"), Decimal("4.00"), Decimal("0")),
    ]

    assert line_total(lines[0]) == Decimal("25.83")
    assert receipt_total(lines) == Decimal("29.83")


def test_only_a_higher_cost_than_before_is_a_warning():
    assert costs_more(ReceiptLineFigures(Decimal("1"), Decimal("90"), Decimal("80")))
    assert not costs_more(ReceiptLineFigures(Decimal("1"), Decimal("80"), Decimal("80")))
    assert not costs_more(ReceiptLineFigures(Decimal("1"), Decimal("90"), Decimal("0")))
