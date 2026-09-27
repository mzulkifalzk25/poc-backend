from dataclasses import dataclass
from datetime import datetime

from apps.accounts.repositories.users import UserRepository, user_repository
from apps.tenants.repositories.devices import DeviceRepository, device_repository


class UnknownCashierError(Exception):
    pass


@dataclass(frozen=True)
class Heartbeat:
    tenant_id: int
    device_id: int
    unsynced_count: int
    app_version: str
    cashier_id: int | None


def record_heartbeat(
    beat: Heartbeat,
    now: datetime,
    users: UserRepository = user_repository,
    devices: DeviceRepository = device_repository,
) -> None:
    """Plain updates: `users.updated_at` must not move, or every counter would
    download the people list again on each beat."""
    if beat.cashier_id is not None:
        if not users.touch_cashier(beat.tenant_id, beat.cashier_id, now):
            raise UnknownCashierError
    devices.record_beat(beat.tenant_id, beat.device_id, now, beat.unsynced_count, beat.app_version)
