from typing import Protocol

from apps.tenants.models import TenantSettings


class SettingsRepository(Protocol):
    def for_tenant(self, tenant_id: int) -> TenantSettings: ...

    def save(self, settings: TenantSettings) -> None: ...


class DjangoSettingsRepository:
    def for_tenant(self, tenant_id: int) -> TenantSettings:
        """A tenant without a settings row gets one with the defaults."""
        settings, _ = TenantSettings.objects.get_or_create(tenant_id=tenant_id)
        return settings

    def save(self, settings: TenantSettings) -> None:
        settings.save()


settings_repository = DjangoSettingsRepository()
