from rest_framework.generics import ListCreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.use_cases.staff import (
    Actor,
    NewStaff,
    StaffConflictError,
    StaffInvalidError,
    create_staff,
    update_staff,
)
from apps.core.api.exceptions import ApiError
from apps.core.api.pagination import PageNumberPagination

from .permissions import IsOwner
from .presenters import present_staff
from .serializers import StaffCreateSerializer, StaffFilterSerializer, StaffUpdateSerializer

_CONFLICT_MESSAGES = {
    "name_exists": "A cashier with this name already exists.",
    "email_exists": "This email is already in use.",
    "username_exists": "This username is already in use.",
    "cannot_deactivate_self": "You cannot deactivate your own account.",
}


def staff_error(error: StaffConflictError | StaffInvalidError) -> ApiError:
    if isinstance(error, StaffInvalidError):
        return ApiError(
            code="validation_error",
            message="Validation failed.",
            fields={error.field_name: [error.message]},
        )
    message = _CONFLICT_MESSAGES[error.code]
    return ApiError(
        code=error.code, message=message, status_code=409, fields={error.field_name: [message]}
    )


def actor_of(request) -> Actor:
    return Actor(tenant_id=request.user.tenant_id, user_id=request.user.id)


def tenant_user(request, user_id: int) -> User:
    user = User.objects.for_tenant(request.user.tenant_id).filter(id=user_id).first()
    if user is None:
        raise ApiError(code="not_found", message="User not found.", status_code=404)
    return user


class StaffListCreateView(ListCreateAPIView):
    permission_classes = [IsOwner]
    pagination_class = PageNumberPagination

    def get_queryset(self):
        filters = StaffFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        queryset = User.objects.for_tenant(self.request.user.tenant_id)
        return _apply_filters(queryset, filters.validated_data).order_by("full_name", "id")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([present_staff(user) for user in page])

    def create(self, request, *args, **kwargs):
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = create_staff(actor_of(request), NewStaff(**serializer.validated_data))
        except (StaffConflictError, StaffInvalidError) as error:
            raise staff_error(error) from None
        return Response(present_staff(user), status=201)


class StaffDetailView(APIView):
    permission_classes = [IsOwner]

    def patch(self, request, user_id: int):
        user = tenant_user(request, user_id)
        serializer = StaffUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            user = update_staff(actor_of(request), user, serializer.validated_data)
        except (StaffConflictError, StaffInvalidError) as error:
            raise staff_error(error) from None
        return Response(present_staff(user))


def _apply_filters(queryset, filters: dict):
    if "role" in filters:
        queryset = queryset.filter(role=filters["role"])
    if "status" in filters:
        queryset = queryset.filter(is_active=filters["status"] == "active")
    if "counter" in filters:
        queryset = queryset.filter(default_counter_id=filters["counter"])
    return queryset
