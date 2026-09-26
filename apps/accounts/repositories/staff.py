from datetime import datetime

from django.db.models import OuterRef, QuerySet, Subquery

from apps.accounts.models import PinDelay, User


def staff_with_pin_delay(tenant_id: int, now: datetime) -> QuerySet[User]:
    """Adds `pin_delay_until`: the latest running delay on any counter."""
    running = PinDelay.objects.filter(
        tenant_id=tenant_id, user_id=OuterRef("pk"), next_allowed_at__gt=now
    ).order_by("-next_allowed_at")
    return User.objects.for_tenant(tenant_id).annotate(
        pin_delay_until=Subquery(running.values("next_allowed_at")[:1])
    )
