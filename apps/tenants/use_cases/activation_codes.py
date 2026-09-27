from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db import transaction

from apps.tenants.domain.activation_code import expiry_for, format_code, generate_code, hash_code
from apps.tenants.models import Counter
from apps.tenants.repositories.activation_codes import (
    ActivationCodeRepository,
    CodeHashTakenError,
    code_repository,
)
from apps.tenants.repositories.counters import CounterRepository, counter_repository
from apps.tenants.repositories.devices import DeviceRepository, device_repository

_MAX_HASH_COLLISION_RETRIES = 5


class CounterNotFoundError(Exception):
    pass


class CounterActiveError(Exception):
    pass


@dataclass(frozen=True)
class IssuedCode:
    code: str
    expires_at: datetime


def issue_activation_code(
    tenant_id: int,
    counter_id: int,
    user_id: int,
    now: datetime,
    counters: CounterRepository = counter_repository,
    devices: DeviceRepository = device_repository,
    codes: ActivationCodeRepository = code_repository,
) -> IssuedCode:
    """Revokes any earlier unused code, then returns a new plain code once."""
    with transaction.atomic():
        counter = _lock_counter(counters, tenant_id, counter_id)
        if devices.counter_has_live_device(counter):
            raise CounterActiveError
        codes.revoke_unused(counter, now)
        return _create_code(codes, counter, user_id, now)


def revoke_activation_code(
    tenant_id: int,
    counter_id: int,
    now: datetime,
    counters: CounterRepository = counter_repository,
    codes: ActivationCodeRepository = code_repository,
) -> None:
    with transaction.atomic():
        counter = _lock_counter(counters, tenant_id, counter_id)
        codes.revoke_unused(counter, now)


def _lock_counter(counters: CounterRepository, tenant_id: int, counter_id: int) -> Counter:
    counter = counters.lock(tenant_id, counter_id)
    if counter is None:
        raise CounterNotFoundError
    return counter


def _create_code(
    codes: ActivationCodeRepository, counter: Counter, user_id: int, now: datetime
) -> IssuedCode:
    for _ in range(_MAX_HASH_COLLISION_RETRIES):
        code = generate_code()
        try:
            row = codes.add(counter, hash_code(code, settings.SECRET_KEY), expiry_for(now), user_id)
        except CodeHashTakenError:
            continue
        return IssuedCode(code=format_code(code), expires_at=row.expires_at)
    raise RuntimeError("Could not issue a unique activation code.")
