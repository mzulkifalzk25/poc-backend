from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import OuterRef, Subquery

from apps.accounts.domain.role_rules import CASHIER
from apps.accounts.models import PinDelay, User

# Rows written in the last minute are sent again next time, so a change that
# commits late with an earlier `updated_at` is never missed.
SYNC_OVERLAP = timedelta(seconds=60)


@dataclass(frozen=True)
class PeopleDelta:
    cashiers: list[User]
    next_since: datetime


def active_roster(tenant_id: int) -> list[User]:
    return list(
        User.objects.for_tenant(tenant_id)
        .filter(role=CASHIER, is_active=True)
        .order_by("full_name", "id")
    )


def people_since(
    tenant_id: int, counter_id: int, since: datetime | None, now: datetime
) -> PeopleDelta:
    """A full sync (no `since`) sends active cashiers only; a delta also sends
    deactivated ones so the counter can remove them."""
    cashiers = User.objects.for_tenant(tenant_id).filter(role=CASHIER)
    if since is None:
        cashiers = cashiers.filter(is_active=True)
    else:
        cashiers = cashiers.filter(updated_at__gt=since)
    unlocks = PinDelay.objects.filter(
        tenant_id=tenant_id, counter_id=counter_id, user_id=OuterRef("pk")
    )
    cashiers = cashiers.annotate(unlocked_at=Subquery(unlocks.values("unlocked_at")[:1]))
    next_since = now - SYNC_OVERLAP
    if since is not None:
        next_since = max(since, next_since)
    return PeopleDelta(list(cashiers.order_by("updated_at", "id")), next_since)
