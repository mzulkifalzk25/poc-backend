from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.catalog.models import Category
from apps.catalog.use_cases.categories import (
    CategoryNameExistsError,
    create_category,
    update_category,
)
from apps.core.api.exceptions import ApiError

from .serializers import CategoryWriteSerializer, present_category


def _name_exists() -> ApiError:
    message = "A category with this name already exists."
    return ApiError(
        code="name_exists", message=message, status_code=409, fields={"name": [message]}
    )


class CategoryListCreateView(APIView):
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == "GET" else [IsOwner()]

    def get(self, request):
        categories = (
            Category.objects.for_tenant(request.user.tenant_id)
            .filter(is_active=True)
            .order_by("sort_order", "name")
        )
        return Response([present_category(category) for category in categories])

    def post(self, request):
        serializer = CategoryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            category = create_category(request.user.tenant_id, **serializer.validated_data)
        except CategoryNameExistsError:
            raise _name_exists() from None
        return Response(present_category(category), status=201)


class CategoryDetailView(APIView):
    permission_classes = [IsOwner]

    def patch(self, request, category_id: int):
        category = _tenant_category(request, category_id)
        serializer = CategoryWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            category = update_category(category, serializer.validated_data)
        except CategoryNameExistsError:
            raise _name_exists() from None
        return Response(present_category(category))


def _tenant_category(request, category_id: int) -> Category:
    category = Category.objects.for_tenant(request.user.tenant_id).filter(id=category_id).first()
    if category is None:
        raise ApiError(code="not_found", message="Category not found.", status_code=404)
    return category
