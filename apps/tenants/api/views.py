from django.utils import timezone
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.core.api.exceptions import ApiError
from apps.tenants.domain.counter_rules import CounterCodeLockedError
from apps.tenants.models import Counter, TenantSettings
from apps.tenants.use_cases.counters import (
    CounterCodeExistsError,
    CounterNotFoundError,
    CounterShiftOpenError,
    counters_table,
    create_counter,
    deactivate_counter,
    update_counter,
)
from apps.tenants.use_cases.settings import tenant_settings, update_settings

from .serializers import CounterSerializer, TenantSettingsSerializer


class TenantSettingsView(APIView):
    permission_classes = [IsOwner]
    http_method_names = ["get", "patch"]

    def get(self, request):
        settings = tenant_settings(request.user.tenant_id)
        return Response(TenantSettingsSerializer(settings).data)

    def patch(self, request):
        settings = tenant_settings(request.user.tenant_id)
        serializer = TenantSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        update_settings(request.user.id, settings, serializer.validated_data, _settings_snapshot)
        return Response(TenantSettingsSerializer(settings).data)


def _settings_snapshot(settings: TenantSettings) -> dict:
    return TenantSettingsSerializer(settings).data


def _code_exists() -> ApiError:
    return ApiError(
        code="code_exists",
        message="This counter code is already in use.",
        status_code=409,
        fields={"code": ["already in use"]},
    )


def _counter_snapshot(counter: Counter) -> dict:
    return CounterSerializer(counter).data


class CounterListCreateView(ListCreateAPIView):
    permission_classes = [IsOwner]
    serializer_class = CounterSerializer

    def get_queryset(self):
        return counters_table(self.request.user.tenant_id, timezone.now()).order_by("code")

    def perform_create(self, serializer):
        try:
            serializer.instance = create_counter(
                self.request.user.tenant_id,
                self.request.user.id,
                serializer.validated_data,
                _counter_snapshot,
            )
        except CounterCodeExistsError:
            raise _code_exists() from None


class CounterDetailView(RetrieveUpdateAPIView):
    permission_classes = [IsOwner]
    serializer_class = CounterSerializer
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        return counters_table(self.request.user.tenant_id, timezone.now())

    def perform_update(self, serializer):
        try:
            update_counter(
                self.request.user.id,
                serializer.instance,
                serializer.validated_data,
                _counter_snapshot,
            )
        except CounterCodeLockedError:
            raise ApiError(
                code="counter_code_locked",
                message="This counter has billed; its code is locked.",
                status_code=409,
            ) from None
        except CounterCodeExistsError:
            raise _code_exists() from None


class CounterDeactivateView(APIView):
    permission_classes = [IsOwner]

    def post(self, request, pk: int):
        try:
            deactivate_counter(request.user.tenant_id, request.user.id, pk, timezone.now())
        except CounterNotFoundError:
            raise ApiError(
                code="not_found", message="Counter not found.", status_code=404
            ) from None
        except CounterShiftOpenError:
            raise ApiError(
                code="shift_open",
                message="This counter has an open shift. Close it before deactivating.",
                status_code=409,
            ) from None
        return Response(status=204)
