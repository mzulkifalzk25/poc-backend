from django.db import IntegrityError, transaction
from django.db.models import Max

from apps.catalog.domain.category_rules import next_sort_order, normalize_category_name
from apps.catalog.models import Category

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
