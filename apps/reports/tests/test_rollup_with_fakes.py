from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.reports.domain.rollup import SoldBill
from apps.reports.use_cases.rollup import roll_up_pending

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
