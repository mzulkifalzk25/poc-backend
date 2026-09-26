from datetime import UTC, datetime, timedelta

from apps.core.domain.cursor import Cursor
from apps.core.domain.sync_cursor import caught_up_cursor

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
FLOOR = Cursor(occurred_at=NOW - timedelta(seconds=10), id=0)


def test_first_sync_with_nothing_returned_starts_ten_seconds_back():
    assert caught_up_cursor(None, None, NOW) == FLOOR


def test_an_old_last_row_is_kept_exactly():
    last = Cursor(occurred_at=NOW - timedelta(hours=2), id=77)

    assert caught_up_cursor(last, None, NOW) == last


def test_a_recent_last_row_steps_back_to_the_overlap():
    last = Cursor(occurred_at=NOW - timedelta(seconds=3), id=77)

    assert caught_up_cursor(last, None, NOW) == FLOOR


def test_no_new_rows_keeps_an_old_since():
    since = Cursor(occurred_at=NOW - timedelta(days=1), id=5)

    assert caught_up_cursor(None, since, NOW) == since


def test_no_new_rows_after_a_recent_since_steps_back():
    since = Cursor(occurred_at=NOW - timedelta(seconds=1), id=5)

    assert caught_up_cursor(None, since, NOW) == FLOOR
