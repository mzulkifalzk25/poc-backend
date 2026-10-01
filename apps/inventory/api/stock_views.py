from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.core.api.exceptions import ApiError
from apps.core.api.pagination import PageNumberPagination
from apps.inventory.use_cases.adjust_stock import Adjustment, ProductNotFoundError, adjust_stock
from apps.inventory.use_cases.stock_browse import browse_movements, stock_rows, stock_summary

from .presenters import present_movement, present_stock_row, present_summary
from .serializers import AdjustSerializer, MovementFilterSerializer, StockFilterSerializer


class StockListView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        filters = StockFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        tenant_id = request.user.tenant_id
        rows = stock_rows(tenant_id, filters.validated_data)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response([present_stock_row(p) for p in page])
        response.data["summary"] = present_summary(stock_summary(tenant_id))
        return response


class StockAdjustView(APIView):
    permission_classes = [IsOwner]

    def post(self, request):
        serializer = AdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = request.headers.get("Idempotency-Key", "")[:64]
        try:
            result = adjust_stock(
                request.user.tenant_id,
                request.user.id,
                Adjustment(key=key, **serializer.validated_data),
                timezone.now(),
            )
        except ProductNotFoundError:
            message = "Product not found."
            raise ApiError(code="not_found", message=message, status_code=404) from None
        return Response({"before": str(result.before), "after": str(result.after)})


class StockMovementsView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        query = MovementFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        page = browse_movements(
            request.user.tenant_id,
            {
                "product": data.get("product"),
                "types": data.get("type"),
                "from_": data.get("since"),
                "to": data.get("until"),
            },
            data.get("cursor"),
            data["limit"],
        )
        cursor = page.next_cursor.encode() if page.next_cursor else None
        return Response(
            {
                "results": [present_movement(m, page.users) for m in page.movements],
                "next_cursor": cursor,
            }
        )
