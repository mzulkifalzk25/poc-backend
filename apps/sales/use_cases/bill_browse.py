from dataclasses import dataclass
from decimal import Decimal

from apps.core.domain.local_days import range_bounds
from apps.sales.domain.bill_cursor import BillCursor
from apps.sales.models import Bill
from apps.sales.repositories.bill_browse import bill_browse_repository as repo


@dataclass(frozen=True)
class BillPage:
    bills: list[Bill]
    next_cursor: BillCursor | None
    count: int
    total: Decimal


def browse_bills(tenant_id: int, timezone_name: str, filters: dict) -> BillPage:
    """Newest first. `date` (or `from`/`to`) are days in the store's time zone;
    the summary covers every bill the filters match, not just this page."""
    query = {key: filters.get(key) for key in ("cashier", "payment", "status")}
    query["bill_no"] = filters.get("search")
    first = filters.get("date") or filters.get("from_date")
    last = filters.get("date") or filters.get("to") or first
    if first:
        query["since"], query["until"] = range_bounds(first, last or first, timezone_name)
    matching = repo.filtered(tenant_id, query)
    count, total = repo.summary(matching)
    limit = filters["limit"]
    rows = repo.page(matching, filters.get("cursor"), limit + 1)
    page, more = rows[:limit], len(rows) > limit
    cursor = BillCursor(page[-1].sold_at, page[-1].id) if more else None
    return BillPage(page, cursor, count, total)


def bill_detail(tenant_id: int, bill_id):
    bill = repo.detail(tenant_id, bill_id)
    if bill is None:
        return None
    return bill, repo.returns_of(bill)
