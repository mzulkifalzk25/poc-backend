from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.counter_context import (
    COUNTER_AUTHENTICATION,
    IsCounterDeviceOrCashier,
    counter_context,
)
from apps.catalog.models import Category, Product
from apps.catalog.use_cases.sync import product_sync_page
from apps.core.api.sync import SyncQuerySerializer


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
        page = product_sync_page(tenant_id, since, page_size, timezone.now())
        return Response(
            {
                "products": [present_sync_product(product) for product in page.products],
                "categories": [present_sync_category(c) for c in page.categories],
                "next_since": page.next_since.encode(),
                "has_more": page.has_more,
            }
        )
