from collections.abc import Callable
from datetime import datetime

from django.db import transaction

from apps.reports.domain.rollup import sum_bills, sum_returns
from apps.reports.repositories.rollup import RollupRepository, rollup_repository

DEFAULT_BATCH_SIZE = 500


def roll_up_pending(
    now: datetime,
    batch_size: int = DEFAULT_BATCH_SIZE,
    rollup: RollupRepository = rollup_repository,
) -> int:
    """Adds every bill and return not rolled up yet to the report tables, one
    batch of each per transaction, and returns how many it added. The deltas
    and `rolled_up_at` commit together, so nothing is ever counted twice."""
    total = 0
    while True:
        with transaction.atomic():
            bills = rollup.claim_pending(batch_size)
            returns = rollup.claim_pending_returns(batch_size)
            if bills or returns:
                tenants = {row.tenant_id for row in [*bills, *returns]}
                timezones = rollup.timezones(tenants)
                rollup.add(sum_returns(returns, timezones, sum_bills(bills, timezones)), now)
                rollup.mark_rolled_up([bill.id for bill in bills], now)
                rollup.mark_returns_rolled_up([ret.id for ret in returns], now)
        total += len(bills) + len(returns)
        if len(bills) < batch_size and len(returns) < batch_size:
            return total


class RollupAlreadyRunning(Exception):
    """Another runner holds the rollup lock."""


def run_rollup(
    clock: Callable[[], datetime],
    *,
    loop: bool = False,
    interval: float = 30,
    batch_size: int = DEFAULT_BATCH_SIZE,
    keep_going: Callable[[], bool] = lambda: True,
    sleep: Callable[[float], None],
    on_pass: Callable[[int], None] = lambda added: None,
    rollup: RollupRepository = rollup_repository,
) -> None:
    """One pass, or with `loop` a pass every `interval` seconds until
    `keep_going` says stop. Only one runner may work at a time."""
    if not rollup.try_lock_runner():
        raise RollupAlreadyRunning
    try:
        on_pass(roll_up_pending(clock(), batch_size, rollup))
        while loop and keep_going():
            sleep(interval)
            on_pass(roll_up_pending(clock(), batch_size, rollup))
    finally:
        rollup.unlock_runner()
