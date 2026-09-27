from apps.tenants.domain.device_token import hash_device_token
from apps.tenants.models import Device
from apps.tenants.repositories.devices import DeviceRepository, device_repository


class DeviceUnknownError(Exception):
    pass


class DeviceRevokedError(Exception):
    pass


def resolve_device(token: str, devices: DeviceRepository = device_repository) -> Device:
    device = devices.by_token_hash(hash_device_token(token))
    if device is None:
        raise DeviceUnknownError
    if device.revoked_at is not None:
        raise DeviceRevokedError
    return device


def ensure_device_live(
    tenant_id: int, device_id: int, devices: DeviceRepository = device_repository
) -> None:
    """For a cashier session bound to a PC: a missing or revoked PC is refused."""
    if not devices.is_live(tenant_id, device_id):
        raise DeviceRevokedError


def bound_device(
    tenant_id: int, device_id: int, devices: DeviceRepository = device_repository
) -> Device:
    """The PC a signed-in cashier's token is bound to."""
    return devices.get(tenant_id, device_id)
