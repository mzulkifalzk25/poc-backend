from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.domain.role_rules import CASHIER
from apps.accounts.use_cases.heartbeat import Heartbeat, UnknownCashierError, record_heartbeat
from apps.accounts.use_cases.login import (
    InvalidCredentials,
    authenticate_account,
    find_login_account,
)
from apps.audit.use_cases.record_activity import ActivityEntry, record_failure
from apps.core.api.exceptions import ApiError
from apps.tenants.api.device_auth import CounterDevice, DeviceAuthentication
from apps.tenants.api.permissions import IsCounterDevice
from apps.tenants.api.serializers import TenantSettingsSerializer
from apps.tenants.use_cases.counters import counter_of
from apps.tenants.use_cases.settings import tenant_settings

from .counter_context import COUNTER_AUTHENTICATION, IsCounterDeviceOrCashier, counter_context
from .presenters import present_user
from .serializers import LoginRequestSerializer
from .throttling import LoginRateThrottle
from .tokens import issue_counter_tokens


class CashierLoginView(APIView):
    """A cashier's email + password, checked on the server, over the network.
    The device token proves the counter PC is activated; the resulting JWT
    is bound to it, same as every other counter-scoped request."""

    authentication_classes = [DeviceAuthentication]
    permission_classes = [IsCounterDevice]
    throttle_classes = [LoginRateThrottle]

    def throttled(self, request, wait):
        account = find_login_account(str(request.data.get("login", "")), (CASHIER,))
        _log_login_failure(request, account, "login_throttled")
        raise ApiError(
            code="login_throttled",
            message="Too many sign-in attempts. Try again shortly.",
            status_code=429,
            retry_after=int(wait) if wait is not None else None,
        )

    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device: CounterDevice = request.user
        data = serializer.validated_data
        try:
            user = authenticate_account(data["login"], data["password"], roles=(CASHIER,))
        except InvalidCredentials as error:
            _log_login_failure(request, error.user, "login_failure")
            raise ApiError(
                code="invalid_credentials", message="Incorrect login or password.", status_code=401
            ) from None
        refresh = issue_counter_tokens(user, device.device_id)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": present_user(user),
            }
        )


def _log_login_failure(request, account, action: str) -> None:
    """Written outside the request transaction. An unknown or ambiguous login
    has no tenant to log against, so it is not logged."""
    if account is None:
        return
    record_failure(
        ActivityEntry(
            tenant_id=account.tenant_id,
            user_id=account.id,
            action=action,
            entity_type="user",
            entity_id=str(account.id),
            ip=request.META.get("REMOTE_ADDR"),
        )
    )


class BootstrapView(APIView):
    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterDeviceOrCashier]

    def get(self, request):
        context = counter_context(request)
        counter = counter_of(context.tenant_id, context.counter_id)
        settings = tenant_settings(context.tenant_id)
        return Response(
            {
                "counter": {"id": counter.id, "name": counter.name, "code": counter.code},
                "settings": TenantSettingsSerializer(settings).data,
                "last_bill_seq": counter.last_bill_seq,
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
