from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from apps.core.domain.local_days import range_bounds
from apps.reports.domain.figures import (
    CashierTotals,
    DayFigures,
    LowStockItem,
    ProductTotals,
    days_in,
    group_days,
    month_start,
    week_start,
    with_stock_bought,
)
from apps.reports.repositories.report_queries import (
    ReportQueryRepository,
    report_query_repository,
)

DASHBOARD_TOP = 5
MAX_SUMMARY_DAYS = 366
MAX_MONEY_DAYS = 93
MAX_MONEY_MONTHS = 24

Period = tuple[date, date, DayFigures]


class RangeError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Dashboard:
    day: date
    today: DayFigures
    yesterday: DayFigures
    series_7: list[tuple[date, Decimal]]
    series_30: list[tuple[date, Decimal]]
    categories: list[tuple[ProductTotals, Decimal]]
    top_products: list[ProductTotals]
    low_stock_count: int
    low_stock: list[LowStockItem]


@dataclass(frozen=True)
class Summary:
    totals: DayFigures
    periods: list[Period]
    group: str


@dataclass(frozen=True)
class Money:
    group: str
    periods: list[Period]
    totals: DayFigures
    deliveries: int


def _check_range(first: date, last: date, max_days: int) -> None:
    if last < first:
        raise RangeError("The end date is before the start date.")
    if (last - first).days + 1 > max_days:
        raise RangeError(f"Choose a range of at most {max_days} days.")


def _total(figures: list[DayFigures]) -> DayFigures:
    return sum(figures, DayFigures())


def _series(by_day: dict[date, DayFigures], first: date, last: date) -> list[tuple[date, Decimal]]:
    return [(day, by_day.get(day, DayFigures()).gross) for day in days_in(first, last)]


def dashboard(
    tenant_id: int,
    day: date,
    repo: ReportQueryRepository = report_query_repository,
) -> Dashboard:
    """`day` is the store's today. Categories and top products cover the last 7 days."""
    week_first = day - timedelta(days=6)
    by_day = repo.daily(tenant_id, day - timedelta(days=29), day)
    products = repo.products(tenant_id, week_first, day)
    by_category: dict[str, ProductTotals] = {}
    for product in products:
        name = product.category_name or "Uncategorised"
        known = by_category.get(name)
        by_category[name] = ProductTotals(
            0,
            name,
            product.category_id,
            name,
            product.tint,
            product.qty + (known.qty if known else Decimal("0")),
            product.revenue + (known.revenue if known else Decimal("0")),
            product.cost + (known.cost if known else Decimal("0")),
        )
    revenue_total = sum((c.revenue for c in by_category.values()), Decimal("0"))
    categories = sorted(by_category.values(), key=lambda c: c.revenue, reverse=True)
    low_count, low_items = repo.low_stock(tenant_id, DASHBOARD_TOP)
    return Dashboard(
        day=day,
        today=by_day.get(day, DayFigures()),
        yesterday=by_day.get(day - timedelta(days=1), DayFigures()),
        series_7=_series(by_day, week_first, day),
        series_30=_series(by_day, day - timedelta(days=29), day),
        categories=[(c, revenue_total) for c in categories[:DASHBOARD_TOP]],
        top_products=sorted(products, key=lambda p: p.revenue, reverse=True)[:DASHBOARD_TOP],
        low_stock_count=low_count,
        low_stock=low_items,
    )


def summary(
    tenant_id: int,
    timezone_name: str,
    first: date,
    last: date,
    group: str,
    repo: ReportQueryRepository = report_query_repository,
) -> Summary:
    _check_range(first, last, MAX_SUMMARY_DAYS)
    if group == "hour":
        since, until = range_bounds(first, last, timezone_name)
        hours = repo.hourly(tenant_id, since, until)
        periods = [(h, h, f) for h, f in hours]
        return Summary(_total([f for _, f in hours]), periods, group)
    by_day = repo.daily(tenant_id, first, last)
    key = week_start if group == "week" else (lambda d: d)
    periods = group_days(by_day, first, last, key)
    return Summary(_total(list(by_day.values())), periods, group)


def money(
    tenant_id: int,
    first: date,
    last: date,
    group: str,
    repo: ReportQueryRepository = report_query_repository,
) -> Money:
    """Every period in the range, with zeros where nothing happened."""
    _check_range(first, last, MAX_MONEY_DAYS if group == "day" else MAX_MONEY_MONTHS * 31)
    if (
        group == "month"
        and (last.year - first.year) * 12 + last.month - first.month >= MAX_MONEY_MONTHS
    ):
        raise RangeError(f"Choose a range of at most {MAX_MONEY_MONTHS} months.")
    by_day = repo.daily(tenant_id, first, last)
    bought = repo.purchases(tenant_id, first, last)
    with_stock = {
        day: with_stock_bought(by_day.get(day, DayFigures()), bought.get(day, Decimal("0")))
        for day in days_in(first, last)
    }
    periods = group_days(
        with_stock, first, last, month_start if group == "month" else (lambda d: d)
    )
    return Money(
        group, periods, _total(list(with_stock.values())), repo.deliveries(tenant_id, first, last)
    )


def products_report(
    tenant_id: int, first: date, last: date, repo: ReportQueryRepository = report_query_repository
) -> list[ProductTotals]:
    _check_range(first, last, MAX_SUMMARY_DAYS)
    return repo.products(tenant_id, first, last)


def cashiers_report(
    tenant_id: int, first: date, last: date, repo: ReportQueryRepository = report_query_repository
) -> list[CashierTotals]:
    _check_range(first, last, MAX_SUMMARY_DAYS)
    return repo.cashiers(tenant_id, first, last)
