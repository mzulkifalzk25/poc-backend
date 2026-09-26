from datetime import datetime

from django.db import IntegrityError, transaction
from django.db.models import Max

from apps.catalog.domain.category_rules import next_sort_order, normalize_category_name
from apps.catalog.models import Category, Product

_NAME_CONSTRAINT = "uniq_category_tenant_name_lower"


class CategoryNameExistsError(Exception):
    pass


def create_category(tenant_id: int, name: str, tint: str) -> Category:
    categories = Category.objects.for_tenant(tenant_id)
    current_max = categories.aggregate(top=Max("sort_order"))["top"]
    category = Category(
        tenant_id=tenant_id,
        name=normalize_category_name(name),
        tint=tint,
        sort_order=next_sort_order(current_max),
    )
    _save(category)
    return category


def update_category(category: Category, changes: dict) -> Category:
    if "name" in changes:
        category.name = normalize_category_name(changes["name"])
    if "tint" in changes:
        category.tint = changes["tint"]
    _save(category)
    return category


def _save(category: Category) -> None:
    try:
        with transaction.atomic():
            category.save()
    except IntegrityError as error:
        if _NAME_CONSTRAINT in str(error):
            raise CategoryNameExistsError from None
        raise


class CategoryHasProductsError(Exception):
    pass


class TargetCategoryInvalidError(Exception):
    pass


def delete_category(category: Category) -> None:
    """Archived products still point at their category, so they count too."""
    if Product.objects.for_tenant(category.tenant_id).filter(category=category).exists():
        raise CategoryHasProductsError
    category.delete()


def move_products(category: Category, to_category_id: int, now: datetime) -> int:
    """Moves live and archived products. `updated_at` is set explicitly
    (a bulk update skips auto_now) so counters pick the change up in sync."""
    target = (
        Category.objects.for_tenant(category.tenant_id)
        .filter(id=to_category_id, is_active=True)
        .exclude(id=category.id)
        .first()
    )
    if target is None:
        raise TargetCategoryInvalidError
    products = Product.objects.for_tenant(category.tenant_id).filter(category=category)
    return products.update(category=target, updated_at=now)
