from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.core.api.exceptions import ApiError
from apps.tenants.use_cases.activation_codes import (
    CounterActiveError,
    CounterNotFoundError,
    issue_activation_code,
    revoke_activation_code,
)


class IssueCodeRequestSerializer(serializers.Serializer):
    counter_id = serializers.IntegerField()


def _counter_not_found() -> ApiError:
    return ApiError(code="not_found", message="Counter not found.", status_code=404)


def _counter_active() -> ApiError:
    return ApiError(
        code="counter_active",
        message="This counter already has an activated PC. Deactivate it first.",
        status_code=409,
    )


class DeviceCodeCreateView(APIView):
    permission_classes = [IsOwner]

    def post(self, request):
        serializer = IssueCodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            issued = issue_activation_code(
                tenant_id=request.user.tenant_id,
                counter_id=serializer.validated_data["counter_id"],
                user_id=request.user.id,
                now=timezone.now(),
            )
        except CounterNotFoundError:
            raise _counter_not_found() from None
        except CounterActiveError:
            raise _counter_active() from None
        return Response({"code": issued.code, "expires_at": issued.expires_at}, status=201)


class DeviceCodeRevokeView(APIView):
    permission_classes = [IsOwner]

    def delete(self, request, counter_id: int):
        try:
            revoke_activation_code(request.user.tenant_id, counter_id, timezone.now())
        except CounterNotFoundError:
            raise _counter_not_found() from None
        return Response(status=204)
