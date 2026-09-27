from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db import transaction

from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.tenants.domain.activation_code import (
    CodeExpiredError,
    CodeInvalidError,
    CodeUsedError,
    ensure_code_usable,
    hash_code,
    normalize_code,
)
from apps.tenants.domain.device_token import generate_device_token, hash_device_token
from apps.tenants.models import Counter, Device, DeviceCode
from apps.tenants.repositories.activation_codes import ActivationCodeRepository, code_repository
from apps.tenants.repositories.counters import CounterRepository, counter_repository
from apps.tenants.repositories.devices import DeviceRepository, device_repository

_REASONS = {
    CodeInvalidError: "code_invalid",
    CodeExpiredError: "code_expired",
    CodeUsedError: "code_used",
}


class ActivationError(Exception):
    """`tenant_id` is known only when the code matched a stored code."""

    def __init__(self, reason: str, tenant_id: int | None = None, counter_id: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.tenant_id = tenant_id
        self.counter_id = counter_id


@dataclass(frozen=True)
class Activation:
    device_token: str
    device: Device
    counter: Counter


def activate_device(
    raw_code: str,
    app_version: str,
    ip: str | None,
    now: datetime,
    counters: CounterRepository = counter_repository,
    devices: DeviceRepository = device_repository,
    codes: ActivationCodeRepository = code_repository,
) -> Activation:
    code = normalize_code(raw_code)
    if code is None:
        raise ActivationError("code_invalid")
    with transaction.atomic():
        row = _lock_usable_code(codes, code, now)
        counter = counters.lock(row.tenant_id, row.counter_id)
        if devices.counter_has_live_device(counter):
            raise ActivationError("counter_active", row.tenant_id, row.counter_id)
        token = generate_device_token()
        device = devices.add(counter, hash_device_token(token), app_version, now)
        codes.mark_used(row, now)
        _log_activation(counter, device, ip, now)
    return Activation(device_token=token, device=device, counter=counter)


def _lock_usable_code(codes: ActivationCodeRepository, code: str, now: datetime) -> DeviceCode:
    row = codes.lock_by_hash(hash_code(code, settings.SECRET_KEY))
    if row is None:
        raise ActivationError("code_invalid")
    try:
        ensure_code_usable(row.expires_at, row.used_at, row.revoked_at, now)
    except tuple(_REASONS) as error:
        raise ActivationError(_REASONS[type(error)], row.tenant_id, row.counter_id) from None
    return row


def _log_activation(counter: Counter, device: Device, ip: str | None, now: datetime) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=counter.tenant_id,
            action="counter_activated",
            entity_type="counter",
            entity_id=str(counter.id),
            device_id=device.id,
            detail={"app_version": device.app_version},
            ip=ip,
            occurred_at=now,
        )
    )
