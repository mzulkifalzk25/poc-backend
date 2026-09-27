from datetime import datetime

from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.use_cases.heartbeat import Heartbeat, UnknownCashierError, record_heartbeat
from apps.accounts.use_cases.people_sync import active_roster, people_since
from apps.accounts.use_cases.pin_login import PinAttempt, PinRejectedError, pin_login
from apps.audit.use_cases.record_activity import ActivityEntry, record_failure
from apps.core.api.exceptions import ApiError
from apps.tenants.api.device_auth import CounterDevice, DeviceAuthentication
from apps.tenants.api.permissions import IsCounterDevice
from apps.tenants.api.serializers import TenantSettingsSerializer
from apps.tenants.use_cases.counters import counter_of
from apps.tenants.use_cases.settings import tenant_settings

from .counter_context import COUNTER_AUTHENTICATION, IsCounterDeviceOrCashier, counter_context
from .presenters import present_person, present_roster_row, present_user
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


class PeopleSyncQuerySerializer(serializers.Serializer):
    since = serializers.CharField(required=False)

    def validate_since(self, value: str) -> datetime | None:
        if value in ("", "0"):
            return None
        return serializers.DateTimeField().to_internal_value(value)


class RosterView(APIView):
    authentication_classes = [DeviceAuthentication]
    permission_classes = [IsCounterDevice]

    def get(self, request):
        cashiers = active_roster(request.user.tenant_id)
        return Response([present_roster_row(user) for user in cashiers])


class PeopleSyncView(APIView):
    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterDeviceOrCashier]

    def get(self, request):
        query = PeopleSyncQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        context = counter_context(request)
        delta = people_since(
            context.tenant_id, context.counter_id, query.validated_data.get("since"), timezone.now()
        )
        return Response(
            {
                "roster": [present_person(user) for user in delta.cashiers],
                "next_since": serializers.DateTimeField().to_representation(delta.next_since),
            }
        )


class BootstrapView(APIView):
    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterDeviceOrCashier]

    def get(self, request):
        context = counter_context(request)
        counter = counter_of(context.tenant_id, context.counter_id)
        settings = tenant_settings(context.tenant_id)
        roster = active_roster(context.tenant_id)
        return Response(
            {
                "counter": {"id": counter.id, "name": counter.name, "code": counter.code},
                "settings": TenantSettingsSerializer(settings).data,
                "last_bill_seq": counter.last_bill_seq,
                "roster": [present_roster_row(user) for user in roster],
                "server_time": _now_text(),
            }
        )


class HeartbeatRequestSerializer(serializers.Serializer):
    unsynced_count = serializers.IntegerField(min_value=0)
    app_version = serializers.CharField(max_length=32, allow_blank=True, default="")
    cashier_id = serializers.IntegerField(required=False, allow_null=True)


class HeartbeatView(APIView):
    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterDeviceOrCashier]

    def post(self, request, counter_id: int):
        context = counter_context(request)
        if counter_id != context.counter_id:
            raise ApiError(code="not_found", message="Counter not found.", status_code=404)
        serializer = HeartbeatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        beat = Heartbeat(
            tenant_id=context.tenant_id,
            device_id=context.device_id,
            unsynced_count=data["unsynced_count"],
            app_version=data["app_version"],
            cashier_id=data.get("cashier_id") or context.cashier_id,
        )
        try:
            record_heartbeat(beat, timezone.now())
        except UnknownCashierError:
            raise ApiError(
                code="validation_error",
                message="Validation failed.",
                fields={"cashier_id": ["Cashier not found."]},
            ) from None
        return Response({"server_time": _now_text()})


def _now_text() -> str:
    return serializers.DateTimeField().to_representation(timezone.now())
