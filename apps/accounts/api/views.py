from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.api.exceptions import ApiError
from apps.tenants.models import Tenant

from ..use_cases.login import InvalidCredentials, authenticate_owner_or_manager
from .presenters import present_tenant, present_user
from .serializers import LoginRequestSerializer


class LoginView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = authenticate_owner_or_manager(**serializer.validated_data)
        except InvalidCredentials:
            raise ApiError(
                code="invalid_credentials",
                message="Incorrect login or password.",
                status_code=401,
            ) from None

        tenant = Tenant.objects.get(id=user.tenant_id)
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
