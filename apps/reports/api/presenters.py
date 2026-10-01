from datetime import date
from decimal import Decimal

from apps.reports.domain.figures import (
    CashierTotals,
    DayFigures,
    average,
    gross_profit,
    net,
    percent_change,
    percent_of,
)
from apps.reports.use_cases.reports import Dashboard, Money, Period, Summary

MONEY = Decimal("0.01")
QTY = Decimal("0.001")


def _s(value: Decimal) -> str:
    return str(value.quantize(MONEY))


def _pct(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def present_dashboard(data: Dashboard) -> dict:
    today, yesterday = data.today, data.yesterday
    category_total = data.categories[0][1] if data.categories else Decimal("0")
    return {
        "date": data.day.isoformat(),
        "today": {
            "sales": _s(today.gross),
            "bills": today.bills,
            "items": str(today.items.quantize(QTY)),
            "refunds": {"count": today.refund_count, "amount": _s(today.refund_amount)},
            "sales_change": _pct(percent_change(today.gross, yesterday.gross)),
            "bills_change": _pct(percent_change(Decimal(today.bills), Decimal(yesterday.bills))),
            "items_change": _pct(percent_change(today.items, yesterday.items)),
        },
        "low_stock_count": data.low_stock_count,
        "series_7": [{"date": d.isoformat(), "sales": _s(v)} for d, v in data.series_7],
        "series_30": [{"date": d.isoformat(), "sales": _s(v)} for d, v in data.series_30],
        "categories": [
            {
                "name": c.name,
                "tint": c.tint,
                "revenue": _s(c.revenue),
                "share": str(percent_of(c.revenue, total)),
            }
            for c, total in data.categories
        ],
        "category_total": _s(category_total),
        "top_products": [
            {
                "product_id": p.product_id,
                "name": p.name,
                "units": str(p.qty.quantize(QTY)),
                "revenue": _s(p.revenue),
            }
            for p in data.top_products
        ],
        "low_stock": [
            {"product_id": i.product_id, "name": i.name, "stock": str(i.qty.quantize(QTY))}
            for i in data.low_stock
        ],
    }


def _period(start: date, end: date, figures: DayFigures) -> dict:
    return {
        "period": start.isoformat(),
        "end": end.isoformat(),
        "revenue": _s(figures.gross),
        "gross_profit": _s(gross_profit(figures)),
        "bills": figures.bills,
    }


def present_summary(data: Summary) -> dict:
    totals = data.totals
    return {
        "group": data.group,
        "kpis": {
            "revenue": _s(totals.gross),
            "gross_profit": _s(gross_profit(totals)),
            "bills": totals.bills,
            "average_bill": _s(average(totals.gross, totals.bills)),
            "refund_count": totals.refund_count,
        },
        "periods": [_period(*period) for period in data.periods],
    }


def _money_figures(figures: DayFigures) -> dict:
    return {
        "sales_total": _s(figures.gross),
        "sales_cash": _s(figures.cash),
        "sales_card": _s(figures.card),
        "sales_wallet": _s(figures.wallet),
        "refunds_total": _s(figures.refund_amount),
        "refunds_count": figures.refund_count,
        "stock_bought": _s(figures.stock_bought),
        "net": _s(net(figures)),
        "gross_profit": _s(gross_profit(figures)),
    }


def present_money(data: Money) -> dict:
    period_label = (
        (lambda d: d.strftime("%Y-%m")) if data.group == "month" else (lambda d: d.isoformat())
    )
    return {
        "group": data.group,
        "periods": [
            {"period": period_label(start), **_money_figures(figures)}
            for start, _end, figures in data.periods
        ],
        "totals": {
            **_money_figures(data.totals),
            "deliveries": data.deliveries,
            "profit_margin": str(percent_of(gross_profit(data.totals), data.totals.gross)),
            "refund_rate": str(percent_of(data.totals.refund_amount, data.totals.gross)),
        },
    }


def present_refunds_by_cashier(rows: list[CashierTotals]) -> list[dict]:
    refunding = [r for r in rows if r.refund_count > 0]
    return [
        {
            "cashier_id": r.cashier_id,
            "name": r.name,
            "is_active": r.is_active,
            "refunds_count": r.refund_count,
            "refunds_amount": _s(r.refund_amount),
        }
        for r in sorted(refunding, key=lambda r: r.refund_amount, reverse=True)
    ]


def present_cashiers(rows: list[CashierTotals], limit: int) -> dict:
    top = sorted(rows, key=lambda r: r.revenue, reverse=True)
    return {
        "total_cashiers": len(rows),
        "refund_count": sum(r.refund_count for r in rows),
        "results": [
            {
                "cashier_id": r.cashier_id,
                "name": r.name,
                "is_active": r.is_active,
                "bills": r.bills,
                "revenue": _s(r.revenue),
            }
            for r in top[:limit]
        ],
    }


def present_categories(rows) -> list[dict]:
    totals: dict[str, dict] = {}
    for row in rows:
        name = row.category_name or "Uncategorised"
        entry = totals.setdefault(
            name,
            {"name": name, "tint": row.tint, "revenue": Decimal("0"), "cost": Decimal("0")},
        )
        entry["revenue"] += row.revenue
        entry["cost"] += row.cost
    result = []
    for entry in sorted(totals.values(), key=lambda e: e["revenue"], reverse=True):
        profit = entry["revenue"] - entry["cost"]
        result.append(
            {
                "name": entry["name"],
                "tint": entry["tint"],
                "revenue": _s(entry["revenue"]),
                "profit": _s(profit),
                "margin": str(percent_of(profit, entry["revenue"])),
            }
        )
    return result


def present_top_products(rows, limit: int) -> list[dict]:
    top = sorted(rows, key=lambda p: p.revenue, reverse=True)[:limit]
    return [
        {
            "product_id": p.product_id,
            "name": p.name,
            "units": str(p.qty.quantize(QTY)),
            "revenue": _s(p.revenue),
        }
        for p in top
    ]


__all__ = [
    "Period",
    "present_categories",
    "present_cashiers",
    "present_dashboard",
    "present_money",
    "present_refunds_by_cashier",
    "present_summary",
    "present_top_products",
]
