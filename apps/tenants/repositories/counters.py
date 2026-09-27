from datetime import datetime
from typing import Protocol

from django.db.models import Exists, OuterRef, QuerySet, Subquery

from apps.shifts.models import Shift
from apps.tenants.models import Counter, Device, DeviceCode


class CounterRepository(Protocol):
    def with_device_state(self, tenant_id: int, now: datetime) -> QuerySet[Counter]: ...

    def code_in_use(self, tenant_id: int, code: str, exclude_id: int | None = None) -> bool: ...

    def save(self, counter: Counter) -> None: ...

    def lock(self, tenant_id: int, counter_id: int) -> Counter | None: ...

    def get(self, tenant_id: int, counter_id: int) -> Counter: ...

    def ids(self, tenant_id: int) -> list[int]: ...

    def exists(self, tenant_id: int, counter_id: int) -> bool: ...


class DjangoCounterRepository:
    def with_device_state(self, tenant_id: int, now: datetime) -> QuerySet[Counter]:
        """One query for the counters table: live PC details, the ready code and
        whether a shift is open."""
        devices = Device.objects.for_tenant(tenant_id).filter(counter=OuterRef("pk"))
        live = devices.filter(revoked_at__isnull=True)
        ready_codes = (
            DeviceCode.objects.for_tenant(tenant_id)
            .filter(
                counter=OuterRef("pk"),
                used_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__gt=now,
            )
            .order_by("-expires_at")
        )
        open_shifts = Shift.objects.for_tenant(tenant_id).filter(
            counter=OuterRef("pk"), status=Shift.Status.OPEN
        )
        return Counter.objects.for_tenant(tenant_id).annotate(
            has_live_device=Exists(live),
            has_open_shift=Exists(open_shifts),
            had_revoked_device=Exists(devices.filter(revoked_at__isnull=False)),
            live_last_seen_at=Subquery(live.values("last_seen_at")[:1]),
            live_app_version=Subquery(live.values("app_version")[:1]),
            live_unsynced_count=Subquery(live.values("unsynced_count")[:1]),
            ready_code_expires_at=Subquery(ready_codes.values("expires_at")[:1]),
        )

    def code_in_use(self, tenant_id: int, code: str, exclude_id: int | None = None) -> bool:
        counters = Counter.objects.for_tenant(tenant_id).filter(code=code)
        if exclude_id is not None:
            counters = counters.exclude(id=exclude_id)
        return counters.exists()

    def save(self, counter: Counter) -> None:
        counter.save()

    def lock(self, tenant_id: int, counter_id: int) -> Counter | None:
        """Row lock until the end of the caller's transaction."""
        return (
            Counter.objects.for_tenant(tenant_id).select_for_update().filter(id=counter_id).first()
        )

    def get(self, tenant_id: int, counter_id: int) -> Counter:
        return Counter.objects.for_tenant(tenant_id).get(id=counter_id)

    def ids(self, tenant_id: int) -> list[int]:
        return list(Counter.objects.for_tenant(tenant_id).values_list("id", flat=True))

    def exists(self, tenant_id: int, counter_id: int) -> bool:
        return Counter.objects.for_tenant(tenant_id).filter(id=counter_id).exists()


counter_repository = DjangoCounterRepository()
