from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.counter_context import (
    COUNTER_AUTHENTICATION,
    CounterContext,
    IsCounterCashier,
    IsCounterDeviceOrCashier,
    counter_context,
)
from apps.core.api.exceptions import ApiError
from apps.shifts.domain.errors import (
    CashierNotFoundError,
    ShiftAlreadyOpenError,
    ShiftIdTakenError,
)
from apps.shifts.use_cases.cashier import shift_cashier
from apps.shifts.use_cases.open_shift import ShiftOpening, current_shift, open_shift

from .presenters import present_shift
from .serializers import OpenShiftRequestSerializer


class OpenShiftView(APIView):
    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterDeviceOrCashier]

    def post(self, request):
        context = counter_context(request)
        serializer = OpenShiftRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            opened = open_shift(_opening(context, serializer.validated_data))
        except ShiftAlreadyOpenError:
            raise ApiError(
                code="shift_already_open",
                message="This counter already has an open shift.",
                status_code=409,
            ) from None
        except ShiftIdTakenError:
            raise field_error("id", "This shift id is already used.") from None
        return Response(present_shift(opened.shift), status=201 if opened.created else 200)


def _opening(context: CounterContext, data: dict) -> ShiftOpening:
    if data["counter_id"] != context.counter_id:
        raise field_error("counter_id", "This PC belongs to another counter.")
    return ShiftOpening(
        tenant_id=context.tenant_id,
        counter_id=context.counter_id,
        device_id=context.device_id,
        cashier_id=cashier_for(context, data.get("cashier_id")),
        shift_id=data["id"],
        opened_at=data["opened_at"],
        opening_cash=data["opening_cash"],
    )


class CurrentShiftView(APIView):
    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterCashier]

    def get(self, request):
        context = counter_context(request)
        shift = current_shift(context.tenant_id, context.counter_id)
        if shift is None:
            return JsonResponse(None, safe=False)
        return Response(present_shift(shift))


def cashier_for(context: CounterContext, body_cashier_id: int | None) -> int:
    try:
        return shift_cashier(context.tenant_id, context.cashier_id, body_cashier_id)
    except CashierNotFoundError:
        raise field_error("cashier_id", "An active cashier of this store is required.") from None


def field_error(field: str, message: str) -> ApiError:
    return ApiError(
        code="validation_error", message="Validation failed.", fields={field: [message]}
    )
