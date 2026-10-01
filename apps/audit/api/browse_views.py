import csv

from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.permissions import IsOwner
from apps.audit.domain.activity_view import TYPES, describe, is_review, label
from apps.audit.models import ActivityLog
from apps.audit.use_cases.browse_activity import browse_activity, matching_rows, names_for
from apps.core.domain.cursor import Cursor
from apps.tenants.use_cases.tenants import tenant_of


class ActivityFilterSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=TYPES, required=False, default="all")
    from_date = serializers.DateField(required=False)
    to = serializers.DateField(required=False)
    user = serializers.IntegerField(required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=25)
    cursor = serializers.CharField(required=False, allow_blank=True)

    def validate_cursor(self, value: str) -> Cursor | None:
        if not value:
            return None
        try:
            return Cursor.decode(value)
        except ValueError:
            raise serializers.ValidationError("Invalid cursor.") from None


def _filters(request) -> dict:
    params = request.query_params.copy()
    if "from" in params:
        params["from_date"] = params["from"]
    serializer = ActivityFilterSerializer(data=params)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _text(row: ActivityLog, names) -> str:
    return describe(
        row.action, row.user_id, row.entity_id, row.before, row.after, row.detail, names
    )


class ActivityLogView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        tenant = tenant_of(request.user.tenant_id)
        page = browse_activity(tenant.id, tenant.timezone, timezone.now(), _filters(request))
        results = [
            {
                "id": row.id,
                "occurred_at": row.occurred_at.isoformat().replace("+00:00", "Z"),
                "user": page.names.users.get(row.user_id) if row.user_id else None,
                "action": label(row.action),
                "detail": _text(row, page.names),
                "flag": "review" if is_review(row.action, row.detail or {}) else "info",
            }
            for row in page.rows
        ]
        cursor = page.next_cursor.encode() if page.next_cursor else None
        return Response({"header": page.header, "results": results, "next_cursor": cursor})


class _Echo:
    def write(self, value: str) -> str:
        return value


class ActivityLogExportView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        tenant = tenant_of(request.user.tenant_id)
        rows = matching_rows(tenant.id, tenant.timezone, _filters(request)).order_by(
            "-occurred_at", "-id"
        )
        writer = csv.writer(_Echo())
        response = StreamingHttpResponse(
            _csv_lines(writer, tenant.id, rows), content_type="text/csv"
        )
        response["Content-Disposition"] = 'attachment; filename="activity-log.csv"'
        return response


def _csv_lines(writer, tenant_id: int, rows):
    yield writer.writerow(["Time (UTC)", "Who", "Action", "Details", "Flag"])
    batch: list[ActivityLog] = []
    for row in rows.iterator(chunk_size=500):
        batch.append(row)
        if len(batch) == 500:
            yield from _csv_batch(writer, tenant_id, batch)
            batch = []
    if batch:
        yield from _csv_batch(writer, tenant_id, batch)


def _safe(cell: str) -> str:
    """A spreadsheet runs a cell that starts with = + - or @ as a formula."""
    return f"'{cell}" if cell[:1] in ("=", "+", "-", "@") else cell


def _csv_batch(writer, tenant_id: int, batch: list[ActivityLog]):
    names = names_for(tenant_id, batch)
    for row in batch:
        yield writer.writerow(
            [
                row.occurred_at.isoformat(),
                _safe(names.users.get(row.user_id, "") if row.user_id else ""),
                label(row.action),
                _safe(_text(row, names)),
                "Review" if is_review(row.action, row.detail or {}) else "Info",
            ]
        )
