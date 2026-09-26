from datetime import UTC, datetime, timedelta

import pytest

from apps.accounts.domain.pin_delay import (
    PinDelayState,
    after_failure,
    cleared,
    delay_seconds,
    seconds_remaining,
)

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("fail_count", "seconds"),
    [(0, 0), (1, 0), (2, 0), (3, 0), (4, 30), (5, 60), (6, 300), (7, 300), (50, 300)],
)
def test_three_free_failures_then_30s_1min_5min_cap(fail_count, seconds):
    assert delay_seconds(fail_count) == seconds


def test_free_failures_set_no_delay():
    state = PinDelayState()
    for _ in range(3):
        state = after_failure(state, NOW)

    assert state.fail_count == 3
    assert state.next_allowed_at is None
    assert seconds_remaining(state, NOW) == 0


def test_fourth_failure_starts_a_30_second_delay():
    state = after_failure(PinDelayState(fail_count=3), NOW)

    assert state.next_allowed_at == NOW + timedelta(seconds=30)
    assert seconds_remaining(state, NOW) == 30
    assert seconds_remaining(state, NOW + timedelta(seconds=29.2)) == 1
    assert seconds_remaining(state, NOW + timedelta(seconds=30)) == 0


def test_delay_grows_to_one_then_five_minutes():
    fifth = after_failure(PinDelayState(fail_count=4), NOW)
    sixth = after_failure(fifth, NOW)
    seventh = after_failure(sixth, NOW)

    assert fifth.next_allowed_at == NOW + timedelta(minutes=1)
    assert sixth.next_allowed_at == NOW + timedelta(minutes=5)
    assert seventh.next_allowed_at == NOW + timedelta(minutes=5)


def test_cleared_state_starts_over():
    assert cleared() == PinDelayState(fail_count=0, next_allowed_at=None)
