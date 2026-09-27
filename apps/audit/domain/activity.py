from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


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
