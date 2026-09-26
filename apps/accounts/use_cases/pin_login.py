from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth.hashers import check_password
from django.db import transaction

from apps.accounts.domain.pin_delay import (
    PinDelayState,
    after_failure,
    cleared,
    seconds_remaining,
)
from apps.accounts.domain.role_rules import CASHIER
from apps.accounts.models import PinDelay, User


class PinRejectedError(Exception):
    """`reason` is `invalid_pin` or `pin_throttled`; `retry_after` in seconds."""

    def __init__(self, reason: str, retry_after: int = 0, fail_count: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after
        self.fail_count = fail_count


@dataclass(frozen=True)
class PinAttempt:
    tenant_id: int
    counter_id: int
    user_id: int
    pin: str


def pin_login(attempt: PinAttempt, now: datetime) -> User:
    """The delay row is committed before a rejection is raised, so a wrong
    PIN counts even though the request fails."""
    user = _active_cashier(attempt)
    with transaction.atomic():
        rejection = _apply_attempt(user, attempt, now)
    if rejection is not None:
        raise rejection
    return user


def _apply_attempt(user: User, attempt: PinAttempt, now: datetime) -> PinRejectedError | None:
    row = _locked_delay_row(attempt)
    state = PinDelayState(row.fail_count, row.next_allowed_at)
    wait = seconds_remaining(state, now)
    if wait:
        return PinRejectedError("pin_throttled", wait, row.fail_count)
    if check_password(attempt.pin, user.pin_hash):
        _save_state(row, cleared())
        user.last_active_at = now
        user.save(update_fields=["last_active_at", "updated_at"])
        return None
    state = after_failure(state, now)
    row.last_failed_at = now
    _save_state(row, state)
    return PinRejectedError("invalid_pin", seconds_remaining(state, now), state.fail_count)


def _active_cashier(attempt: PinAttempt) -> User:
    user = (
        User.objects.for_tenant(attempt.tenant_id)
        .filter(id=attempt.user_id, role=CASHIER, is_active=True)
        .first()
    )
    if user is None or not user.pin_hash:
        raise PinRejectedError("invalid_pin")
    return user


def _locked_delay_row(attempt: PinAttempt) -> PinDelay:
    row, _ = PinDelay.objects.select_for_update().get_or_create(
        tenant_id=attempt.tenant_id, counter_id=attempt.counter_id, user_id=attempt.user_id
    )
    return row


def _save_state(row: PinDelay, state: PinDelayState) -> None:
    row.fail_count = state.fail_count
    row.next_allowed_at = state.next_allowed_at
    row.save()
