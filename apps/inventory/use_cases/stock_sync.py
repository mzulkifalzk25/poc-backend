from dataclasses import dataclass
from datetime import datetime

from apps.core.domain.cursor import Cursor
from apps.core.domain.sync_cursor import caught_up_cursor
from apps.core.repositories.keyset import cursor_of
from apps.inventory.models import StockLevel
from apps.inventory.repositories.stock_levels import StockLevelRepository, stock_level_repository


@dataclass(frozen=True)
class StockSync:
    levels: list[StockLevel]
    next_since: Cursor


def stock_since(
    tenant_id: int,
    since: Cursor | None,
    now: datetime,
    stock: StockLevelRepository = stock_level_repository,
) -> StockSync:
    """Not paged (the contract shape has no `has_more`): one small row per
    product, all changes since the cursor."""
    rows = stock.changed_after(tenant_id, since)
    last = cursor_of(rows[-1]) if rows else None
    return StockSync(rows, caught_up_cursor(last, since, now))
