import pytest
from django.db import IntegrityError, transaction

from apps.tenants.models import Counter


@pytest.mark.django_db
def test_counter_code_is_unique_per_tenant():
    Counter.objects.create(tenant_id=1, name="Counter 1", code="001")

    with pytest.raises(IntegrityError), transaction.atomic():
        Counter.objects.create(tenant_id=1, name="Counter 1 Duplicate", code="001")


@pytest.mark.django_db
def test_same_counter_code_is_allowed_across_tenants():
    Counter.objects.create(tenant_id=1, name="Counter 1", code="001")
    Counter.objects.create(tenant_id=2, name="Counter 1", code="001")

    assert Counter.objects.filter(code="001").count() == 2


@pytest.mark.django_db
def test_counter_starts_with_no_bills():
    counter = Counter.objects.create(tenant_id=1, name="Counter 1", code="001")

    assert counter.last_bill_seq == 0
    assert counter.is_active is True
