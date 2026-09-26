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


def activate_device(raw_code: str, app_version: str, ip: str | None, now: datetime) -> Activation:
    code = normalize_code(raw_code)
    if code is None:
        raise ActivationError("code_invalid")
    with transaction.atomic():
        row = _lock_usable_code(code, now)
        counter = (
            Counter.objects.for_tenant(row.tenant_id).select_for_update().get(id=row.counter_id)
        )
        live = Device.objects.for_tenant(row.tenant_id).filter(
            counter=counter, revoked_at__isnull=True
        )
        if live.exists():
            raise ActivationError("counter_active", row.tenant_id, row.counter_id)
        token = generate_device_token()
        device = Device.objects.create(
            tenant_id=counter.tenant_id,
            counter=counter,
            token_hash=hash_device_token(token),
            app_version=app_version,
            last_seen_at=now,
        )
        row.used_at = now
        row.save(update_fields=["used_at", "updated_at"])
        _log_activation(counter, device, ip, now)
    return Activation(device_token=token, device=device, counter=counter)


def _lock_usable_code(code: str, now: datetime) -> DeviceCode:
    code_hash = hash_code(code, settings.SECRET_KEY)
    row = DeviceCode.objects.select_for_update().filter(code_hash=code_hash).first()
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
