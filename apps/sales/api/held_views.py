from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.counter_context import (
    COUNTER_AUTHENTICATION,
    IsCounterCashier,
    counter_context,
)
from apps.sales.models import HeldBill
from apps.sales.use_cases.held_bills import REJECTED, HeldScope, HeldUpload, sync_held_bills

MAX_HELD = 100


class HeldSyncRequestSerializer(serializers.Serializer):
    held = serializers.ListField(child=serializers.JSONField(), max_length=MAX_HELD)


class HeldBillSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField(max_length=100, allow_blank=True)
    payload = serializers.DictField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    status = serializers.ChoiceField(choices=HeldBill.Status.values)
    updated_at = serializers.DateTimeField()


class HeldBillSyncView(APIView):
    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterCashier]

    def post(self, request):
        context = counter_context(request)
        serializer = HeldSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results, uploads = [], []
        for raw in serializer.validated_data["held"]:
            item = HeldBillSerializer(data=raw)
            if item.is_valid():
                uploads.append(HeldUpload(**item.validated_data))
                results.append(item.validated_data["id"])
            else:
                results.append(_raw_id(raw))
        scope = HeldScope(context.tenant_id, context.counter_id, context.cashier_id)
        statuses = sync_held_bills(scope, uploads) if uploads else {}
        return Response({"results": [_row(held_id, statuses) for held_id in results]})


def _raw_id(raw) -> str | None:
    held_id = raw.get("id") if isinstance(raw, dict) else None
    return held_id if isinstance(held_id, str) else None


def _row(held_id, statuses: dict) -> dict:
    status = statuses.get(held_id, REJECTED)
    return {"id": None if held_id is None else str(held_id), "status": status}
