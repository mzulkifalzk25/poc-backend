from django.contrib import admin

from apps.audit.models import ActivityLog
from apps.core.read_only_admin import ReadOnlyAdmin


@admin.register(ActivityLog)
class ActivityLogAdmin(ReadOnlyAdmin):
    """Append-only: the database trigger also refuses UPDATE and DELETE."""

    list_display = ("occurred_at", "action", "entity_type", "entity_id", "user_id", "tenant_id")
    list_filter = ("tenant_id", "action")
    search_fields = ("entity_id",)
