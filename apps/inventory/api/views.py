from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.counter_context import (
    COUNTER_AUTHENTICATION,
    IsCounterDeviceOrCashier,
    counter_context,
)
from apps.core.api.sync import SyncQuerySerializer
from apps.inventory.use_cases.stock_sync import stock_since


class StockSyncView(APIView):
    """Not paged (the contract shape has no `has_more`): one small row per
    product, all changes since the cursor."""

    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterDeviceOrCashier]

    def get(self, request):
        query = SyncQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        since = query.validated_data.get("since")
        tenant_id = counter_context(request).tenant_id
        sync = stock_since(tenant_id, since, timezone.now())
        return Response(
            {
                "levels": [
                    {"product_id": row.product_id, "qty": str(row.qty)} for row in sync.levels
                ],
                "next_since": sync.next_since.encode(),
            }
        )
