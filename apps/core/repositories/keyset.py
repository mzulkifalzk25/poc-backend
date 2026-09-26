from django.db.models import Q, QuerySet

from apps.core.domain.cursor import Cursor


def rows_after(queryset: QuerySet, cursor: Cursor | None) -> QuerySet:
    """Rows after `cursor` in `(updated_at, id)` order."""
    if cursor is not None:
        queryset = queryset.filter(
            Q(updated_at__gt=cursor.occurred_at)
            | Q(updated_at=cursor.occurred_at, id__gt=cursor.id)
        )
    return queryset.order_by("updated_at", "id")


def cursor_of(row) -> Cursor:
    return Cursor(occurred_at=row.updated_at, id=row.id)
