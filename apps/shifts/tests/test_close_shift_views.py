from uuid import uuid4

import pytest

from apps.audit.models import ActivityLog
from apps.shifts.models import Shift
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

from .conftest import make_cashier

OPEN_URL = "/api/v1/shifts/open"
MATCHING_SUMMARY = {"bills": 0, "total_sales": "0.00", "cash": "0.00"}


def _close_url(shift_id) -> str:
    return f"/api/v1/shifts/{shift_id}/close"


def _open(client, counter: Counter, cashier_id: int) -> str:
    shift_id = str(uuid4())
    body = {
        "id": shift_id,
        "counter_id": counter.id,
        "opened_at": "2026-09-27T04:00:00Z",
        "opening_cash": "5000.00",
        "cashier_id": cashier_id,
    }
    assert client.post(OPEN_URL, body, format="json").status_code == 201
    return shift_id


def _close_body(cashier_id: int | None = None, **changes) -> dict:
    body = {
        "closed_at": "2026-09-27T16:00:00Z",
        "counted_cash": "5030.00",
        "local_summary": MATCHING_SUMMARY,
        "unsynced_count": 0,
    }
    if cashier_id is not None:
        body["cashier_id"] = cashier_id
    return {**body, **changes}


@pytest.mark.django_db
def test_close_returns_the_server_figures(pc, counter, cashier, device):
    shift_id = _open(pc, counter, cashier.id)

    response = pc.post(_close_url(shift_id), _close_body(cashier.id), format="json")

    assert response.status_code == 200
    body = response.json()
    assert (body["expected_cash"], body["difference"], body["mismatch"]) == (
        "5000.00",
        "30.00",
        False,
    )
    assert body["server_summary"]["bills"] == 0
    assert body["server_summary"]["expected_cash"] == "5000.00"
    shift = Shift.objects.get(id=shift_id)
    assert (shift.status, str(shift.counted_cash), shift.unsynced_at_close) == (
        "closed",
        "5030.00",
        0,
    )
    assert shift.summary["local"] == MATCHING_SUMMARY
    entry = ActivityLog.objects.get(action="shift_closed")
    assert (entry.user_id, entry.device_id, entry.entity_id) == (cashier.id, device[0].id, shift_id)
    assert entry.detail["difference"] == "30.00"


@pytest.mark.django_db
def test_signed_in_cashier_closes_without_naming_a_cashier(pc, till, counter, cashier):
    shift_id = _open(pc, counter, cashier.id)

    response = till.post(_close_url(shift_id), _close_body(), format="json")

    assert response.status_code == 200
    assert ActivityLog.objects.get(action="shift_closed").user_id == cashier.id


@pytest.mark.django_db
def test_closing_again_returns_the_stored_result(pc, counter, cashier):
    shift_id = _open(pc, counter, cashier.id)
    first = pc.post(_close_url(shift_id), _close_body(cashier.id), format="json").json()

    again = pc.post(
        _close_url(shift_id), _close_body(cashier.id, counted_cash="1.00"), format="json"
    )

    assert again.status_code == 200
    assert again.json() == first
    assert ActivityLog.objects.filter(action="shift_closed").count() == 1


@pytest.mark.django_db
def test_unsynced_sales_or_a_different_local_count_are_a_mismatch(pc, counter, cashier):
    first = _open(pc, counter, cashier.id)
    unsynced = pc.post(_close_url(first), _close_body(cashier.id, unsynced_count=4), format="json")
    second = _open(pc, counter, cashier.id)
    other = _close_body(cashier.id, local_summary={"bills": 5, "cash": "900.00"})
    different = pc.post(_close_url(second), other, format="json")

    assert unsynced.json()["mismatch"] is True
    assert different.json()["mismatch"] is True


@pytest.mark.django_db
def test_a_closed_shift_frees_the_counter(pc, counter, cashier):
    shift_id = _open(pc, counter, cashier.id)
    pc.post(_close_url(shift_id), _close_body(cashier.id), format="json")

    assert _open(pc, counter, cashier.id) != shift_id


@pytest.mark.django_db
def test_unknown_or_other_counters_shifts_are_not_found(pc, tenant, counter, cashier):
    other_counter = Counter.objects.create(tenant_id=tenant.id, name="Counter 1", code="001")
    other_pc = device_client(activated_device(other_counter)[1])
    other_shift = _open(other_pc, other_counter, cashier.id)

    unknown = pc.post(_close_url(uuid4()), _close_body(cashier.id), format="json")
    other = pc.post(_close_url(other_shift), _close_body(cashier.id), format="json")

    assert (unknown.status_code, other.status_code) == (404, 404)
    assert Shift.objects.get(id=other_shift).status == "open"


@pytest.mark.django_db
def test_another_tenants_shift_is_not_found(pc, cashier):
    foreign = make_tenant("other-mart")
    foreign_counter = Counter.objects.create(tenant_id=foreign.id, name="C2", code="002")
    foreign_pc = device_client(activated_device(foreign_counter)[1])
    foreign_shift = _open(foreign_pc, foreign_counter, make_cashier(foreign).id)

    response = pc.post(_close_url(foreign_shift), _close_body(cashier.id), format="json")

    assert response.status_code == 404
    assert Shift.objects.get(id=foreign_shift).status == "open"


@pytest.mark.django_db
def test_pc_token_close_needs_an_active_cashier(pc, tenant, counter, cashier):
    shift_id = _open(pc, counter, cashier.id)
    deactivated = make_cashier(tenant, "Usman Tariq", is_active=False)

    missing = pc.post(_close_url(shift_id), _close_body(), format="json")
    inactive = pc.post(_close_url(shift_id), _close_body(deactivated.id), format="json")

    assert (missing.status_code, inactive.status_code) == (400, 400)
    assert Shift.objects.get(id=shift_id).status == "open"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "changes",
    [
        {"counted_cash": "-5.00"},
        {"counted_cash": "abc"},
        {"closed_at": "yesterday"},
        {"unsynced_count": -1},
        {"local_summary": "all good"},
    ],
)
def test_malformed_close_requests_are_refused(pc, counter, cashier, changes):
    shift_id = _open(pc, counter, cashier.id)

    response = pc.post(_close_url(shift_id), _close_body(cashier.id, **changes), format="json")

    assert response.status_code == 400
    assert Shift.objects.get(id=shift_id).status == "open"


@pytest.mark.django_db
def test_owner_cannot_close_a_counters_shift(pc, tenant, counter, cashier):
    shift_id = _open(pc, counter, cashier.id)

    response = authed_client(tenant)[0].post(_close_url(shift_id), _close_body(), format="json")

    assert response.status_code == 403
