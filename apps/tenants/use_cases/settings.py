from collections.abc import Callable

from django.db import transaction

from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.tenants.models import TenantSettings
from apps.tenants.repositories.settings import SettingsRepository, settings_repository

# The activity log keeps the settings as the API shows them; the API layer
# supplies that view.
Snapshot = Callable[[TenantSettings], dict]


def tenant_settings(
    tenant_id: int, repo: SettingsRepository = settings_repository
) -> TenantSettings:
    return repo.for_tenant(tenant_id)


def update_settings(
    user_id: int,
    settings: TenantSettings,
    changes: dict,
    snapshot: Snapshot,
    repo: SettingsRepository = settings_repository,
) -> TenantSettings:
    before = dict(snapshot(settings))
    for name, value in changes.items():
        setattr(settings, name, value)
    with transaction.atomic():
        repo.save(settings)
        record_activity(
            ActivityEntry(
                tenant_id=settings.tenant_id,
                user_id=user_id,
                action="settings_changed",
                entity_type="tenant_settings",
                entity_id=str(settings.id),
                before=before,
                after=snapshot(settings),
            )
        )
    return settings
