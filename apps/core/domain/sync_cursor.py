from datetime import datetime, timedelta

from apps.core.domain.cursor import Cursor

SYNC_OVERLAP = timedelta(seconds=10)


def caught_up_cursor(
    last: Cursor | None, since: Cursor | None, now: datetime, overlap: timedelta = SYNC_OVERLAP
) -> Cursor:
    """`next_since` for the last page of a delta sync. A cursor never points
    later than `now - overlap`, so a row saved just before and committed just
    after this read is sent next time. Rows re-sent inside the overlap are
    harmless upserts. The client never edits the cursor."""
    floor = now - overlap
    candidate = last or since
    if candidate is None or candidate.occurred_at > floor:
        return Cursor(occurred_at=floor, id=0)
    return candidate
