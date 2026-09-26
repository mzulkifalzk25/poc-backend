from dataclasses import dataclass
from typing import ClassVar

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.request import Request

from apps.core.api.exceptions import ApiError
from apps.tenants.models import Device
from apps.tenants.use_cases.device_access import (
    DeviceRevokedError,
    DeviceUnknownError,
    resolve_device,
)

KEYWORD = "Device"


@dataclass(frozen=True)
class CounterDevice:
    """`request.user` for a counter PC before anyone signs in."""

    device_id: int
    tenant_id: int
    counter_id: int
    is_authenticated: ClassVar[bool] = True
    is_anonymous: ClassVar[bool] = False


def device_revoked() -> ApiError:
    return ApiError(code="device_revoked", message="This PC was deactivated.", status_code=401)


def _device_invalid() -> ApiError:
    return ApiError(code="device_invalid", message="This PC is not activated.", status_code=401)


class DeviceAuthentication(BaseAuthentication):
    """`Authorization: Device <token>` for counter-PC requests."""

    def authenticate(self, request: Request) -> tuple[CounterDevice, Device] | None:
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != KEYWORD.lower().encode():
            return None
        if len(parts) != 2:
            raise _device_invalid()
        try:
            device = resolve_device(parts[1].decode())
        except (UnicodeDecodeError, DeviceUnknownError):
            raise _device_invalid() from None
        except DeviceRevokedError:
            raise device_revoked() from None
        principal = CounterDevice(device.id, device.tenant_id, device.counter_id)
        return principal, device

    def authenticate_header(self, request: Request) -> str:
        return KEYWORD
