from apps.tenants.domain.device_token import hash_device_token
from apps.tenants.models import Device


class DeviceUnknownError(Exception):
    pass


class DeviceRevokedError(Exception):
    pass


def resolve_device(token: str) -> Device:
    device = Device.objects.filter(token_hash=hash_device_token(token)).first()
    if device is None:
        raise DeviceUnknownError
    if device.revoked_at is not None:
        raise DeviceRevokedError
    return device


def ensure_device_live(tenant_id: int, device_id: int) -> None:
    """For a cashier session bound to a PC: a missing or revoked PC is refused."""
    if not (
        Device.objects.for_tenant(tenant_id).filter(id=device_id, revoked_at__isnull=True).exists()
    ):
        raise DeviceRevokedError
