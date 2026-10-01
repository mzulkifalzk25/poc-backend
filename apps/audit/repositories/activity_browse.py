from typing import Protocol

from django.db.models import Count, Q, QuerySet

from apps.accounts.models import User
from apps.audit.models import ActivityLog
from apps.catalog.models import Product
from apps.core.domain.cursor import Cursor
from apps.tenants.models import Counter


class ActivityBrowseRepository(Protocol):
    def filtered(self, tenant_id: int, filters: dict) -> QuerySet[ActivityLog]: ...

    def page(
        self, rows: QuerySet[ActivityLog], cursor: Cursor | None, limit: int
    ) -> list[ActivityLog]: ...

    def counts_in(self, tenant_id: int, since, until) -> dict[str, int]: ...

    def user_names(self, tenant_id: int, ids: set[int]) -> dict[int, str]: ...

    def product_names(self, tenant_id: int, ids: set[str]) -> dict[str, str]: ...

    def counter_names(self, tenant_id: int, ids: set[int]) -> dict[int, str]: ...


class DjangoActivityBrowseRepository:
    def filtered(self, tenant_id: int, filters: dict):
        rows = ActivityLog.objects.for_tenant(tenant_id)
        if filters.get("actions"):
            rows = rows.filter(action__in=filters["actions"])
        if filters.get("since"):
            rows = rows.filter(occurred_at__gte=filters["since"])
        if filters.get("until"):
            rows = rows.filter(occurred_at__lt=filters["until"])
        if filters.get("user"):
            rows = rows.filter(user_id=filters["user"])
        return rows

    def page(self, rows, cursor: Cursor | None, limit: int) -> list[ActivityLog]:
        if cursor:
            rows = rows.filter(
                Q(occurred_at__lt=cursor.occurred_at)
                | Q(occurred_at=cursor.occurred_at, id__lt=cursor.id)
            )
        return list(rows.order_by("-occurred_at", "-id")[:limit])

    def counts_in(self, tenant_id: int, since, until) -> dict[str, int]:
        rows = ActivityLog.objects.for_tenant(tenant_id).filter(
            occurred_at__gte=since, occurred_at__lt=until
        )
        return dict(
            rows.filter(action__in=["held_bill_deleted", "return_processed", "price_changed"])
            .values_list("action")
            .annotate(total=Count("id"))
        )

    def user_names(self, tenant_id: int, ids: set[int]) -> dict[int, str]:
        users = User.objects.for_tenant(tenant_id).filter(id__in=ids)
        return dict(users.values_list("id", "full_name"))

    def product_names(self, tenant_id: int, ids: set[str]) -> dict[str, str]:
        numeric = [int(i) for i in ids if i.isdigit()]
        products = Product.objects.for_tenant(tenant_id).filter(id__in=numeric)
        return {str(pk): name for pk, name in products.values_list("id", "name")}

    def counter_names(self, tenant_id: int, ids: set[int]) -> dict[int, str]:
        counters = Counter.objects.for_tenant(tenant_id).filter(id__in=ids)
        return dict(counters.values_list("id", "name"))


activity_browse_repository = DjangoActivityBrowseRepository()
