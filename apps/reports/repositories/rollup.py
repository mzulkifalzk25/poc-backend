from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from django.db import connection

from apps.reports.domain.rollup import RollupDeltas, SoldBill, SoldLine
from apps.sales.models import Bill, BillItem, Payment
from apps.tenants.models import Tenant

_SALES_COLUMNS = ("bills", "items", "gross", "tax", "cash", "card", "wallet", "cost")


class RollupRepository(Protocol):
    def claim_pending(self, limit: int) -> list[SoldBill]: ...

    def timezones(self, tenant_ids: set[int]) -> dict[int, str]: ...

    def add(self, deltas: RollupDeltas, now: datetime) -> None: ...

    def mark_rolled_up(self, bill_ids: list[UUID], now: datetime) -> None: ...


def _upsert(table: str, keys: Sequence[str], sums: Sequence[str], rows: list[tuple]) -> None:
    """Adds each row's sums to the existing row with the same keys, or inserts it.
    The last two values of every row are created_at and updated_at."""
    if not rows:
        return
    columns = [*keys, *sums, "created_at", "updated_at"]
    added = ", ".join(f"{name} = {table}.{name} + EXCLUDED.{name}" for name in sums)
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(['%s'] * len(columns))}) "
        f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {added}, updated_at = EXCLUDED.updated_at"
    )
    with connection.cursor() as cursor:
        cursor.executemany(sql, sorted(rows, key=lambda row: row[: len(keys)]))


def _sales_rows(deltas: dict, now: datetime) -> list[tuple]:
    return [
        (*key, *(getattr(delta, name) for name in _SALES_COLUMNS), now, now)
        for key, delta in deltas.items()
    ]


class DjangoRollupRepository:
    def claim_pending(self, limit: int) -> list[SoldBill]:
        """Locks up to `limit` bills not rolled up yet, oldest upload first.
        Rows another runner holds are skipped, never waited for."""
        bills = list(
            Bill.objects.filter(rolled_up_at__isnull=True)
            .order_by("received_at")
            .select_for_update(skip_locked=True)[:limit]
        )
        ids = [bill.id for bill in bills]
        tenants = {bill.tenant_id for bill in bills}
        lines: dict[UUID, list[SoldLine]] = defaultdict(list)
        for item in BillItem.objects.filter(tenant_id__in=tenants, bill_id__in=ids):
            lines[item.bill_id].append(
                SoldLine(item.product_id, item.qty, item.line_total, item.cost_snapshot)
            )
        payments: dict[UUID, list[tuple[str, object]]] = defaultdict(list)
        for payment in Payment.objects.filter(tenant_id__in=tenants, bill_id__in=ids):
            payments[payment.bill_id].append((payment.method, payment.amount))
        return [
            SoldBill(
                id=bill.id,
                tenant_id=bill.tenant_id,
                counter_id=bill.counter_id,
                cashier_id=bill.cashier_id,
                sold_at=bill.sold_at,
                item_count=bill.item_count,
                tax=bill.tax_amount,
                total=bill.total,
                payments=tuple(payments[bill.id]),
                lines=tuple(lines[bill.id]),
            )
            for bill in bills
        ]

    def timezones(self, tenant_ids: set[int]) -> dict[int, str]:
        return dict(Tenant.objects.filter(id__in=tenant_ids).values_list("id", "timezone"))

    def add(self, deltas: RollupDeltas, now: datetime) -> None:
        _upsert(
            "sales_hourly",
            ("tenant_id", "counter_id", "hour_start"),
            _SALES_COLUMNS,
            _sales_rows(deltas.hourly, now),
        )
        _upsert(
            "sales_daily",
            ("tenant_id", "local_date"),
            _SALES_COLUMNS,
            _sales_rows(deltas.daily, now),
        )
        _upsert(
            "sales_daily_product",
            ("tenant_id", "local_date", "product_id"),
            ("qty", "revenue", "cost"),
            [(*key, d.qty, d.revenue, d.cost, now, now) for key, d in deltas.products.items()],
        )
        _upsert(
            "sales_daily_cashier",
            ("tenant_id", "local_date", "cashier_id"),
            ("bills", "revenue"),
            [(*key, d.bills, d.revenue, now, now) for key, d in deltas.cashiers.items()],
        )

    def mark_rolled_up(self, bill_ids: list[UUID], now: datetime) -> None:
        Bill.objects.filter(id__in=bill_ids).update(rolled_up_at=now)


rollup_repository = DjangoRollupRepository()
