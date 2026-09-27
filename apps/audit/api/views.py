from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.counter_context import (
    COUNTER_AUTHENTICATION,
    IsCounterDeviceOrCashier,
    counter_context,
)
from apps.audit.use_cases.upload_events import REJECTED, EventSource, EventUpload, upload_events

MAX_EVENTS = 100


class EventBatchRequestSerializer(serializers.Serializer):
    events = serializers.ListField(
        child=serializers.JSONField(), allow_empty=False, max_length=MAX_EVENTS
    )


class EventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    action = serializers.CharField(max_length=50)
    occurred_at = serializers.DateTimeField()
    entity_type = serializers.CharField(max_length=50, required=False, allow_null=True)
    entity_id = serializers.CharField(max_length=64, required=False, allow_null=True)
    detail = serializers.DictField(required=False, allow_null=True)


class EventBatchView(APIView):
    authentication_classes = COUNTER_AUTHENTICATION
    permission_classes = [IsCounterDeviceOrCashier]

    def post(self, request):
        context = counter_context(request)
        serializer = EventBatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parsed = [_parse(raw) for raw in serializer.validated_data["events"]]
        source = EventSource(
            tenant_id=context.tenant_id,
            user_id=context.cashier_id,
            device_id=context.device_id,
            counter_id=context.counter_id,
            ip=request.META.get("REMOTE_ADDR"),
        )
        valid = [event for event in parsed if isinstance(event, EventUpload)]
        statuses = iter(upload_events(source, valid) if valid else [])
        results = [
            {"id": str(event.id), "status": next(statuses)}
            if isinstance(event, EventUpload)
            else {"id": event, "status": REJECTED}
            for event in parsed
        ]
        return Response({"results": results})


def _parse(raw) -> EventUpload | str | None:
    """An event, or the raw id of a malformed one."""
    event = EventSerializer(data=raw)
    if not event.is_valid():
        raw_id = raw.get("id") if isinstance(raw, dict) else None
        return raw_id if isinstance(raw_id, str) else None
    data = event.validated_data
    return EventUpload(
        id=data["id"],
        action=data["action"],
        occurred_at=data["occurred_at"],
        entity_type=data.get("entity_type") or "",
        entity_id=data.get("entity_id") or "",
        detail=data.get("detail") or {},
    )
