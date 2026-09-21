import pytest

from apps.tenants.models import Tenant, TenantSettings


@pytest.mark.django_db
def test_tenant_settings_currency_is_always_pkr():
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")

    settings = TenantSettings.objects.create(tenant=tenant, currency="USD")

    assert settings.currency == "PKR"


@pytest.mark.django_db
def test_tenant_settings_defaults():
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")

    settings = TenantSettings.objects.create(tenant=tenant)

    assert settings.tax_rate == 0
    assert settings.prices_include_tax is False
    assert settings.block_when_out_of_stock is False
    assert settings.receipt_paper_mm == 80
    assert settings.receipt_show_barcode is True
