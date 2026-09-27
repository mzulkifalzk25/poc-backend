import psycopg
import pytest
from django.db import connection
from django.utils import timezone

from apps.sales.models import Bill
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

from .conftest import make_cashier
from .factories import make_product
from .payloads import BATCH_URL, batch, bill, line


def _post(client, counter, *bills):
    return client.post(BATCH_URL, batch(counter.id, *bills), format="json")


@pytest.mark.django_db
def test_owner_and_anonymous_callers_cannot_upload(tenant, counter, cashier, oil):
    body = batch(counter.id, bill(cashier.id, [line(oil)]))

    assert authed_client(tenant)[0].post(BATCH_URL, body, format="json").status_code == 403
    assert device_client("x" * 43).post(BATCH_URL, body, format="json").status_code == 401
    assert not Bill.objects.exists()


@pytest.mark.django_db
def test_a_revoked_pc_cannot_upload(pc, device, counter, cashier, oil):
    device[0].revoked_at = timezone.now()
    device[0].save()

    response = _post(pc, counter, bill(cashier.id, [line(oil)]))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "device_revoked"


@pytest.fixture
def foreign():
    tenant = make_tenant("other-mart")
    counter = Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")
    return {
        "counter": counter,
        "pc": device_client(activated_device(counter)[1]),
        "cashier": make_cashier(tenant, "Other Cashier"),
        "product": make_product(tenant.id, "8961002300022", price="50.00"),
    }


@pytest.mark.django_db
def test_another_tenants_product_or_cashier_is_rejected(pc, counter, cashier, oil, foreign):
    their_product = bill(cashier.id, [line(foreign["product"])], seq=1)
    their_cashier = bill(foreign["cashier"].id, [line(oil)], seq=2)

    results = _post(pc, counter, their_product, their_cashier).json()["results"]

    assert [r["status"] for r in results] == ["rejected", "rejected"]
    assert results[1]["errors"] == ["cashier_id: Unknown cashier."]
    assert not Bill.objects.filter(tenant_id=counter.tenant_id).exists()


@pytest.mark.django_db
def test_a_bill_id_stored_by_another_tenant_is_rejected(pc, counter, cashier, oil, foreign):
    theirs = bill(foreign["cashier"].id, [line(foreign["product"])])
    assert (
        _post(foreign["pc"], foreign["counter"], theirs).json()["results"][0]["status"] == "created"
    )

    mine = {**bill(cashier.id, [line(oil)]), "id": theirs["id"]}
    result = _post(pc, counter, mine).json()["results"][0]

    assert result["status"] == "rejected"
    assert Bill.objects.get(id=theirs["id"]).tenant_id == foreign["counter"].tenant_id


@pytest.mark.django_db
def test_tenants_keep_separate_bill_numbers(pc, counter, cashier, oil, foreign):
    _post(
        foreign["pc"], foreign["counter"], bill(foreign["cashier"].id, [line(foreign["product"])])
    )

    result = _post(pc, counter, bill(cashier.id, [line(oil)])).json()["results"][0]

    assert (result["status"], result["flags"]) == ("created", [])


@pytest.mark.django_db(transaction=True)
def test_a_second_batch_for_the_same_counter_waits_with_retry_after(pc, counter, cashier, oil):
    settings = connection.settings_dict
    with psycopg.connect(
        dbname=settings["NAME"],
        user=settings["USER"],
        password=settings["PASSWORD"],
        host=settings["HOST"] or None,
        port=settings["PORT"] or None,
        autocommit=True,
    ) as other:
        other.execute("SELECT pg_advisory_lock(7301, %s)", [counter.id])
        busy = _post(pc, counter, bill(cashier.id, [line(oil)]))

    assert busy.status_code == 429
    assert busy.json()["error"]["code"] == "batch_busy"
    assert busy["Retry-After"] == "5"
    assert not Bill.objects.exists()
    assert _post(pc, counter, bill(cashier.id, [line(oil)])).status_code == 200
