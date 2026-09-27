from collections.abc import Callable
from datetime import datetime

from django.db import transaction
from django.db.models import QuerySet

from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.shifts.repositories.shifts import ShiftRepository, shift_repository
from apps.tenants.domain.counter_rules import ensure_code_can_change
from apps.tenants.models import Counter
from apps.tenants.repositories.counters import CounterRepository, counter_repository
from apps.tenants.repositories.devices import DeviceRepository, device_repository

# The activity log keeps the counter as the API shows it; the API layer
# supplies that view.
Snapshot = Callable[[Counter], dict]


class CounterCodeExistsError(Exception):
    pass


def counters_table(
    tenant_id: int, now: datetime, repo: CounterRepository = counter_repository
) -> QuerySet[Counter]:
    return repo.with_device_state(tenant_id, now)


def counter_of(
    tenant_id: int, counter_id: int, repo: CounterRepository = counter_repository
) -> Counter:
    return repo.get(tenant_id, counter_id)


def create_counter(
    tenant_id: int,
    user_id: int,
    fields: dict,
    snapshot: Snapshot,
    repo: CounterRepository = counter_repository,
) -> Counter:
    if repo.code_in_use(tenant_id, fields["code"]):
        raise CounterCodeExistsError
    counter = Counter(tenant_id=tenant_id, **fields)
    with transaction.atomic():
        repo.save(counter)
        _log(counter, user_id, "counter_created", None, snapshot(counter))
    return counter


def update_counter(
    user_id: int,
    counter: Counter,
    changes: dict,
    snapshot: Snapshot,
    repo: CounterRepository = counter_repository,
) -> Counter:
    """A counter's code is locked once it has billed, and unique per tenant."""
    new_code = changes.get("code", counter.code)
    if new_code != counter.code:
        ensure_code_can_change(counter.code, new_code, counter.last_bill_seq)
        if repo.code_in_use(counter.tenant_id, new_code, exclude_id=counter.id):
            raise CounterCodeExistsError
    before = dict(snapshot(counter))
    for name, value in changes.items():
        setattr(counter, name, value)
    with transaction.atomic():
        repo.save(counter)
        _log(counter, user_id, "counter_updated", before, snapshot(counter))
    return counter


def _log(counter: Counter, user_id: int, action: str, before: dict | None, after: dict) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=counter.tenant_id,
            user_id=user_id,
            action=action,
            entity_type="counter",
            entity_id=str(counter.id),
            before=before,
            after=after,
        )
    )


class CounterNotFoundError(Exception):
    pass


class CounterShiftOpenError(Exception):
    pass


def deactivate_counter(
    tenant_id: int,
    user_id: int,
    counter_id: int,
    now: datetime,
    repo: CounterRepository = counter_repository,
    devices: DeviceRepository = device_repository,
    shifts: ShiftRepository = shift_repository,
) -> None:
    """Revokes the counter's live PC. The counter row lock keeps a shift from
    opening between the check and the revoke (opening takes the same lock)."""
    with transaction.atomic():
        counter = repo.lock(tenant_id, counter_id)
        if counter is None:
            raise CounterNotFoundError
        if shifts.open_at_counter(tenant_id, counter_id) is not None:
            raise CounterShiftOpenError
        device = devices.revoke_live(counter, user_id, now)
        if device is not None:
            _log(counter, user_id, "counter_deactivated", None, {"device_id": device.id})
