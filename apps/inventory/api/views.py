from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.counter_context import (
    COUNTER_AUTHENTICATION,
    IsCounterDeviceOrCashier,
    counter_context,
)
from apps.core.api.sync import SyncQuerySerializer
from apps.core.domain.sync_cursor import caught_up_cursor
from apps.core.repositories.keyset import cursor_of, rows_after
from apps.inventory.models import StockLevel


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
        rows = list(rows_after(StockLevel.objects.for_tenant(tenant_id), since))
        last = cursor_of(rows[-1]) if rows else None
        next_since = caught_up_cursor(last, since, timezone.now())
        return Response(
            {
                "levels": [{"product_id": row.product_id, "qty": str(row.qty)} for row in rows],
                "next_since": next_since.encode(),
            }
        )
