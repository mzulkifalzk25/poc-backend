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
from apps.accounts.models import PinDelay, User
from apps.accounts.repositories.pin_delays import PinDelayRepository, pin_delay_repository
from apps.accounts.repositories.users import UserRepository, user_repository


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


def pin_login(
    attempt: PinAttempt,
    now: datetime,
    users: UserRepository = user_repository,
    delays: PinDelayRepository = pin_delay_repository,
) -> User:
    """The delay row is committed before a rejection is raised, so a wrong
    PIN counts even though the request fails."""
    user = _active_cashier(users, attempt)
    with transaction.atomic():
        rejection = _apply_attempt(users, delays, user, attempt, now)
    if rejection is not None:
        raise rejection
    return user


def _apply_attempt(
    users: UserRepository,
    delays: PinDelayRepository,
    user: User,
    attempt: PinAttempt,
    now: datetime,
) -> PinRejectedError | None:
    row = delays.lock(attempt.tenant_id, attempt.counter_id, attempt.user_id)
    state = PinDelayState(row.fail_count, row.next_allowed_at)
    wait = seconds_remaining(state, now)
    if wait:
        return PinRejectedError("pin_throttled", wait, row.fail_count)
    if check_password(attempt.pin, user.pin_hash):
        _save_state(delays, row, cleared())
        user.last_active_at = now
        users.save(user, ["last_active_at", "updated_at"])
        return None
    state = after_failure(state, now)
    row.last_failed_at = now
    _save_state(delays, row, state)
    return PinRejectedError("invalid_pin", seconds_remaining(state, now), state.fail_count)


def _active_cashier(users: UserRepository, attempt: PinAttempt) -> User:
    user = users.active_cashier(attempt.tenant_id, attempt.user_id)
    if user is None or not user.pin_hash:
        raise PinRejectedError("invalid_pin")
    return user


def _save_state(delays: PinDelayRepository, row: PinDelay, state: PinDelayState) -> None:
    row.fail_count = state.fail_count
    row.next_allowed_at = state.next_allowed_at
    delays.save(row)
