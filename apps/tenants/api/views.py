from rest_framework.generics import RetrieveUpdateAPIView

from apps.accounts.api.permissions import IsOwner
from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.tenants.models import TenantSettings

from .serializers import TenantSettingsSerializer


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
