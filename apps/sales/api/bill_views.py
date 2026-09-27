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
from apps.sales.use_cases.bill_upload import BillBatch, BillResult, rejected
from apps.sales.use_cases.upload_bills import upload_bills

from .bill_serializers import BatchRequestSerializer, BillSerializer, flat_errors, to_bill_upload

BUSY_RETRY_AFTER = 5


class BillBatchView(APIView):
    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterDeviceOrCashier]

    def post(self, request):
        context = counter_context(request)
        serializer = BatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["counter_id"] != context.counter_id:
            raise ApiError(
                code="validation_error",
                message="Validation failed.",
                fields={"counter_id": ["This PC belongs to another counter."]},
            )
        parsed = [_parse(raw) for raw in serializer.validated_data["bills"]]
        batch = BillBatch(
            tenant_id=context.tenant_id,
            counter_id=context.counter_id,
            device_id=context.device_id,
            received_at=timezone.now(),
            bills=[item for item in parsed if not isinstance(item, BillResult)],
        )
        stored = iter(_upload(batch) if batch.bills else [])
        results = [item if isinstance(item, BillResult) else next(stored) for item in parsed]
        return Response(
            {
                "server_time": serializers.DateTimeField().to_representation(batch.received_at),
                "results": [_present(result) for result in results],
            }
        )


def _parse(raw):
    bill = BillSerializer(data=raw)
    if bill.is_valid():
        return to_bill_upload(bill.validated_data)
    raw = raw if isinstance(raw, dict) else {}
    bill_id, bill_no = raw.get("id"), raw.get("bill_no")
    return rejected(
        bill_id if isinstance(bill_id, str) else None,
        bill_no if isinstance(bill_no, str) else None,
        flat_errors(bill.errors),
    )


def _upload(batch: BillBatch) -> list[BillResult]:
    try:
        return upload_bills(batch)
    except BatchBusyError:
        raise ApiError(
            code="batch_busy",
            message="This counter's last upload is still being saved. Try again shortly.",
            status_code=429,
            retry_after=BUSY_RETRY_AFTER,
        ) from None


def _present(result: BillResult) -> dict:
    return {
        "id": result.id,
        "status": result.status,
        "bill_no": result.bill_no,
        "flags": result.flags,
        "errors": result.errors,
    }
