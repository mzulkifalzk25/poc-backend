from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.tenants.api.device_auth import device_revoked
from apps.tenants.use_cases.device_access import DeviceRevokedError, ensure_device_live

DEVICE_CLAIM = "device_id"


class DeviceBoundJWTAuthentication(JWTAuthentication):
    """A token carrying a `device_id` claim (a cashier signed in on a counter
    PC) stops working as soon as that PC is deactivated."""

    def authenticate(self, request: Request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        device_id = token.get(DEVICE_CLAIM)
        if device_id is not None:
            try:
                ensure_device_live(user.tenant_id, int(device_id))
            except DeviceRevokedError:
                raise device_revoked() from None
        return result
