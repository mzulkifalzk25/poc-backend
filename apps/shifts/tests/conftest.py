import pytest
from rest_framework.test import APIClient

from apps.accounts.api.tokens import issue_counter_tokens
from apps.accounts.models import User
from apps.tenants.models import Counter, Device, Tenant
from apps.tenants.tests.helpers import activated_device, device_client, make_tenant


def cashier_client(cashier: User, device: Device) -> APIClient:
    client = APIClient()
    access = issue_counter_tokens(cashier, device.id).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def make_cashier(tenant: Tenant, name: str = "Zainab Khan", **fields) -> User:
    return User.objects.create(tenant_id=tenant.id, full_name=name, role="cashier", **fields)


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
def till(cashier, device) -> APIClient:
    """The cashier signed in on the PC."""
    return cashier_client(cashier, device[0])
