from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner, IsOwnerOrCashier
from apps.catalog.models import Product
from apps.catalog.repositories.products import products_with_stock
from apps.catalog.use_cases.products import (
    BarcodeExistsError,
    CategoryNotFoundError,
    NewProduct,
    archive_product,
    create_product,
    restore_product,
    update_product,
)
from apps.core.api.exceptions import ApiError

from .product_presenters import present_product, present_product_detail
from .product_serializers import ProductCreateSerializer, ProductWriteSerializer


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


def tenant_product(request, product_id: int) -> Product:
    product = products_with_stock(request.user.tenant_id).filter(id=product_id).first()
    if product is None:
        raise ApiError(code="not_found", message="Product not found.", status_code=404)
    return product


class ProductDetailView(APIView):
    permission_classes = [IsOwner]

    def get(self, request, product_id: int):
        product = tenant_product(request, product_id)
        return Response(present_product_detail(product, product.qty))

    def patch(self, request, product_id: int):
        product = tenant_product(request, product_id)
        serializer = ProductWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            update_product(product, request.user.id, serializer.validated_data, timezone.now())
        except BarcodeExistsError:
            raise barcode_exists() from None
        except CategoryNotFoundError:
            raise category_not_found() from None
        return Response(present_product_detail(product, product.qty))


class ProductArchiveView(APIView):
    permission_classes = [IsOwner]

    def post(self, request, product_id: int):
        product = tenant_product(request, product_id)
        archive_product(product, request.user.id, timezone.now())
        return Response(present_product_detail(product, product.qty))


class ProductRestoreView(APIView):
    permission_classes = [IsOwner]

    def post(self, request, product_id: int):
        product = tenant_product(request, product_id)
        try:
            restore_product(product, request.user.id, timezone.now())
        except BarcodeExistsError:
            raise barcode_exists() from None
        return Response(present_product_detail(product, product.qty))


class ProductByBarcodeView(APIView):
    permission_classes = [IsOwnerOrCashier]

    def get(self, request, code: str):
        product = (
            products_with_stock(request.user.tenant_id)
            .filter(barcode=code.strip(), is_archived=False)
            .first()
        )
        if product is None:
            raise ApiError(
                code="unknown_barcode", message="No live product has this barcode.", status_code=404
            )
        include_cost = request.user.role == "owner"
        return Response(present_product(product, product.qty, include_cost=include_cost))
