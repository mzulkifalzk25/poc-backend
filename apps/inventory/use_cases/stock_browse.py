from dataclasses import dataclass

from django.db.models import QuerySet

from apps.core.domain.cursor import Cursor
from apps.inventory.models import StockMovement
from apps.inventory.repositories.stock_admin import StockAdminRepository, stock_admin_repository


@dataclass(frozen=True)
class MovementPage:
    movements: list[StockMovement]
    users: dict[int, str]
    next_cursor: Cursor | None


def stock_rows(
    tenant_id: int, filters: dict, repo: StockAdminRepository = stock_admin_repository
) -> QuerySet:
    return repo.stock_rows(tenant_id, filters)


def stock_summary(tenant_id: int, repo: StockAdminRepository = stock_admin_repository) -> dict:
    return repo.summary(tenant_id)


def browse_movements(
    tenant_id: int,
    filters: dict,
    cursor: Cursor | None,
    limit: int,
    repo: StockAdminRepository = stock_admin_repository,
) -> MovementPage:
    """Newest first; the next cursor is set only when more rows follow."""
    rows = repo.movements(tenant_id, filters, cursor, limit + 1)
    page, more = rows[:limit], len(rows) > limit
    users = repo.user_names(tenant_id, {m.user_id for m in page if m.user_id})
    next_cursor = Cursor(page[-1].occurred_at, page[-1].id) if more else None
    return MovementPage(page, users, next_cursor)
