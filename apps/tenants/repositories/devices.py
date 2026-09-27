from datetime import datetime
from typing import Protocol

from apps.tenants.models import Counter, Device


class DeviceRepository(Protocol):
    def by_token_hash(self, token_hash: str) -> Device | None: ...

    def is_live(self, tenant_id: int, device_id: int) -> bool: ...

    def get(self, tenant_id: int, device_id: int) -> Device: ...

    def counter_has_live_device(self, counter: Counter) -> bool: ...

    def add(self, counter: Counter, token_hash: str, app_version: str, now: datetime) -> Device: ...


class DjangoDeviceRepository:
    def by_token_hash(self, token_hash: str) -> Device | None:
        """Global on purpose: the token alone identifies the PC and its tenant."""
        return Device.objects.filter(token_hash=token_hash).first()

    def is_live(self, tenant_id: int, device_id: int) -> bool:
        return (
            Device.objects.for_tenant(tenant_id)
            .filter(id=device_id, revoked_at__isnull=True)
            .exists()
        )

    def get(self, tenant_id: int, device_id: int) -> Device:
        return Device.objects.for_tenant(tenant_id).get(id=device_id)

    def counter_has_live_device(self, counter: Counter) -> bool:
        return (
            Device.objects.for_tenant(counter.tenant_id)
            .filter(counter=counter, revoked_at__isnull=True)
            .exists()
        )

    def add(self, counter: Counter, token_hash: str, app_version: str, now: datetime) -> Device:
        return Device.objects.create(
            tenant_id=counter.tenant_id,
            counter=counter,
            token_hash=token_hash,
            app_version=app_version,
            last_seen_at=now,
        )


device_repository = DjangoDeviceRepository()
