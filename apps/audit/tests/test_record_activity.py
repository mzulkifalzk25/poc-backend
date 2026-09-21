import pytest
from django.db import transaction

from apps.audit.models import ActivityLog
from apps.audit.use_cases.record_activity import ActivityEntry, record_activity


@pytest.mark.django_db
def test_record_activity_writes_a_row_for_the_tenant():
    record_activity(
        ActivityEntry(tenant_id=1, action="product_created", entity_type="product", entity_id="7")
    )

    row = ActivityLog.objects.for_tenant(1).get()
    assert row.action == "product_created"
    assert row.entity_type == "product"
    assert row.entity_id == "7"


@pytest.mark.django_db
def test_a_rolled_back_change_leaves_no_activity_entry():
    class _Boom(Exception):
        pass

    with pytest.raises(_Boom), transaction.atomic():
        record_activity(ActivityEntry(tenant_id=1, action="product_created"))
        raise _Boom

    assert ActivityLog.objects.count() == 0
