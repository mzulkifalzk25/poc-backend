import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.shifts.tests.conftest import cashier_client, make_cashier
from apps.tenants.models import Counter, Device, Tenant
from apps.tenants.tests.helpers import activated_device, device_client, make_tenant

from .factories import make_product

__all__ = ["cashier_client", "make_cashier"]


@pytest.fixture
def tenant() -> Tenant:
    return make_tenant()


@pytest.fixture
def counter(tenant) -> Counter:
    return Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")


@pytest.fixture
def device(counter) -> tuple[Device, str]:
    return activated_device(counter)


@pytest.fixture
def pc(device) -> APIClient:
    return device_client(device[1])


@pytest.fixture
def cashier(tenant) -> User:
    return make_cashier(tenant)


@pytest.fixture
def oil(tenant) -> Product:
    return make_product(tenant.id, "8961002300022", price="50.00", name="Cooking Oil 1L")


@pytest.fixture
def rice(tenant) -> Product:
    return make_product(tenant.id, "8961002300039", price="1650.00", name="Basmati Rice 5kg")
