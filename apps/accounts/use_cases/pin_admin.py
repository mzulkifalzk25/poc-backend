from datetime import datetime

from django.db import transaction

from apps.accounts.domain.pin import generate_pin
from apps.accounts.domain.role_rules import CASHIER
from apps.accounts.models import User
from apps.accounts.repositories.pin_delays import PinDelayRepository, pin_delay_repository
from apps.accounts.repositories.users import UserRepository, user_repository
from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.tenants.repositories.counters import CounterRepository, counter_repository

from .staff import Actor, set_pin


class NotACashierError(Exception):
    pass


def unlock_cashier(
    actor: Actor,
    user: User,
    now: datetime,
    users: UserRepository = user_repository,
    delays: PinDelayRepository = pin_delay_repository,
    counters: CounterRepository = counter_repository,
) -> None:
    _ensure_cashier(user)
    with transaction.atomic():
        _clear_delays_everywhere(delays, counters, user, now)
        users.save(user, ["updated_at"])
        _log(actor, "pin_unlock", user, now)


def reset_pin(
    actor: Actor,
    user: User,
    now: datetime,
    users: UserRepository = user_repository,
    delays: PinDelayRepository = pin_delay_repository,
    counters: CounterRepository = counter_repository,
) -> str:
    """Returns the new PIN once; it also clears any delay."""
    _ensure_cashier(user)
    pin = generate_pin()
    set_pin(user, pin)
    with transaction.atomic():
        users.save(user, ["pin_hash", "pin_verifier", "updated_at"])
        _clear_delays_everywhere(delays, counters, user, now)
        _log(actor, "pin_reset", user, now)
    return pin


def _ensure_cashier(user: User) -> None:
    if user.role != CASHIER:
        raise NotACashierError


def _clear_delays_everywhere(
    delays: PinDelayRepository, counters: CounterRepository, user: User, now: datetime
) -> None:
    """A row per counter, so a counter holding offline-only failures also sees
    `unlocked_at` in its next people sync."""
    delays.clear_everywhere(user, counters.ids(user.tenant_id), now)


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
