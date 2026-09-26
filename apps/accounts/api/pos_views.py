from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.use_cases.pin_login import PinAttempt, PinRejectedError, pin_login
from apps.audit.use_cases.record_activity import ActivityEntry, record_failure
from apps.core.api.exceptions import ApiError
from apps.tenants.api.device_auth import CounterDevice, DeviceAuthentication
from apps.tenants.api.permissions import IsCounterDevice

from .presenters import present_user
from .tokens import issue_counter_tokens

_PIN_ERRORS = {
    "invalid_pin": (401, "Wrong PIN."),
    "pin_throttled": (429, "Too many wrong PINs. Wait, then try again."),
}
_FAILURE_ACTIONS = {"invalid_pin": "pin_failure", "pin_throttled": "pin_throttled"}


class PinLoginRequestSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    pin = serializers.CharField(max_length=16, trim_whitespace=False)


class PinLoginView(APIView):
    authentication_classes = [DeviceAuthentication]
    permission_classes = [IsCounterDevice]

    def post(self, request):
        serializer = PinLoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device: CounterDevice = request.user
        attempt = PinAttempt(
            tenant_id=device.tenant_id,
            counter_id=device.counter_id,
            user_id=serializer.validated_data["user_id"],
            pin=serializer.validated_data["pin"],
        )
        try:
            user = pin_login(attempt, timezone.now())
        except PinRejectedError as error:
            _log_pin_failure(request, device, attempt, error)
            raise _pin_error(error) from None
        refresh = issue_counter_tokens(user, device.device_id)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": present_user(user),
            }
        )


def _pin_error(error: PinRejectedError) -> ApiError:
    status_code, message = _PIN_ERRORS[error.reason]
    return ApiError(
        code=error.reason,
        message=message,
        status_code=status_code,
        retry_after=error.retry_after or None,
    )


def _log_pin_failure(request, device: CounterDevice, attempt: PinAttempt, error) -> None:
    record_failure(
        ActivityEntry(
            tenant_id=device.tenant_id,
            user_id=attempt.user_id,
            action=_FAILURE_ACTIONS[error.reason],
            entity_type="user",
            entity_id=str(attempt.user_id),
            device_id=device.device_id,
            detail={
                "counter_id": device.counter_id,
                "fail_count": error.fail_count,
                "retry_after": error.retry_after,
            },
            ip=request.META.get("REMOTE_ADDR"),
        )
    )
