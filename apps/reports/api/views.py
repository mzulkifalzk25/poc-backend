import csv

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.core.api.exceptions import ApiError
from apps.core.domain.local_days import local_today
from apps.reports.use_cases import reports
from apps.reports.use_cases.reports import RangeError
from apps.tenants.use_cases.tenants import tenant_of

from . import presenters
from .serializers import (
    DashboardQuerySerializer,
    ExportQuerySerializer,
    MoneyQuerySerializer,
    RangeSerializer,
    SummaryQuerySerializer,
    TopProductsQuerySerializer,
)


def _query(serializer_class, request) -> dict:
    params = request.query_params.copy()
    if "from" in params:
        params["from_date"] = params["from"]
    serializer = serializer_class(data=params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _range_error(error: RangeError) -> ApiError:
    return ApiError(code="validation_error", message=error.message, fields={"to": [error.message]})


class OwnerReportView(APIView):
    permission_classes = [IsOwner]


class DashboardView(OwnerReportView):
    def get(self, request):
        query = _query(DashboardQuerySerializer, request)
        tenant = tenant_of(request.user.tenant_id)
        day = query.get("date") or local_today(timezone.now(), tenant.timezone)
        return Response(presenters.present_dashboard(reports.dashboard(tenant.id, day)))


class SummaryView(OwnerReportView):
    def get(self, request):
        query = _query(SummaryQuerySerializer, request)
        tenant = tenant_of(request.user.tenant_id)
        try:
            data = reports.summary(
                tenant.id, tenant.timezone, query["from_date"], query["to"], query["group"]
            )
        except RangeError as error:
            raise _range_error(error) from None
        return Response(presenters.present_summary(data))


class CategoriesView(OwnerReportView):
    def get(self, request):
        query = _query(RangeSerializer, request)
        try:
            rows = reports.products_report(request.user.tenant_id, query["from_date"], query["to"])
        except RangeError as error:
            raise _range_error(error) from None
        return Response(presenters.present_categories(rows))


class TopProductsView(OwnerReportView):
    def get(self, request):
        query = _query(TopProductsQuerySerializer, request)
        try:
            rows = reports.products_report(request.user.tenant_id, query["from_date"], query["to"])
        except RangeError as error:
            raise _range_error(error) from None
        return Response(presenters.present_top_products(rows, query["limit"]))


class CashiersView(OwnerReportView):
    def get(self, request):
        query = _query(TopProductsQuerySerializer, request)
        try:
            rows = reports.cashiers_report(request.user.tenant_id, query["from_date"], query["to"])
        except RangeError as error:
            raise _range_error(error) from None
        return Response(presenters.present_cashiers(rows, query["limit"]))


class MoneyView(OwnerReportView):
    def get(self, request):
        query = _query(MoneyQuerySerializer, request)
        try:
            data = reports.money(
                request.user.tenant_id, query["from_date"], query["to"], query["group"]
            )
        except RangeError as error:
            raise _range_error(error) from None
        return Response(presenters.present_money(data))


class RefundsByCashierView(OwnerReportView):
    def get(self, request):
        query = _query(RangeSerializer, request)
        try:
            rows = reports.cashiers_report(request.user.tenant_id, query["from_date"], query["to"])
        except RangeError as error:
            raise _range_error(error) from None
        return Response(presenters.present_refunds_by_cashier(rows))


class ExportView(OwnerReportView):
    """One CSV for the chosen report and range, sent straight back."""

    def get(self, request):
        query = _query(ExportQuerySerializer, request)
        tenant = tenant_of(request.user.tenant_id)
        first, last, report = query["from_date"], query["to"], query["report"]
        try:
            header, rows = _export_rows(tenant, report, first, last, query["group"])
        except RangeError as error:
            raise _range_error(error) from None
        response = HttpResponse(content_type="text/csv")
        name = f"{report}-{first.isoformat()}-{last.isoformat()}.csv"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        writer = csv.writer(response)
        writer.writerow(header)
        writer.writerows(rows)
        return response


def _export_rows(tenant, report: str, first, last, group: str):
    if report == "money":
        data = presenters.present_money(
            reports.money(tenant.id, first, last, "month" if group == "month" else "day")
        )
        columns = [
            "sales_total",
            "sales_cash",
            "sales_card",
            "sales_wallet",
            "refunds_total",
            "refunds_count",
            "stock_bought",
            "net",
            "gross_profit",
        ]
        rows = [[p["period"], *[p[c] for c in columns]] for p in data["periods"]]
        return ["period", *columns], rows
    if report == "refunds_by_cashier":
        rows = presenters.present_refunds_by_cashier(
            reports.cashiers_report(tenant.id, first, last)
        )
        header = ["cashier", "active", "refunds_count", "refunds_amount"]
        return header, [
            [r["name"], r["is_active"], r["refunds_count"], r["refunds_amount"]] for r in rows
        ]
    summary_group = group if group in ("hour", "day", "week") else "day"
    data = presenters.present_summary(
        reports.summary(tenant.id, tenant.timezone, first, last, summary_group)
    )
    return ["period", "revenue", "gross_profit", "bills"], [
        [p["period"], p["revenue"], p["gross_profit"], p["bills"]] for p in data["periods"]
    ]
