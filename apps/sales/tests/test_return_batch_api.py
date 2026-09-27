from uuid import uuid4

import psycopg
import pytest
from django.db import connection
from django.utils import timezone

from apps.sales.models import Return
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

from .conftest import cashier_client, make_cashier
from .factories import make_product
from .payloads import BATCH_URL, batch, bill, line

RETURNS_URL = "/api/v1/returns/batch"


def _return(product, qty: str = "1.000", amount: str = "50.00", **changes) -> dict:
    body = {
        "id": str(uuid4()),
        "shift_id": str(uuid4()),
        "lines": [{"product_id": product.id, "qty": qty}],
        "reason": "changed_mind",
        "restock": True,
        "refund": {"method": "cash", "amount": amount},
        "returned_at": "2026-09-27T07:52:10Z",
    }
    return {**body, **changes}


def _post(client, *returns):
    return client.post(RETURNS_URL, {"returns": list(returns)}, format="json")


@pytest.fixture
def till(cashier, device):
    return cashier_client(cashier, device[0])


@pytest.mark.django_db
def test_a_signed_in_cashier_uploads_a_return(till, cashier, oil):
    body = _return(oil, original_bill_no="002-000999")

    response = _post(till, body)

    assert response.status_code == 200
    assert response.json()["server_time"]
    assert response.json()["results"] == [
        {"id": body["id"], "status": "created", "flags": ["bill_not_found"], "errors": []}
    ]
    stored = Return.objects.get(id=body["id"])
    assert (stored.cashier_id, stored.original_bill_no) == (cashier.id, "002-000999")


@pytest.mark.django_db
def test_the_same_batch_twice_stores_each_return_once(till, oil):
    body = _return(oil)
    _post(till, body)

    again = _post(till, body, body)

    assert [r["status"] for r in again.json()["results"]] == ["duplicate", "duplicate"]
    assert Return.objects.count() == 1


@pytest.mark.django_db
def test_a_pc_token_names_the_cashier_in_the_body(pc, cashier, oil):
    body = _return(oil, cashier_id=cashier.id)

    result = _post(pc, body).json()["results"][0]

    assert result["status"] == "created"
    assert Return.objects.get(id=body["id"]).cashier_id == cashier.id


@pytest.mark.django_db
def test_a_malformed_return_is_rejected_without_blocking_the_rest(till, oil):
    good = _return(oil)
    bad = _return(oil, qty="0", reason="bored", refund={"method": "cheque", "amount": "1"})

    results = _post(till, bad, good, "not a return").json()["results"]

    assert [r["status"] for r in results] == ["rejected", "created", "rejected"]
    assert results[0]["id"] == bad["id"]
    assert (
        "lines.0.qty: Ensure this value is greater than or equal to 0.001."
        in (results[0]["errors"])
    )
    assert any(error.startswith("reason:") for error in results[0]["errors"])
    assert any(error.startswith("refund.method:") for error in results[0]["errors"])
    assert results[2]["id"] is None


@pytest.mark.django_db
def test_an_empty_or_oversized_batch_is_a_validation_error(till, oil):
    assert _post(till).status_code == 400
    assert _post(till, *[_return(oil) for _ in range(51)]).status_code == 400
    assert not Return.objects.exists()


@pytest.mark.django_db
def test_owner_and_anonymous_callers_cannot_upload(tenant, oil):
    body = {"returns": [_return(oil)]}

    assert authed_client(tenant)[0].post(RETURNS_URL, body, format="json").status_code == 403
    assert device_client("x" * 43).post(RETURNS_URL, body, format="json").status_code == 401
    assert not Return.objects.exists()


@pytest.mark.django_db
def test_a_revoked_pc_cannot_upload(till, device, oil):
    device[0].revoked_at = timezone.now()
    device[0].save()

    response = _post(till, _return(oil))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "device_revoked"


@pytest.fixture
def foreign():
    tenant = make_tenant("other-mart")
    counter = Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")
    device = activated_device(counter)
    cashier = make_cashier(tenant, "Other Cashier")
    return {
        "pc": device_client(device[1]),
        "counter": counter,
        "cashier": cashier,
        "till": cashier_client(cashier, device[0]),
        "product": make_product(tenant.id, "8961002300022", price="50.00"),
    }


@pytest.mark.django_db
def test_another_stores_product_or_cashier_is_rejected(pc, till, oil, foreign):
    their_product = _return(foreign["product"])
    their_cashier = _return(oil, cashier_id=foreign["cashier"].id)

    first = _post(till, their_product).json()["results"][0]
    second = _post(pc, their_cashier).json()["results"][0]

    assert (first["status"], first["errors"]) == (
        "rejected",
        ["lines.0.product_id: Unknown product."],
    )
    assert (second["status"], second["errors"]) == ("rejected", ["cashier_id: Unknown cashier."])


@pytest.mark.django_db
def test_a_return_id_stored_by_another_store_is_rejected(till, oil, foreign):
    theirs = _return(foreign["product"])
    assert _post(foreign["till"], theirs).json()["results"][0]["status"] == "created"

    result = _post(till, {**_return(oil), "id": theirs["id"]}).json()["results"][0]

    assert result["status"] == "rejected"
    assert Return.objects.get(id=theirs["id"]).tenant_id == foreign["counter"].tenant_id


@pytest.mark.django_db
def test_another_stores_bill_number_is_not_found(till, oil, foreign):
    sale = bill(foreign["cashier"].id, [line(foreign["product"])])
    foreign["pc"].post(BATCH_URL, batch(foreign["counter"].id, sale), format="json")

    result = _post(till, _return(oil, original_bill_no=sale["bill_no"])).json()["results"][0]

    assert result["flags"] == ["bill_not_found"]
    assert Return.objects.get(id=result["id"]).original_bill_id is None


@pytest.mark.django_db(transaction=True)
def test_a_second_batch_for_the_same_counter_waits_with_retry_after(till, counter, oil):
    settings = connection.settings_dict
    with psycopg.connect(
        dbname=settings["NAME"],
        user=settings["USER"],
        password=settings["PASSWORD"],
        host=settings["HOST"] or None,
        port=settings["PORT"] or None,
        autocommit=True,
    ) as other:
        other.execute("SELECT pg_advisory_lock(7303, %s)", [counter.id])
        busy = _post(till, _return(oil))

    assert busy.status_code == 429
    assert busy.json()["error"]["code"] == "batch_busy"
    assert busy["Retry-After"] == "5"
    assert not Return.objects.exists()
    assert _post(till, _return(oil)).status_code == 200
