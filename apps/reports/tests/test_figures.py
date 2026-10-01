from datetime import date
from decimal import Decimal

from apps.reports.domain.figures import (
    DayFigures,
    average,
    days_in,
    gross_profit,
    group_days,
    month_start,
    net,
    percent_change,
    percent_of,
    week_start,
)

D = Decimal


def test_gross_profit_counts_a_restocked_refund_back_and_a_loss_in_full():
    restocked = DayFigures(
        gross=D("1000"), cost=D("800"), refund_amount=D("100"), refund_cost_recovered=D("80")
    )
    thrown_away = DayFigures(
        gross=D("1000"), cost=D("800"), refund_amount=D("100"), refund_cost_recovered=D("0")
    )

    assert gross_profit(restocked) == D("180")
    assert gross_profit(thrown_away) == D("100")


def test_net_is_sales_minus_refunds_minus_stock_bought():
    day = DayFigures(gross=D("1000"), refund_amount=D("100"), stock_bought=D("300"))

    assert net(day) == D("600")


def test_percent_change_needs_something_to_compare_with():
    assert percent_change(D("106.2"), D("100")) == D("6.2")
    assert percent_change(D("50"), D("100")) == D("-50.0")
    assert percent_change(D("5"), D("0")) is None


def test_shares_and_averages_handle_zero():
    assert percent_of(D("38"), D("100")) == D("38.0")
    assert percent_of(D("1"), D("0")) == D("0")
    assert average(D("1062"), 0) == D("0")
    assert average(D("1000"), 3) == D("333.33")


def test_days_run_inclusive_and_periods_start_on_monday_or_the_first():
    assert days_in(date(2026, 9, 18), date(2026, 9, 20)) == [
        date(2026, 9, 18),
        date(2026, 9, 19),
        date(2026, 9, 20),
    ]
    assert week_start(date(2026, 9, 19)) == date(2026, 9, 14)
    assert month_start(date(2026, 9, 19)) == date(2026, 9, 1)


def test_grouping_sums_days_and_cuts_the_edges_to_the_range():
    by_day = {
        date(2026, 9, 18): DayFigures(gross=D("10")),
        date(2026, 9, 19): DayFigures(gross=D("20")),
        date(2026, 9, 21): DayFigures(gross=D("5")),
    }

    weeks = group_days(by_day, date(2026, 9, 18), date(2026, 9, 21), week_start)

    assert [(s, e, f.gross) for s, e, f in weeks] == [
        (date(2026, 9, 14), date(2026, 9, 20), D("30")),
        (date(2026, 9, 21), date(2026, 9, 21), D("5")),
    ]
