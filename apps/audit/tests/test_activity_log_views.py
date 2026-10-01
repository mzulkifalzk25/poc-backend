from datetime import UTC, datetime

import pytest

from apps.audit.models import ActivityLog
from apps.tenants.tests.helpers import authed_client, make_tenant

LOG = "/api/v1/activity-log"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner(tenant):
    return authed_client(tenant)


def _row(tenant, user, action, minute, **extra) -> ActivityLog:
    return ActivityLog.objects.create(
        tenant_id=tenant.id,
        user_id=user.id,
        action=action,
        occurred_at=datetime(2026, 9, 19, 10, minute, tzinfo=UTC),
        **extra,
    )


@pytest.mark.django_db
def test_rows_are_newest_first_with_labels_details_and_flags(owner, tenant):
    client, user = owner
    _row(tenant, user, "shift_opened", 1, detail={"opening_cash": "5000.00"})
    _row(
        tenant,
        user,
        "return_processed",
        2,
        detail={"amount": "570.00", "items": [{}, {}]},
    )

    body = client.get(LOG).json()

    assert [r["action"] for r in body["results"]] == ["Refund", "Shift opened"]
    refund = body["results"][0]
    assert refund["detail"] == "cashier Owner · 2 items · Rs 570"
    assert refund["flag"] == "review" and body["results"][1]["flag"] == "info"
    assert refund["user"] == "Owner"


@pytest.mark.django_db
def test_type_filter_and_cursor(owner, tenant):
    client, user = owner
    for minute in (1, 2, 3):
        _row(tenant, user, "price_changed", minute, entity_type="product", entity_id="7")
    _row(tenant, user, "shift_opened", 4)

    first = client.get(LOG, {"type": "price", "limit": 2}).json()
    rest = client.get(LOG, {"type": "price", "limit": 2, "cursor": first["next_cursor"]}).json()

    assert len(first["results"]) == 2 and len(rest["results"]) == 1
    assert rest["next_cursor"] is None


@pytest.mark.django_db
def test_header_counts_today_in_the_store_time_zone(owner, tenant):
    client, user = owner
    now = datetime.now(UTC)
    for action in ("return_processed", "return_processed", "held_bill_deleted", "price_changed"):
        ActivityLog.objects.create(
            tenant_id=tenant.id, user_id=user.id, action=action, occurred_at=now
        )
    ActivityLog.objects.create(
        tenant_id=tenant.id,
        user_id=user.id,
        action="return_processed",
        occurred_at=datetime(2020, 1, 1, tzinfo=UTC),
    )

    header = client.get(LOG).json()["header"]

    assert header == {
        "held_bills_deleted_today": 1,
        "refunds_today": 2,
        "price_changes_today": 1,
    }


@pytest.mark.django_db
def test_another_stores_log_is_never_shown(owner):
    client, _ = owner
    other = make_tenant("other-mart")
    ActivityLog.objects.create(
        tenant_id=other.id, action="shift_opened", occurred_at=datetime.now(UTC)
    )

    assert client.get(LOG).json()["results"] == []


@pytest.mark.django_db
def test_export_is_csv_for_the_chosen_filter_and_neutralises_formulas(owner, tenant):
    client, user = owner
    _row(tenant, user, "shift_opened", 1)
    _row(tenant, user, "return_processed", 2, detail={"amount": "100.00", "items": []})
    user.full_name = "=cmd"
    user.save()

    response = client.get(f"{LOG}/export", {"type": "refund"})
    text = b"".join(response.streaming_content).decode()

    assert response["Content-Type"] == "text/csv"
    assert text.splitlines()[0] == "Time (UTC),Who,Action,Details,Flag"
    assert len(text.splitlines()) == 2
    assert "'=cmd" in text and "Review" in text


@pytest.mark.django_db
def test_a_cashier_cannot_read_the_log(tenant):
    client, _ = authed_client(tenant, "cashier")

    assert client.get(LOG).status_code == 403
