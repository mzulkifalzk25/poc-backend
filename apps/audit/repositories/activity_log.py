from typing import Protocol

from apps.audit.domain.activity import ActivityEntry
from apps.audit.models import ActivityLog


class ActivityLogRepository(Protocol):
    def add(self, entry: ActivityEntry) -> ActivityLog: ...

    def add_outside_transaction(self, entry: ActivityEntry) -> ActivityLog: ...


class DjangoActivityLogRepository:
    def add(self, entry: ActivityEntry) -> ActivityLog:
        return self._write(entry, using="default")

    def add_outside_transaction(self, entry: ActivityEntry) -> ActivityLog:
        """The `audit` connection commits on its own, so a rollback of the
        request's transaction can never erase the row."""
        return self._write(entry, using="audit")

    def _write(self, entry: ActivityEntry, using: str) -> ActivityLog:
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
            occurred_at=entry.occurred_at,
            ip=entry.ip,
        )


activity_log = DjangoActivityLogRepository()
