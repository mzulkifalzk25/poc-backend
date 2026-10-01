from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from django.db.models import Sum

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.catalog.repositories.products import product_repository
from apps.inventory.models import StockReceipt
from apps.reports.domain.figures import CashierTotals, DayFigures, LowStockItem, ProductTotals
from apps.reports.models import (
    PurchasesDaily,
    SalesDaily,
    SalesDailyCashier,
    SalesDailyProduct,
    SalesHourly,
)

_DAY_COLUMNS = (
    "bills",
    "items",
    "gross",
    "cash",
    "card",
    "wallet",
    "cost",
    "refund_count",
    "refund_amount",
    "refund_cost_recovered",
)


def _figures(row: dict) -> DayFigures:
    return DayFigures(**{column: row[column] for column in _DAY_COLUMNS})


class ReportQueryRepository(Protocol):
    def daily(self, tenant_id: int, first: date, last: date) -> dict[date, DayFigures]: ...

    def hourly(
        self, tenant_id: int, since: datetime, until: datetime
    ) -> list[tuple[datetime, DayFigures]]: ...

    def purchases(self, tenant_id: int, first: date, last: date) -> dict[date, Decimal]: ...

    def deliveries(self, tenant_id: int, first: date, last: date) -> int: ...

    def products(self, tenant_id: int, first: date, last: date) -> list[ProductTotals]: ...

    def cashiers(self, tenant_id: int, first: date, last: date) -> list[CashierTotals]: ...

    def low_stock(self, tenant_id: int, limit: int) -> tuple[int, list[LowStockItem]]: ...


class DjangoReportQueryRepository:
    """Reads only the pre-summed tables, never raw bills."""

    def daily(self, tenant_id: int, first: date, last: date) -> dict[date, DayFigures]:
        rows = SalesDaily.objects.for_tenant(tenant_id).filter(
            local_date__gte=first, local_date__lte=last
        )
        return {
            row["local_date"]: _figures(row) for row in rows.values("local_date", *_DAY_COLUMNS)
        }

    def hourly(
        self, tenant_id: int, since: datetime, until: datetime
    ) -> list[tuple[datetime, DayFigures]]:
        rows = SalesHourly.objects.for_tenant(tenant_id).filter(
            hour_start__gte=since, hour_start__lt=until
        )
        totals = rows.values("hour_start").annotate(**{c: Sum(c) for c in _DAY_COLUMNS})
        return sorted(
            ((row["hour_start"], _figures(row)) for row in totals), key=lambda item: item[0]
        )

    def purchases(self, tenant_id: int, first: date, last: date) -> dict[date, Decimal]:
        rows = PurchasesDaily.objects.for_tenant(tenant_id).filter(
            local_date__gte=first, local_date__lte=last
        )
        return dict(rows.values_list("local_date", "amount"))

    def deliveries(self, tenant_id: int, first: date, last: date) -> int:
        return (
            StockReceipt.objects.for_tenant(tenant_id)
            .filter(
                status=StockReceipt.Status.CONFIRMED,
                delivery_date__gte=first,
                delivery_date__lte=last,
            )
            .count()
        )

    def products(self, tenant_id: int, first: date, last: date) -> list[ProductTotals]:
        rows = (
            SalesDailyProduct.objects.for_tenant(tenant_id)
            .filter(local_date__gte=first, local_date__lte=last)
            .values("product_id")
            .annotate(qty=Sum("qty"), revenue=Sum("revenue"), cost=Sum("cost"))
        )
        products = {
            p.id: p
            for p in Product.objects.for_tenant(tenant_id)
            .filter(id__in=[row["product_id"] for row in rows])
            .select_related("category")
        }
        result = []
        for row in rows:
            product = products.get(row["product_id"])
            category = product.category if product else None
            result.append(
                ProductTotals(
                    product_id=row["product_id"],
                    name=product.name if product else f"Product {row['product_id']}",
                    category_id=category.id if category else None,
                    category_name=category.name if category else "",
                    tint=category.tint if category else "",
                    qty=row["qty"],
                    revenue=row["revenue"],
                    cost=row["cost"],
                )
            )
        return result

    def cashiers(self, tenant_id: int, first: date, last: date) -> list[CashierTotals]:
        rows = (
            SalesDailyCashier.objects.for_tenant(tenant_id)
            .filter(local_date__gte=first, local_date__lte=last)
            .values("cashier_id")
            .annotate(
                bills=Sum("bills"),
                revenue=Sum("revenue"),
                refund_count=Sum("refund_count"),
                refund_amount=Sum("refund_amount"),
            )
        )
        users = {
            u.id: u
            for u in User.objects.for_tenant(tenant_id).filter(
                id__in=[row["cashier_id"] for row in rows]
            )
        }
        return [
            CashierTotals(
                cashier_id=row["cashier_id"],
                name=users[row["cashier_id"]].full_name if row["cashier_id"] in users else "",
                is_active=users[row["cashier_id"]].is_active
                if row["cashier_id"] in users
                else False,
                bills=row["bills"],
                revenue=row["revenue"],
                refund_count=row["refund_count"],
                refund_amount=row["refund_amount"],
            )
            for row in rows
        ]

    def low_stock(self, tenant_id: int, limit: int) -> tuple[int, list[LowStockItem]]:
        """Low and out (zero or below) together, emptiest first."""
        low = product_repository.list_rows(tenant_id, {"stock": "low"})
        out = product_repository.list_rows(tenant_id, {"stock": "out"})
        count = low.count() + out.count()
        emptiest = sorted(
            [
                *out.order_by("stock_qty", "name_lc")[:limit],
                *low.order_by("stock_qty", "name_lc")[:limit],
            ],
            key=lambda product: (product.stock_qty, product.name_lc),
        )[:limit]
        return count, [LowStockItem(p.id, p.name, p.stock_qty) for p in emptiest]


report_query_repository = DjangoReportQueryRepository()
