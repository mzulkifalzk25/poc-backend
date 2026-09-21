from django.db import models

from apps.core.models import TenantModel


class ActivityLog(TenantModel):
    """Append-only: a database trigger rejects UPDATE and DELETE."""

    user_id = models.BigIntegerField(null=True, blank=True)
    action = models.CharField(max_length=50)
    entity_type = models.CharField(max_length=50, blank=True, default="")
    entity_id = models.CharField(max_length=64, blank=True, default="")
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    detail = models.JSONField(null=True, blank=True)
    device_id = models.BigIntegerField(null=True, blank=True)
    client_event_id = models.UUIDField(null=True, blank=True)
    occurred_at = models.DateTimeField()
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["tenant_id", "-occurred_at", "-id"], name="audit_log_tenant_time_idx"
            ),
            models.Index(
                fields=["tenant_id", "action", "-occurred_at", "-id"],
                name="audit_log_tenant_action_idx",
            ),
            models.Index(
                fields=["tenant_id", "entity_type", "entity_id"], name="audit_log_entity_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "client_event_id"],
                condition=models.Q(client_event_id__isnull=False),
                name="uniq_audit_log_tenant_client_event_id",
            )
        ]
