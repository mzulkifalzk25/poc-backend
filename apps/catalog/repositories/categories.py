from typing import Protocol

from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q

from apps.catalog.domain.errors import CategoryNameExistsError
from apps.catalog.models import Category

_NAME_CONSTRAINT = "uniq_category_tenant_name_lower"


class CategoryRepository(Protocol):
    def list_with_counts(self, tenant_id: int) -> list[Category]: ...

    def in_tenant(self, tenant_id: int, category_id: int) -> Category | None: ...

    def active_in_tenant(self, tenant_id: int, category_id: int) -> Category | None: ...

    def max_sort_order(self, tenant_id: int) -> int | None: ...

    def save_unique(self, category: Category) -> None: ...

    def delete(self, category: Category) -> None: ...

    def active_for_sync(self, tenant_id: int) -> list[Category]: ...


class DjangoCategoryRepository:
    def list_with_counts(self, tenant_id: int) -> list[Category]:
        """Active categories in `sort_order`, each with `product_count` of live products."""
        return list(
            Category.objects.for_tenant(tenant_id)
            .filter(is_active=True)
            .annotate(product_count=Count("products", filter=Q(products__is_archived=False)))
            .order_by("sort_order", "name")
        )

    def in_tenant(self, tenant_id: int, category_id: int) -> Category | None:
        return Category.objects.for_tenant(tenant_id).filter(id=category_id).first()

    def active_in_tenant(self, tenant_id: int, category_id: int) -> Category | None:
        return Category.objects.for_tenant(tenant_id).filter(id=category_id, is_active=True).first()

    def max_sort_order(self, tenant_id: int) -> int | None:
        return Category.objects.for_tenant(tenant_id).aggregate(top=Max("sort_order"))["top"]

    def save_unique(self, category: Category) -> None:
        try:
            with transaction.atomic():
                category.save()
        except IntegrityError as error:
            if _NAME_CONSTRAINT in str(error):
                raise CategoryNameExistsError from None
            raise

    def delete(self, category: Category) -> None:
        category.delete()

    def active_for_sync(self, tenant_id: int) -> list[Category]:
        return list(
            Category.objects.for_tenant(tenant_id).filter(is_active=True).order_by("sort_order")
        )


category_repository = DjangoCategoryRepository()
