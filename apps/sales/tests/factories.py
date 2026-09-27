"""Plain row builders for sales tests."""

from decimal import Decimal
from uuid import uuid4

from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Category, Product
from apps.inventory.models import StockLevel
from apps.sales.models import Bill
from apps.tenants.models import Counter


def make_product(
    tenant_id: int,
    barcode: str = "8961002300022",
    price: str = "620.00",
    stock: str | None = "100",
    **extra,
) -> Product:
    """With a stock level of `stock`, or no stock row when it is None."""
    category, _ = Category.objects.get_or_create(tenant_id=tenant_id, name="Grocery", tint="green")
    product = Product.objects.create(
        tenant_id=tenant_id,
        barcode=barcode,
        name=extra.pop("name", "Cooking Oil 1L"),
        name_lc="cooking oil 1l",
        category=category,
        unit="litre",
        price=Decimal(price),
        cost=Decimal(extra.pop("cost", "540.00")),
        **extra,
    )
    if stock is not None:
        StockLevel.objects.create(tenant_id=tenant_id, product=product, qty=Decimal(stock))
    return product


def make_bill(counter: Counter, cashier: User, bill_no: str = "002000001", **extra) -> Bill:
    now = timezone.now()
    return Bill.objects.create(
        id=extra.pop("id", uuid4()),
        tenant_id=counter.tenant_id,
        counter=counter,
        shift_id=extra.pop("shift_id", uuid4()),
        cashier=cashier,
        bill_no=bill_no,
        sold_at=now,
        received_at=now,
        item_count=Decimal("1"),
        subtotal=Decimal("620.00"),
        tax_amount=Decimal("0.00"),
        rounding=Decimal("0.00"),
        total=Decimal("620.00"),
        **extra,
    )
