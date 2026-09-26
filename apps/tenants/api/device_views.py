from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.audit.use_cases.record_activity import ActivityEntry, record_failure
from apps.core.api.exceptions import ApiError
from apps.tenants.use_cases.activate_device import ActivationError, activate_device
from apps.tenants.use_cases.activation_codes import (
    CounterActiveError,
    CounterNotFoundError,
    issue_activation_code,
    revoke_activation_code,
)

from .throttling import ActivationRateThrottle


class IssueCodeRequestSerializer(serializers.Serializer):
    counter_id = serializers.IntegerField()


def _counter_not_found() -> ApiError:
    return ApiError(code="not_found", message="Counter not found.", status_code=404)


def _counter_active() -> ApiError:
    return ApiError(
        code="counter_active",
        message="This counter already has an activated PC. Deactivate it first.",
        status_code=409,
    )


class DeviceCodeCreateView(APIView):
    permission_classes = [IsOwner]

    def post(self, request):
        serializer = IssueCodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            issued = issue_activation_code(
                tenant_id=request.user.tenant_id,
                counter_id=serializer.validated_data["counter_id"],
                user_id=request.user.id,
                now=timezone.now(),
            )
        except CounterNotFoundError:
            raise _counter_not_found() from None
        except CounterActiveError:
            raise _counter_active() from None
        return Response({"code": issued.code, "expires_at": issued.expires_at}, status=201)


class DeviceCodeRevokeView(APIView):
    permission_classes = [IsOwner]

    def delete(self, request, counter_id: int):
        try:
            revoke_activation_code(request.user.tenant_id, counter_id, timezone.now())
        except CounterNotFoundError:
            raise _counter_not_found() from None
        return Response(status=204)


class ActivateRequestSerializer(serializers.Serializer):
    code = serializers.CharField(trim_whitespace=True)
    app_version = serializers.CharField(max_length=32, allow_blank=True, default="")


_ACTIVATION_ERRORS = {
    "code_invalid": (400, "This code is not valid. Check it and try again."),
    "code_expired": (410, "This code has expired. Ask the owner for a new code."),
    "code_used": (409, "This code has already been used. Ask the owner for a new code."),
    "counter_active": (409, "This counter already has an activated PC."),
}


class DeviceActivateView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ActivationRateThrottle]

    def throttled(self, request, wait):
        raise ApiError(
            code="activation_throttled",
            message="Too many activation attempts. Try again later.",
            status_code=429,
            retry_after=int(wait) if wait is not None else None,
        )

    def post(self, request):
        serializer = ActivateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ip = request.META.get("REMOTE_ADDR")
        try:
            activation = activate_device(
                raw_code=serializer.validated_data["code"],
                app_version=serializer.validated_data["app_version"],
                ip=ip,
                now=timezone.now(),
            )
        except ActivationError as error:
            _log_failed_activation(error, ip)
            status_code, message = _ACTIVATION_ERRORS[error.reason]
            raise ApiError(code=error.reason, message=message, status_code=status_code) from None
        counter = activation.counter
        return Response(
            {
                "device_token": activation.device_token,
                "counter": {"id": counter.id, "name": counter.name, "code": counter.code},
            }
        )


def _log_failed_activation(error: ActivationError, ip: str | None) -> None:
    if error.tenant_id is None:
        return
    record_failure(
        ActivityEntry(
            tenant_id=error.tenant_id,
            action="activation_failed",
            entity_type="counter",
            entity_id=str(error.counter_id),
            detail={"reason": error.reason},
            ip=ip,
        )
    )
