from datetime import datetime

from apps.catalog.domain.category_rules import next_sort_order, normalize_category_name
from apps.catalog.models import Category
from apps.catalog.repositories.categories import CategoryRepository, category_repository
from apps.catalog.repositories.products import ProductRepository, product_repository


class CategoryHasProductsError(Exception):
    pass


class TargetCategoryInvalidError(Exception):
    pass


def category_list(
    tenant_id: int, categories: CategoryRepository = category_repository
) -> list[Category]:
    return categories.list_with_counts(tenant_id)


def find_category(
    tenant_id: int, category_id: int, categories: CategoryRepository = category_repository
) -> Category | None:
    return categories.in_tenant(tenant_id, category_id)


def create_category(
    tenant_id: int, name: str, tint: str, categories: CategoryRepository = category_repository
) -> Category:
    category = Category(
        tenant_id=tenant_id,
        name=normalize_category_name(name),
        tint=tint,
        sort_order=next_sort_order(categories.max_sort_order(tenant_id)),
    )
    categories.save_unique(category)
    return category


def update_category(
    category: Category, changes: dict, categories: CategoryRepository = category_repository
) -> Category:
    if "name" in changes:
        category.name = normalize_category_name(changes["name"])
    if "tint" in changes:
        category.tint = changes["tint"]
    categories.save_unique(category)
    return category


def delete_category(
    category: Category,
    categories: CategoryRepository = category_repository,
    products: ProductRepository = product_repository,
) -> None:
    """Archived products still point at their category, so they count too."""
    if products.any_in_category(category):
        raise CategoryHasProductsError
    categories.delete(category)


def move_products(
    category: Category,
    to_category_id: int,
    now: datetime,
    categories: CategoryRepository = category_repository,
    products: ProductRepository = product_repository,
) -> int:
    """Moves live and archived products to another active category of the tenant."""
    target = categories.active_in_tenant(category.tenant_id, to_category_id)
    if target is None or target.id == category.id:
        raise TargetCategoryInvalidError
    return products.move_category(category, target, now)
