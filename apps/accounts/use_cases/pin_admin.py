from datetime import datetime

from django.db import transaction

from apps.accounts.domain.pin import generate_pin
from apps.accounts.domain.role_rules import CASHIER
from apps.accounts.models import PinDelay, User
from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.tenants.models import Counter

from .staff import Actor, set_pin


class NotACashierError(Exception):
    pass


def unlock_cashier(actor: Actor, user: User, now: datetime) -> None:
    _ensure_cashier(user)
    with transaction.atomic():
        _clear_delays_everywhere(user, now)
        user.save(update_fields=["updated_at"])
        _log(actor, "pin_unlock", user, now)


def reset_pin(actor: Actor, user: User, now: datetime) -> str:
    """Returns the new PIN once; it also clears any delay."""
    _ensure_cashier(user)
    pin = generate_pin()
    set_pin(user, pin)
    with transaction.atomic():
        user.save(update_fields=["pin_hash", "pin_verifier", "updated_at"])
        _clear_delays_everywhere(user, now)
        _log(actor, "pin_reset", user, now)
    return pin


def _ensure_cashier(user: User) -> None:
    if user.role != CASHIER:
        raise NotACashierError


def _clear_delays_everywhere(user: User, now: datetime) -> None:
    """A row per counter, so a counter holding offline-only failures also sees
    `unlocked_at` in its next people sync."""
    counter_ids = Counter.objects.for_tenant(user.tenant_id).values_list("id", flat=True)
    rows = [
        PinDelay(
            tenant_id=user.tenant_id,
            counter_id=counter_id,
            user_id=user.id,
            fail_count=0,
            next_allowed_at=None,
            unlocked_at=now,
        )
        for counter_id in counter_ids
    ]
    PinDelay.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["tenant_id", "counter_id", "user_id"],
        update_fields=["fail_count", "next_allowed_at", "unlocked_at", "updated_at"],
    )


def _log(actor: Actor, action: str, user: User, now: datetime) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            action=action,
            entity_type="user",
            entity_id=str(user.id),
            occurred_at=now,
        )
    )
