from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.counter_context import (
    COUNTER_AUTHENTICATION,
    IsCounterDeviceOrCashier,
    counter_context,
)
from apps.core.api.exceptions import ApiError
from apps.sales.domain.errors import BatchBusyError
from apps.sales.use_cases.bill_upload import REJECTED
from apps.sales.use_cases.return_upload import ReturnBatch, ReturnResult
from apps.sales.use_cases.upload_returns import upload_returns

from .bill_serializers import flat_errors
from .bill_views import BUSY_RETRY_AFTER
from .return_serializers import ReturnBatchRequestSerializer, ReturnSerializer, to_return_upload


class ReturnBatchView(APIView):
    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterDeviceOrCashier]

    def post(self, request):
        context = counter_context(request)
        serializer = ReturnBatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parsed = [_parse(raw) for raw in serializer.validated_data["returns"]]
        batch = ReturnBatch(
            tenant_id=context.tenant_id,
            counter_id=context.counter_id,
            device_id=context.device_id,
            cashier_id=context.cashier_id,
            received_at=timezone.now(),
            returns=[item for item in parsed if not isinstance(item, ReturnResult)],
        )
        stored = iter(_upload(batch) if batch.returns else [])
        results = [item if isinstance(item, ReturnResult) else next(stored) for item in parsed]
        return Response(
            {
                "server_time": serializers.DateTimeField().to_representation(batch.received_at),
                "results": [_present(result) for result in results],
            }
        )


def _parse(raw):
    ret = ReturnSerializer(data=raw)
    if ret.is_valid():
        return to_return_upload(ret.validated_data)
    return_id = raw.get("id") if isinstance(raw, dict) else None
    errors = [text.replace("bill: ", "return: ", 1) for text in flat_errors(ret.errors)]
    return ReturnResult(return_id if isinstance(return_id, str) else None, REJECTED, [], errors)


def _upload(batch: ReturnBatch) -> list[ReturnResult]:
    try:
        return upload_returns(batch)
    except BatchBusyError:
        raise ApiError(
            code="batch_busy",
            message="This counter's last upload is still being saved. Try again shortly.",
            status_code=429,
            retry_after=BUSY_RETRY_AFTER,
        ) from None


def _present(result: ReturnResult) -> dict:
    return {
        "id": result.id,
        "status": result.status,
        "flags": result.flags,
        "errors": result.errors,
    }
