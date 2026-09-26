import math
from dataclasses import dataclass
from datetime import datetime, timedelta

FREE_FAILURES = 3
DELAYS_SECONDS = (30, 60, 300)


@dataclass(frozen=True)
class PinDelayState:
    """Wrong PINs for one cashier at one counter."""

    fail_count: int = 0
    next_allowed_at: datetime | None = None


def delay_seconds(fail_count: int) -> int:
    """Three free wrong PINs, then 30 s, 1 min and 5 min (the cap)."""
    extra = fail_count - FREE_FAILURES
    if extra <= 0:
        return 0
    return DELAYS_SECONDS[min(extra, len(DELAYS_SECONDS)) - 1]


def after_failure(state: PinDelayState, now: datetime) -> PinDelayState:
    fail_count = state.fail_count + 1
    delay = delay_seconds(fail_count)
    next_allowed_at = now + timedelta(seconds=delay) if delay else None
    return PinDelayState(fail_count=fail_count, next_allowed_at=next_allowed_at)


def cleared() -> PinDelayState:
    """After a correct PIN, an owner unlock or a PIN reset."""
    return PinDelayState()


def seconds_remaining(state: PinDelayState, now: datetime) -> int:
    if state.next_allowed_at is None or state.next_allowed_at <= now:
        return 0
    return math.ceil((state.next_allowed_at - now).total_seconds())
