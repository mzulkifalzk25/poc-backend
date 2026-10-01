from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.core.api.exceptions import ApiError
from apps.sales.use_cases.bill_browse import bill_detail, browse_bills
from apps.tenants.use_cases.tenants import tenant_of

from .browse_presenters import present_bill_detail, present_bill_row
from .browse_serializers import BillFilterSerializer


class BillListView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        params = request.query_params.copy()
        if "from" in params:
            params["from_date"] = params["from"]
        filters = BillFilterSerializer(data=params)
        filters.is_valid(raise_exception=True)
        tenant = tenant_of(request.user.tenant_id)
        page = browse_bills(tenant.id, tenant.timezone, filters.validated_data)
        return Response(
            {
                "summary": {"bills": page.count, "total": str(page.total)},
                "results": [present_bill_row(bill) for bill in page.bills],
                "next_cursor": page.next_cursor.encode() if page.next_cursor else None,
            }
        )


class BillDetailView(APIView):
    permission_classes = [IsOwner]

    def get(self, request, bill_id):
        found = bill_detail(request.user.tenant_id, bill_id)
        if found is None:
            raise ApiError(code="not_found", message="Bill not found.", status_code=404)
        return Response(present_bill_detail(*found))
