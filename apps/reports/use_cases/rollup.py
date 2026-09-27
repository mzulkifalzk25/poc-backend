from datetime import datetime

from django.db import transaction

from apps.reports.domain.rollup import sum_bills
from apps.reports.repositories.rollup import RollupRepository, rollup_repository

DEFAULT_BATCH_SIZE = 500


def roll_up_pending(
    now: datetime,
    batch_size: int = DEFAULT_BATCH_SIZE,
    rollup: RollupRepository = rollup_repository,
) -> int:
    """Adds every bill not rolled up yet to the report tables, one batch per
    transaction, and returns how many it added. A bill's deltas and its
    `rolled_up_at` commit together, so a bill is never counted twice."""
    total = 0
    while True:
        with transaction.atomic():
            bills = rollup.claim_pending(batch_size)
            if bills:
                deltas = sum_bills(bills, rollup.timezones({bill.tenant_id for bill in bills}))
                rollup.add(deltas, now)
                rollup.mark_rolled_up([bill.id for bill in bills], now)
        total += len(bills)
        if len(bills) < batch_size:
            return total
