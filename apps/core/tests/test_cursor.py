from datetime import UTC, datetime

from apps.core.domain.cursor import Cursor


def test_cursor_round_trip():
    original = Cursor(occurred_at=datetime(2026, 9, 19, 12, 47, 3, tzinfo=UTC), id=42)

    decoded = Cursor.decode(original.encode())

    assert decoded == original


def test_cursor_token_is_opaque_and_url_safe():
    token = Cursor(occurred_at=datetime(2026, 9, 19, 12, 47, 3, tzinfo=UTC), id=42).encode()

    assert "|" not in token
    assert all(char.isalnum() or char in "-_=" for char in token)
