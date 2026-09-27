from datetime import datetime
from uuid import UUID, uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.api.tokens import issue_counter_tokens
from apps.accounts.models import User
from apps.audit.domain.client_events import is_client_action
from apps.audit.models import ActivityLog
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

URL = "/api/v1/audit/events/batch"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def counter(tenant):
    return Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")


@pytest.fixture
def device(counter):
    return activated_device(counter)


@pytest.fixture
def pc(device):
    return device_client(device[1])


@pytest.fixture
def cashier(tenant):
    return User.objects.create(
        tenant_id=tenant.id, full_name="Zainab Khan", role="cashier", pin_hash="x"
    )


@pytest.fixture
def till(cashier, device):
    client = APIClient()
    access = issue_counter_tokens(cashier, device[0].id).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _event(action="held_bill_deleted", event_id=None, **changes) -> dict:
    body = {
        "id": str(event_id or uuid4()),
        "action": action,
        "occurred_at": "2026-09-27T07:40:00Z",
        "entity_type": "held_bill",
        "entity_id": str(uuid4()),
        "detail": {"title": "Bill for Ahmed", "total": "1350.00"},
    }
    return {**body, **changes}


def _send(client, *events):
    return client.post(URL, {"events": list(events)}, format="json")


def test_only_pin_failures_and_held_bill_deletes_are_accepted():
    assert is_client_action("pin_failure") and is_client_action("held_bill_deleted")
    assert not any(is_client_action(a) for a in ["price_change", "shift_closed", "refund", ""])


@pytest.mark.django_db
def test_the_server_stamps_who_where_and_keeps_the_time(till, counter, device, cashier):
    body = _event(detail={"title": "Bill for Ahmed", "counter_id": 999, "total": "1350.00"})

    response = _send(till, body)

    assert response.json() == {"results": [{"id": body["id"], "status": "created"}]}
    entry = ActivityLog.objects.get(client_event_id=body["id"])
    assert (entry.tenant_id, entry.user_id, entry.device_id) == (
        counter.tenant_id,
        cashier.id,
        device[0].id,
    )
    assert entry.detail == {"title": "Bill for Ahmed", "total": "1350.00", "counter_id": counter.id}
    assert (entry.action, entry.entity_type, entry.entity_id) == (
        "held_bill_deleted",
        "held_bill",
        body["entity_id"],
    )
    assert entry.occurred_at == datetime.fromisoformat(body["occurred_at"])
    assert entry.ip == "127.0.0.1"


@pytest.mark.django_db
def test_a_pc_token_uploads_offline_pin_failures_without_a_user(pc, device):
    body = _event("pin_failure", entity_type=None, entity_id=None, detail={"user_id": 12})

    assert _send(pc, body).json()["results"][0]["status"] == "created"
    entry = ActivityLog.objects.get(client_event_id=body["id"])
    assert (entry.user_id, entry.device_id, entry.entity_type) == (None, device[0].id, "")


@pytest.mark.django_db
def test_retries_and_repeats_are_duplicates(till):
    body = _event()
    _send(till, body)

    again = _send(till, body, body).json()["results"]

    assert [r["status"] for r in again] == ["duplicate", "duplicate"]
    assert ActivityLog.objects.filter(client_event_id=body["id"]).count() == 1


@pytest.mark.django_db
def test_other_actions_and_malformed_events_are_rejected(till):
    other = _event("price_change")
    bad_time = _event(occurred_at="later")
    good = _event()

    results = _send(till, other, bad_time, {"action": "pin_failure"}, good).json()["results"]

    assert results == [
        {"id": other["id"], "status": "rejected"},
        {"id": bad_time["id"], "status": "rejected"},
        {"id": None, "status": "rejected"},
        {"id": good["id"], "status": "created"},
    ]
    assert ActivityLog.objects.count() == 1


@pytest.mark.django_db
def test_tenants_have_separate_event_ids(till, cashier):
    foreign = make_tenant("other-mart")
    foreign_counter = Counter.objects.create(tenant_id=foreign.id, name="C2", code="002")
    foreign_pc = device_client(activated_device(foreign_counter)[1])
    event_id = uuid4()

    mine = _send(till, _event(event_id=event_id)).json()["results"][0]
    theirs = _send(foreign_pc, _event(event_id=event_id)).json()["results"][0]

    assert (mine["status"], theirs["status"]) == ("created", "created")
    tenants = set(
        ActivityLog.objects.filter(client_event_id=event_id).values_list("tenant_id", flat=True)
    )
    assert tenants == {cashier.tenant_id, foreign.id}


@pytest.mark.django_db
@pytest.mark.parametrize("count", [0, 101])
def test_a_batch_holds_one_to_a_hundred_events(till, count):
    assert _send(till, *[_event() for _ in range(count)]).status_code == 400


@pytest.mark.django_db
def test_owners_and_revoked_pcs_cannot_upload(tenant, pc, device):
    assert _send(authed_client(tenant)[0], _event()).status_code == 403
    device[0].revoked_at = timezone.now()
    device[0].save()
    response = _send(pc, _event())
    assert (response.status_code, response.json()["error"]["code"]) == (401, "device_revoked")
    assert not ActivityLog.objects.exists()


@pytest.mark.django_db
def test_uploaded_ids_are_stored_as_uuids(till):
    body = _event()
    _send(till, body)

    assert ActivityLog.objects.get().client_event_id == UUID(body["id"])
