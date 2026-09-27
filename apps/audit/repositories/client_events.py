from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.audit.domain.activity import ActivityEntry
from apps.audit.models import ActivityLog

_CLIENT_EVENT_CONSTRAINT = "uniq_audit_log_tenant_client_event_id"


class ClientEventRepository(Protocol):
    def stored_ids(self, tenant_id: int, ids: Iterable[UUID]) -> set[UUID]: ...

    def add(self, entry: ActivityEntry) -> bool: ...


class DjangoClientEventRepository:
    def stored_ids(self, tenant_id: int, ids: Iterable[UUID]) -> set[UUID]:
        rows = ActivityLog.objects.for_tenant(tenant_id).filter(client_event_id__in=list(ids))
        return set(rows.values_list("client_event_id", flat=True))

    def add(self, entry: ActivityEntry) -> bool:
        """False when the event is already stored (a retry that raced)."""
        try:
            with transaction.atomic():
                ActivityLog.objects.create(
                    tenant_id=entry.tenant_id,
                    user_id=entry.user_id,
                    action=entry.action,
                    entity_type=entry.entity_type,
                    entity_id=entry.entity_id,
                    detail=entry.detail,
                    device_id=entry.device_id,
                    client_event_id=entry.client_event_id,
                    occurred_at=entry.occurred_at,
                    ip=entry.ip,
                )
        except IntegrityError as error:
            if _CLIENT_EVENT_CONSTRAINT in str(error):
                return False
            raise
        return True


client_event_repository = DjangoClientEventRepository()
