from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.reports.domain.rollup import SoldBill
from apps.reports.use_cases.rollup import RollupAlreadyRunning, roll_up_pending, run_rollup

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def sold() -> SoldBill:
    return SoldBill(
        id=uuid4(),
        tenant_id=1,
        counter_id=2,
        cashier_id=5,
        sold_at=NOW,
        item_count=Decimal("1"),
        tax=Decimal("0"),
        total=Decimal("620"),
        payments=(("cash", Decimal("620")),),
        lines=(),
    )


class FakeRollup:
    def __init__(self, pending: list[SoldBill]) -> None:
        self.pending = pending
        self.added: list = []
        self.marked: list = []
        self.locked = False
        self.lock_taken_elsewhere = False

    def try_lock_runner(self) -> bool:
        if self.lock_taken_elsewhere:
            return False
        self.locked = True
        return True

    def unlock_runner(self) -> None:
        self.locked = False

    def claim_pending(self, limit: int) -> list[SoldBill]:
        batch, self.pending = self.pending[:limit], self.pending[limit:]
        return batch

    def timezones(self, tenant_ids: set[int]) -> dict[int, str]:
        return dict.fromkeys(tenant_ids, "Asia/Karachi")

    def add(self, deltas, now) -> None:
        self.added.append(deltas)

    def mark_rolled_up(self, bill_ids, now) -> None:
        self.marked.append(bill_ids)


# The use case opens a real transaction; every read and write goes to the fake.
pytestmark = pytest.mark.django_db


def test_drains_the_queue_one_batch_at_a_time():
    fake = FakeRollup([sold() for _ in range(5)])

    assert roll_up_pending(NOW, batch_size=2, rollup=fake) == 5
    assert [len(ids) for ids in fake.marked] == [2, 2, 1]
    assert sum(next(iter(d.daily.values())).bills for d in fake.added) == 5


def test_an_empty_queue_writes_nothing():
    fake = FakeRollup([])

    assert roll_up_pending(NOW, rollup=fake) == 0
    assert fake.added == [] and fake.marked == []


def test_a_loop_runs_a_pass_every_interval_until_told_to_stop():
    fake = FakeRollup([sold(), sold()])
    passes: list[int] = []
    sleeps: list[float] = []
    stop_after = iter([True, True, False])

    run_rollup(
        lambda: NOW,
        loop=True,
        interval=30,
        keep_going=lambda: next(stop_after),
        sleep=sleeps.append,
        on_pass=passes.append,
        rollup=fake,
    )

    assert passes == [2, 0, 0]
    assert sleeps == [30, 30]
    assert fake.locked is False


def test_the_lock_is_released_when_a_pass_fails():
    fake = FakeRollup([sold()])

    def broken(deltas, now):
        raise RuntimeError("database gone")

    fake.add = broken
    with pytest.raises(RuntimeError):
        run_rollup(lambda: NOW, sleep=lambda seconds: None, rollup=fake)

    assert fake.locked is False


def test_a_second_runner_is_refused_and_writes_nothing():
    fake = FakeRollup([sold()])
    fake.lock_taken_elsewhere = True

    with pytest.raises(RollupAlreadyRunning):
        run_rollup(lambda: NOW, sleep=lambda seconds: None, rollup=fake)

    assert fake.marked == []
