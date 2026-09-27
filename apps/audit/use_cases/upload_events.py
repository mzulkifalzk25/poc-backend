from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.audit.domain.activity import ActivityEntry
from apps.audit.domain.client_events import is_client_action
from apps.audit.repositories.client_events import ClientEventRepository, client_event_repository

CREATED, DUPLICATE, REJECTED = "created", "duplicate", "rejected"


@dataclass(frozen=True)
class EventUpload:
    id: UUID
    action: str
    occurred_at: datetime
    entity_type: str
    entity_id: str
    detail: dict


@dataclass(frozen=True)
class EventSource:
    """Stamped by the server from the token and request; never from the body."""

    tenant_id: int
    user_id: int | None
    device_id: int
    counter_id: int
    ip: str | None


def upload_events(
    source: EventSource,
    events: list[EventUpload],
    repo: ClientEventRepository = client_event_repository,
) -> list[str]:
    """Idempotent on the event id (stored as `client_event_id`)."""
    with transaction.atomic():
        seen = repo.stored_ids(source.tenant_id, [event.id for event in events])
        return [_upload_one(source, event, seen, repo) for event in events]


def _upload_one(
    source: EventSource, event: EventUpload, seen: set[UUID], repo: ClientEventRepository
) -> str:
    if not is_client_action(event.action):
        return REJECTED
    if event.id in seen:
        return DUPLICATE
    seen.add(event.id)
    return CREATED if repo.add(_entry(source, event)) else DUPLICATE


def _entry(source: EventSource, event: EventUpload) -> ActivityEntry:
    return ActivityEntry(
        tenant_id=source.tenant_id,
        user_id=source.user_id,
        action=event.action,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        device_id=source.device_id,
        detail={**event.detail, "counter_id": source.counter_id},
        ip=source.ip,
        occurred_at=event.occurred_at,
        client_event_id=event.id,
    )
