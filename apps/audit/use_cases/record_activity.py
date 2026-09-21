from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.utils import timezone

from apps.audit.models import ActivityLog


@dataclass(frozen=True)
class ActivityEntry:
    tenant_id: int
    action: str
    entity_type: str = ""
    entity_id: str = ""
    user_id: int | None = None
    device_id: int | None = None
    before: dict | None = None
    after: dict | None = None
    detail: dict | None = None
    ip: str | None = None
    occurred_at: datetime | None = None
    client_event_id: UUID | None = None


def record_activity(entry: ActivityEntry) -> ActivityLog:
    """Write an activity-log row in the caller's current transaction."""
    return _write(entry, using="default")


def record_failure(entry: ActivityEntry) -> ActivityLog:
    """Write a failure entry (PIN/password failures, throttled sign-ins,
    failed activation) on the separate `audit` connection, so a rollback of
    the request's own transaction can never erase it."""
    return _write(entry, using="audit")


def _write(entry: ActivityEntry, using: str) -> ActivityLog:
    return ActivityLog.objects.using(using).create(
        tenant_id=entry.tenant_id,
        user_id=entry.user_id,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        before=entry.before,
        after=entry.after,
        detail=entry.detail,
        device_id=entry.device_id,
        client_event_id=entry.client_event_id,
        occurred_at=entry.occurred_at or timezone.now(),
        ip=entry.ip,
    )
