from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.reports.models import SalesDaily


@pytest.mark.django_db
def test_one_daily_row_per_tenant_and_day_with_zero_defaults():
    row = SalesDaily.objects.create(tenant_id=1, local_date=date(2026, 9, 19))
    SalesDaily.objects.create(tenant_id=2, local_date=date(2026, 9, 19))

    with pytest.raises(IntegrityError), transaction.atomic():
        SalesDaily.objects.create(tenant_id=1, local_date=date(2026, 9, 19))

    row.refresh_from_db()
    assert (row.bills, row.gross, row.refund_amount) == (0, 0, 0)
