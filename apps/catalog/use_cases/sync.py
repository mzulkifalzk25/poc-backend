from dataclasses import dataclass
from datetime import datetime

from apps.catalog.models import Category, Product
from apps.catalog.repositories.categories import CategoryRepository, category_repository
from apps.catalog.repositories.products import ProductRepository, product_repository
from apps.core.domain.cursor import Cursor
from apps.core.domain.sync_cursor import caught_up_cursor
from apps.core.repositories.keyset import cursor_of


@dataclass(frozen=True)
class ProductSyncPage:
    products: list[Product]
    categories: list[Category]
    next_since: Cursor
    has_more: bool


def product_sync_page(
    tenant_id: int,
    since: Cursor | None,
    page_size: int,
    now: datetime,
    products: ProductRepository = product_repository,
    categories: CategoryRepository = category_repository,
) -> ProductSyncPage:
    """`categories` is always the full list, so a deleted category disappears.
    Only the last page steps the cursor back for late commits."""
    rows = products.changed_after(tenant_id, since, page_size + 1)
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    last = cursor_of(rows[-1]) if rows else None
    next_since = last if has_more else caught_up_cursor(last, since, now)
    return ProductSyncPage(rows, categories.active_for_sync(tenant_id), next_since, has_more)
