from dataclasses import dataclass
from datetime import datetime

from apps.audit.domain.activity_view import Names, actions_for
from apps.audit.models import ActivityLog
from apps.audit.repositories.activity_browse import activity_browse_repository as repo
from apps.core.domain.cursor import Cursor
from apps.core.domain.local_days import local_today, range_bounds


@dataclass(frozen=True)
class ActivityPage:
    rows: list[ActivityLog]
    next_cursor: Cursor | None
    names: Names
    header: dict[str, int]


def _query(filters: dict, timezone_name: str) -> dict:
    query = {"actions": actions_for(filters.get("type", "all")), "user": filters.get("user")}
    first, last = filters.get("from_date"), filters.get("to")
    if first or last:
        query["since"], query["until"] = range_bounds(first or last, last or first, timezone_name)
    return query


def matching_rows(tenant_id: int, timezone_name: str, filters: dict):
    return repo.filtered(tenant_id, _query(filters, timezone_name))


def names_for(tenant_id: int, rows: list[ActivityLog]) -> Names:
    counters = {r.detail["counter_id"] for r in rows if r.detail and r.detail.get("counter_id")}
    products = {r.entity_id for r in rows if r.entity_type == "product"}
    return Names(
        users=repo.user_names(tenant_id, {r.user_id for r in rows if r.user_id}),
        products=repo.product_names(tenant_id, products),
        counters=repo.counter_names(tenant_id, counters),
    )


def browse_activity(
    tenant_id: int, timezone_name: str, now: datetime, filters: dict
) -> ActivityPage:
    limit = filters["limit"]
    rows = repo.page(
        matching_rows(tenant_id, timezone_name, filters), filters.get("cursor"), limit + 1
    )
    page, more = rows[:limit], len(rows) > limit
    today = local_today(now, timezone_name)
    counts = repo.counts_in(tenant_id, *range_bounds(today, today, timezone_name))
    header = {
        "held_bills_deleted_today": counts.get("held_bill_deleted", 0),
        "refunds_today": counts.get("return_processed", 0),
        "price_changes_today": counts.get("price_changed", 0),
    }
    cursor = Cursor(page[-1].occurred_at, page[-1].id) if more else None
    return ActivityPage(page, cursor, names_for(tenant_id, page), header)
