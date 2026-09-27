from datetime import UTC, datetime

import pytest

from apps.sales.domain.errors import BatchBusyError
from apps.sales.use_cases.bill_upload import BillBatch
from apps.sales.use_cases.upload_bills import BatchRepositories, upload_bills


class LockedBills:
    def try_lock_counter(self, counter_id: int) -> bool:
        return False


@pytest.mark.django_db
def test_a_busy_counter_writes_nothing():
    batch = BillBatch(1, 2, 3, datetime(2026, 9, 27, tzinfo=UTC), bills=[])

    with pytest.raises(BatchBusyError):
        upload_bills(batch, BatchRepositories(bills=LockedBills()))
