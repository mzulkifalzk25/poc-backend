from uuid import uuid4

import pytest
from django.utils import timezone

from apps.audit.models import ActivityLog
from apps.sales.models import HeldBill
from apps.shifts.models import Shift
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import activated_device, authed_client, make_tenant

from .conftest import cashier_client, make_cashier

SYNC_URL = "/api/v1/held-bills/sync"


@pytest.fixture
def till(cashier, device):
    return cashier_client(cashier, device[0])


def _held(held_id=None, updated_at="2026-09-27T08:00:00Z", **changes) -> dict:
    body = {
        "id": str(held_id or uuid4()),
        "title": "Customer in blue kurta",
        "payload": {"lines": [{"product_id": 1, "qty": "2.000"}]},
        "total": "1350.00",
        "status": "held",
        "updated_at": updated_at,
    }
    return {**body, **changes}


def _sync(client, *held):
    return client.post(SYNC_URL, {"held": list(held)}, format="json")


@pytest.mark.django_db
def test_a_new_held_bill_is_mirrored_with_the_counters_open_shift(till, counter, cashier):
    shift = Shift.objects.create(
        id=uuid4(),
        tenant_id=counter.tenant_id,
        counter=counter,
        cashier=cashier,
        opened_at=timezone.now(),
        opening_cash="0",
    )
    body = _held()

    response = _sync(till, body)

    assert response.status_code == 200
    assert response.json() == {"results": [{"id": body["id"], "status": "created"}]}
    row = HeldBill.objects.get(id=body["id"])
    assert (row.counter_id, row.cashier_id, row.shift_id) == (counter.id, cashier.id, shift.id)
    assert (row.title, str(row.total), row.status) == ("Customer in blue kurta", "1350.00", "held")


@pytest.mark.django_db
def test_without_an_open_shift_the_shift_is_empty(till):
    body = _held()

    _sync(till, body)

    assert HeldBill.objects.get(id=body["id"]).shift_id is None


@pytest.mark.django_db
def test_the_newest_counter_change_wins(till):
    held_id = uuid4()
    _sync(till, _held(held_id, "2026-09-27T08:00:00Z"))

    newer = _sync(till, _held(held_id, "2026-09-27T08:05:00Z", status="recalled"))
    older = _sync(till, _held(held_id, "2026-09-27T08:01:00Z", status="deleted"))

    assert newer.json()["results"][0]["status"] == "updated"
    assert older.json()["results"][0]["status"] == "unchanged"
    assert HeldBill.objects.get(id=held_id).status == "recalled"


@pytest.mark.django_db
def test_a_deleted_held_bill_is_never_logged(till):
    held_id = uuid4()
    _sync(till, _held(held_id))

    _sync(till, _held(held_id, "2026-09-27T09:00:00Z", status="deleted"))

    assert HeldBill.objects.get(id=held_id).status == "deleted"
    assert not ActivityLog.objects.exists()


@pytest.mark.django_db
def test_malformed_rows_are_rejected_alone(till):
    good, bad = _held(), _held(status="lost", total="-1")

    results = _sync(till, good, bad, "junk").json()["results"]

    assert results == [
        {"id": good["id"], "status": "created"},
        {"id": bad["id"], "status": "rejected"},
        {"id": None, "status": "rejected"},
    ]
    assert HeldBill.objects.count() == 1


@pytest.mark.django_db
def test_another_counters_or_tenants_held_bill_is_rejected(till, tenant, cashier):
    other = Counter.objects.create(tenant_id=tenant.id, name="Counter 1", code="001")
    other_till = cashier_client(cashier, activated_device(other)[0])
    foreign = make_tenant("other-mart")
    foreign_counter = Counter.objects.create(tenant_id=foreign.id, name="Counter 2", code="002")
    foreign_till = cashier_client(make_cashier(foreign), activated_device(foreign_counter)[0])
    theirs, foreign_one = _held(), _held()
    _sync(other_till, theirs)
    _sync(foreign_till, foreign_one)

    results = _sync(till, {**theirs, "updated_at": "2026-09-28T00:00:00Z"}, foreign_one).json()

    assert [r["status"] for r in results["results"]] == ["rejected", "rejected"]
    assert HeldBill.objects.get(id=theirs["id"]).counter_id == other.id
    assert HeldBill.objects.get(id=foreign_one["id"]).tenant_id == foreign.id


@pytest.mark.django_db
def test_held_bill_sync_is_for_signed_in_cashiers_only(pc, tenant):
    assert _sync(pc, _held()).status_code == 403
    assert _sync(authed_client(tenant)[0], _held()).status_code == 403


@pytest.mark.django_db
def test_at_most_a_hundred_held_bills_per_request(till):
    response = _sync(till, *[_held() for _ in range(101)])

    assert response.status_code == 400
