from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from apps.reports.domain.rollup import (
    RefundedReturn,
    ReturnedLine,
    RollupDeltas,
    SoldBill,
    SoldLine,
    local_hour,
    sum_bills,
    sum_returns,
)

KARACHI = "Asia/Karachi"
D = Decimal


def bill(sold_at: datetime, method: str = "cash", **extra) -> SoldBill:
    lines = extra.pop(
        "lines",
        (SoldLine(product_id=7, qty=D("2"), line_total=D("1240"), cost_snapshot=D("540.33")),),
    )
    values = {
        "id": uuid4(),
        "tenant_id": 1,
        "counter_id": 2,
        "cashier_id": 5,
        "sold_at": sold_at,
        "item_count": D("2"),
        "tax": D("0"),
        "total": D("1240"),
        "payments": ((method, D("1240")),),
        "lines": lines,
    }
    return SoldBill(**{**values, **extra})


def test_buckets_by_the_tenant_local_hour_and_day():
    late_evening_utc = datetime(2026, 9, 18, 20, 30, tzinfo=UTC)

    hour = local_hour(late_evening_utc, KARACHI)

    assert hour == datetime(2026, 9, 19, 1, 0, tzinfo=ZoneInfo(KARACHI))
    assert hour.date() == date(2026, 9, 19)


def test_sums_bills_in_the_same_hour_and_splits_by_payment_method():
    at = datetime(2026, 9, 19, 7, 5, tzinfo=UTC)
    later = datetime(2026, 9, 19, 7, 55, tzinfo=UTC)

    deltas = sum_bills([bill(at), bill(later, method="card")], {1: KARACHI})

    ((hour_key, hourly),) = deltas.hourly.items()
    assert hour_key == (1, 2, datetime(2026, 9, 19, 12, 0, tzinfo=ZoneInfo(KARACHI)))
    assert (hourly.bills, hourly.items, hourly.gross) == (2, D("4"), D("2480"))
    assert (hourly.cash, hourly.card, hourly.wallet) == (D("1240"), D("1240"), D("0"))
    assert hourly.cost == D("2161.32")
    assert deltas.daily[(1, date(2026, 9, 19))].bills == 2


def test_keeps_counters_apart_by_hour_but_together_by_day():
    at = datetime(2026, 9, 19, 7, 5, tzinfo=UTC)

    deltas = sum_bills([bill(at), bill(at, counter_id=3)], {1: KARACHI})

    assert len(deltas.hourly) == 2
    assert deltas.daily[(1, date(2026, 9, 19))].bills == 2


def test_sums_products_and_cashiers_per_day():
    at = datetime(2026, 9, 19, 7, 5, tzinfo=UTC)
    rice = SoldLine(product_id=9, qty=D("1"), line_total=D("1650"), cost_snapshot=D("1480"))

    deltas = sum_bills(
        [bill(at), bill(at, cashier_id=6, lines=(rice,), total=D("1650"))], {1: KARACHI}
    )

    oil = deltas.products[(1, date(2026, 9, 19), 7)]
    assert (oil.qty, oil.revenue, oil.cost) == (D("2"), D("1240"), D("1080.66"))
    assert deltas.products[(1, date(2026, 9, 19), 9)].revenue == D("1650")
    assert deltas.cashiers[(1, date(2026, 9, 19), 5)].revenue == D("1240")
    assert deltas.cashiers[(1, date(2026, 9, 19), 6)].bills == 1


def test_keeps_tenants_apart_in_their_own_time_zones():
    at = datetime(2026, 9, 18, 20, 30, tzinfo=UTC)

    deltas = sum_bills([bill(at), bill(at, tenant_id=2)], {1: KARACHI, 2: "UTC"})

    assert set(deltas.daily) == {(1, date(2026, 9, 19)), (2, date(2026, 9, 18))}


def refund(returned_at: datetime, restock: bool = True, **extra) -> RefundedReturn:
    values = {
        "id": uuid4(),
        "tenant_id": 1,
        "counter_id": 2,
        "cashier_id": 5,
        "returned_at": returned_at,
        "refund_total": D("621"),
        "restock": restock,
        "lines": (
            ReturnedLine(product_id=7, qty=D("1"), refund=D("620.00"), cost_snapshot=D("540.33")),
        ),
    }
    return RefundedReturn(**{**values, **extra})


def test_a_return_fills_the_refund_columns_and_leaves_sales_gross():
    sale = bill(datetime(2026, 9, 19, 6, 10, tzinfo=UTC))
    back = refund(datetime(2026, 9, 19, 6, 40, tzinfo=UTC))

    deltas = sum_returns([back], {1: KARACHI}, sum_bills([sale], {1: KARACHI}))

    [day] = deltas.daily.values()
    assert (day.bills, day.gross) == (1, D("1240"))
    assert (day.refund_count, day.refund_amount, day.refund_cost_recovered) == (
        1,
        D("621"),
        D("540.33"),
    )
    [hour] = deltas.hourly.values()
    assert (hour.refund_count, hour.refund_amount) == (1, D("621"))
    [product] = deltas.products.values()
    assert (product.qty, product.returns_qty, product.refund_amount) == (
        D("2"),
        D("1"),
        D("620.00"),
    )
    [cashier] = deltas.cashiers.values()
    assert (cashier.bills, cashier.refund_count, cashier.refund_amount) == (1, 1, D("621"))


def test_a_return_not_restocked_recovers_no_cost():
    deltas = sum_returns(
        [refund(datetime(2026, 9, 19, 6, 40, tzinfo=UTC), restock=False)],
        {1: KARACHI},
        RollupDeltas(),
    )

    [day] = deltas.daily.values()
    assert (day.refund_amount, day.refund_cost_recovered) == (D("621"), D("0"))


def test_a_return_lands_on_the_day_it_happened_not_the_sale_day():
    after_midnight_karachi = datetime(2026, 9, 19, 19, 30, tzinfo=UTC)

    deltas = sum_returns([refund(after_midnight_karachi)], {1: KARACHI}, RollupDeltas())

    assert list(deltas.daily) == [(1, date(2026, 9, 20))]
    assert list(deltas.cashiers) == [(1, date(2026, 9, 20), 5)]
