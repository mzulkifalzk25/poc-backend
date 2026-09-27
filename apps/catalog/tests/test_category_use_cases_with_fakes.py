"""The use cases run against in-memory repositories: no database needed."""

from datetime import UTC, datetime

import pytest

from apps.catalog.models import Category
from apps.catalog.use_cases.categories import (
    CategoryHasProductsError,
    TargetCategoryInvalidError,
    create_category,
    delete_category,
    move_products,
)

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


class FakeCategories:
    def __init__(self, *categories: Category):
        self.rows = {c.id: c for c in categories}
        self.saved: list[Category] = []
        self.deleted: list[Category] = []

    def active_in_tenant(self, tenant_id, category_id):
        row = self.rows.get(category_id)
        return row if row and row.tenant_id == tenant_id and row.is_active else None

    def max_sort_order(self, tenant_id):
        orders = [c.sort_order for c in self.rows.values() if c.tenant_id == tenant_id]
        return max(orders, default=None)

    def save_unique(self, category):
        self.saved.append(category)

    def delete(self, category):
        self.deleted.append(category)


class FakeProducts:
    def __init__(self, in_use: set[int] = frozenset()):
        self.in_use = in_use
        self.moves: list[tuple[int, int]] = []

    def any_in_category(self, category):
        return category.id in self.in_use

    def move_category(self, category, target, now):
        self.moves.append((category.id, target.id))
        return 3


def _category(category_id, tenant_id=1, sort_order=1, is_active=True):
    return Category(
        id=category_id, tenant_id=tenant_id, name=f"C{category_id}", tint="green",
        sort_order=sort_order, is_active=is_active,
    )  # fmt: skip


def test_new_category_goes_last_with_a_clean_name():
    categories = FakeCategories(_category(1, sort_order=4))

    created = create_category(1, "  Fresh   Fruit ", "teal", categories=categories)

    assert (created.name, created.sort_order) == ("Fresh Fruit", 5)
    assert categories.saved == [created]


def test_delete_is_blocked_while_products_use_the_category():
    grocery = _category(1)
    categories = FakeCategories(grocery)

    with pytest.raises(CategoryHasProductsError):
        delete_category(grocery, categories=categories, products=FakeProducts({1}))
    assert categories.deleted == []


@pytest.mark.parametrize(
    ("other", "to_category_id"),
    [
        (None, 2),
        (None, 1),
        (_category(2, tenant_id=9), 2),
        (_category(2, is_active=False), 2),
    ],
    ids=["missing", "itself", "other-tenant", "inactive"],
)
def test_move_needs_another_active_category_of_the_tenant(other, to_category_id):
    source = _category(1)
    categories = FakeCategories(source, *([other] if other else []))
    products = FakeProducts()

    with pytest.raises(TargetCategoryInvalidError):
        move_products(source, to_category_id, NOW, categories=categories, products=products)
    assert products.moves == []


def test_move_returns_the_moved_count():
    products = FakeProducts()
    categories = FakeCategories(_category(1), _category(2))

    moved = move_products(_category(1), 2, NOW, categories=categories, products=products)

    assert (moved, products.moves) == (3, [(1, 2)])
