from decimal import Decimal

import pytest

from apps.catalog.models import Category, Product
from apps.inventory.models import StockLevel
from apps.tenants.tests.helpers import authed_client, make_tenant


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def owner(tenant):
    return authed_client(tenant)


@pytest.fixture
def owner_client(owner):
    return owner[0]


@pytest.fixture
def make_product(tenant):
    category = Category.objects.create(tenant_id=tenant.id, name="Grocery", tint="green")

    def make(name: str, qty: str = "10", alert: str = "5", cost: str = "80.00", tenant_id=None):
        product = Product.objects.create(
            tenant_id=tenant_id or tenant.id,
            barcode=f"896{abs(hash(name)) % 10**9:09d}",
            name=name,
            name_lc=name.lower(),
            category=category,
            unit="pcs",
            price=Decimal("100.00"),
            cost=Decimal(cost),
            low_stock_alert=Decimal(alert),
        )
        StockLevel.objects.create(tenant_id=product.tenant_id, product=product, qty=Decimal(qty))
        return product

    return make
