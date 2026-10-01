from apps.audit.domain.activity_view import Names, actions_for, describe, is_review, rupees

NAMES = Names(users={1: "Zainab Khan"}, products={"7": "Cooking Oil 1L"}, counters={2: "Counter 2"})


def test_filter_groups_map_to_actions():
    assert actions_for("all") is None
    assert actions_for("stock") == ["stock_adjusted", "stock_received"]


def test_money_reads_in_whole_rupees():
    assert rupees("1350.00") == "Rs 1,350"
    assert rupees("569.50") == "Rs 570"


def test_a_refund_reads_like_the_design():
    text = describe(
        "return_processed", 1, "x", None, None, {"amount": "570.00", "items": [{}, {}]}, NAMES
    )

    assert text == "cashier Zainab · 2 items · Rs 570"


def test_a_price_change_names_the_product():
    text = describe("price_changed", 1, "7", {"price": "600.00"}, {"price": "620.00"}, None, NAMES)

    assert text == "Cooking Oil 1L · Rs 600 to Rs 620"


def test_a_stock_adjustment_shows_the_signed_change_and_reason():
    text = describe(
        "stock_adjusted",
        1,
        "7",
        {"qty": "9.000"},
        {"qty": "69.000"},
        {"reason": "count_correction"},
        NAMES,
    )

    assert text == "Cooking Oil 1L · +60 · count correction"


def test_shift_close_says_over_short_or_matched():
    base = {"counter_id": 2}
    over = describe("shift_closed", 1, "s", None, None, {**base, "difference": "150.00"}, NAMES)
    short = describe("shift_closed", 1, "s", None, None, {**base, "difference": "-230.00"}, NAMES)
    even = describe("shift_closed", 1, "s", None, None, {**base, "difference": "0.00"}, NAMES)

    assert over.endswith("Rs 150 over") and short.endswith("Rs 230 short")
    assert even.endswith("cash matched")


def test_review_flags_refunds_deleted_held_bills_and_cash_differences():
    assert is_review("return_processed", {})
    assert is_review("held_bill_deleted", {})
    assert is_review("shift_closed", {"difference": "5.00"})
    assert not is_review("shift_closed", {"difference": "0.00"})
    assert not is_review("price_changed", {})
