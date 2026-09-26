from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.tenants.domain.activation_code import expiry_for, format_code, generate_code, hash_code
from apps.tenants.models import Counter, Device, DeviceCode

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
    tenant_id: int, counter_id: int, user_id: int, now: datetime
) -> IssuedCode:
    """Revokes any earlier unused code, then returns a new plain code once."""
    with transaction.atomic():
        counter = _lock_counter(tenant_id, counter_id)
        live = Device.objects.for_tenant(tenant_id).filter(counter=counter, revoked_at__isnull=True)
        if live.exists():
            raise CounterActiveError
        _revoke_unused_codes(counter, now)
        return _create_code(counter, user_id, now)


def revoke_activation_code(tenant_id: int, counter_id: int, now: datetime) -> None:
    with transaction.atomic():
        counter = _lock_counter(tenant_id, counter_id)
        _revoke_unused_codes(counter, now)


def _lock_counter(tenant_id: int, counter_id: int) -> Counter:
    try:
        return Counter.objects.for_tenant(tenant_id).select_for_update().get(id=counter_id)
    except Counter.DoesNotExist:
        raise CounterNotFoundError from None


def _revoke_unused_codes(counter: Counter, now: datetime) -> None:
    DeviceCode.objects.for_tenant(counter.tenant_id).filter(
        counter=counter, used_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now)


def _create_code(counter: Counter, user_id: int, now: datetime) -> IssuedCode:
    for _ in range(_MAX_HASH_COLLISION_RETRIES):
        code = generate_code()
        try:
            with transaction.atomic():
                row = DeviceCode.objects.create(
                    tenant_id=counter.tenant_id,
                    counter=counter,
                    code_hash=hash_code(code, settings.SECRET_KEY),
                    expires_at=expiry_for(now),
                    created_by=user_id,
                )
        except IntegrityError:
            continue
        return IssuedCode(code=format_code(code), expires_at=row.expires_at)
    raise RuntimeError("Could not issue a unique activation code.")
