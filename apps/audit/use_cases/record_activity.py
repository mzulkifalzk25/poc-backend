from dataclasses import replace

from django.utils import timezone

from apps.audit.domain.activity import ActivityEntry
from apps.audit.models import ActivityLog
from apps.audit.repositories.activity_log import ActivityLogRepository, activity_log

__all__ = ["ActivityEntry", "record_activity", "record_failure"]


def record_activity(entry: ActivityEntry, log: ActivityLogRepository = activity_log) -> ActivityLog:
    """Write an activity-log row in the caller's current transaction."""
    return log.add(_stamped(entry))


def record_failure(entry: ActivityEntry, log: ActivityLogRepository = activity_log) -> ActivityLog:
    """Write a failure entry (PIN/password failures, throttled sign-ins,
    failed activation) outside the request's transaction."""
    return log.add_outside_transaction(_stamped(entry))


def _stamped(entry: ActivityEntry) -> ActivityEntry:
    return entry if entry.occurred_at else replace(entry, occurred_at=timezone.now())
