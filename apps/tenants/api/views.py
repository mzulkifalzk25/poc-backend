from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView

from apps.accounts.api.permissions import IsOwner
from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.core.api.exceptions import ApiError
from apps.tenants.domain.counter_rules import CounterCodeLockedError, ensure_code_can_change
from apps.tenants.models import Counter, TenantSettings

from .serializers import CounterSerializer, TenantSettingsSerializer


class TenantSettingsView(RetrieveUpdateAPIView):
    permission_classes = [IsOwner]
    serializer_class = TenantSettingsSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        settings, _ = TenantSettings.objects.get_or_create(tenant_id=self.request.user.tenant_id)
        return settings

    def perform_update(self, serializer):
        before = TenantSettingsSerializer(serializer.instance).data
        instance = serializer.save()
        record_activity(
            ActivityEntry(
                tenant_id=self.request.user.tenant_id,
                user_id=self.request.user.id,
                action="settings_changed",
                entity_type="tenant_settings",
                entity_id=str(instance.id),
                before=dict(before),
                after=TenantSettingsSerializer(instance).data,
            )
        )


class CounterListCreateView(ListCreateAPIView):
    permission_classes = [IsOwner]
    serializer_class = CounterSerializer

    def get_queryset(self):
        return Counter.objects.for_tenant(self.request.user.tenant_id).order_by("code")

    def perform_create(self, serializer):
        tenant_id = self.request.user.tenant_id
        code = serializer.validated_data["code"]
        if Counter.objects.for_tenant(tenant_id).filter(code=code).exists():
            raise ApiError(
                code="code_exists",
                message="This counter code is already in use.",
                status_code=409,
                fields={"code": ["already in use"]},
            )

        counter = serializer.save(tenant_id=tenant_id)
        record_activity(
            ActivityEntry(
                tenant_id=tenant_id,
                user_id=self.request.user.id,
                action="counter_created",
                entity_type="counter",
                entity_id=str(counter.id),
                after=CounterSerializer(counter).data,
            )
        )


class CounterDetailView(RetrieveUpdateAPIView):
    permission_classes = [IsOwner]
    serializer_class = CounterSerializer
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        return Counter.objects.for_tenant(self.request.user.tenant_id)

    def perform_update(self, serializer):
        counter = serializer.instance
        new_code = serializer.validated_data.get("code", counter.code)

        if new_code != counter.code:
            try:
                ensure_code_can_change(counter.code, new_code, counter.last_bill_seq)
            except CounterCodeLockedError:
                raise ApiError(
                    code="counter_code_locked",
                    message="This counter has billed; its code is locked.",
                    status_code=409,
                ) from None
            if (
                Counter.objects.for_tenant(counter.tenant_id)
                .exclude(id=counter.id)
                .filter(code=new_code)
                .exists()
            ):
                raise ApiError(
                    code="code_exists",
                    message="This counter code is already in use.",
                    status_code=409,
                    fields={"code": ["already in use"]},
                )

        before = CounterSerializer(counter).data
        instance = serializer.save()
        record_activity(
            ActivityEntry(
                tenant_id=instance.tenant_id,
                user_id=self.request.user.id,
                action="counter_updated",
                entity_type="counter",
                entity_id=str(instance.id),
                before=dict(before),
                after=CounterSerializer(instance).data,
            )
        )
