from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.catalog.use_cases.products import (
    BarcodeExistsError,
    CategoryNotFoundError,
    NewProduct,
    create_product,
)
from apps.core.api.exceptions import ApiError

from .product_presenters import present_product_detail
from .product_serializers import ProductCreateSerializer


def barcode_exists() -> ApiError:
    message = "A live product already uses this barcode."
    return ApiError(
        code="barcode_exists", message=message, status_code=409, fields={"barcode": [message]}
    )


def category_not_found() -> ApiError:
    return ApiError(
        code="validation_error",
        message="Validation failed.",
        fields={"category_id": ["Category not found."]},
    )


class ProductListCreateView(APIView):
    permission_classes = [IsOwner]

    def post(self, request):
        serializer = ProductCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new = NewProduct(**serializer.validated_data)
        try:
            product = create_product(request.user.tenant_id, request.user.id, new)
        except BarcodeExistsError:
            raise barcode_exists() from None
        except CategoryNotFoundError:
            raise category_not_found() from None
        return Response(present_product_detail(product, new.stock), status=201)
