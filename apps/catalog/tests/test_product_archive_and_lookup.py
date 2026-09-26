import pytest
from rest_framework.test import APIClient

from apps.audit.models import ActivityLog
from apps.catalog.models import Category, Product
from apps.tenants.tests.helpers import authed_client, make_tenant

PRODUCTS_URL = "/api/v1/products"
BARCODE = "8961002300022"


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner(tenant):
    return authed_client(tenant)


@pytest.fixture
def grocery(tenant):
    return Category.objects.create(tenant_id=tenant.id, name="Grocery", tint="green")


def _create(client, category, barcode=BARCODE, name="Cooking Oil 1L"):
    body = {
        "barcode": barcode,
        "name": name,
        "category_id": category.id,
        "unit": "litre",
        "price": "620.00",
        "cost": "540.00",
        "stock": "3",
    }
    return client.post(PRODUCTS_URL, body, format="json").json()


@pytest.mark.django_db
def test_archive_marks_the_product_and_logs_it(tenant, owner, grocery):
    client, owner_user = owner
    oil = _create(client, grocery)

    response = client.post(f"{PRODUCTS_URL}/{oil['id']}/archive")

    assert response.status_code == 200
    body = response.json()
    assert body["is_archived"] is True and body["archived_at"] and body["status"] == "archived"
    product = Product.objects.get(id=oil["id"])
    assert product.archived_by == owner_user.id
    assert ActivityLog.objects.for_tenant(tenant.id).filter(action="product_archived").count() == 1


@pytest.mark.django_db
def test_archiving_twice_changes_nothing(tenant, owner, grocery):
    oil = _create(owner[0], grocery)
    owner[0].post(f"{PRODUCTS_URL}/{oil['id']}/archive")
    first_archived_at = Product.objects.get(id=oil["id"]).archived_at

    response = owner[0].post(f"{PRODUCTS_URL}/{oil['id']}/archive")

    assert response.status_code == 200
    assert Product.objects.get(id=oil["id"]).archived_at == first_archived_at
    assert ActivityLog.objects.for_tenant(tenant.id).filter(action="product_archived").count() == 1


@pytest.mark.django_db
def test_restore_brings_it_back(tenant, owner, grocery):
    oil = _create(owner[0], grocery)
    owner[0].post(f"{PRODUCTS_URL}/{oil['id']}/archive")

    response = owner[0].post(f"{PRODUCTS_URL}/{oil['id']}/restore")

    assert response.status_code == 200
    assert response.json()["is_archived"] is False and response.json()["archived_at"] is None
    assert ActivityLog.objects.for_tenant(tenant.id).filter(action="product_restored").count() == 1


@pytest.mark.django_db
def test_restore_is_refused_while_a_live_product_has_the_barcode(owner, grocery):
    old = _create(owner[0], grocery)
    owner[0].post(f"{PRODUCTS_URL}/{old['id']}/archive")
    _create(owner[0], grocery, name="New Oil 1L")

    response = owner[0].post(f"{PRODUCTS_URL}/{old['id']}/restore")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "barcode_exists"
    assert Product.objects.get(id=old["id"]).is_archived is True


@pytest.mark.django_db
def test_barcode_lookup_finds_the_live_product(owner, grocery):
    oil = _create(owner[0], grocery)

    response = owner[0].get(f"{PRODUCTS_URL}/by-barcode/{BARCODE}")

    assert response.status_code == 200
    assert response.json()["id"] == oil["id"]
    assert response.json()["cost"] == "540.00"


@pytest.mark.django_db
def test_cashier_lookup_hides_cost(tenant, owner, grocery):
    _create(owner[0], grocery)
    cashier, _ = authed_client(tenant, role="cashier")

    response = cashier.get(f"{PRODUCTS_URL}/by-barcode/{BARCODE}")

    assert response.status_code == 200
    assert "cost" not in response.json()


@pytest.mark.django_db
def test_archived_or_unknown_barcode_is_404_unknown_barcode(owner, grocery):
    oil = _create(owner[0], grocery)
    owner[0].post(f"{PRODUCTS_URL}/{oil['id']}/archive")

    for code in (BARCODE, "0000000000000"):
        response = owner[0].get(f"{PRODUCTS_URL}/by-barcode/{code}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "unknown_barcode"


@pytest.mark.django_db
def test_lookup_never_finds_another_tenants_product(owner, grocery):
    _create(owner[0], grocery)
    other_client, _ = authed_client(make_tenant("other-mart"))

    assert other_client.get(f"{PRODUCTS_URL}/by-barcode/{BARCODE}").status_code == 404


@pytest.mark.django_db
def test_other_tenant_and_cashier_cannot_archive_or_restore(tenant, owner, grocery):
    oil = _create(owner[0], grocery)
    other_client, _ = authed_client(make_tenant("other-mart"))
    cashier, _ = authed_client(tenant, role="cashier")

    for action in ("archive", "restore"):
        assert other_client.post(f"{PRODUCTS_URL}/{oil['id']}/{action}").status_code == 404
        assert cashier.post(f"{PRODUCTS_URL}/{oil['id']}/{action}").status_code == 403
    assert Product.objects.get(id=oil["id"]).is_archived is False


@pytest.mark.django_db
def test_manager_cannot_look_up_barcodes(tenant):
    manager, _ = authed_client(tenant, role="manager")

    assert manager.get(f"{PRODUCTS_URL}/by-barcode/{BARCODE}").status_code == 403


def test_lookup_needs_sign_in():
    assert APIClient().get(f"{PRODUCTS_URL}/by-barcode/{BARCODE}").status_code == 401
