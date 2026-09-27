from django.conf import settings
from django.db import models

from apps.core.models import TenantModel
from apps.tenants.models import Counter


class Shift(TenantModel):
    """A cashier's shift at a counter. The id is the counter's client UUID."""

    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"

    id = models.UUIDField(primary_key=True)
    counter = models.ForeignKey(
        Counter, on_delete=models.PROTECT, related_name="shifts", db_index=False
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shifts", db_index=False
    )
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_cash = models.DecimalField(max_digits=12, decimal_places=2)
    counted_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    difference = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    unsynced_at_close = models.PositiveIntegerField(null=True, blank=True)
    summary = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "counter"],
                condition=models.Q(status="open"),
                name="uniq_shift_open_per_counter",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "counter", "-opened_at"], name="shift_counter_opened_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"Shift {self.id} at counter {self.counter_id}"
