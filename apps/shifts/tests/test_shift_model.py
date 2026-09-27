from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.shifts.models import Shift
from apps.tenants.models import Counter


@pytest.fixture
def counter() -> Counter:
    return Counter.objects.create(tenant_id=1, name="Counter 2", code="002")


@pytest.fixture
def cashier() -> User:
    return User.objects.create(tenant_id=1, full_name="Zainab Khan", role="cashier")


def _shift(counter: Counter, cashier: User, status: str = "open") -> Shift:
    return Shift.objects.create(
        id=uuid4(),
        tenant_id=counter.tenant_id,
        counter=counter,
        cashier=cashier,
        opened_at=timezone.now(),
        opening_cash="5000.00",
        status=status,
    )


@pytest.mark.django_db
def test_a_new_shift_is_open_and_keeps_the_client_id(counter, cashier):
    shift = _shift(counter, cashier)

    stored = Shift.objects.get(id=shift.id)
    assert stored.status == "open"
    assert str(stored.opening_cash) == "5000.00"
    assert stored.expected_cash is None


@pytest.mark.django_db
def test_a_counter_has_at_most_one_open_shift(counter, cashier):
    _shift(counter, cashier)

    with pytest.raises(IntegrityError), transaction.atomic():
        _shift(counter, cashier)


@pytest.mark.django_db
def test_closed_shifts_do_not_block_a_new_open_one(counter, cashier):
    _shift(counter, cashier, status="closed")
    _shift(counter, cashier, status="closed")

    assert _shift(counter, cashier).status == "open"


@pytest.mark.django_db
def test_other_counters_open_their_own_shift(counter, cashier):
    other = Counter.objects.create(tenant_id=1, name="Counter 1", code="001")
    _shift(counter, cashier)

    assert _shift(other, cashier).counter_id == other.id
