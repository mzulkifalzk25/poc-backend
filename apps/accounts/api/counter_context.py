from dataclasses import dataclass

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.domain.role_rules import CASHIER
from apps.tenants.api.device_auth import CounterDevice, DeviceAuthentication
from apps.tenants.use_cases.device_access import bound_device

from .authentication import DEVICE_CLAIM, DeviceBoundJWTAuthentication

COUNTER_AUTHENTICATION = [DeviceBoundJWTAuthentication, DeviceAuthentication]


@dataclass(frozen=True)
class CounterContext:
    tenant_id: int
    counter_id: int
    device_id: int
    cashier_id: int | None


def _bound_device_id(request: Request) -> int | None:
    token = request.auth
    if isinstance(request.user, CounterDevice) or token is None:
        return None
    device_id = token.get(DEVICE_CLAIM)
    if getattr(request.user, "role", None) != CASHIER or device_id is None:
        return None
    return int(device_id)


class IsCounterDeviceOrCashier(BasePermission):
    """D, C: the PC itself, or a cashier signed in on an activated PC."""

    message = "An activated counter PC is required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return isinstance(request.user, CounterDevice) or _bound_device_id(request) is not None


class IsCounterCashier(BasePermission):
    """C: a cashier signed in on an activated PC."""

    message = "A cashier signed in on a counter PC is required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return _bound_device_id(request) is not None


def counter_context(request: Request) -> CounterContext:
    user = request.user
    if isinstance(user, CounterDevice):
        return CounterContext(user.tenant_id, user.counter_id, user.device_id, None)
    device_id = _bound_device_id(request)
    device = bound_device(user.tenant_id, device_id)
    return CounterContext(user.tenant_id, device.counter_id, device.id, user.id)
