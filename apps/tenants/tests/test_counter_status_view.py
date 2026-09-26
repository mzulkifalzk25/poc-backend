from datetime import timedelta

import pytest
from django.utils import timezone

from apps.tenants.models import Counter, Device, DeviceCode

from .helpers import authed_client, make_tenant

COUNTERS_URL = "/api/v1/counters"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner_client(tenant):
    client, _ = authed_client(tenant)
    return client


@pytest.fixture
def counter(tenant) -> Counter:
    return Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")


def _row(client, counter: Counter) -> dict:
    rows = {row["id"]: row for row in client.get(COUNTERS_URL).json()}
    return rows[counter.id]


def _code(counter: Counter, **fields) -> DeviceCode:
    fields.setdefault("expires_at", timezone.now() + timedelta(minutes=15))
    return DeviceCode.objects.create(
        tenant_id=counter.tenant_id, counter=counter, code_hash=f"{counter.id}" * 8, **fields
    )


def _device(counter: Counter, suffix: str = "a", **fields) -> Device:
    return Device.objects.create(
        tenant_id=counter.tenant_id, counter=counter, token_hash=suffix * 64, **fields
    )


@pytest.mark.django_db
def test_new_counter_is_not_activated(owner_client, counter):
    row = _row(owner_client, counter)

    assert row["status"] == "not_activated"
    assert row["code_expires_at"] is None
    assert row["last_seen_at"] is None
    assert row["app_version"] is None
    assert row["unsynced_count"] is None
    assert row["has_open_shift"] is False
    assert row["has_bills"] is False
    assert row["next_bill_no"] == "002000001"


@pytest.mark.django_db
def test_counter_with_an_unused_code_is_code_ready(owner_client, counter):
    code = _code(counter)

    row = _row(owner_client, counter)

    assert row["status"] == "code_ready"
    assert row["code_expires_at"] is not None
    assert row["code_expires_at"].startswith(code.expires_at.strftime("%Y-%m-%dT%H:%M"))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [
        {"expires_at": timezone.now() - timedelta(minutes=1)},
        {"revoked_at": timezone.now()},
        {"used_at": timezone.now()},
    ],
)
def test_expired_revoked_or_used_codes_are_not_ready(owner_client, counter, fields):
    _code(counter, **fields)

    assert _row(owner_client, counter)["status"] == "not_activated"


@pytest.mark.django_db
def test_counter_with_a_live_pc_shows_its_details(owner_client, counter):
    seen = timezone.now()
    _device(counter, app_version="1.2.0", last_seen_at=seen, unsynced_count=4)

    row = _row(owner_client, counter)

    assert row["status"] == "activated"
    assert row["app_version"] == "1.2.0"
    assert row["unsynced_count"] == 4
    assert row["last_seen_at"] is not None
    assert row["code_expires_at"] is None


@pytest.mark.django_db
def test_counter_whose_pc_was_revoked_is_deactivated(owner_client, counter):
    _device(counter, revoked_at=timezone.now(), app_version="1.0.0")

    row = _row(owner_client, counter)

    assert row["status"] == "deactivated"
    assert row["app_version"] is None


@pytest.mark.django_db
def test_deactivated_counter_with_a_new_code_is_code_ready(owner_client, counter):
    _device(counter, revoked_at=timezone.now())
    _code(counter)

    assert _row(owner_client, counter)["status"] == "code_ready"


@pytest.mark.django_db
def test_owner_flag_does_not_change_the_status(owner_client, counter):
    _device(counter)
    Counter.objects.filter(id=counter.id).update(is_active=False)

    row = _row(owner_client, counter)

    assert row["is_active"] is False
    assert row["status"] == "activated"


@pytest.mark.django_db
def test_counter_that_billed_has_bills_and_the_next_number(owner_client, counter):
    Counter.objects.filter(id=counter.id).update(last_bill_seq=742)

    row = _row(owner_client, counter)

    assert row["has_bills"] is True
    assert row["last_bill_seq"] == 742
    assert row["next_bill_no"] == "002000743"


@pytest.mark.django_db
def test_detail_and_rename_use_the_same_shape(owner_client, counter):
    _device(counter)

    response = owner_client.patch(f"{COUNTERS_URL}/{counter.id}", {"name": "Front"})

    assert response.status_code == 200
    assert response.json()["status"] == "activated"


@pytest.mark.django_db
def test_another_tenants_pcs_never_show_on_my_counters(owner_client, counter):
    other = Counter.objects.create(
        tenant_id=make_tenant("other-mart").id, name="Counter 2", code="002"
    )
    _device(other, app_version="9.9.9")

    rows = owner_client.get(COUNTERS_URL).json()

    assert [row["id"] for row in rows] == [counter.id]
    assert rows[0]["status"] == "not_activated"


@pytest.mark.django_db
def test_counters_list_is_one_query_whatever_the_count(
    owner_client, tenant, django_assert_max_num_queries
):
    for code in ("001", "002", "003"):
        live = Counter.objects.create(tenant_id=tenant.id, name=f"Counter {code}", code=code)
        _device(live, suffix=code[-1])

    with django_assert_max_num_queries(2):  # the signed-in user, then the counters
        response = owner_client.get(COUNTERS_URL)

    assert len(response.json()) == 3
