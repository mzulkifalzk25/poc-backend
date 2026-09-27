from uuid import uuid4

import pytest
from django.utils import timezone

from apps.audit.models import ActivityLog
from apps.shifts.models import Shift
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

from .conftest import cashier_client, make_cashier

OPEN_URL = "/api/v1/shifts/open"
CURRENT_URL = "/api/v1/shifts/current"


def _body(counter: Counter, cashier_id: int | None = None, **changes) -> dict:
    body = {
        "id": str(uuid4()),
        "counter_id": counter.id,
        "opened_at": "2026-09-27T04:00:00Z",
        "opening_cash": "5000.00",
    }
    if cashier_id is not None:
        body["cashier_id"] = cashier_id
    return {**body, **changes}


@pytest.mark.django_db
def test_pc_token_opens_a_shift_for_the_named_cashier(pc, counter, cashier, device):
    body = _body(counter, cashier.id)

    response = pc.post(OPEN_URL, body, format="json")

    assert response.status_code == 201
    shift = Shift.objects.get(id=body["id"])
    assert (shift.counter_id, shift.cashier_id, shift.status) == (counter.id, cashier.id, "open")
    assert response.json()["opening_cash"] == "5000.00"
    assert response.json()["expected_cash"] is None
    entry = ActivityLog.objects.get(action="shift_opened")
    assert (entry.user_id, entry.device_id, entry.entity_id) == (
        cashier.id,
        device[0].id,
        body["id"],
    )
    assert entry.detail == {"counter_id": counter.id, "opening_cash": "5000.00"}


@pytest.mark.django_db
def test_cashier_token_uses_its_own_cashier(till, tenant, counter, cashier):
    other = make_cashier(tenant, "Bilal Raza")

    response = till.post(OPEN_URL, _body(counter, other.id), format="json")

    assert response.status_code == 201
    assert response.json()["cashier_id"] == cashier.id


@pytest.mark.django_db
def test_opening_twice_with_the_same_id_is_a_duplicate(pc, counter, cashier):
    body = _body(counter, cashier.id)
    pc.post(OPEN_URL, body, format="json")

    response = pc.post(OPEN_URL, body, format="json")

    assert response.status_code == 200
    assert response.json()["id"] == body["id"]
    assert Shift.objects.count() == 1
    assert ActivityLog.objects.filter(action="shift_opened").count() == 1


@pytest.mark.django_db
def test_a_second_open_shift_on_the_counter_is_refused(pc, counter, cashier):
    pc.post(OPEN_URL, _body(counter, cashier.id), format="json")

    response = pc.post(OPEN_URL, _body(counter, cashier.id), format="json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "shift_already_open"
    assert Shift.objects.count() == 1


@pytest.mark.django_db
def test_a_closed_shift_lets_a_new_one_open(pc, counter, cashier):
    first = _body(counter, cashier.id)
    pc.post(OPEN_URL, first, format="json")
    Shift.objects.filter(id=first["id"]).update(status="closed", closed_at=timezone.now())

    response = pc.post(OPEN_URL, _body(counter, cashier.id), format="json")

    assert response.status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize("cashier_state", ["missing", "deactivated", "owner", "other_tenant"])
def test_pc_token_needs_an_active_cashier_of_the_tenant(pc, tenant, counter, cashier_state):
    cashier_ids = {
        "missing": None,
        "deactivated": make_cashier(tenant, "Usman Tariq", is_active=False).id,
        "owner": authed_client(tenant)[1].id,
        "other_tenant": make_cashier(make_tenant("other-mart")).id,
    }

    response = pc.post(OPEN_URL, _body(counter, cashier_ids[cashier_state]), format="json")

    assert response.status_code == 400
    assert "cashier_id" in response.json()["error"]["fields"]
    assert not Shift.objects.exists()


@pytest.mark.django_db
def test_the_counter_comes_from_the_pc(pc, tenant, counter, cashier):
    other = Counter.objects.create(tenant_id=tenant.id, name="Counter 1", code="001")

    response = pc.post(OPEN_URL, _body(other, cashier.id), format="json")

    assert response.status_code == 400
    assert "counter_id" in response.json()["error"]["fields"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "changes",
    [
        {"opening_cash": "-1.00"},
        {"opening_cash": "12.345"},
        {"id": "not-a-uuid"},
        {"opened_at": ""},
    ],
)
def test_malformed_open_requests_are_refused(pc, counter, cashier, changes):
    response = pc.post(OPEN_URL, _body(counter, cashier.id, **changes), format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.django_db
def test_an_id_used_by_another_tenant_is_refused(pc, counter, cashier):
    other_tenant = make_tenant("other-mart")
    other_counter = Counter.objects.create(tenant_id=other_tenant.id, name="C1", code="001")
    other_pc = device_client(activated_device(other_counter)[1])
    body = _body(other_counter, make_cashier(other_tenant).id)
    assert other_pc.post(OPEN_URL, body, format="json").status_code == 201

    response = pc.post(OPEN_URL, {**body, "counter_id": counter.id, "cashier_id": cashier.id})

    assert response.status_code == 400
    assert "id" in response.json()["error"]["fields"]
    assert Shift.objects.get(id=body["id"]).tenant_id == other_tenant.id


@pytest.mark.django_db
def test_owner_and_anonymous_callers_cannot_open(tenant, counter, cashier):
    owner = authed_client(tenant)[0]

    assert owner.post(OPEN_URL, _body(counter, cashier.id), format="json").status_code == 403
    assert device_client("x" * 43).post(OPEN_URL, _body(counter)).status_code == 401


@pytest.mark.django_db
def test_a_revoked_pc_is_refused(pc, device, counter, cashier):
    device[0].revoked_at = timezone.now()
    device[0].save()

    response = pc.post(OPEN_URL, _body(counter, cashier.id), format="json")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "device_revoked"


@pytest.mark.django_db
def test_current_gives_the_counters_open_shift(pc, till, counter, cashier):
    body = _body(counter, cashier.id)
    pc.post(OPEN_URL, body, format="json")

    response = till.get(CURRENT_URL)

    assert response.status_code == 200
    assert response.json()["id"] == body["id"]
    assert response.json()["status"] == "open"


@pytest.mark.django_db
def test_current_is_null_without_an_open_shift(till):
    response = till.get(CURRENT_URL)

    assert response.status_code == 200
    assert response.json() is None


@pytest.mark.django_db
def test_current_never_shows_another_tenants_or_counters_shift(till, tenant, cashier):
    other_counter = Counter.objects.create(tenant_id=tenant.id, name="Counter 1", code="001")
    other_pc = device_client(activated_device(other_counter)[1])
    other_pc.post(OPEN_URL, _body(other_counter, cashier.id), format="json")
    foreign = make_tenant("other-mart")
    foreign_counter = Counter.objects.create(tenant_id=foreign.id, name="C2", code="002")
    foreign_device, foreign_token = activated_device(foreign_counter)
    device_client(foreign_token).post(
        OPEN_URL, _body(foreign_counter, make_cashier(foreign).id), format="json"
    )

    assert till.get(CURRENT_URL).json() is None
    assert (
        cashier_client(make_cashier(foreign, "Hina Malik"), foreign_device)
        .get(CURRENT_URL)
        .json()["counter_id"]
        == foreign_counter.id
    )


@pytest.mark.django_db
def test_current_is_for_signed_in_cashiers_only(pc, tenant):
    assert pc.get(CURRENT_URL).status_code == 403
    assert authed_client(tenant)[0].get(CURRENT_URL).status_code == 403
