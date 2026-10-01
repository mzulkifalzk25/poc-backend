from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.core.api.exceptions import ApiError
from apps.core.api.pagination import PageNumberPagination
from apps.inventory.use_cases.receipts import (
    NewLine,
    NewReceipt,
    ProductsNotFoundError,
    ReceiptNotFoundError,
    SupplierNameExistsError,
    SupplierNotFoundError,
    confirm_receipt,
    cost_increase_lines,
    create_receipt,
    create_supplier,
    find_receipt,
    receipt_history,
    receipt_lines,
    supplier_list,
)

from .presenters import present_receipt, present_supplier
from .serializers import ReceiptSerializer, SupplierSerializer


def _invalid(field: str, message: str) -> ApiError:
    return ApiError(
        code="validation_error", message="Validation failed.", fields={field: [message]}
    )


class SupplierListCreateView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        return Response([present_supplier(s) for s in supplier_list(request.user.tenant_id)])

    def post(self, request):
        serializer = SupplierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            supplier = create_supplier(request.user.tenant_id, **serializer.validated_data)
        except SupplierNameExistsError:
            message = "A supplier with this name already exists."
            raise ApiError(
                code="name_exists", message=message, status_code=409, fields={"name": [message]}
            ) from None
        return Response(present_supplier(supplier), status=201)


class ReceiptListCreateView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(
            receipt_history(request.user.tenant_id), request, view=self
        )
        return paginator.get_paginated_response([present_receipt(r) for r in page])

    def post(self, request):
        serializer = ReceiptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        new = NewReceipt(
            supplier_id=data["supplier_id"],
            invoice_no=data["invoice_no"],
            delivery_date=data["delivery_date"],
            lines=[NewLine(**line) for line in data["lines"]],
        )
        try:
            receipt = create_receipt(request.user.tenant_id, new)
        except SupplierNotFoundError:
            raise _invalid("supplier_id", "Supplier not found.") from None
        except ProductsNotFoundError:
            raise _invalid("lines", "A product on the delivery was not found.") from None
        return Response(present_receipt(receipt, receipt_lines(receipt)), status=201)


class ReceiptDetailView(APIView):
    permission_classes = [IsOwner]

    def get(self, request, receipt_id: int):
        receipt = find_receipt(request.user.tenant_id, receipt_id)
        if receipt is None:
            raise ApiError(code="not_found", message="Receipt not found.", status_code=404)
        return Response(present_receipt(receipt, receipt_lines(receipt)))


class ReceiptConfirmView(APIView):
    permission_classes = [IsOwner]

    def post(self, request, receipt_id: int):
        try:
            receipt, lines = confirm_receipt(
                request.user.tenant_id, request.user.id, receipt_id, timezone.now()
            )
        except ReceiptNotFoundError:
            raise ApiError(
                code="not_found", message="Receipt not found.", status_code=404
            ) from None
        increases = [
            {
                "product_id": line.product_id,
                "name": line.product.name,
                "prev_cost": str(line.prev_cost),
                "unit_cost": str(line.unit_cost),
            }
            for line in cost_increase_lines(lines)
        ]
        return Response({**present_receipt(receipt, lines), "cost_increase_items": increases})
