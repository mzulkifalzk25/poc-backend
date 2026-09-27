import pytest

from apps.tenants.models import Counter
from apps.tenants.tests.helpers import activated_device, authed_client, device_client, make_tenant

from .conftest import cashier_client, make_cashier
from .factories import make_product
from .payloads import BATCH_URL, batch, bill, line

LOOKUP_URL = "/api/v1/bills/lookup"


@pytest.fixture
def till(cashier, device):
    return cashier_client(cashier, device[0])


def _upload(pc, counter, *bills):
    return pc.post(BATCH_URL, batch(counter.id, *bills), format="json").json()["results"]


@pytest.mark.django_db
def test_lookup_gives_the_lines_with_returnable_quantities(pc, till, counter, cashier, oil, rice):
    _upload(pc, counter, bill(cashier.id, [line(oil, "5.000"), line(rice, line_no=2)]))

    response = till.get(LOOKUP_URL, {"bill_no": "002000743"})

    assert response.status_code == 200
    assert response.json() == {
        "bill_no": "002000743",
        "lines": [
            {
                "product_id": oil.id,
                "name": oil.name,
                "qty": "5.000",
                "unit_price": "50.00",
                "returnable_qty": "5.000",
            },
            {
                "product_id": rice.id,
                "name": rice.name,
                "qty": "1.000",
                "unit_price": "1650.00",
                "returnable_qty": "1.000",
            },
        ],
    }


@pytest.mark.django_db
def test_lookup_accepts_the_printed_form(pc, till, counter, cashier, oil):
    _upload(pc, counter, bill(cashier.id, [line(oil)]))

    assert till.get(LOOKUP_URL, {"bill_no": "002-000743"}).status_code == 200


@pytest.mark.django_db
def test_lookup_finds_other_counters_bills(till, tenant, cashier, oil):
    other = Counter.objects.create(tenant_id=tenant.id, name="Counter 1", code="001")
    _upload(
        device_client(activated_device(other)[1]), other, bill(cashier.id, [line(oil)], code="001")
    )

    assert till.get(LOOKUP_URL, {"bill_no": "001000743"}).status_code == 200


@pytest.mark.django_db
def test_lookup_prefers_the_bill_that_owns_the_number(pc, till, counter, cashier, oil, rice):
    _upload(pc, counter, bill(cashier.id, [line(oil)]))
    _upload(pc, counter, bill(cashier.id, [line(rice)]))

    lines = till.get(LOOKUP_URL, {"bill_no": "002000743"}).json()["lines"]

    assert [row["product_id"] for row in lines] == [oil.id]


@pytest.mark.django_db
@pytest.mark.parametrize("bill_no", ["002000999", "abc", "0020007431"])
def test_an_unknown_bill_is_not_found(pc, till, counter, cashier, oil, bill_no):
    _upload(pc, counter, bill(cashier.id, [line(oil)]))

    response = till.get(LOOKUP_URL, {"bill_no": bill_no})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "bill_not_found"


@pytest.mark.django_db
def test_lookup_needs_a_bill_number(till):
    response = till.get(LOOKUP_URL)

    assert response.status_code == 400
    assert "bill_no" in response.json()["error"]["fields"]


@pytest.mark.django_db
def test_another_tenants_bill_is_not_found(till):
    foreign = make_tenant("other-mart")
    counter = Counter.objects.create(tenant_id=foreign.id, name="Counter 2", code="002")
    product = make_product(foreign.id, price="50.00")
    pc = device_client(activated_device(counter)[1])
    _upload(pc, counter, bill(make_cashier(foreign).id, [line(product)]))

    assert till.get(LOOKUP_URL, {"bill_no": "002000743"}).status_code == 404


@pytest.mark.django_db
def test_lookup_is_for_signed_in_cashiers_only(pc, tenant):
    assert pc.get(LOOKUP_URL, {"bill_no": "002000743"}).status_code == 403
    assert authed_client(tenant)[0].get(LOOKUP_URL, {"bill_no": "002000743"}).status_code == 403
