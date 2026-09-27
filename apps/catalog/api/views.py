from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.catalog.domain.errors import CategoryNameExistsError
from apps.catalog.models import Category
from apps.catalog.use_cases.categories import (
    CategoryHasProductsError,
    TargetCategoryInvalidError,
    category_list,
    create_category,
    delete_category,
    find_category,
    move_products,
    update_category,
)
from apps.core.api.exceptions import ApiError

from .serializers import CategoryWriteSerializer, MoveProductsSerializer, present_category


def _name_exists() -> ApiError:
    message = "A category with this name already exists."
    return ApiError(
        code="name_exists", message=message, status_code=409, fields={"name": [message]}
    )


class CategoryListCreateView(APIView):
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == "GET" else [IsOwner()]

    def get(self, request):
        categories = category_list(request.user.tenant_id)
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

    def delete(self, request, category_id: int):
        category = _tenant_category(request, category_id)
        try:
            delete_category(category)
        except CategoryHasProductsError:
            raise ApiError(
                code="category_has_products",
                message="This category still has products (archived ones too). Move them first.",
                status_code=409,
            ) from None
        return Response(status=204)


class CategoryMoveProductsView(APIView):
    permission_classes = [IsOwner]

    def post(self, request, category_id: int):
        category = _tenant_category(request, category_id)
        serializer = MoveProductsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            moved = move_products(
                category, serializer.validated_data["to_category_id"], timezone.now()
            )
        except TargetCategoryInvalidError:
            raise ApiError(
                code="validation_error",
                message="Validation failed.",
                fields={"to_category_id": ["Choose another category of this store."]},
            ) from None
        return Response({"moved": moved})


def _tenant_category(request, category_id: int) -> Category:
    category = find_category(request.user.tenant_id, category_id)
    if category is None:
        raise ApiError(code="not_found", message="Category not found.", status_code=404)
    return category
