from dataclasses import dataclass
from datetime import datetime

from apps.accounts.domain.role_rules import CASHIER
from apps.accounts.models import User
from apps.tenants.models import Device


class UnknownCashierError(Exception):
    pass


@dataclass(frozen=True)
class Heartbeat:
    tenant_id: int
    device_id: int
    unsynced_count: int
    app_version: str
    cashier_id: int | None


def record_heartbeat(beat: Heartbeat, now: datetime) -> None:
    """Plain updates: `users.updated_at` must not move, or every counter would
    download the people list again on each beat."""
    if beat.cashier_id is not None:
        updated = (
            User.objects.for_tenant(beat.tenant_id)
            .filter(id=beat.cashier_id, role=CASHIER)
            .update(last_active_at=now)
        )
        if not updated:
            raise UnknownCashierError
    Device.objects.for_tenant(beat.tenant_id).filter(id=beat.device_id).update(
        last_seen_at=now, unsynced_count=beat.unsynced_count, app_version=beat.app_version
    )
