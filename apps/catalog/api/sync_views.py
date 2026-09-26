from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.counter_context import (
    COUNTER_AUTHENTICATION,
    IsCounterDeviceOrCashier,
    counter_context,
)
from apps.catalog.models import Category, Product
from apps.core.api.sync import SyncQuerySerializer
from apps.core.domain.sync_cursor import caught_up_cursor
from apps.core.repositories.keyset import cursor_of, rows_after


def present_sync_product(product: Product) -> dict:
    """What a counter stores offline: never `cost`; archived rows included so
    the counter removes them."""
    return {
        "id": product.id,
        "barcode": product.barcode,
        "name": product.name,
        "name_lc": product.name_lc,
        "category_id": product.category_id,
        "unit": product.unit,
        "price": str(product.price),
        "low_stock_alert": str(product.low_stock_alert),
        "is_archived": product.is_archived,
    }


def present_sync_category(category: Category) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "tint": category.tint,
        "sort_order": category.sort_order,
    }


class ProductSyncView(APIView):
    """`categories` is always the full list, so a deleted category disappears."""

    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterDeviceOrCashier]

    def get(self, request):
        query = SyncQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        since, page_size = query.validated_data.get("since"), query.validated_data["page_size"]
        tenant_id = counter_context(request).tenant_id
        rows = list(rows_after(Product.objects.for_tenant(tenant_id), since)[: page_size + 1])
        has_more = len(rows) > page_size
        rows = rows[:page_size]
        last = cursor_of(rows[-1]) if rows else None
        next_since = last if has_more else caught_up_cursor(last, since, timezone.now())
        categories = Category.objects.for_tenant(tenant_id).filter(is_active=True)
        return Response(
            {
                "products": [present_sync_product(product) for product in rows],
                "categories": [present_sync_category(c) for c in categories.order_by("sort_order")],
                "next_since": next_since.encode(),
                "has_more": has_more,
            }
        )
