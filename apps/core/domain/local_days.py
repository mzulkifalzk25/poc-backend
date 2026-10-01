from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def day_start(local_date: date, timezone_name: str) -> datetime:
    """UTC instant the local day begins."""
    return datetime.combine(local_date, time.min, ZoneInfo(timezone_name)).astimezone(UTC)


def range_bounds(first: date, last: date, timezone_name: str) -> tuple[datetime, datetime]:
    """`[start, end)` in UTC covering the local days `first` to `last` inclusive."""
    return day_start(first, timezone_name), day_start(last + timedelta(days=1), timezone_name)


def local_today(now: datetime, timezone_name: str) -> date:
    return now.astimezone(ZoneInfo(timezone_name)).date()
