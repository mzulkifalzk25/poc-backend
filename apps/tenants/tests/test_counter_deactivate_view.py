from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.api.tokens import issue_counter_tokens
from apps.accounts.models import User
from apps.audit.models import ActivityLog
from apps.shifts.models import Shift
from apps.shifts.use_cases.open_shift import ShiftOpening, open_shift
from apps.tenants.models import Counter, Device
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant
from apps.tenants.use_cases.device_access import DeviceRevokedError


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner(tenant):
    return authed_client(tenant)


@pytest.fixture
def counter(tenant) -> Counter:
    return Counter.objects.create(
        tenant_id=tenant.id, name="Counter 2", code="002", last_bill_seq=742
    )


@pytest.fixture
def device(counter) -> tuple[Device, str]:
    return activated_device(counter)


@pytest.fixture
def cashier(tenant) -> User:
    return User.objects.create(
        tenant_id=tenant.id, full_name="Zainab Khan", role="cashier", pin_hash="x"
    )


def _url(counter: Counter) -> str:
    return f"/api/v1/counters/{counter.id}/deactivate"


def _open_shift(counter: Counter, cashier: User, status: str = "open") -> Shift:
    return Shift.objects.create(
        id=uuid4(),
        tenant_id=counter.tenant_id,
        counter=counter,
        cashier=cashier,
        opened_at=timezone.now(),
        opening_cash="5000.00",
        status=status,
    )


def _counter_row(owner_client: APIClient, counter: Counter) -> dict:
    rows = owner_client.get("/api/v1/counters").json()
    return next(row for row in rows if row["id"] == counter.id)


@pytest.mark.django_db
def test_deactivation_revokes_the_pc_and_logs_it(owner, counter, device):
    client, user = owner

    response = client.post(_url(counter))

    assert response.status_code == 204
    device[0].refresh_from_db()
    assert device[0].revoked_at is not None
    assert device[0].revoked_by == user.id
    entry = ActivityLog.objects.get(action="counter_deactivated")
    assert (entry.user_id, entry.entity_id, entry.after) == (
        user.id,
        str(counter.id),
        {"device_id": device[0].id},
    )


@pytest.mark.django_db
def test_the_revoked_pc_and_its_cashier_sessions_are_refused(owner, counter, device, cashier):
    refresh = issue_counter_tokens(cashier, device[0].id)
    cashier_client = APIClient()
    cashier_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    owner[0].post(_url(counter))

    responses = [
        device_client(device[1]).get("/api/v1/pos/bootstrap"),
        cashier_client.get("/api/v1/pos/bootstrap"),
        APIClient().post("/api/v1/auth/refresh", {"refresh": str(refresh)}, format="json"),
    ]

    assert [r.status_code for r in responses] == [401, 401, 401]
    assert {r.json()["error"]["code"] for r in responses} == {"device_revoked"}


@pytest.mark.django_db
def test_the_counter_keeps_its_code_and_sequence(owner, counter, device):
    owner[0].post(_url(counter))

    row = _counter_row(owner[0], counter)
    assert (row["code"], row["last_bill_seq"], row["next_bill_no"]) == ("002", 742, "002000743")
    assert (row["status"], row["is_active"]) == ("deactivated", True)


@pytest.mark.django_db
def test_an_open_shift_blocks_deactivation(owner, counter, device, cashier):
    _open_shift(counter, cashier)

    response = owner[0].post(_url(counter))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "shift_open"
    device[0].refresh_from_db()
    assert device[0].revoked_at is None
    assert not ActivityLog.objects.filter(action="counter_deactivated").exists()


@pytest.mark.django_db
def test_closed_shifts_do_not_block_deactivation(owner, counter, device, cashier):
    _open_shift(counter, cashier, status="closed")

    assert owner[0].post(_url(counter)).status_code == 204


@pytest.mark.django_db
def test_a_counter_without_a_live_pc_is_a_quiet_no_op(owner, counter):
    response = owner[0].post(_url(counter))

    assert response.status_code == 204
    assert not ActivityLog.objects.filter(action="counter_deactivated").exists()


@pytest.mark.django_db
def test_another_tenants_or_unknown_counter_is_not_found(owner):
    foreign = Counter.objects.create(tenant_id=make_tenant("other-mart").id, name="C1", code="001")
    foreign_device, _ = activated_device(foreign)

    assert owner[0].post(_url(foreign)).status_code == 404
    assert owner[0].post("/api/v1/counters/999999/deactivate").status_code == 404
    foreign_device.refresh_from_db()
    assert foreign_device.revoked_at is None


@pytest.mark.django_db
def test_only_the_owner_deactivates(tenant, counter, device):
    cashier_client, _ = authed_client(tenant, role="cashier")

    assert cashier_client.post(_url(counter)).status_code == 403
    assert device_client(device[1]).post(_url(counter)).status_code in (401, 403)
    assert APIClient().post(_url(counter)).status_code == 401


@pytest.mark.django_db
def test_counters_list_shows_an_open_shift(owner, counter, cashier):
    assert _counter_row(owner[0], counter)["has_open_shift"] is False
    shift = _open_shift(counter, cashier)
    assert _counter_row(owner[0], counter)["has_open_shift"] is True
    Shift.objects.filter(id=shift.id).update(status="closed")
    assert _counter_row(owner[0], counter)["has_open_shift"] is False


@pytest.mark.django_db
def test_a_shift_cannot_open_on_a_pc_revoked_meanwhile(counter, device, cashier):
    Device.objects.filter(id=device[0].id).update(revoked_at=timezone.now())
    opening = ShiftOpening(
        tenant_id=counter.tenant_id,
        counter_id=counter.id,
        device_id=device[0].id,
        cashier_id=cashier.id,
        shift_id=uuid4(),
        opened_at=datetime(2026, 9, 27, 4, 0, tzinfo=UTC),
        opening_cash=Decimal("5000.00"),
    )

    with pytest.raises(DeviceRevokedError):
        open_shift(opening)
    assert not Shift.objects.exists()
