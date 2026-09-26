from datetime import timedelta

from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.tenants.api.device_auth import device_revoked
from apps.tenants.use_cases.device_access import DeviceRevokedError, ensure_device_live

from .authentication import DEVICE_CLAIM

COUNTER_REFRESH_LIFETIME = timedelta(days=30)


class CounterRefreshToken(RefreshToken):
    """A refresh token bound to a counter PC slides 30 days on every rotation,
    so a long outage never locks the counter out."""

    def set_exp(self, claim="exp", from_time=None, lifetime=None) -> None:
        if lifetime is None and DEVICE_CLAIM in self.payload:
            lifetime = COUNTER_REFRESH_LIFETIME
        super().set_exp(claim=claim, from_time=from_time, lifetime=lifetime)


def issue_counter_tokens(user: User, device_id: int) -> CounterRefreshToken:
    refresh = CounterRefreshToken()
    refresh[api_settings.USER_ID_CLAIM] = str(user.id)
    refresh[DEVICE_CLAIM] = device_id
    refresh.set_exp()
    refresh.outstand()
    return refresh


class RefreshSerializer(TokenRefreshSerializer):
    token_class = CounterRefreshToken

    def validate(self, attrs: dict) -> dict:
        refresh = self.token_class(attrs["refresh"])
        device_id = refresh.payload.get(DEVICE_CLAIM)
        if device_id is not None:
            _ensure_live(refresh.payload.get(api_settings.USER_ID_CLAIM), int(device_id))
        return super().validate(attrs)


def _ensure_live(user_id: str | None, device_id: int) -> None:
    tenant_id = User.objects.filter(id=user_id).values_list("tenant_id", flat=True).first()
    try:
        if tenant_id is None:
            raise DeviceRevokedError
        ensure_device_live(tenant_id, device_id)
    except DeviceRevokedError:
        raise device_revoked() from None
