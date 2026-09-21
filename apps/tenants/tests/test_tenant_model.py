import pytest
from django.db import IntegrityError

from apps.tenants.models import Tenant


@pytest.mark.django_db
def test_tenant_defaults_to_pkr_timezone_and_active_status():
    tenant = Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")

    assert tenant.timezone == "Asia/Karachi"
    assert tenant.status == "active"
    assert str(tenant) == "Fresh Basket Mart"


@pytest.mark.django_db
def test_slug_is_unique():
    Tenant.objects.create(name="Fresh Basket Mart", slug="fresh-basket-mart")

    with pytest.raises(IntegrityError):
        Tenant.objects.create(name="Another Mart", slug="fresh-basket-mart")
