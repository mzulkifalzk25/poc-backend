import pytest
from django.apps import apps
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import ActivityLog
from apps.catalog.models import Category, Product
from apps.core.models import TenantModel
from apps.inventory.models import StockLevel
from apps.tenants.domain.activation_code import hash_code, normalize_code
from apps.tenants.domain.device_token import hash_device_token
from apps.tenants.models import Counter, Device, DeviceCode, Tenant, TenantSettings
from apps.tenants.tests.helpers import device_client, make_tenant
from scripts.seed.demo_tenant import RESET_ORDER, seed_demo_tenant
from scripts.seed.sample_data import COUNTERS, PRODUCTS, TENANT_SLUG
from scripts.seed.summary import summary_lines


def _seed():
    return seed_demo_tenant(timezone.now(), COUNTERS, PRODUCTS)


def _tenant_counts(tenant_id: int) -> dict[str, int]:
    return {
        model.__name__: model.objects.for_tenant(tenant_id).count()
        for model in (*RESET_ORDER, ActivityLog)
    }


def test_reset_covers_every_tenant_table_except_the_activity_log():
    tenant_models = {
        model
        for model in apps.get_models()
        if issubclass(model, TenantModel) and model is not ActivityLog
    }

    assert tenant_models == set(RESET_ORDER)


@pytest.mark.django_db
def test_seeds_the_store_owner_and_settings():
    result = _seed()

    tenant = Tenant.objects.get(slug=TENANT_SLUG)
    owner = User.objects.for_tenant(tenant.id).get(role="owner")
    assert (tenant.name, tenant.timezone) == ("Fresh Basket Mart", "Asia/Karachi")
    assert TenantSettings.objects.get(tenant=tenant).store_name == "Fresh Basket Mart"
    assert (owner.full_name, owner.username) == ("Sana Ahmed", "sana")
    assert owner.check_password(result.owner_password)


@pytest.mark.django_db
def test_seeds_cashiers_with_working_passwords_emails_and_default_counters():
    result = _seed()

    counters = dict(Counter.objects.for_tenant(result.tenant.id).values_list("id", "code"))
    for cashier in User.objects.for_tenant(result.tenant.id).filter(role="cashier"):
        password = result.cashier_passwords[cashier.full_name]
        assert cashier.check_password(password)
        assert cashier.email == cashier.full_name.lower().replace(" ", ".") + "@example.com"
    rows = User.objects.for_tenant(result.tenant.id).filter(role="cashier").order_by("id")
    assert [(u.full_name, counters.get(u.default_counter_id), u.is_active) for u in rows] == [
        ("Zainab Khan", "002", True),
        ("Bilal Raza", "001", True),
        ("Hina Malik", "003", True),
        ("Usman Tariq", None, False),
    ]


@pytest.mark.django_db
def test_counters_001_and_002_are_activated_and_003_has_a_fresh_code():
    result = _seed()

    live = Device.objects.for_tenant(result.tenant.id).filter(revoked_at__isnull=True)
    assert sorted(live.values_list("counter__code", flat=True)) == ["001", "002"]
    for code, token in result.device_tokens.items():
        assert live.get(counter__code=code).token_hash == hash_device_token(token)
    issued = result.activation_codes["003"]
    code_hash = hash_code(normalize_code(issued.code), settings.SECRET_KEY)
    row = DeviceCode.objects.get(tenant_id=result.tenant.id, code_hash=code_hash)
    assert (row.counter.code, row.used_at, row.revoked_at) == ("003", None, None)
    assert list(result.activation_codes) == ["003"]


@pytest.mark.django_db
def test_seeds_categories_products_and_stock_levels():
    result = _seed()

    tenant_id = result.tenant.id
    assert Category.objects.for_tenant(tenant_id).count() == 7
    products = Product.objects.for_tenant(tenant_id).select_related("category")
    assert {(p.barcode, p.name, p.category.name, p.price) for p in products} == {
        (s.barcode, s.name, s.category, s.price) for s in PRODUCTS
    }
    assert all(p.name_lc == p.name.lower() for p in products)
    stock = dict(StockLevel.objects.for_tenant(tenant_id).values_list("product__barcode", "qty"))
    assert stock == {s.barcode: s.stock for s in PRODUCTS}


@pytest.mark.django_db
def test_running_twice_resets_the_demo_tenant_without_duplicates():
    first = _seed()
    Product.objects.for_tenant(first.tenant.id).filter(barcode=PRODUCTS[0].barcode).update(
        name="Changed"
    )
    counts = _tenant_counts(first.tenant.id)

    second = _seed()

    assert second.tenant.id == first.tenant.id
    assert _tenant_counts(second.tenant.id) == counts
    assert Product.objects.get(tenant_id=second.tenant.id, barcode=PRODUCTS[0].barcode).name == (
        PRODUCTS[0].name
    )
    assert second.owner_password != first.owner_password


@pytest.mark.django_db
def test_keeps_earlier_activity_entries_and_writes_none_itself():
    first = _seed()
    ActivityLog.objects.create(
        tenant_id=first.tenant.id, action="login_failure", occurred_at=timezone.now()
    )

    second = _seed()

    assert ActivityLog.objects.for_tenant(second.tenant.id).count() == 1


@pytest.mark.django_db
def test_never_touches_another_tenant():
    other = make_tenant("other-mart")
    Counter.objects.create(tenant_id=other.id, name="Counter 1", code="001")
    Category.objects.create(tenant_id=other.id, name="Grocery", tint="green")
    before = _tenant_counts(other.id)

    _seed()
    _seed()

    assert _tenant_counts(other.id) == before


@pytest.mark.django_db
def test_printed_owner_password_and_device_token_work_over_http():
    result = _seed()

    login = APIClient().post(
        "/api/v1/auth/login", {"login": "sana", "password": result.owner_password}, format="json"
    )
    sync = device_client(result.device_tokens["002"]).get("/api/v1/products/sync/")

    assert login.status_code == 200, login.json()
    assert sync.status_code == 200, sync.json()
    assert len(sync.json()["products"]) == len(PRODUCTS)


@pytest.mark.django_db
def test_summary_prints_every_credential():
    result = _seed()

    text = "\n".join(summary_lines(result))

    assert result.owner_password in text
    assert all(password in text for password in result.cashier_passwords.values())
    assert all(token in text for token in result.device_tokens.values())
    assert result.activation_codes["003"].code in text
