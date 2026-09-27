from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.audit.use_cases.record_activity import ActivityEntry, record_failure
from apps.core.api.exceptions import ApiError
from apps.tenants.use_cases.tenants import tenant_of

from ..use_cases.login import (
    InvalidCredentials,
    authenticate_owner_or_manager,
    find_login_account,
)
from .presenters import present_tenant, present_user
from .serializers import LoginRequestSerializer, LogoutRequestSerializer
from .throttling import LoginRateThrottle
from .tokens import RefreshSerializer


class LoginView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def throttled(self, request, wait):
        account = find_login_account(str(request.data.get("login", "")))
        _log_login_failure(request, account, "login_throttled")
        raise ApiError(
            code="login_throttled",
            message="Too many sign-in attempts. Try again shortly.",
            status_code=429,
            retry_after=int(wait) if wait is not None else None,
        )

    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = authenticate_owner_or_manager(**serializer.validated_data)
        except InvalidCredentials as error:
            _log_login_failure(request, error.user, "login_failure")
            raise ApiError(
                code="invalid_credentials",
                message="Incorrect login or password.",
                status_code=401,
            ) from None

        tenant = tenant_of(user.tenant_id)
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": present_user(user),
                "tenant": present_tenant(tenant),
                "landing": "admin",
            }
        )


def _log_login_failure(request, account, action: str) -> None:
    """Written outside the request transaction. An unknown or ambiguous login
    has no tenant to log against, so it is not logged."""
    if account is None:
        return
    record_failure(
        ActivityEntry(
            tenant_id=account.tenant_id,
            user_id=account.id,
            action=action,
            entity_type="user",
            entity_id=str(account.id),
            ip=request.META.get("REMOTE_ADDR"),
        )
    )


class RefreshView(TokenRefreshView):
    """Rotating refresh: ROTATE_REFRESH_TOKENS and BLACKLIST_AFTER_ROTATION
    are on, so this both validates `refresh` and issues a fresh pair. A
    counter session's token is refused once its PC is deactivated."""

    serializer_class = RefreshSerializer


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass

        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        tenant = tenant_of(user.tenant_id)
        return Response(
            {
                "user": present_user(user),
                "tenant": present_tenant(tenant),
                "permissions": {},
            }
        )
