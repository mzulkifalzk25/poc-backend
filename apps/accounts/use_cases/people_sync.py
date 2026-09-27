from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.accounts.models import User
from apps.accounts.repositories.users import UserRepository, user_repository

# Rows written in the last minute are sent again next time, so a change that
# commits late with an earlier `updated_at` is never missed.
SYNC_OVERLAP = timedelta(seconds=60)


@dataclass(frozen=True)
class PeopleDelta:
    cashiers: list[User]
    next_since: datetime


def active_roster(tenant_id: int, users: UserRepository = user_repository) -> list[User]:
    return users.active_roster(tenant_id)


def people_since(
    tenant_id: int,
    counter_id: int,
    since: datetime | None,
    now: datetime,
    users: UserRepository = user_repository,
) -> PeopleDelta:
    """A full sync (no `since`) sends active cashiers only; a delta also sends
    deactivated ones so the counter can remove them."""
    cashiers = users.cashiers_for_sync(tenant_id, counter_id, since)
    next_since = now - SYNC_OVERLAP
    if since is not None:
        next_since = max(since, next_since)
    return PeopleDelta(cashiers, next_since)
